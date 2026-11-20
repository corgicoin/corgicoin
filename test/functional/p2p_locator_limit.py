#!/usr/bin/env python3
"""A getheaders or getblocks locator of more than 101 hashes is refused and scored.

An honest locator has about 30 hashes. Each one is looked up under cs_main, and a 5 MB message holds about 150,000 of them.
"""
import struct

from mininode import P2PConnection
from test_framework import CorgiTestFramework, assert_equal, wait_until


def locator(n):
    # nVersion, CompactSize count, n hashes, hashStop
    count = bytes([n]) if n < 253 else b"\xfd" + struct.pack("<H", n)
    return struct.pack("<i", 70001) + count + b"".join(struct.pack("<I", i + 1) + b"\x00" * 28 for i in range(n)) + b"\x00" * 32


class LocatorLimitTest(CorgiTestFramework):
    num_nodes = 1

    def log_text(self):
        with open(self.nodes[0].debug_log, errors="replace") as f:
            return f.read()

    def run_test(self):
        node = self.nodes[0]
        node.generate(5)
        for command in ("getheaders", "getblocks"):
            self.log("%s with a locator of 101 hashes is answered, with 102 refused and scored" % command)
            peer = P2PConnection(node.p2p_port)
            wait_until(lambda: peer.got_verack, what="verack")
            peer.send(command, locator(101))
            peer.send("ping", b"\x00" * 8)
            wait_until(lambda: peer.counts.get("pong", 0) >= 1, what="a pong after the 101-hash locator")
            assert "%s locator size" % command not in self.log_text()
            mark = len(self.log_text())                  # (what is scored is judged from here: the first command's line is in the log already)
            peer.send(command, locator(102))
            wait_until(lambda: "%s locator size = 102" % command in self.log_text(), what="the long locator to be refused")
            assert "misbehaving" in self.log_text()[mark:], "the peer was not scored"
            peer.close()


if __name__ == "__main__":
    LocatorLimitTest().main()
