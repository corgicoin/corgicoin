#!/usr/bin/env python3
"""Headers-first: an honest peer on another chain is not scored as a replay when someone else's chain is our best header.

A full answer (2000 headers) that holds nothing new and ends no higher than where we asked from is a replay: scored and not asked again.
But the node asks from its best header, and a peer on another chain answers from the fork point: with a fork at the start and a best header
above height 2000, the answer is full, ends below where the request started, and is all new. It was scored and never asked again, so a
peer that fed the node a cheap chain first (all it needs is more work than the first 2000 honest headers) kept the honest ones out.

  1. A first peer gives a chain of 2100 headers; it is the best header.
  2. A second peer on another chain of 2200 gives its first 2000: the node must not score it, and must ask it for the rest (so no 'no higher
     than where we asked' line in the log); its chain, now the heavier, is asked for blocks.

The chains are made of headers with their proof of work ground out here (regtest is easy), not mined blocks: mining thousands of blocks in
seconds runs the block times ahead of the clock until the LWMA limit on the future refuses the next one.
"""
import hashlib

from mininode import P2PConnection
from p2p_headers_first import varint
from p2p_headers_first_limits import grind, header_hash
from test_framework import CorgiTestFramework, assert_equal, wait_until

X_LEN, Y_LEN = 2100, 2200
CHAIN_ID = 0x00C6
REGTEST_FORK_HEIGHT = 200          # from here every block carries the chain ID in its version


def make_chain(tag, length, genesis):
    bits = int(genesis["bits"], 16)
    headers, prev, t = [], genesis["hash"], genesis["time"]
    for i in range(1, length + 1):
        t += 1
        version = genesis["version"] if i < REGTEST_FORK_HEIGHT else (CHAIN_ID << 16) | 1
        h = grind(version, prev, hashlib.sha256(("%s/%d" % (tag, i)).encode()).digest(), t, bits)
        headers.append(h + b"\x00")
        prev = header_hash(h)
    return headers


class ForkScoreTest(CorgiTestFramework):
    num_nodes = 1
    extra_args = [["-headersfirst=1"]]

    def run_test(self):
        node = self.nodes[0]
        genesis = node.getblock(node.getblockhash(0))
        self.log("two chains from the first block: %d and %d headers" % (X_LEN, Y_LEN))
        hx = make_chain("x", X_LEN, genesis)
        hy = make_chain("y", Y_LEN, genesis)
        assert hx[0] != hy[0]

        self.log("a first peer gives its whole chain: it is the best header")
        x = P2PConnection(node.p2p_port, start_height=X_LEN)
        wait_until(lambda: x.counts.get("getheaders", 0) >= 1, what="getheaders to the first peer")
        x.send("headers", varint(2000) + b"".join(hx[:2000]))
        wait_until(lambda: x.counts.get("getheaders", 0) >= 2, what="the node to ask the first peer for the rest")
        x.send("headers", varint(X_LEN - 2000) + b"".join(hx[2000:]))
        wait_until(lambda: node.getblockchaininfo()["header_only_entries"] == X_LEN, what="%d headers held" % X_LEN)

        self.log("a second peer on another chain answers from the fork point: full, all new, ending below where the node asked from")
        y = P2PConnection(node.p2p_port, start_height=Y_LEN)
        wait_until(lambda: y.counts.get("getheaders", 0) >= 1, what="getheaders to the second peer")
        y.send("headers", varint(2000) + b"".join(hy[:2000]))
        wait_until(lambda: y.counts.get("getheaders", 0) >= 2, what="the node to ask the second peer for the rest of its chain")
        assert "no higher than where we asked" not in open(node.debug_log, errors="replace").read()
        assert_equal([p["banscore"] for p in node.getpeerinfo()], [0, 0])

        self.log("the rest of its chain makes it the heaviest: its blocks are asked for")
        y.send("headers", varint(Y_LEN - 2000) + b"".join(hy[2000:]))
        wait_until(lambda: y.counts.get("getdata", 0) >= 1, what="getdata to the second peer")
        assert_equal([p["banscore"] for p in node.getpeerinfo()], [0, 0])


if __name__ == "__main__":
    ForkScoreTest().main()
