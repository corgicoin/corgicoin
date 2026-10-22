#!/usr/bin/env python3
"""Peers that leave a ping unanswered past -pingtimeout are disconnected."""
from mininode import P2PConnection
from test_framework import CorgiTestFramework, assert_equal, wait_until

PING_TIMEOUT = 3


class PingTimeoutTest(CorgiTestFramework):
    num_nodes = 1
    extra_args = [["-pingtimeout=%d" % PING_TIMEOUT]]

    def run_test(self):
        node = self.nodes[0]

        self.log("connect a peer that answers pings and one that doesn't")
        good = P2PConnection(node.p2p_port, answer_pings=True)
        silent = P2PConnection(node.p2p_port, answer_pings=False)
        wait_until(lambda: good.got_verack and silent.got_verack, what="handshakes")
        wait_until(lambda: node.getconnectioncount() == 2, what="two peers")
        wait_until(lambda: good.pings_received and silent.pings_received, what="initial pings")

        self.log("the silent peer is dropped after the timeout")
        wait_until(lambda: silent.closed, timeout=PING_TIMEOUT + 15, what="silent peer dropped")
        with open(node.debug_log) as f:
            assert "ping timeout" in f.read()

        self.log("the responsive peer stays connected")
        assert not good.closed
        assert_equal(node.getconnectioncount(), 1)
        assert "pingtime" in node.getpeerinfo()[0]
        good.close()
        silent.close()


if __name__ == "__main__":
    PingTimeoutTest().main()
