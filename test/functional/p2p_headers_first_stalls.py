#!/usr/bin/env python3
"""Headers-first (-headersfirst) when peers do not do their part.

1. Peers that connect, answer pings and ignore getheaders hold the few header-sync slots. After -headersynctimeout they are dropped, and
   the node syncs the old way (getblocks) from a peer that does answer.
2. A header chain built on a block that is then invalidated does not stay the best header.
3. A best header that no connected peer has told us of (its peer went away) does not stay the best header.
"""
import struct

from mininode import P2PConnection
from test_framework import CorgiTestFramework, assert_equal, wait_until


def header_bytes(node, block_hash):
    """The header of a block as a peer sends it in a headers message: 80 bytes, no AuxPoW proof, and a transaction count of 0."""
    b = node.getblock(block_hash)
    return struct.pack("<i32s32sIII", b["version"], bytes.fromhex(b["previousblockhash"])[::-1], bytes.fromhex(b["merkleroot"])[::-1],
                       b["time"], int(b["bits"], 16), b["nonce"]) + b"\x00"


def varint(n):
    return bytes([n]) if n < 253 else b"\xfd" + struct.pack("<H", n)


class HeadersFirstStallsTest(CorgiTestFramework):
    num_nodes = 3
    extra_args = [["-headersfirst=1", "-headersynctimeout=6"], [], ["-headersfirst=1", "-headersynctimeout=600", "-blocktimeout=600"]]

    def log_text(self, node):
        with open(node.debug_log, errors="replace") as f:
            return f.read()

    def run_test(self):
        a, b, c = self.nodes
        b.generate(40)

        self.log("three peers that never answer getheaders are dropped, and the node syncs with getblocks from a peer that does")
        silent = [P2PConnection(a.p2p_port, start_height=50) for _ in range(3)]
        for p in silent:
            wait_until(lambda p=p: p.got_verack, what="verack")
        wait_until(lambda: all(p.closed for p in silent), timeout=60, what="the silent peers to be dropped")
        assert "did not answer getheaders" in self.log_text(a)
        self.connect_nodes(0, 1)
        wait_until(lambda: a.getblockcount() == 40, timeout=120, what="the sync that falls back to getblocks")
        assert_equal(a.getbestblockhash(), b.getbestblockhash())

        self.log("a header chain built on a block that is invalidated is not the best header any more")
        self.connect_nodes(2, 1)
        wait_until(lambda: c.getblockcount() == 40, timeout=120, what="node c to take the 40 blocks")
        self.disconnect_nodes(2, 1)                  # from here c hears of the new blocks only through the peer below, which never sends them
        self.nodes[1].generate(10)
        wait_until(lambda: b.getblockcount() == 50, what="b to have 50 blocks")
        peer = P2PConnection(c.p2p_port, start_height=50)
        wait_until(lambda: peer.got_verack, what="verack")
        wait_until(lambda: peer.counts.get("getheaders", 0) >= 1, what="the node to ask for headers")
        peer.send("headers", varint(10) + b"".join(header_bytes(b, b.getblockhash(i)) for i in range(41, 51)))
        wait_until(lambda: "headers from" in self.log_text(c) and "best header 50" in self.log_text(c), what="the headers to be taken")
        h35 = c.getblockhash(35)
        c.invalidateblock(h35)
        wait_until(lambda: "descends from a block that failed" in self.log_text(c), what="the best header to be dropped")
        wait_until(lambda: "the best header is now" in self.log_text(c), what="another best header to be picked once the chain is rolled back")
        assert_equal(c.getblockcount(), 34)

        self.log("a best header whose peer went away is not kept as the best header")
        c.reconsiderblock(h35)
        headers = b"".join(header_bytes(b, b.getblockhash(i)) for i in range(41, 51))
        before = self.log_text(c).count("best header 50")
        peer.send("headers", varint(10) + headers)
        wait_until(lambda: self.log_text(c).count("best header 50") > before, what="the headers to be taken again")
        mark = len(self.log_text(c))
        peer.close()
        other = P2PConnection(c.p2p_port, start_height=0)       # the check is made while a peer is connected, and this one knows nothing of that header
        wait_until(lambda: other.got_verack, what="verack")
        wait_until(lambda: "the best header is now" in self.log_text(c)[mark:], timeout=60, what="the best header to be picked again once nobody has it")


if __name__ == "__main__":
    HeadersFirstStallsTest().main()
