#!/usr/bin/env python3
"""A set that falls out of step with the chain is not rebuilt inline, stops being written, and is rebuilt at the next start.

-testcoinsbreak (regtest) makes the set refuse one block's changes. The node must go on connecting blocks (the index decides), must not stop to
rebuild the set while it holds cs_main, and must write nothing more to the set: its tip marker is removed, so the next start rebuilds it from the
blocks and the set it gives is the one the blocks give.
"""
from test_framework import CorgiTestFramework, assert_equal, wait_until


class ChainstateStaleTest(CorgiTestFramework):
    num_nodes = 1
    extra_args = [["-testcoinsbreak=30"]]

    def log_text(self, node):
        with open(node.debug_log, errors="replace") as f:
            return f.read()

    def run_test(self):
        node = self.nodes[0]
        self.log("blocks are connected past the height where the set goes out of step")
        node.generate(20)
        node.generate(25)                       # past 30
        assert_equal(node.getblockcount(), 45)
        text = self.log_text(node)
        assert "it will be rebuilt at the next start" in text, "the stale set was not reported"
        assert "COINS: rebuilding" not in text, "the set was rebuilt inline"
        node.generate(5)                        # and the node carries on
        assert_equal(node.getblockcount(), 50)
        tip = node.getbestblockhash()

        self.log("the next start rebuilds it from the blocks")
        node.stop()
        node.extra_args = [a for a in node.extra_args if not a.startswith("-testcoinsbreak")]
        node.start()
        assert_equal(node.getblockcount(), 50)
        assert_equal(node.getbestblockhash(), tip)
        text = self.log_text(node)
        assert "COINS: rebuilding" in text and "COINS: rebuilt" in text, "the set was not rebuilt at the start"
        assert_equal(node.gettxoutsetinfo("coins")["hash_serialized"], node.gettxoutsetinfo("blocks")["hash_serialized"])
        node.generate(3)
        assert_equal(node.gettxoutsetinfo("coins")["hash_serialized"], node.gettxoutsetinfo("blocks")["hash_serialized"])



if __name__ == "__main__":
    ChainstateStaleTest().main()
