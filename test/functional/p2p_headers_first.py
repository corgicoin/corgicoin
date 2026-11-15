#!/usr/bin/env python3
"""Headers-first sync (-headersfirst).

A node started with -headersfirst joins two peers that hold the same chain. It asks for headers, checks them, and then fetches the
blocks from both peers at once (a window ahead of its tip) rather than from one peer in 500s. It ends on the same chain as they have.
Bad input is refused: headers that do not connect, headers with the wrong difficulty, and a headers message that is too long.
"""
import struct

from mininode import P2PConnection
from test_framework import CorgiTestFramework, assert_equal, wait_until

BLOCKS = 2010        # more than one headers message (2000 each)


def header_bytes(node, block_hash, **override):
    """The header of a block as a peer would send it in a headers message: 80 bytes, no AuxPoW proof, and a transaction count of 0."""
    b = node.getblock(block_hash)
    f = dict(version=b["version"], prev=bytes.fromhex(b["previousblockhash"])[::-1], merkle=bytes.fromhex(b["merkleroot"])[::-1],
             time=b["time"], bits=int(b["bits"], 16), nonce=b["nonce"])
    f.update(override)
    return struct.pack("<i32s32sIII", f["version"], f["prev"], f["merkle"], f["time"], f["bits"], f["nonce"]) + b"\x00"


def varint(n):
    return bytes([n]) if n < 253 else b"\xfd" + struct.pack("<H", n)


class HeadersFirstTest(CorgiTestFramework):
    num_nodes = 4
    extra_args = [[], [], ["-headersfirst=1"], ["-headersfirst=1", "-blocktimeout=5"]]

    def log_text(self, node):
        with open(node.debug_log, errors="replace") as f:
            return f.read()

    def run_test(self):
        a, b, c, d = self.nodes
        for _ in range(BLOCKS // 300):          # in batches: one RPC call has two minutes, and a loaded machine needs more for 2100 blocks
            a.generate(300)
        a.generate(BLOCKS % 300)
        self.connect_nodes(1, 0)
        self.sync_blocks([a, b], timeout=240)
        assert_equal(b.getblockcount(), BLOCKS)

        self.log("a headers-first node joins two peers with the same chain")
        self.connect_nodes(2, 0)
        self.connect_nodes(2, 1)
        wait_until(lambda: c.getblockcount() == BLOCKS, timeout=240, what="headers-first sync (%d)" % c.getblockcount())
        assert_equal(c.getbestblockhash(), a.getbestblockhash())

        text = self.log_text(c)
        assert "headers-first: asking" in text and "for headers" in text, "no header request in the log"
        assert "headers-first: " in text and " headers from " in text
        askers = {l.split("asking ")[1].split(" for ")[0] for l in text.split("\n") if "headers-first: asking" in l and " blocks from height" in l}
        self.log("blocks were asked of: %s" % sorted(askers))
        assert len(askers) >= 2, "blocks came from one peer only: %s" % sorted(askers)
        self.log("a node that is not headers-first never logs any of it")
        assert "headers-first:" not in self.log_text(a)

        self.log("and it keeps up with new blocks as before")
        a.generate(5)
        wait_until(lambda: c.getblockcount() == BLOCKS + 5, what="new blocks")
        assert_equal(c.getbestblockhash(), a.getbestblockhash())

        self.log("bad headers from a peer: refused, node unaffected")
        tip = c.getbestblockhash()
        h = c.getblock(tip)
        peer = P2PConnection(c.p2p_port, start_height=0)
        wait_until(lambda: peer.got_verack, what="verack")
        # does not connect: its parent is nothing the node knows
        peer.send("headers", varint(1) + header_bytes(c, tip, prev=b"\x11" * 32))
        wait_until(lambda: "do not connect" in self.log_text(c), what="the unconnected header to be noticed")
        # wrong difficulty for its place
        peer.send("headers", varint(1) + header_bytes(c, tip, bits=int(h["bits"], 16) ^ 0x00010000))
        wait_until(lambda: "bad header from" in self.log_text(c), what="the bad header to be refused")
        # too many in one message
        one = header_bytes(c, tip)
        peer.send("headers", varint(2001) + one * 2001)
        wait_until(lambda: "headers message size = 2001" in self.log_text(c), what="the oversize message to be refused")
        peer.send("ping", b"\x00" * 8)
        wait_until(lambda: peer.counts.get("pong", 0) >= 1, what="a pong: the node carries on")
        assert_equal(c.getbestblockhash(), a.getbestblockhash())

        self.log("a peer that gives headers but never the blocks is dropped, and the node does not wait on it for ever")
        stall = P2PConnection(d.p2p_port, start_height=60)
        wait_until(lambda: stall.counts.get("getheaders", 0) >= 1, what="the node to ask the peer for headers")
        stall.send("headers", varint(60) + b"".join(header_bytes(a, a.getblockhash(i)) for i in range(1, 61)))
        wait_until(lambda: stall.counts.get("getdata", 0) >= 1, what="the node to ask the peer for blocks")
        wait_until(lambda: stall.closed, timeout=40, what="the node to drop the peer that sent no block")
        assert "did not send block" in self.log_text(d)
        assert_equal(d.getblockcount(), 0)
        self.log("and then it syncs from a peer that does")
        self.connect_nodes(3, 0)
        wait_until(lambda: d.getblockcount() == BLOCKS + 5, timeout=240, what="sync after the stalled peer")


if __name__ == "__main__":
    HeadersFirstTest().main()
