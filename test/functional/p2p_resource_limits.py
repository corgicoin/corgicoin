#!/usr/bin/env python3
"""What a peer can make a node remember or queue is bounded.

- inv: every item a peer announced and never delivered stayed in mapAlreadyAskedFor for ever (50000 per message,
  no penalty). It holds at most 50000 now (getmemoryinfo.askedfor).
- addr: a peer's list of known addresses took 100 bytes per distinct address with no limit and no penalty at
  exactly 1000 per message. It holds at most 5000 per peer (getpeerinfo.addr_known).
- getdata: one message of 50000 items was answered to the end at once, every reply queued in memory under cs_main.
  It is now answered as the send buffer drains, in order, and all of it is delivered.
"""
import os
import random
import struct

from mininode import P2PConnection
from test_framework import CorgiTestFramework, assert_equal, wait_until


class ResourceLimitsTest(CorgiTestFramework):
    num_nodes = 1

    def run_test(self):
        node = self.nodes[0]
        node.generate(3)
        peer = P2PConnection(node.p2p_port)
        wait_until(lambda: peer.got_verack, what="verack")
        assert_equal(node.getmemoryinfo()["askedfor"], 0)

        self.log("500000 announced transactions that never arrive: the node remembers at most 50000")
        # One message at a time: each is 1.8 MB, and ten sent back to back pass the node's 5 MB receive buffer before it has
        # processed the first, which disconnects the peer (flood control, as it should) on a slow machine or under the
        # sanitizers. A ping after each, answered in order, says when the node has got through it.
        for i in range(10):
            peer.send_inv([(1, os.urandom(32)) for _ in range(50000)])
            peer.send("ping", struct.pack("<Q", i))
            wait_until(lambda: peer.counts.get("pong", 0) >= i + 1, timeout=120, what="the node to process announcement %d" % (i + 1))
        wait_until(lambda: node.getmemoryinfo()["askedfor"] >= 50000 or node.getpeerinfo()[0]["banscore"] > 0,
                   timeout=60, what="the node to take in the announcements")
        # let it finish the backlog
        wait_until(lambda: node.getmemoryinfo()["askedfor"] == 50000, timeout=60, what="askedfor to settle at its cap")
        assert node.getmemoryinfo()["askedfor"] <= 50000

        self.log("20 addr messages of 1000 addresses each: the peer's known-address list stays bounded")
        import time
        for i in range(20):
            peer.send_addrs([("10.%d.%d.%d" % (i % 250 + 1, j // 250, j % 250 + 1), 62556) for j in range(1000)])
            time.sleep(0.05)  # 20000 addresses, 1 MB: four times the cap of 5000. (100 messages, 5 MB, reached the node's receive flood limit when the machine was busy)
        wait_until(lambda: node.getpeerinfo()[0]["addr_known"] > 0, what="addresses to be taken in")
        wait_until(lambda: peer.counts.get("addr", 0) >= 0, what="settling")
        import time
        time.sleep(3)
        assert node.getpeerinfo()[0]["addr_known"] <= 5000, node.getpeerinfo()[0]["addr_known"]

        self.log("one getdata for the same block 50000 times is answered in full, a send buffer at a time")
        block = bytes.fromhex(node.getbestblockhash())[::-1]
        before = peer.counts.get("block", 0)
        peer.send_inv([(2, block)] * 50000, command="getdata")
        wait_until(lambda: peer.counts.get("block", 0) - before >= 50000, timeout=120, what="all 50000 blocks to arrive")
        assert_equal(node.getpeerinfo()[0]["getdata_queued"], 0)
        node.getblockcount()
        peer.close()


if __name__ == "__main__":
    ResourceLimitsTest().main()
