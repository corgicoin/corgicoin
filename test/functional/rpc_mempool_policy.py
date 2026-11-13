#!/usr/bin/env python3
"""Relay policy: a transaction over 100 kB is not standard, and the reason is reported.

Legacy signature hashing re-serialises the whole transaction for every input, so a transaction of thousands of inputs
costs the node seconds of CPU to verify (and a bad signature on the last input wastes all of it). Relay accepted up to the
1 MB block limit. Policy is switched on for regtest with -acceptnonstdtxn=0 (it is the default on mainnet).
"""
from decimal import Decimal

from test_framework import CorgiTestFramework, assert_equal


class MempoolPolicyTest(CorgiTestFramework):
    num_nodes = 1
    extra_args = [["-acceptnonstdtxn=0"]]

    def spend(self, node, utxos, dest):
        total = sum(u["amount"] for u in utxos)
        fee = Decimal(len(utxos) * 2)           # well over 1 CORG per kB
        raw = node.createrawtransaction([{"txid": u["txid"], "vout": u["vout"]} for u in utxos], {dest: total - fee})
        signed = node.signrawtransaction(raw)
        assert signed["complete"]
        return signed["hex"]

    def run_test(self):
        node = self.nodes[0]
        node.generate(780)
        utxos = node.listunspent()
        assert len(utxos) >= 740, len(utxos)
        dest = node.getnewaddress()

        self.log("a small transaction is accepted as before")
        small = self.spend(node, utxos[:3], dest)
        assert_equal(node.testmempoolaccept([small])[0]["allowed"], True)

        self.log("a transaction of 700 inputs is over 100 kB and is refused as nonstandard")
        big = self.spend(node, utxos[3:703], dest)
        assert len(big) // 2 > 100000, len(big) // 2
        res = node.testmempoolaccept([big])[0]
        assert_equal(res["allowed"], False)
        assert_equal(res["reject-reason"], "nonstandard")

        self.log("so it is not accepted into the pool either")
        try:
            node.sendrawtransaction(big)
        except Exception:
            pass
        else:
            raise AssertionError("an oversized transaction was accepted into the memory pool")
        assert_equal(node.getmempoolinfo()["size"], 0)

        self.log("the same coins in two transactions under the limit are fine")
        a = self.spend(node, utxos[3:353], dest)
        assert len(a) // 2 < 100000, len(a) // 2
        node.sendrawtransaction(a)


if __name__ == "__main__":
    MempoolPolicyTest().main()
