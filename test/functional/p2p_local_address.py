#!/usr/bin/env python3
"""The address a node advertises as its own keeps its port when it is added twice.

AddLocal is called again for an address already known (an -externalip given twice, an address found by discovery and then by a lookup, a UPnP
renewal). The second call raised the stored port by one where it should have raised the score, so the node told every peer, in its version
message and in the addresses it relays, a port nobody listens on.
"""
import re

from mininode import P2PConnection
from test_framework import CorgiTestFramework, assert_equal, wait_until


class LocalAddressTest(CorgiTestFramework):
    num_nodes = 1

    def advertised(self, node):
        """The 'us=' address in the last 'send version message' line of the log."""
        found = re.findall(r"send version message: .* us=(\S+),", open(node.debug_log, errors="replace").read())
        return found[-1] if found else None

    def check(self, node, args, what):
        node.stop()
        node.start(args)
        before = len(re.findall(r"send version message", open(node.debug_log, errors="replace").read()))
        peer = P2PConnection(node.p2p_port)
        wait_until(lambda: peer.got_verack, what="verack")
        wait_until(lambda: len(re.findall(r"send version message", open(node.debug_log, errors="replace").read())) > before, what="the version message")
        assert_equal(self.advertised(node), "8.8.8.8:%d" % node.p2p_port)
        peer.close()
        self.log("%s: advertised 8.8.8.8:%d" % (what, node.p2p_port))

    def run_test(self):
        node = self.nodes[0]
        self.check(node, ["-externalip=8.8.8.8"], "-externalip once")
        self.check(node, ["-externalip=8.8.8.8", "-externalip=8.8.8.8"], "-externalip twice (the address is added again)")


if __name__ == "__main__":
    LocalAddressTest().main()
