#!/usr/bin/env python3
"""Headers-first and a reorganisation: a node that has mined its own short branch joins a peer with a longer one and follows it."""
from test_framework import CorgiTestFramework, assert_equal, wait_until


class HeadersFirstReorgTest(CorgiTestFramework):
    num_nodes = 2
    extra_args = [[], ["-headersfirst=1"]]

    def run_test(self):
        a, b = self.nodes
        a.generate(50)
        self.connect_nodes(1, 0)
        self.sync_blocks()
        self.disconnect_nodes(1, 0)

        self.log("two branches from the same block: 5 blocks on the headers-first node, 10 on the other")
        b.generate(5)
        a.generate(10)
        short_tip = b.getbestblockhash()
        assert short_tip != a.getbestblockhash()

        self.log("they meet: the node asks for the headers of the longer branch, finds where they part, and fetches only its blocks")
        self.connect_nodes(1, 0)
        wait_until(lambda: b.getbestblockhash() == a.getbestblockhash(), timeout=60, what="the reorganisation (%d vs %d)" % (b.getblockcount(), a.getblockcount()))
        assert_equal(b.getblockcount(), 60)
        with open(b.debug_log, errors="replace") as f:
            text = f.read()
        assert "headers-first: asking" in text and "for headers" in text
        assert "blocks from height 51" in text, "the blocks of the longer branch were not fetched from where the branches parted"


if __name__ == "__main__":
    HeadersFirstReorgTest().main()
