#!/usr/bin/env python3
"""The recovery phrase, a restore from it, and an encrypted backup of the restored wallet: the history is visible at every step.

Node a is an HD wallet that has received coins on several of its addresses. Node b is restored from the phrase alone (sethdseed with the
phrase: the look-ahead finds the used keys and carries on after the last one). b's backup, imported by a fresh node c (adoptphrase=true),
gives c the same balance and a wallet that can spend, and its next address is not one that a or b had given out. A backup of the restored wallet
holds the phrase, an hdindex past the last used key, and every key with its HD path (read back here through backup_crafter.decrypt).
(How far back the import searches the chain is not tested: it depends on the key times against the clock, and the tests have no clock to move.)
"""
import json
import os

from backup_crafter import decrypt, require_crypto
from test_framework import CorgiTestFramework, assert_equal

PASS = "a long backup passphrase"


class PhraseRestoreBackupTest(CorgiTestFramework):
    num_nodes = 3
    extra_args = [["-hdrestoregap=30"], ["-hdrestoregap=30"], ["-hdrestoregap=30"]]

    def setup_nodes(self):
        super().setup_nodes()
        require_crypto(self)

    def run_test(self):
        a, b, c = self.nodes
        a.sethdseed()
        phrase = a.gethdseed(True)["mnemonic"]
        a.generate(101)
        addrs = [a.getnewaddress("a%d" % i) for i in range(12)]
        for i in (2, 5, 9):
            a.sendtoaddress(addrs[i], 3 + i)
        a.generate(1)
        used = [int(a.validateaddress(x)["hdkeypath"].rsplit("/", 1)[1]) for x in addrs]
        self.log("a: phrase, %d addresses (indices %d..%d), coins on three of them, balance %s" % (len(addrs), min(used), max(used), a.getbalance()))

        self.connect_nodes(1, 0)
        self.connect_nodes(2, 0)
        self.sync_blocks()

        self.log("b is restored from the phrase alone and finds a's coins")
        b.sethdseed(phrase)
        assert_equal(b.gethdseed(True)["mnemonic"], phrase)
        assert_equal(b.getbalance(), a.getbalance())
        for x in addrs[:10]:
            assert_equal(b.validateaddress(x)["ismine"], True)
        b_next = b.getnewaddress()

        self.log("b's backup holds the phrase, an hdindex past the keys in use, and the keys with their paths")
        path = os.path.join(b.datadir, "restored.backup")
        b.exportwalletencrypted(path, PASS)
        plain = json.loads(decrypt(PASS, open(path, "rb").read()))
        assert_equal(plain["hdmnemonic"], phrase)
        assert_equal(plain["chain"], "regtest")
        indices = sorted(int(k["hdkeypath"].rsplit("/", 1)[1]) for k in plain["keys"] if k.get("hdkeypath"))
        assert indices and indices[0] == 0, indices
        assert plain["hdindex"] >= max(used) + 1, (plain["hdindex"], used)
        assert all("time" in k for k in plain["keys"])

        self.log("c imports it (adoptphrase=true): the same balance, a wallet that can spend, and a next address that was not given out before")
        r = c.importwalletencrypted(path, PASS, True)
        assert_equal(r["phrase_adopted"], True)
        assert_equal(c.gethdseed(True)["mnemonic"], phrase)
        assert_equal(c.getbalance(), a.getbalance())
        c_next = c.getnewaddress()
        assert c_next not in addrs, "the next address is one the old wallet had already given out"
        c.sendtoaddress(a.getnewaddress(), 2)
        c.generate(1)
        self.sync_blocks()
        assert c.getbalance() > 0
        r = c.verifywallet()
        assert_equal(r["ok"], True)


if __name__ == "__main__":
    PhraseRestoreBackupTest().main()
