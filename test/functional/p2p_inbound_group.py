#!/usr/bin/env python3
"""-maxinboundpergroup: one network group may hold only so many inbound slots.

(Peers on this machine are not counted unless the regtest hook -testgrouplocal is given, which is what lets a test see the rule.)
"""
from mininode import P2PConnection
from test_framework import CorgiTestFramework, assert_equal, wait_until


class InboundGroupTest(CorgiTestFramework):
    num_nodes = 2
    extra_args = [["-maxinboundpergroup=2", "-testgrouplocal=1"], []]

    def run_test(self):
        node, free = self.nodes

        self.log("two connections from the group are accepted, the third is dropped, and the first two are left alone")
        first, second = P2PConnection(node.p2p_port), P2PConnection(node.p2p_port)
        wait_until(lambda: first.got_verack and second.got_verack, what="two handshakes")
        third = P2PConnection(node.p2p_port)
        wait_until(lambda: third.closed, what="the third connection to be dropped")
        assert_equal((first.closed, second.closed), (False, False))
        assert_equal(len(node.getpeerinfo()), 2)

        self.log("a place freed in the group can be taken again")
        first.close()
        wait_until(lambda: len(node.getpeerinfo()) == 1, what="the first peer to go")
        fourth = P2PConnection(node.p2p_port)
        wait_until(lambda: fourth.got_verack, what="a new connection to be accepted")

        self.log("without the option there is no limit")
        peers = [P2PConnection(free.p2p_port) for _ in range(5)]
        wait_until(lambda: all(p.got_verack for p in peers), what="five handshakes")
        for p in peers + [second, fourth]:
            p.close()


if __name__ == "__main__":
    InboundGroupTest().main()
