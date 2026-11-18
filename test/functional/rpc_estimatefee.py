#!/usr/bin/env python3
"""estimatefee: what to pay to be in a block within N blocks, learned from blocks that left some transactions waiting.

Blocks here hold about 8 of the same-size transactions (-blockmaxsize), and every round adds 12 paying 1 to 12 coins, so the
cheap ones wait several blocks and the dear ones go in the next. A fresh node has seen nothing and says -1. After enough rounds
the estimate for the next block is above the one for 25 blocks, and neither is below the relay minimum.
"""
from decimal import Decimal

from test_framework import CorgiTestFramework, assert_equal, assert_raises_rpc_error


class EstimateFeeTest(CorgiTestFramework):
    num_nodes = 1
    extra_args = [["-blockmaxsize=2200", "-blockprioritysize=0"]]

    def run_test(self):
        node = self.nodes[0]
        node.generate(260)
        coins = [c for c in node.listunspent() if c["amount"] > 100]
        assert len(coins) >= 200, len(coins)
        dest = node.getnewaddress()

        self.log("a node that has seen nothing says so, and the argument is checked")
        assert_equal(node.estimatefee(1), -1)
        assert_equal(node.estimatefee(25), -1)
        assert_raises_rpc_error(-8, "1 to 25", node.estimatefee, 0)
        assert_raises_rpc_error(-8, "1 to 25", node.estimatefee, 26)

        self.log("rounds of 12 transactions paying 1 to 12 coins, a block holds about 8, so the rest wait for the next")
        used = 0
        for _ in range(16):
            for fee in range(1, 13):
                c = coins[used]
                used += 1
                raw = node.createrawtransaction([{"txid": c["txid"], "vout": c["vout"]}], {dest: c["amount"] - Decimal(fee)})
                node.sendrawtransaction(node.signrawtransaction(raw)["hex"])
            node.generate(1)                        # the best payers go in; the cheap ones wait
            while node.getmempoolinfo()["size"] > 0:
                node.generate(1)                    # and go in a block later (an estimator only learns from what confirms)

        self.log("the next-block estimate is dear, the 25-block one is cheap, and none is under the minimum")
        fast, slow = node.estimatefee(1), node.estimatefee(25)
        self.log("estimatefee(1) = %s, estimatefee(25) = %s" % (fast, slow))
        assert fast != -1 and slow != -1
        assert fast > slow, (fast, slow)
        assert slow >= Decimal(1), slow            # the relay minimum is 1 coin per kB
        # the estimate never goes up as the wait allowed gets longer
        previous = None
        for n in (1, 2, 3, 5, 10, 25):
            e = node.estimatefee(n)
            assert e != -1
            if previous is not None:
                assert e <= previous, (n, e, previous)
            previous = e


if __name__ == "__main__":
    EstimateFeeTest().main()
