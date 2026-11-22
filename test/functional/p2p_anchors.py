#!/usr/bin/env python3
"""-anchors: up to two outbound peers are kept across a restart (anchors.dat) and connected to first.

Node a has outbound connections to b, c and d. Stopped with -anchors=1 (regtest turns it off unless asked), it writes anchors.dat with
two of them; started again with nothing else to dial, it connects to exactly those two, and removes the file once read. A node that was
killed (so it wrote nothing) starts with no connections; a node with -anchors=0 writes nothing.
"""
import os

from test_framework import CorgiTestFramework, assert_equal, wait_until


class AnchorsTest(CorgiTestFramework):
    num_nodes = 4
    extra_args = [["-anchors=1"], [], [], []]

    def anchors_file(self, node):
        return os.path.join(node.datadir, "regtest", "anchors.dat")

    def outbound(self, node):
        return sorted(p["addr"] for p in node.getpeerinfo() if not p.get("inbound", False))

    def run_test(self):
        a, b, c, d = self.nodes
        for n in (1, 2, 3):
            self.connect_nodes(0, n)
        assert_equal(len(self.outbound(a)), 3)

        self.log("stopped with 3 outbound peers: anchors.dat is written (two of them)")
        a.stop()
        assert os.path.exists(self.anchors_file(a)), "no anchors.dat after a clean stop"

        self.log("started again, nothing else to dial: it connects to two, and the file is removed once read")
        a.start()
        wait_until(lambda: len(self.outbound(a)) >= 2, timeout=60, what="a to reach its anchor peers")
        assert not os.path.exists(self.anchors_file(a)), "anchors.dat was not removed after it was read"
        peers = self.outbound(a)
        assert_equal(len(peers), 2)
        assert set(peers) <= {b.p2p_addr, c.p2p_addr, d.p2p_addr}, peers
        with open(a.debug_log, errors="replace") as f:
            log = f.read()
        assert log.count("Connecting to anchor peer") == 2, log.count("Connecting to anchor peer")

        self.log("killed (no clean stop): nothing was written, so it starts with no connections")
        assert not os.path.exists(self.anchors_file(a))
        a.process.kill()
        a.process.wait()
        a._exit_noted = True
        a.start()
        assert_equal(a.getconnectioncount(), 0)
        self.log("a node with -anchors=0 writes no file")
        for n in (1, 2):
            self.connect_nodes(0, n)
        a.stop()
        a.start(["-anchors=0"])
        a.stop()
        assert not os.path.exists(self.anchors_file(a))


if __name__ == "__main__":
    AnchorsTest().main()
