#!/usr/bin/env python3
"""A peer's user agent can be anything it likes; it must not break getpeerinfo.

The user agent in a peer's version message is untrusted bytes. A byte that is not valid UTF-8 used to make every
getpeerinfo call fail for as long as that peer stayed connected (the JSON writer threw), which blinds monitoring
and pool health checks, and a very long one or one with a newline in it reached the log as it was. The node now
keeps printable ASCII only, capped at 256 bytes, and the JSON writer replaces anything invalid instead of throwing.
"""
from mininode import P2PConnection
from test_framework import CorgiTestFramework, assert_equal, wait_until


class BadSubverTest(CorgiTestFramework):
    num_nodes = 1

    def run_test(self):
        node = self.nodes[0]
        cases = {
            "invalid UTF-8 and a newline": (b"/bad\xff\xfe\n/ok:1/", "/bad/ok:1/"),
            "control characters": (b"/tab\there\x00nul\x1b[31m/", "/tabherenul[31m/"),
            "300 bytes": (b"/" + b"a" * 298 + b"/", ("/" + "a" * 255)),
            "a normal user agent": (b"/Satoshi:0.8.6/", "/Satoshi:0.8.6/"),
        }
        peers = []
        for label, (raw, expected) in cases.items():
            self.log("peer with " + label)
            p = P2PConnection(node.p2p_port, subver=raw)
            peers.append(p)
            wait_until(lambda: p.got_verack, what="verack")
            wait_until(lambda: len(node.getpeerinfo()) == len(peers), what="the peer in getpeerinfo")
            info = node.getpeerinfo()      # must not throw
            assert any(i["subver"] == expected for i in info), (expected, [i["subver"] for i in info])
        self.log("all four peers listed together")
        assert_equal(len(node.getpeerinfo()), len(cases))
        for p in peers:
            p.close()


if __name__ == "__main__":
    BadSubverTest().main()
