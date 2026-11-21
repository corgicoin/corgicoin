#!/usr/bin/env python3
"""getheaders is answered at a bounded rate per peer: a burst of 100, then one a second.

Each answer reads up to 2000 headers, from disk for a merged-mined one. A peer that sends them back to back gets the burst answered and the
rest ignored (not scored: a slow link is not a fault), the node carries on, and the next request after a pause is answered again. Another
peer is not affected.
"""
import struct
import time

from mininode import P2PConnection
from test_framework import CorgiTestFramework, assert_equal, wait_until

BURST = 100
SENT = 400


def getheaders(tip_hash_hex=None):
    # a locator holding the genesis hash only: the answer is every header after it (here a few)
    return struct.pack("<i", 70001) + b"\x01" + bytes.fromhex(tip_hash_hex)[::-1] + b"\x00" * 32


class GetHeadersRateTest(CorgiTestFramework):
    num_nodes = 1

    def log_text(self):
        with open(self.nodes[0].debug_log, errors="replace") as f:
            return f.read()

    def run_test(self):
        node = self.nodes[0]
        node.generate(5)
        genesis = node.getblockhash(0)
        msg = getheaders(genesis)

        peer = P2PConnection(node.p2p_port)
        wait_until(lambda: peer.got_verack, what="verack")
        start = time.time()
        for _ in range(SENT):
            peer.send("getheaders", msg)
        peer.send("ping", b"\x00" * 8)
        wait_until(lambda: peer.counts.get("pong", 0) >= 1, timeout=60, what="a pong: the node carries on")
        took = time.time() - start
        answered = peer.counts.get("headers", 0)
        self.log("%d getheaders sent in %.1f s: %d answered" % (SENT, took, answered))
        assert BURST <= answered <= BURST + int(took) + 2, "answered %d (burst %d, %.1f s)" % (answered, BURST, took)
        assert "not answered: too many too fast" in self.log_text()
        assert "misbehaving" not in self.log_text(), "a peer that asks too often is not scored"

        self.log("after a pause the next request is answered")
        time.sleep(3)
        before = peer.counts.get("headers", 0)
        peer.send("getheaders", msg)
        wait_until(lambda: peer.counts.get("headers", 0) > before, what="an answer after the pause")

        self.log("another peer has a burst of its own")
        other = P2PConnection(node.p2p_port)
        wait_until(lambda: other.got_verack, what="verack")
        other.send("getheaders", msg)
        wait_until(lambda: other.counts.get("headers", 0) >= 1, what="the other peer's answer")
        peer.close()
        other.close()


if __name__ == "__main__":
    GetHeadersRateTest().main()
