#!/usr/bin/env python3
"""signrawtransaction with inputs the node does not know, with output numbers out of range, and with
variants that have different numbers of inputs: the node must answer and stay up (it used to read
past the end of a vector)."""
from decimal import Decimal

from test_framework import CorgiTestFramework, assert_equal


class RawTransactionTest(CorgiTestFramework):
    num_nodes = 1

    def alive(self, node):
        node.getblockcount()

    def run_test(self):
        node = self.nodes[0]
        node.generate(60)
        utxos = node.listunspent()
        assert len(utxos) >= 2
        dest = node.getnewaddress()
        amount = Decimal("1.5")

        self.log("an input whose previous transaction the node has never seen")
        raw = node.createrawtransaction([{"txid": "ab" * 32, "vout": 0}], {dest: amount})
        res = node.signrawtransaction(raw)
        assert_equal(res["complete"], False)
        self.alive(node)

        self.log("a real previous transaction, but an output number it does not have")
        real = utxos[0]
        raw = node.createrawtransaction([{"txid": real["txid"], "vout": 999}], {dest: amount})
        res = node.signrawtransaction(raw)
        assert_equal(res["complete"], False)
        self.alive(node)

        self.log("variants with different numbers of inputs are merged without reading past the shorter one")
        two = node.createrawtransaction(
            [{"txid": utxos[0]["txid"], "vout": utxos[0]["vout"]},
             {"txid": utxos[1]["txid"], "vout": utxos[1]["vout"]}], {dest: amount})
        one = node.createrawtransaction([{"txid": utxos[0]["txid"], "vout": utxos[0]["vout"]}], {dest: amount})
        res = node.signrawtransaction(two + one)
        assert "hex" in res
        self.alive(node)

        self.log("an ordinary spend of a wallet output still signs completely")
        raw = node.createrawtransaction([{"txid": real["txid"], "vout": real["vout"]}], {dest: real["amount"] - 1})
        res = node.signrawtransaction(raw)
        assert_equal(res["complete"], True)
        node.sendrawtransaction(res["hex"])


if __name__ == "__main__":
    RawTransactionTest().main()
