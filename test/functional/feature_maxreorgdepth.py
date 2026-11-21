#!/usr/bin/env python3
"""-maxreorgdepth=<n>: a chain with more work that would remove more than n blocks from ours is not taken.

Node a runs with -maxreorgdepth=5; node c, the control, has no limit; node b is the other chain's miner. All three share 10 blocks.
  1. a and b split; a mines 4, b mines 6 (a would remove 4, no more than 5): a follows b.
  2. a and c split from b; each mines 7 on its own, b mines 10 more (they would remove 7, more than 5): c follows b and a does not: it stays
     on its own chain, says so in its log and in getinfo's errors, and goes on being a working node (it still mines on its own chain).
  3. a is restarted without the option and b mines one more block: a takes b's chain.
  4. A limit of exactly the depth is not a refusal: depth 5 with -maxreorgdepth=5 (a fourth node, d) follows.
"""
from test_framework import CorgiTestFramework, assert_equal, wait_until


class MaxReorgDepthTest(CorgiTestFramework):
    num_nodes = 4
    extra_args = [["-maxreorgdepth=5"], [], [], ["-maxreorgdepth=5"]]

    def log_text(self, node):
        with open(node.debug_log, errors="replace") as f:
            return f.read()

    def run_test(self):
        a, b, c, d = self.nodes
        self.connect_nodes(0, 1)
        self.connect_nodes(2, 1)
        self.connect_nodes(3, 1)
        b.generate(10)
        self.sync_blocks(timeout=120)
        assert_equal(a.getblockcount(), 10)

        self.log("a fork that removes 4 blocks, with a limit of 5: taken")
        self.disconnect_nodes(0, 1)
        a.generate(4)
        b.generate(6)
        self.connect_nodes(0, 1)
        wait_until(lambda: a.getbestblockhash() == b.getbestblockhash(), timeout=60, what="a to follow b over a fork of 4")
        assert_equal(a.getblockcount(), 16)
        assert "not reorganising" not in self.log_text(a)
        self.sync_blocks(timeout=120)

        self.log("a fork that removes exactly the limit (5) is taken too (the limit is a count of blocks removed)")
        self.disconnect_nodes(3, 1)
        d.generate(5)
        b.generate(8)
        self.connect_nodes(3, 1)
        wait_until(lambda: d.getbestblockhash() == b.getbestblockhash(), timeout=60, what="d to follow b over a fork of 5")
        self.sync_blocks(timeout=120)
        assert "not reorganising" not in self.log_text(d)

        self.log("a fork that removes 7: the node with the limit stays, the control follows")
        self.disconnect_nodes(0, 1)
        self.disconnect_nodes(2, 1)
        a.generate(7)
        c.generate(7)
        b.generate(10)
        mine = a.getbestblockhash()
        self.connect_nodes(0, 1)
        self.connect_nodes(2, 1)
        wait_until(lambda: c.getbestblockhash() == b.getbestblockhash(), timeout=60, what="the control to follow b")
        wait_until(lambda: "not reorganising" in self.log_text(a), timeout=60, what="a to refuse the deep fork")
        assert_equal(a.getbestblockhash(), mine)
        assert "-maxreorgdepth" in a.getinfo()["errors"], a.getinfo()["errors"]
        assert "more than -maxreorgdepth=5 blocks back" in self.log_text(a)

        self.log("a still works: it mines on its own chain, and a block of b's chain that arrives later is refused again")
        height = a.getblockcount()
        a.generate(1)
        assert_equal(a.getblockcount(), height + 1)
        b.generate(1)
        wait_until(lambda: c.getbestblockhash() == b.getbestblockhash(), timeout=60, what="c to follow b's new block")
        assert a.getbestblockhash() != b.getbestblockhash()

        self.log("restarted without the option, the next block of b's chain is taken")
        a.stop()
        a.extra_args = []
        a.start()
        self.connect_nodes(0, 1)
        b.generate(1)
        wait_until(lambda: a.getbestblockhash() == b.getbestblockhash(), timeout=90, what="a, without the limit, to follow b")


if __name__ == "__main__":
    MaxReorgDepthTest().main()
