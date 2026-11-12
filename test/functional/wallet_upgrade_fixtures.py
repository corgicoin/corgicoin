#!/usr/bin/env python3
"""Wallets made by older releases must load, unlock and spend in this build.

The fixtures in data/wallets/ were made by the real v4.7.0.0 binary (make_fixtures.py regenerates them):

  v47-hd            an HD wallet. v4.5-v4.7 stored its keys with the wrong compression flag, so its coins could not
                    be spent and dumpprivkey exported the wrong key
  v47-hd-encrypted  the same, then encrypted. v4.5-v4.7 left plaintext keys behind and could not load it again
  v47-encrypted     a non-HD wallet encrypted with v4.2-v4.7's PBKDF2 passphrase derivation

For each one this checks that the wallet loads, its passphrase unlocks it, every address it handed out is still its
own, dumpprivkey returns a key that really belongs to that address (imported into a separate wallet it gives the same
address), the recovery phrase restores the same addresses, and coins received on an old address can be spent and
confirm. The tests that missed both v4.8 wallet bugs only ever used fresh wallets.
"""
import json
import os
import shutil

from test_framework import CorgiTestFramework, TestNode, assert_equal, assert_raises_rpc_error

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "wallets")


class WalletUpgradeFixturesTest(CorgiTestFramework):
    num_nodes = 1   # node0 is a fresh wallet used to check exported keys and recovery phrases

    def fixture_node(self, name):
        node = TestNode(len(self.nodes), self.options.corgicoind, os.path.join(self.tmpdir, name), None)
        os.makedirs(os.path.join(node.datadir, "regtest"), exist_ok=True)
        shutil.copy(os.path.join(DATA, name, "wallet.dat"), os.path.join(node.datadir, "regtest", "wallet.dat"))
        self.nodes.append(node)
        node.start()
        return node

    def unlock(self, node, info):
        if info["passphrase"]:
            node.walletpassphrase(info["passphrase"], 600)

    def spend_from(self, node, addr, what):
        """Pay 10 to addr, then spend exactly that output with a raw transaction and confirm it."""
        funding = node.sendtoaddress(addr, 10)
        node.generate(1)
        utxo = [u for u in node.listunspent(1) if u["txid"] == funding and u["amount"] == 10]
        assert_equal(len(utxo), 1)
        raw = node.createrawtransaction([{"txid": utxo[0]["txid"], "vout": utxo[0]["vout"]}],
                                        {node.getnewaddress(): utxo[0]["amount"] - 1})
        signed = node.signrawtransaction(raw)
        assert signed["complete"], "cannot sign for %s" % what
        txid = node.sendrawtransaction(signed["hex"])
        node.generate(1)
        assert_equal(node.gettransaction(txid)["confirmations"], 1)

    def check_fixture(self, name):
        with open(os.path.join(DATA, name, "info.json")) as f:
            info = json.load(f)
        checker = self.nodes[0]

        self.log("%s (made by %s): loads" % (name, info["made_by"]))
        node = self.fixture_node(name)
        if info["passphrase"]:
            assert_raises_rpc_error(-13, None, node.dumpprivkey, info["addresses"][0])   # locked after loading
            assert_raises_rpc_error(-14, None, node.walletpassphrase, "not the passphrase", 60)
        self.unlock(node, info)

        self.log("%s: its addresses are still its own and export keys that really belong to them" % name)
        keys = {}
        for addr in info["addresses"]:
            assert node.validateaddress(addr)["ismine"], addr
            keys[addr] = node.dumpprivkey(addr)
            checker.importprivkey(keys[addr])
            assert checker.validateaddress(addr)["ismine"], "the key dumped for %s gives a different address" % addr

        if info["mnemonic"]:
            self.log("%s: the recovery phrase restores the same first address" % name)
            restore = TestNode(len(self.nodes), self.options.corgicoind, os.path.join(self.tmpdir, name + "-restore"), None)
            self.nodes.append(restore)
            restore.start()
            restore.sethdseed(info["mnemonic"])
            assert_equal(restore.getnewaddress(), info["addresses"][0])
            restore.stop()

        self.log("%s: coins received on an old address can be spent" % name)
        node.generate(51)                       # mined to the fixture's own key pool; the first reward matures
        self.spend_from(node, info["addresses"][0], name + " old address")

        if info["mnemonic"]:
            # v4.5-v4.7 lost the compression flag only for keys derived in the running session (a key reloaded from
            # disk gets it back from its stored public key), so derive one now and use it before any restart
            self.log("%s: a key derived in this session exports correctly and can be spent at once" % name)
            fresh = node.getnewaddress()
            checker.importprivkey(node.dumpprivkey(fresh))
            assert checker.validateaddress(fresh)["ismine"], "the key dumped for a new HD address gives a different address"
            self.spend_from(node, fresh, name + " new HD address")

        self.log("%s: and it all survives a restart" % name)
        node.stop()
        node.start()
        self.unlock(node, info)
        for addr in info["addresses"]:
            assert_equal(node.dumpprivkey(addr), keys[addr])
        node.stop()
        return node

    def run_test(self):
        for name in ("v47-hd", "v47-hd-encrypted", "v47-encrypted"):
            node = self.check_fixture(name)
            if name == "v47-hd-encrypted":
                with open(node.debug_log, errors="replace") as f:
                    log = f.read()
                assert "plaintext key(s) found next to encrypted ones" in log, "the leftover plaintext keys were not found"
                assert "encrypted 12 leftover plaintext key(s)" in log, "the leftover plaintext keys were not encrypted"


if __name__ == "__main__":
    WalletUpgradeFixturesTest().main()
