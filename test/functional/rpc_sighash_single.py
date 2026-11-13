#!/usr/bin/env python3
"""signrawtransaction refuses to sign SIGHASH_SINGLE for an input that has no output at its index.

For such an input the signature hash is the constant 1, so the signature is valid for any input of the same key
in any transaction, and anyone who sees the transaction can spend the rest of that key's coins with it.
"""
from decimal import Decimal

from test_framework import CorgiTestFramework, assert_equal


class SighashSingleTest(CorgiTestFramework):
    num_nodes = 1

    def run_test(self):
        node = self.nodes[0]
        node.generate(60)
        a, b = node.listunspent()[:2]
        dest = node.getnewaddress()
        raw = node.createrawtransaction(
            [{"txid": a["txid"], "vout": a["vout"]}, {"txid": b["txid"], "vout": b["vout"]}], {dest: Decimal(10)})

        self.log("SINGLE: input 0 has output 0 and is signed, input 1 has none and is not")
        keys = [node.dumpprivkey(u["address"]) for u in (a, b)]
        res = node.signrawtransaction(raw, [], keys, "SINGLE")
        tx = node.decoderawtransaction(res["hex"])
        assert tx["vin"][0]["scriptSig"]["hex"] != "", "input 0 should be signed"
        assert_equal(tx["vin"][1]["scriptSig"]["hex"], "")
        assert_equal(res["complete"], False)

        self.log("ALL still signs both")
        res = node.signrawtransaction(raw)
        assert_equal(res["complete"], True)


if __name__ == "__main__":
    SighashSingleTest().main()
