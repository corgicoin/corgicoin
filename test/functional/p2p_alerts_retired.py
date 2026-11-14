#!/usr/bin/env python3
"""Alerts are retired: the node reads an alert message and drops it, and does not pass it on.

The alert key is not secret, every alert cost a signature check, and an alert could put any text in the status bar of every
node. The message is no longer parsed, checked or relayed; a peer that sends one is not punished (old nodes still do).
"""
import os

from test_framework import CorgiTestFramework, wait_until
from mininode import P2PConnection


class AlertsRetiredTest(CorgiTestFramework):
    num_nodes = 1
    extra_args = [["-debug=net"]]

    def run_test(self):
        node = self.nodes[0]
        sender = P2PConnection(node.p2p_port)
        listener = P2PConnection(node.p2p_port)
        wait_until(lambda: sender.got_verack and listener.got_verack, timeout=20, what="the handshakes")

        self.log("an alert (here: bytes that are not even a well formed one) is dropped by name, and the sender stays connected")
        sender.send("alert", os.urandom(120))
        wait_until(lambda: "alerts are retired" in open(node.debug_log, errors="replace").read(), timeout=20,
                   what="the node to say it ignored the alert")
        assert not sender.closed
        assert node.getpeerinfo()[0]["banscore"] == 0 if node.getpeerinfo() else True

        self.log("and nothing was relayed to the other peer")
        assert listener.counts.get("alert", 0) == 0
        sender.close()
        listener.close()


if __name__ == "__main__":
    AlertsRetiredTest().main()
