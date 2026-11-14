#!/usr/bin/env python3
"""A send the mempool refuses must leave the wallet as it was.

CommitTransaction used to record the transaction and mark its coins spent, then ask the mempool. A refusal (here: a
transaction over 100 kB, not standard with -acceptnonstdtxn=0) left the coins marked spent, the balance short, and
nothing on the network. The mempool is now asked first, as a dry run.
"""
from decimal import Decimal

from test_framework import CorgiTestFramework, assert_equal


class CommitDryRunTest(CorgiTestFramework):
    num_nodes = 1
    extra_args = [["-acceptnonstdtxn=0"]]

    def run_test(self):
        node = self.nodes[0]
        node.generate(110)
        dest = node.getnewaddress()

        self.log("1000 small coins")
        node.sendmany("", {node.getnewaddress(): 1 for _ in range(1000)})
        node.generate(1)
        balance = node.getbalance()
        unspent = len(node.listunspent())
        assert unspent > 1000, unspent

        self.log("a send that needs all of them is over 100 kB: refused")
        refused = False
        try:
            node.sendtoaddress(dest, balance - 5)
        except Exception as e:
            refused = True
        assert refused, "the oversized send was accepted: the policy is not in force"

        self.log("the wallet is as it was: balance, coins, and nothing in the mempool")
        assert_equal(node.getbalance(), balance)
        assert_equal(len(node.listunspent()), unspent)
        assert_equal(node.getmempoolinfo()["size"], 0)

        self.log("and a send that fits still works with the same coins")
        node.sendtoaddress(dest, 10)
        assert_equal(node.getmempoolinfo()["size"], 1)


if __name__ == "__main__":
    CommitDryRunTest().main()
