#!/usr/bin/env python3
"""A pool transaction that spends a coin a block has spent otherwise is removed when the block connects, with what is built on it.

Node 0 has T1 (and T1's child) in its pool. Node 1 mines T2, which spends the same coin, and node 0 takes the block. Pool removal went
by transaction ID, so T1 (not in the block) stayed, announced to peers and counted against the pool, until it expired.
"""
from test_framework import CorgiTestFramework, assert_equal


class MempoolConflictBlockTest(CorgiTestFramework):
    num_nodes = 2

    def run_test(self):
        n0, n1 = self.nodes
        n0.generate(51)
        self.connect_nodes(1, 0)
        self.sync_blocks()
        self.disconnect_nodes(1, 0)

        coin = n0.listunspent()[0]
        inputs = [{"txid": coin["txid"], "vout": coin["vout"]}]
        addr0 = n0.getnewaddress()
        t1_hex = n0.signrawtransaction(n0.createrawtransaction(inputs, {addr0: coin["amount"] - 1}))["hex"]
        t2_hex = n0.signrawtransaction(n0.createrawtransaction(inputs, {n1.getnewaddress(): coin["amount"] - 5}))["hex"]

        t1 = n0.sendrawtransaction(t1_hex)
        # a child of T1, also in the pool
        child_in = [{"txid": t1, "vout": [o["n"] for o in n0.decoderawtransaction(t1_hex)["vout"]][0]}]
        child_hex = n0.signrawtransaction(n0.createrawtransaction(child_in, {n0.getnewaddress(): coin["amount"] - 2}))["hex"]
        child = n0.sendrawtransaction(child_hex)
        assert_equal(sorted(n0.getrawmempool()), sorted([t1, child]))

        t2 = n1.sendrawtransaction(t2_hex)
        n1.generate(1)
        self.connect_nodes(0, 1)
        self.sync_blocks()
        assert_equal(n0.gettransaction(t2)["confirmations"], 1)

        self.log("T1 and its child are gone from the pool: T1 can never confirm")
        assert_equal(n0.getrawmempool(), [])


if __name__ == "__main__":
    MempoolConflictBlockTest().main()
