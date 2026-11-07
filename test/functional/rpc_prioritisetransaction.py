#!/usr/bin/env python3
"""prioritisetransaction: holding a transaction back, releasing it, and letting one in that is below the relay fee."""
from decimal import Decimal

from test_framework import CorgiTestFramework, assert_equal, assert_raises_rpc_error

COIN = 100000000


class PrioritiseTransactionTest(CorgiTestFramework):
    num_nodes = 1

    def raw_spend(self, node, utxo, fee):
        raw = node.createrawtransaction([{"txid": utxo["txid"], "vout": utxo["vout"]}], {node.getnewaddress(): utxo["amount"] - fee})
        signed = node.signrawtransaction(raw)
        assert signed["complete"]
        return signed["hex"]

    def run_test(self):
        node = self.nodes[0]
        node.generate(51)
        utxos = node.listunspent()

        self.log("a negative fee delta keeps a pooled transaction out of the next block")
        txid = node.sendrawtransaction(self.raw_spend(node, utxos[0], Decimal(1)))
        assert_equal(node.prioritisetransaction(txid, 0, -10 * COIN), True)
        node.generate(1)
        assert_equal(node.getrawmempool(), [txid])

        self.log("deltas add up, so cancelling it out lets the transaction through")
        assert_equal(node.prioritisetransaction(txid, 0, 10 * COIN), True)
        node.generate(1)
        assert_equal(node.getrawmempool(), [])
        assert_equal(node.getrawtransaction(txid, 1)["confirmations"], 1)

        self.log("a delta set before the transaction arrives lets in a fee that is below the relay minimum")
        low = self.raw_spend(node, utxos[1], Decimal("0.0001"))
        low_txid = node.decoderawtransaction(low)["txid"]
        assert_raises_rpc_error(-22, None, node.sendrawtransaction, low)
        assert_equal(node.prioritisetransaction(low_txid, 0, 5 * COIN), True)
        assert_equal(node.sendrawtransaction(low), low_txid)
        node.generate(1)
        assert_equal(node.getrawmempool(), [])

        self.log("a priority delta is accepted as an integer or a fraction")
        assert_equal(node.prioritisetransaction("00" * 32, 1000, 0), True)
        assert_equal(node.prioritisetransaction("00" * 32, 0.5, 0), True)

        self.log("argument checks")
        assert_raises_rpc_error(-8, None, node.prioritisetransaction, "zz", 0, 0)
        assert_raises_rpc_error(-8, None, node.prioritisetransaction, "ab" * 31, 0, 0)
        assert_raises_rpc_error(-3, None, node.prioritisetransaction, txid, "x", 0)
        assert_raises_rpc_error(-3, None, node.prioritisetransaction, txid, 0, 0.5)
        assert_raises_rpc_error(-1, None, node.prioritisetransaction, txid, 0)
        assert_raises_rpc_error(-1, None, node.prioritisetransaction, txid, 0, 0, 0)


if __name__ == "__main__":
    PrioritiseTransactionTest().main()
