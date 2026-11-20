#!/usr/bin/env python3
"""A peer that joins after the headers are in, and has no more than our best header, is still used for blocks.

The node learns a peer's tip from the headers the peer sends. A peer level with our best header used to be asked for nothing, so it
never became a source of blocks and sat idle while one other peer did all the work (and could not take over if that one stalled).
Now it is asked once for its tip, and then the blocks are shared.
"""
from mininode import P2PConnection
from p2p_headers_first import header_bytes, varint
from test_framework import CorgiTestFramework, wait_until

HEIGHT = 100        # below the merged-mining fork height of regtest, so a header is 80 bytes with no proof


class HeadersFirstLatePeerTest(CorgiTestFramework):
    num_nodes = 2
    extra_args = [[], ["-headersfirst=1"]]

    def run_test(self):
        a, node = self.nodes
        a.generate(HEIGHT)
        headers = [header_bytes(a, a.getblockhash(i)) for i in range(1, HEIGHT + 1)]

        self.log("a first peer gives all the headers and then holds the blocks back")
        first = P2PConnection(node.p2p_port, start_height=HEIGHT)
        wait_until(lambda: first.counts.get("getheaders", 0) >= 1, what="getheaders to the first peer")
        first.send("headers", varint(HEIGHT) + b"".join(headers))
        wait_until(lambda: first.counts.get("getdata", 0) >= 1, what="getdata to the first peer")

        self.log("a second peer at the same height joins after the headers are in")
        second = P2PConnection(node.p2p_port, start_height=HEIGHT)
        wait_until(lambda: second.counts.get("getheaders", 0) >= 1, what="the node to ask the late peer for its tip")
        assert "for its tip" in open(node.debug_log, errors="replace").read(), "no request for the tip in the log"
        assert second.counts.get("getdata", 0) == 0, "asked for blocks before knowing the peer's tip"

        self.log("it answers with its tip, and the node asks it for the blocks the first peer is not bringing")
        second.send("headers", varint(1) + headers[-1])
        wait_until(lambda: second.counts.get("getdata", 0) >= 1, what="getdata to the late peer")


if __name__ == "__main__":
    HeadersFirstLatePeerTest().main()
