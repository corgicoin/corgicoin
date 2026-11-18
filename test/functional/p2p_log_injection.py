#!/usr/bin/env python3
"""A peer cannot write its own lines into debug.log.

The command name of a message header is 12 bytes of the peer's choosing. One that is not printable text makes the header invalid,
and the node used to log it as it came: a newline in it began a line the peer had written.
"""
import time

from mininode import P2PConnection
from test_framework import CorgiTestFramework, assert_equal, wait_until


class LogInjectionTest(CorgiTestFramework):
    num_nodes = 1

    def run_test(self):
        node = self.nodes[0]
        peer = P2PConnection(node.p2p_port)
        wait_until(lambda: peer.got_verack, what="verack")

        self.log("a header whose command holds a newline and a forged log line")
        peer.send("x\nINJECTED line\x01\x1b[31m", b"")
        peer.send("ping", b"\x00" * 8)              # and the node carries on: the next message is read
        wait_until(lambda: peer.counts.get("pong", 0) >= 1, what="a pong after the bad header")

        with open(node.debug_log, errors="replace") as f:
            lines = f.read().split("\n")
        assert any("ERRORS IN HEADER" in l for l in lines), "the bad header was not logged at all"
        forged = [l for l in lines if l.startswith("INJECTED")]
        assert_equal(forged, [])
        assert not any("\x1b" in l or "\x01" in l for l in lines), "a control character from the peer reached the log"


if __name__ == "__main__":
    LogInjectionTest().main()
