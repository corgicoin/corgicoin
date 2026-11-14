#!/usr/bin/env python3
"""A block that cannot hold everything takes the transactions that pay the most per byte first.

-blockmaxsize makes a small block so that a full one is easy to arrange. -blockprioritysize=0 puts no part of it aside for the
oldest, biggest-valued coins, so it is fee per byte all the way. 30 transactions of the same size pay 1 to 30 coins: the block
must hold the ones that pay most. Without the option (the default) a node still builds a block, and -blockmaxsize is respected.
"""
from decimal import Decimal

from test_framework import CorgiTestFramework, assert_equal


class FeeRateBlocksTest(CorgiTestFramework):
    num_nodes = 1
    extra_args = [["-blockmaxsize=3500", "-blockprioritysize=0"]]

    def run_test(self):
        node = self.nodes[0]
        node.generate(140)
        coins = [c for c in node.listunspent() if c["amount"] > 100][:30]
        assert len(coins) == 30, len(coins)
        dest = node.getnewaddress()

        self.log("30 transactions of one size, paying 1 to 30 coins each, in a random order")
        fees = {}
        order = list(range(30))
        order = order[::2] + order[1::2]              # not sorted
        for i in order:
            fee = Decimal(i + 1)
            raw = node.createrawtransaction([{"txid": coins[i]["txid"], "vout": coins[i]["vout"]}], {dest: coins[i]["amount"] - fee})
            txid = node.sendrawtransaction(node.signrawtransaction(raw)["hex"])
            fees[txid] = fee
        assert_equal(node.getmempoolinfo()["size"], 30)

        self.log("one block: it is small, so it holds only some, and they are the best payers")
        node.generate(1)
        mined = [t for t in node.getblock(node.getbestblockhash())["tx"][1:]]
        assert 3 <= len(mined) < 30, len(mined)
        assert_equal(sorted(fees[t] for t in mined), sorted(fees.values())[-len(mined):])

        self.log("and the next block takes the next best, and so on until nothing is left")
        left = set(fees) - set(mined)
        while node.getmempoolinfo()["size"] > 0:
            node.generate(1)
            block = node.getblock(node.getbestblockhash())["tx"][1:]
            assert block, "a block with nothing in it while the pool is not empty"
            best_left = sorted((fees[t] for t in left), reverse=True)[:len(block)]
            assert_equal(sorted((fees[t] for t in block), reverse=True), best_left)
            left -= set(block)
        assert_equal(left, set())

        self.log("a block never goes over -blockmaxsize")
        for h in range(141, node.getblockcount() + 1):
            assert node.getblock(node.getblockhash(h))["size"] <= 3500, h


if __name__ == "__main__":
    FeeRateBlocksTest().main()
