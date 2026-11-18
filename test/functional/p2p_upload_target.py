#!/usr/bin/env python3
"""-maxuploadtarget: a node that has sent what it promised in a day stops sending old blocks and lets the asking peer go.

The target here is 1 MiB. A peer asks for an old block again and again; the node serves it until most of the target is gone,
then, for blocks the node counts as old (older than the tip by a second here, the regtest-only -testhistoricalblockage), it
stops and disconnects the peer, and getnettotals says so. New blocks are still sent. A peer that asks for nothing is left alone.
"""
import time

from test_framework import CorgiTestFramework, assert_equal, wait_until
from mininode import P2PConnection


class UploadTargetTest(CorgiTestFramework):
    num_nodes = 1
    extra_args = [["-maxuploadtarget=1", "-testhistoricalblockage=1"]]

    def run_test(self):
        node = self.nodes[0]
        node.generate(1)
        old = bytes.fromhex(node.getblockhash(1))[::-1]
        time.sleep(3)       # "old" is measured from the tip's time: the blocks on top are more than the (test) second later
        node.generate(5)
        tip = bytes.fromhex(node.getbestblockhash())[::-1]

        self.log("before anything is sent, the target is set and not reached")
        info = node.getnettotals()["uploadtarget"]
        assert_equal(info["target"], 1024 * 1024)
        assert_equal(info["target_reached"], False)
        assert_equal(info["serve_historical_blocks"], True)
        assert info["time_left_in_cycle"] > 0

        quiet = P2PConnection(node.p2p_port)
        asker = P2PConnection(node.p2p_port)
        wait_until(lambda: quiet.got_verack and asker.got_verack, timeout=20, what="the handshakes")

        self.log("a peer asks for the same old block again and again: it is served until the target is nearly spent")
        for _ in range(40):
            try:
                asker.send_inv([(2, old)] * 5000, command="getdata")
            except OSError:         # the node let go of it mid-send: that is what is being asked for
                break
            if asker.closed:
                break
        wait_until(lambda: asker.closed, timeout=60, what="the node to let go of a peer asking for old blocks after the target")

        info = node.getnettotals()["uploadtarget"]
        assert_equal(info["serve_historical_blocks"], False)         # nine tenths are gone
        assert info["bytes_left_in_cycle"] < 1024 * 1024 // 5, info
        assert_equal(quiet.closed, False)                           # the peer that asked for nothing was left alone

        self.log("with the target spent, the newest block is still sent: a miner's own block must reach the network")
        late = P2PConnection(node.p2p_port)
        wait_until(lambda: late.got_verack, timeout=20, what="the handshake")
        late.send_inv([(2, tip)], command="getdata")
        wait_until(lambda: late.counts.get("block", 0) >= 1, timeout=20, what="the tip block")
        assert_equal(late.closed, False)

        self.log("a node with no target says it has none")
        node.stop()
        node.start(["-maxuploadtarget=0"])
        info = node.getnettotals()["uploadtarget"]
        assert_equal((info["target"], info["target_reached"], info["serve_historical_blocks"]), (0, False, True))
        quiet.close()
        asker.close()


if __name__ == "__main__":
    UploadTargetTest().main()
