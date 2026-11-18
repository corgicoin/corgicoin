#!/usr/bin/env python3
"""A send the mempool refuses must leave the wallet as it was.

CommitTransaction used to record the transaction and mark its coins spent, then ask the mempool. A refusal (here: the
pool is full and the wallet's transaction pays the lowest fee rate, so it is turned away) left the coins marked spent,
the balance short, and nothing on the network. The mempool is now asked first, as a dry run.
"""
from decimal import Decimal

from test_framework import CorgiTestFramework, assert_equal


class CommitDryRunTest(CorgiTestFramework):
    num_nodes = 1
    extra_args = [["-maxmempoolkb=10"]]

    def spend(self, node, utxo, dest, fee):
        raw = node.createrawtransaction([{"txid": utxo["txid"], "vout": utxo["vout"]}], {dest: utxo["amount"] - Decimal(fee)})
        signed = node.signrawtransaction(raw)
        assert signed["complete"]
        return signed["hex"]

    def run_test(self):
        node = self.nodes[0]
        node.generate(300)
        utxos = node.listunspent()
        dest = node.getnewaddress()

        self.log("fill the pool with transactions that pay well, each a little more than the last")
        for i, u in enumerate(utxos[:80]):
            node.sendrawtransaction(self.spend(node, u, dest, Decimal("20") + Decimal(i) / 100))
        full = node.getmempoolinfo()
        assert full["size"] < 80, "nothing was dropped: the cap is not in force: %r" % full

        balance = node.getbalance()
        unspent = len(node.listunspent())
        assert unspent > 100, unspent

        self.log("the wallet's own send pays the minimum fee rate: the full pool turns it away")
        refused = False
        try:
            node.sendtoaddress(dest, 1)
        except Exception:
            refused = True
        assert refused, "the wallet's send was accepted into a full pool"

        self.log("the wallet is as it was: balance, coins, and the pool")
        assert_equal(node.getbalance(), balance)
        assert_equal(len(node.listunspent()), unspent)
        assert_equal(node.getmempoolinfo()["size"], full["size"])

        self.log("a block empties the pool and the same coins are spendable")
        node.generate(1)
        node.sendtoaddress(dest, 1)
        assert_equal(node.getmempoolinfo()["size"], 1)


if __name__ == "__main__":
    CommitDryRunTest().main()
