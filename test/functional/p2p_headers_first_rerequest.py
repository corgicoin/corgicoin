#!/usr/bin/env python3
"""Headers-first: a block that one peer has sat on for 10 seconds is asked of a second peer as well, and not of a third.

The blocks of the window are shared out between peers, 64 in flight each. A peer that takes its share and never answers holds those blocks
until -blocktimeout (120 s) drops it, and with enough of them the whole window is held. Now a block asked of one peer more than 10 seconds
ago is also asked of another that has room, so honest peers go on taking the blocks in order.

  1. A first peer gives all the headers and is asked for 64 blocks, which it never sends.
  2. A second peer joins, is asked for the blocks nobody holds, and 10 seconds after, for the first peer's as well.
  3. A third peer is asked for blocks that only one peer holds, but not for the ones two hold.
"""
import struct
import time

from mininode import P2PConnection
from p2p_headers_first import header_bytes, varint
from test_framework import CorgiTestFramework, assert_equal, wait_until

HEIGHT = 100        # below the merged-mining fork height of regtest, so a header is 80 bytes with no proof


def asked(peer):
    """The hashes (as hex, display order) the node has asked this peer for with getdata."""
    out = []
    for payload in list(peer.messages.get("getdata", [])):
        n, off = payload[0], 1
        if n == 0xfd:
            n, off = struct.unpack("<H", payload[1:3])[0], 3
        for i in range(n):
            out.append(payload[off + 4:off + 36][::-1].hex())
            off += 36
    return out


class HeadersFirstRerequestTest(CorgiTestFramework):
    num_nodes = 2
    extra_args = [[], ["-headersfirst=1"]]

    def run_test(self):
        a, node = self.nodes
        a.generate(HEIGHT)
        headers = [header_bytes(a, a.getblockhash(i)) for i in range(1, HEIGHT + 1)]
        first_block = a.getblockhash(1)
        held_by_first = [a.getblockhash(i) for i in range(1, 65)]

        self.log("a first peer is asked for 64 blocks and sends none")
        first = P2PConnection(node.p2p_port, start_height=HEIGHT)
        wait_until(lambda: first.counts.get("getheaders", 0) >= 1, what="getheaders to the first peer")
        first.send("headers", varint(HEIGHT) + b"".join(headers))
        wait_until(lambda: len(asked(first)) >= 64, what="the 64 blocks to be asked of the first peer (they come over a few ticks)")
        t0 = time.time()
        assert_equal(set(asked(first)), set(held_by_first))

        self.log("a second peer joins and is asked for the blocks nobody holds, not for the first peer's")
        second = P2PConnection(node.p2p_port, start_height=HEIGHT)
        wait_until(lambda: second.counts.get("getheaders", 0) >= 1, what="the node to ask the second peer for its tip")
        second.send("headers", varint(1) + headers[-1])
        wait_until(lambda: len(asked(second)) >= HEIGHT - 64, what="the rest of the blocks to be asked of the second peer")
        assert first_block not in asked(second), "asked for a block another peer was asked for a moment ago"
        assert_equal(len(asked(second)), HEIGHT - 64)

        self.log("10 seconds on, the second peer is asked for the first peer's blocks too")
        wait_until(lambda: first_block in asked(second), timeout=40, what="the block the first peer sits on to be asked of the second")
        waited = time.time() - t0
        assert waited >= 9, "asked again after only %.1f seconds" % waited
        assert node.process.poll() is None

        self.log("a third peer is asked for blocks that one peer holds, not for the ones two hold")
        third = P2PConnection(node.p2p_port, start_height=HEIGHT)
        wait_until(lambda: third.counts.get("getheaders", 0) >= 1, what="the node to ask the third peer for its tip")
        third.send("headers", varint(1) + headers[-1])
        wait_until(lambda: len(asked(third)) > 0, what="getdata to the third peer")
        time.sleep(2)               # the rest of what it is asked for comes over a few ticks
        two_hold = set(asked(second)) & set(held_by_first)
        assert two_hold, "the second peer was asked for none of the first peer's blocks"
        assert not (set(asked(third)) & two_hold), "a third peer was asked for a block two peers hold"


if __name__ == "__main__":
    HeadersFirstRerequestTest().main()
