#!/usr/bin/env python3
"""Headers-first: no blocks are asked for from a peer whose header chain has less work than -minimumchainwork.

The headers of such a chain are kept and checked as any others and nobody is scored for them, but headers-first does not fetch its blocks.
(A block announced with inv, sent unasked, or asked for the old way is handled as before and is not covered.) Once a peer shows a chain
with at least the floor's work, its blocks are asked for.

  1. -minimumchainwork is set to the work of block 70. A peer gives the headers of blocks 1 to 40: they are held (header_only_entries 40), no
     getdata goes to the peer, it is not scored, and the node stays at height 0.
  2. A second peer gives the headers of blocks 1 to 100: the node asks it for blocks. The first peer is still not asked for any.
  3. With -minimumchainwork=0 a peer with a short chain is asked for its blocks, as before.
"""
from mininode import P2PConnection
from p2p_headers_first import header_bytes, varint
from test_framework import CorgiTestFramework, assert_equal, wait_until

HEIGHT = 100        # below the merged-mining fork height of regtest, so a header is 80 bytes with no proof
SHORT = 40
FLOOR_AT = 70


class HeadersFirstMinWorkTest(CorgiTestFramework):
    num_nodes = 2
    extra_args = [[], ["-headersfirst=1"]]

    def banscores(self, node):
        return [p["banscore"] for p in node.getpeerinfo()]

    def run_test(self):
        a, node = self.nodes
        a.generate(HEIGHT)
        headers = [header_bytes(a, a.getblockhash(i)) for i in range(1, HEIGHT + 1)]
        # every regtest block carries the same work: the tip's chain work, over the number of blocks counting the genesis block
        per_block = int(a.getblockchaininfo()["chainwork"], 16) // (HEIGHT + 1)
        assert per_block > 0 and int(a.getblockchaininfo()["chainwork"], 16) == per_block * (HEIGHT + 1)
        floor = "%x" % (per_block * (FLOOR_AT + 1))            # the work of block FLOOR_AT
        assert per_block * (SHORT + 1) < per_block * (FLOOR_AT + 1) <= per_block * (HEIGHT + 1)

        node.stop()
        node.start(["-minimumchainwork=" + floor])
        assert_equal(node.getblockchaininfo()["minimumchainwork"].lstrip("0"), floor)

        self.log("a peer whose chain (%d blocks) has less work than the floor (block %d): its headers are held, no blocks are asked for" % (SHORT, FLOOR_AT))
        first = P2PConnection(node.p2p_port, start_height=SHORT)
        wait_until(lambda: first.counts.get("getheaders", 0) >= 1, what="getheaders to the first peer")
        first.send("headers", varint(SHORT) + b"".join(headers[:SHORT]))
        wait_until(lambda: node.getblockchaininfo()["header_only_entries"] == SHORT, what="the %d headers to be held" % SHORT)
        wait_until(lambda: "less work than -minimumchainwork" in open(node.debug_log, errors="replace").read(), what="the node to say it holds back the blocks")
        first.send("ping", b"\x01" * 8)
        wait_until(lambda: first.counts.get("pong", 0) >= 1, what="the node to answer (it has handled the headers)")
        assert_equal(first.counts.get("getdata", 0), 0)
        assert_equal(node.getblockcount(), 0)
        assert_equal(self.banscores(node), [0])

        self.log("a peer with a chain past the floor: its blocks are asked for and taken, and the first peer is still not asked")
        second = P2PConnection(node.p2p_port, start_height=HEIGHT)
        wait_until(lambda: second.counts.get("getheaders", 0) >= 1, what="getheaders to the second peer")
        second.send("headers", varint(HEIGHT) + b"".join(headers))
        wait_until(lambda: second.counts.get("getdata", 0) >= 1, what="getdata to the second peer")
        assert_equal(first.counts.get("getdata", 0), 0)
        assert_equal(self.banscores(node), [0, 0])
        # (the node is not connected to a, so no block arrives: the point is that the second peer was asked and the first was not)
        first.close()
        second.close()

        self.log("-minimumchainwork=0: a peer with a short chain is asked for its blocks as before")
        node.stop()
        node.start(["-minimumchainwork=0"])
        third = P2PConnection(node.p2p_port, start_height=SHORT)
        wait_until(lambda: third.counts.get("getheaders", 0) >= 1, what="getheaders to the third peer")
        third.send("headers", varint(SHORT) + b"".join(headers[:SHORT]))
        wait_until(lambda: third.counts.get("getdata", 0) >= 1, what="getdata to the third peer")


if __name__ == "__main__":
    HeadersFirstMinWorkTest().main()
