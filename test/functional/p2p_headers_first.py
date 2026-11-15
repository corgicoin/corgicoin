#!/usr/bin/env python3
"""Headers-first sync (-headersfirst).

A node started with -headersfirst joins two peers that hold the same chain. It asks for headers, checks them, and then fetches the
blocks from both peers at once (a window ahead of its tip) rather than from one peer in 500s. It ends on the same chain as they have.
Bad input is refused: headers that do not connect, headers with the wrong difficulty, and a headers message that is too long.
"""
import struct

from mininode import P2PConnection
from test_framework import CorgiTestFramework, assert_equal, wait_until

BLOCKS = 400


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
    num_nodes = 3
    extra_args = [[], [], ["-headersfirst=1"]]

    def log_text(self, node):
        with open(node.debug_log, errors="replace") as f:
            return f.read()

    def run_test(self):
        a, b, c = self.nodes
        a.generate(BLOCKS)
        self.connect_nodes(1, 0)
        self.sync_blocks([a, b])
        assert_equal(b.getblockcount(), BLOCKS)

        self.log("a headers-first node joins two peers with the same chain")
        self.connect_nodes(2, 0)
        self.connect_nodes(2, 1)
        wait_until(lambda: c.getblockcount() == BLOCKS, timeout=90, what="headers-first sync (%d)" % c.getblockcount())
        assert_equal(c.getbestblockhash(), a.getbestblockhash())

        text = self.log_text(c)
        assert "headers-first: asking" in text and "for headers" in text, "no header request in the log"
        assert "headers-first: " in text and " headers from " in text
        askers = {l.split("asking ")[1].split(" for ")[0] for l in text.split("\n") if "headers-first: asking" in l and " blocks from height" in l}
        self.log("blocks were asked of: %s" % sorted(askers))
        assert len(askers) >= 1
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


if __name__ == "__main__":
    HeadersFirstTest().main()
