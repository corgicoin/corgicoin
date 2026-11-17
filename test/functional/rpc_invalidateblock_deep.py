#!/usr/bin/env python3
"""invalidateblock far below the tip: the rollback runs in one database transaction and must fit its lock table.

The Berkeley DB lock table was 10000. Every block taken off the chain in a rollback holds locks until the single
transaction commits, so a deep rollback (an operator undoing a bad stretch of chain, or a deep reorganisation) could
run out of them, and on some nodes and not others. -dbmaxlocks defaults to 537000 now.
"""
from test_framework import CorgiTestFramework, assert_equal


class DeepInvalidateTest(CorgiTestFramework):
    num_nodes = 1

    def run_test(self):
        node = self.nodes[0]
        node.generate(400)
        assert_equal(node.getblockcount(), 400)
        first = node.getblockhash(1)

        self.log("invalidating block 1 rolls back 400 blocks")
        node.invalidateblock(first)
        assert_equal(node.getblockcount(), 0)

        self.log("and reconsidering it brings them back")
        node.reconsiderblock(first)
        assert_equal(node.getblockcount(), 400)


if __name__ == "__main__":
    DeepInvalidateTest().main()
