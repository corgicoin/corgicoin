#!/usr/bin/env python3
"""invalidateblock / reconsiderblock: roll back, refuse the heavier chain (also across a restart), undo."""
from test_framework import (CorgiTestFramework, assert_equal, assert_raises_rpc_error, wait_until)


def tip_status(node, block_hash):
    for tip in node.getchaintips():
        if tip["hash"] == block_hash:
            return tip["status"]
    return None


class InvalidateBlockTest(CorgiTestFramework):
    num_nodes = 2

    def run_test(self):
        n0, n1 = self.nodes
        self.connect_nodes(1, 0)

        self.log("both nodes share a 20-block chain")
        n0.generate(20)
        self.sync_blocks([n0, n1])
        target = n0.getblockhash(11)
        old_tip = n0.getbestblockhash()

        self.log("argument checks")
        assert_raises_rpc_error(-8, None, n1.invalidateblock, 11)  # a height is not accepted
        assert_raises_rpc_error(-8, None, n1.invalidateblock, "not-a-hash")
        assert_raises_rpc_error(-5, None, n1.invalidateblock, "00" * 32)
        assert_raises_rpc_error(-1, None, n1.invalidateblock, n0.getblockhash(0))  # genesis

        self.log("invalidating block 11 rolls node1 back to height 10")
        n1.invalidateblock(target)
        assert_equal(n1.getblockcount(), 10)
        assert_equal(n1.getbestblockhash(), n0.getblockhash(10))
        assert_equal(tip_status(n1, old_tip), "invalid")
        assert_equal(n0.getblockcount(), 20)  # the other node is untouched

        self.log("node1 refuses new blocks built on the invalid chain")
        n0.generate(3)
        new_tip = n0.getbestblockhash()
        wait_until(lambda: tip_status(n1, new_tip) == "invalid", what="node1 to receive the new blocks")
        assert_equal(n1.getblockcount(), 10)

        self.log("node1 can mine a different chain from the rollback point")
        n1.generate(4)
        fork_tip = n1.getbestblockhash()
        assert_equal(n1.getblockcount(), 14)
        assert fork_tip != old_tip

        self.log("the invalidation survives a restart")
        n1.stop()
        n1.start()
        self.connect_nodes(1, 0)
        assert_equal(n1.getbestblockhash(), fork_tip)
        n0.generate(1)  # a block on the invalid chain arrives after the restart
        newest = n0.getbestblockhash()
        wait_until(lambda: tip_status(n1, newest) == "invalid", what="node1 to receive the newest block")
        assert_equal(n1.getbestblockhash(), fork_tip)
        assert_equal(n1.getblockcount(), 14)

        self.log("reconsiderblock switches back to the most-work chain")
        n1.reconsiderblock(target)
        assert_equal(n1.getbestblockhash(), newest)
        assert_equal(n1.getblockcount(), 24)
        assert_equal(tip_status(n1, fork_tip), "valid-headers")
        self.sync_blocks([n0, n1])


if __name__ == "__main__":
    InvalidateBlockTest().main()
