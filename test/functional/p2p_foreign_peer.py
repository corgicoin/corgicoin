#!/usr/bin/env python3
"""A peer that says it is a Dogecoin node is disconnected; an ordinary peer stays.

Dogecoin uses the same magic bytes as this chain, so its nodes can connect, take an inbound slot, and never agree on a block.
"""
from test_framework import CorgiTestFramework, wait_until
from mininode import P2PConnection


class ForeignPeerTest(CorgiTestFramework):
    num_nodes = 1

    def run_test(self):
        node = self.nodes[0]

        self.log("a peer whose user agent is Dogecoin Core's is dropped")
        doge = P2PConnection(node.p2p_port, subver=b"/Shibetoshi:1.14.6/")
        wait_until(lambda: doge.closed, timeout=20, what="the Dogecoin peer to be disconnected")

        self.log("an ordinary peer is kept, and only it is listed")
        peer = P2PConnection(node.p2p_port, subver=b"/corgi-mininode:0.1/")
        wait_until(lambda: peer.got_verack, timeout=20, what="the ordinary peer to complete the handshake")
        assert not peer.closed
        wait_until(lambda: len(node.getpeerinfo()) == 1, timeout=20, what="one peer in getpeerinfo")
        peer.close()


if __name__ == "__main__":
    ForeignPeerTest().main()
