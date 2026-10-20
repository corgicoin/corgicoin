#!/usr/bin/env python3
"""Block sync and reorg: a late joiner catches up, and the most-work chain wins after a split."""
from test_framework import CorgiTestFramework, assert_equal


class BlockSyncTest(CorgiTestFramework):
    """Three nodes: initial catch-up, a network split, and a reorg on rejoin."""
    num_nodes = 3

    def run_test(self):
        n0, n1, n2 = self.nodes

        self.log("node0 mines alone; node1 catches up from scratch")
        n0.generate(120)
        self.connect_nodes(1, 0)
        self.sync_blocks([n0, n1])
        assert_equal(n1.getblockcount(), 120)

        self.log("chain on node2 joins too")
        self.connect_nodes(2, 0)
        self.sync_blocks()

        self.log("split: node2 is isolated, both sides mine")
        self.disconnect_nodes(2, 0)
        n0.generate(5)
        self.sync_blocks([n0, n1])
        n2.generate(12)  # longer fork
        assert_equal(n0.getblockcount(), 125)
        assert_equal(n2.getblockcount(), 132)
        fork_tip = n2.getbestblockhash()
        orphaned = n0.getbestblockhash()

        self.log("rejoin: the longer fork wins everywhere")
        self.connect_nodes(0, 2)
        self.sync_blocks()
        for n in self.nodes:
            assert_equal(n.getbestblockhash(), fork_tip)
            assert_equal(n.getblockcount(), 132)

        self.log("the losing tip is now a side branch")
        tips = {t["hash"]: t for t in n0.getchaintips()}
        assert orphaned in tips, "orphaned tip missing from getchaintips"
        assert tips[orphaned]["status"] != "active"


if __name__ == "__main__":
    BlockSyncTest().main()
