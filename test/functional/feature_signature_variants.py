#!/usr/bin/env python3
"""Signature variants are accepted or refused alike by this build and a release (v4.9.0.0).

Node 0 runs this build and node 1 the alternate build (--alt-corgicoind or $CORGICOIND_ALT), connected. Node 0 makes raw transactions and
mines them, and node 1 must take the transactions into its pool and the blocks into its chain (so both builds judge the signatures the same way):
 - each of the six signature hash types (ALL, NONE, SINGLE, each with ANYONECANPAY) on a two-input, two-output transaction;
 - a P2SH 2-of-3 multisig spend;
 - a coin of an uncompressed key (imported from a compressed key's secret, written in the uncompressed form);
 - a payment made on node 1 and mined there, which node 0 must take.
And one that must be refused by both: the 2-of-3 spend with one signature damaged, which neither pool takes, and a block carrying it, which
neither chain takes (hand-made, block_builder.py).

What makes it fail: a build that accepted a signature the other refuses (one of the nodes would stay behind, the sync would time out, or the
refusals would differ); a damaged signature accepted anywhere.
"""
import hashlib
import os
from decimal import Decimal

from block_builder import build_block, next_block_value
from test_framework import CorgiTestFramework, JSONRPCException, assert_equal

B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58decode_check(s):
    n = 0
    for c in s:
        n = n * 58 + B58.index(c)
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big")
    raw = b"\x00" * (len(s) - len(s.lstrip("1"))) + raw
    payload, check = raw[:-4], raw[-4:]
    assert hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4] == check, "bad base58 checksum"
    return payload


def b58encode_check(payload):
    data = payload + hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    n = int.from_bytes(data, "big")
    out = ""
    while n:
        n, r = divmod(n, 58)
        out = B58[r] + out
    return "1" * (len(data) - len(data.lstrip(b"\x00"))) + out


class SignatureVariantsTest(CorgiTestFramework):
    num_nodes = 2

    def node_binary(self, index):
        return self.options.alt_corgicoind if index == 1 else self.options.corgicoind

    def setup_nodes(self):
        if not self.options.alt_corgicoind:
            self.skip_test("pass --alt-corgicoind (or set CORGICOIND_ALT) to a second build")
        if not os.path.isfile(self.options.alt_corgicoind):
            self.skip_test("alternate build not found at %r" % self.options.alt_corgicoind)
        super().setup_nodes()
        self.nodes[1].old_release = True

    def mine_and_sync(self, node, n=1):
        node.generate(n)
        self.sync_blocks(timeout=90)
        assert_equal(self.nodes[0].getbestblockhash(), self.nodes[1].getbestblockhash())

    def run_test(self):
        n0, n1 = self.nodes
        self.connect_nodes(0, 1)
        n0.generate(70)
        self.sync_blocks()

        self.log("each signature hash type on a two-input, two-output transaction")
        for kind in ("ALL", "NONE", "SINGLE", "ALL|ANYONECANPAY", "NONE|ANYONECANPAY", "SINGLE|ANYONECANPAY"):
            a, b = n0.listunspent()[:2]
            keys = [n0.dumpprivkey(n0.getrawtransaction(u["txid"], 1)["vout"][u["vout"]]["scriptPubKey"]["addresses"][0]) for u in (a, b)]
            total = a["amount"] + b["amount"] - Decimal("0.01")
            raw = n0.createrawtransaction([{"txid": u["txid"], "vout": u["vout"]} for u in (a, b)],
                                          {n0.getnewaddress(): total / 2, n0.getnewaddress(): total / 2})
            res = n0.signrawtransaction(raw, [], keys, kind)
            assert_equal(res["complete"], True, kind)
            txid = n0.sendrawtransaction(res["hex"])
            self.sync_mempools(timeout=60)
            assert txid in n1.getrawmempool(), "%s: the release did not take the transaction" % kind
            self.mine_and_sync(n0)
            self.log("  %s: accepted by both" % kind)

        self.log("a P2SH 2-of-3 multisig spend")
        ms_addrs = [n0.getnewaddress() for _ in range(3)]
        pubkeys = [n0.validateaddress(a)["pubkey"] for a in ms_addrs]
        ms = n0.createmultisig(2, pubkeys)
        n0.addmultisigaddress(2, pubkeys)
        funding = n0.sendtoaddress(ms["address"], 10)
        self.mine_and_sync(n0)
        vout = [o for o in n0.getrawtransaction(funding, 1)["vout"] if ms["address"] in o["scriptPubKey"].get("addresses", [])][0]
        prev = [{"txid": funding, "vout": vout["n"], "scriptPubKey": vout["scriptPubKey"]["hex"], "redeemScript": ms["redeemScript"]}]
        keys = [n0.dumpprivkey(a) for a in ms_addrs[:2]]
        dest = n0.getnewaddress()
        spend = n0.createrawtransaction([{"txid": funding, "vout": vout["n"]}], {dest: Decimal(10) - Decimal("0.01")})
        signed = n0.signrawtransaction(spend, prev, keys)
        assert_equal(signed["complete"], True)
        txid = n0.sendrawtransaction(signed["hex"])
        self.sync_mempools(timeout=60)
        assert txid in n1.getrawmempool()
        self.mine_and_sync(n0)

        self.log("the same spend with one signature damaged is refused by both pools and by both chains")
        funding2 = n0.sendtoaddress(ms["address"], 10)
        self.mine_and_sync(n0)
        vout2 = [o for o in n0.getrawtransaction(funding2, 1)["vout"] if ms["address"] in o["scriptPubKey"].get("addresses", [])][0]
        prev2 = [{"txid": funding2, "vout": vout2["n"], "scriptPubKey": vout2["scriptPubKey"]["hex"], "redeemScript": ms["redeemScript"]}]
        spend2 = n0.createrawtransaction([{"txid": funding2, "vout": vout2["n"]}], {dest: Decimal(10) - Decimal("0.01")})
        good = n0.signrawtransaction(spend2, prev2, keys)["hex"]
        scriptsig = n0.decoderawtransaction(good)["vin"][0]["scriptSig"]["hex"]
        # OP_0, then the first signature (a length byte, then the DER): damage one byte of the number r
        pos = 2 + 2 + 2 * 8
        bad_sig = scriptsig[:pos] + ("%02x" % (int(scriptsig[pos:pos + 2], 16) ^ 0x55)) + scriptsig[pos + 2:]
        assert bad_sig != scriptsig and good.count(scriptsig) == 1
        bad = good.replace(scriptsig, bad_sig)
        for node in (n0, n1):
            try:
                node.sendrawtransaction(bad)
                raise AssertionError("a transaction with a damaged signature was accepted by a pool")
            except JSONRPCException:
                pass
        tip = n0.getbestblockhash()
        block = build_block(n0, [bytes.fromhex(bad)])
        r0, r1 = n0.submitblock(block), n1.submitblock(block)
        assert_equal(r0, r1)
        assert r0 is not None, "a block with a damaged signature was accepted"
        assert_equal(n0.getbestblockhash(), tip)
        assert_equal(n1.getbestblockhash(), tip)
        self.log("  refused by both (%s)" % r0)

        self.log("the coin of an uncompressed key")
        any_addr = n0.getaddressesbyaccount("")[0]
        payload = b58decode_check(n0.dumpprivkey(any_addr))
        version, secret = payload[:1], payload[1:33]
        unc_wif = b58encode_check(version + secret)                  # the secret without the "compressed" byte
        n0.importprivkey(unc_wif, "unc", False)
        unc_addr = n0.getaddressesbyaccount("unc")[0]
        assert unc_addr != any_addr
        funding3 = n0.sendtoaddress(unc_addr, 5)
        self.mine_and_sync(n0)
        vout3 = [o for o in n0.getrawtransaction(funding3, 1)["vout"] if unc_addr in o["scriptPubKey"].get("addresses", [])][0]
        spend3 = n0.createrawtransaction([{"txid": funding3, "vout": vout3["n"]}], {n0.getnewaddress(): Decimal(5) - Decimal("0.01")})
        signed3 = n0.signrawtransaction(spend3, [{"txid": funding3, "vout": vout3["n"], "scriptPubKey": vout3["scriptPubKey"]["hex"]}], [unc_wif])
        assert_equal(signed3["complete"], True)
        txid = n0.sendrawtransaction(signed3["hex"])
        self.sync_mempools(timeout=60)
        assert txid in n1.getrawmempool()
        self.mine_and_sync(n0)

        self.log("a payment made and mined on the release is taken by this build")
        n1.sendtoaddress(n0.getnewaddress(), 3)
        self.sync_mempools(timeout=60)
        self.mine_and_sync(n1)


if __name__ == "__main__":
    SignatureVariantsTest().main()
