#!/usr/bin/env python3
"""Headers-first is only for peers that speak 70014. An older node is never sent a getheaders.

Every release before this one crashes on a getheaders whose range holds a merged-mined block (the chain has had them since block 50000),
so a node that asked its peers for headers would crash every old node it met. Peers older than 70014 are synced the way they always were,
with getblocks; peers at 70014 or more are asked for headers.
"""
from mininode import P2PConnection
from test_framework import CorgiTestFramework, wait_until


class HeadersFirstOldPeerTest(CorgiTestFramework):
    num_nodes = 1

    def run_test(self):
        node = self.nodes[0]

        self.log("a peer at 70001 that has more blocks than we do: asked for blocks, never for headers")
        old = P2PConnection(node.p2p_port, start_height=50, protocol_version=70001)
        wait_until(lambda: old.got_verack, what="verack from the old peer")
        wait_until(lambda: old.counts.get("getblocks", 0) >= 1, what="getblocks to the old peer")
        assert old.counts.get("getheaders", 0) == 0, "an old peer was sent getheaders"

        self.log("a peer at 70013 (feefilter, but not the getheaders fix) is treated as old too")
        mid = P2PConnection(node.p2p_port, start_height=50, protocol_version=70013)
        wait_until(lambda: mid.got_verack, what="verack from the 70013 peer")
        wait_until(lambda: mid.counts.get("getblocks", 0) >= 1 or old.counts.get("getblocks", 0) >= 2, what="a getblocks")
        assert mid.counts.get("getheaders", 0) == 0, "a 70013 peer was sent getheaders"

        self.log("a peer at 70014: asked for headers")
        new = P2PConnection(node.p2p_port, start_height=50)
        wait_until(lambda: new.got_verack, what="verack from the new peer")
        wait_until(lambda: new.counts.get("getheaders", 0) >= 1, what="getheaders to the new peer")
        assert old.counts.get("getheaders", 0) == 0 and mid.counts.get("getheaders", 0) == 0


if __name__ == "__main__":
    HeadersFirstOldPeerTest().main()
