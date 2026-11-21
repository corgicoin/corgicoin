#!/usr/bin/env python3
"""A send that spends many coins with one confirmation each (CWalletTx::AddSupportingTransactions).

The function collects the transactions a new one depends on, in a work queue that it grows while it walks it: each input with fewer than
3 confirmations puts its own inputs on the queue. The walk used a range-for over the vector, so a push_back that reallocated it left the loop
reading freed memory (a heap-use-after-free that AddressSanitizer reports, and in a release build a crash or garbage at random).

Node b is paid 20 times by node a (20 transactions, all in one block, so 1 confirmation each), then pays 90 back: that spends 18 or more of
its coins, and each coin's parent transaction puts further entries on the queue, which passes the capacity of the vector (16, 32) while the
loop is running. Under the sanitizer job this crashed the node before the fix; elsewhere it passes either way, which is the nature of the bug.
"""
from test_framework import CorgiTestFramework, assert_equal


class SendManyYoungInputsTest(CorgiTestFramework):
    num_nodes = 2

    def run_test(self):
        a, b = self.nodes
        self.connect_nodes(0, 1)
        a.generate(120)
        self.sync_blocks(timeout=120)

        self.log("b is paid 20 times, all in one block")
        for _ in range(20):
            a.sendtoaddress(b.getnewaddress(), 5)
        a.generate(1)
        self.sync_blocks(timeout=120)
        assert_equal(b.getbalance(), 100)

        self.log("b pays 90 back: 18 or more inputs of 1 confirmation each")
        txid = b.sendtoaddress(a.getnewaddress(), 90)
        raw = b.decoderawtransaction(b.getrawtransaction(txid))
        assert len(raw["vin"]) >= 18, len(raw["vin"])
        self.sync_mempools(timeout=60)
        a.generate(1)
        self.sync_blocks(timeout=120)
        assert_equal(b.gettransaction(txid)["confirmations"], 1)
        assert b.getbalance() < 10


if __name__ == "__main__":
    SendManyYoungInputsTest().main()
