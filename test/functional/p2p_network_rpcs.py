#!/usr/bin/env python3
"""Network RPCs: ping latency, traffic counters, bans, addnode, disconnectnode."""
import time

from test_framework import (CorgiTestFramework, assert_equal, assert_greater_than,
                            assert_raises_rpc_error, wait_until)


class P2PNetworkRPCTest(CorgiTestFramework):
    """Covers the RPCs added in v4.6 (PR #60)."""
    num_nodes = 2

    def run_test(self):
        n0, n1 = self.nodes
        self.connect_nodes(0, 1)

        self.log("ping round-trip is measured")
        n0.ping()
        wait_until(lambda: "pingtime" in n0.getpeerinfo()[0], what="pingtime on node0")
        peer = n0.getpeerinfo()[0]
        assert_greater_than(peer["pingtime"], 0)
        assert peer["minping"] <= peer["pingtime"]
        assert_greater_than(peer["bytessent"], 0)
        assert_greater_than(peer["bytesrecv"], 0)

        self.log("getnettotals covers per-peer traffic")
        totals = n0.getnettotals()
        assert totals["totalbytessent"] >= peer["bytessent"]
        assert totals["totalbytesrecv"] >= peer["bytesrecv"]
        assert abs(totals["timemillis"] / 1000 - time.time()) < 60

        self.log("addnode list management")
        assert_equal(n0.getaddednodeinfo(), [])
        n0.addnode(n1.p2p_addr, "add")
        assert_raises_rpc_error(-23, None, n0.addnode, n1.p2p_addr, "add")
        [info] = n0.getaddednodeinfo(n1.p2p_addr)
        assert_equal(info["connected"], True)
        assert_raises_rpc_error(-24, None, n0.getaddednodeinfo, "10.0.0.1:1")

        self.log("added node is re-dialed after a disconnect")
        # Don't poll for the node being briefly "not connected": `addnode add` wakes the
        # added-node thread, and if its pass lands just after the disconnect it re-dials
        # within milliseconds, so the dropped state can be missed entirely (flaky). Node1
        # sees node0 as an inbound peer on an ephemeral port, so a re-dial shows up as
        # an inbound peer on a different port, whichever way that race goes.
        old_inbound = [p["addr"] for p in n1.getpeerinfo() if p["inbound"]]
        assert_equal(len(old_inbound), 1)
        n0.disconnectnode(n1.p2p_addr)
        wait_until(lambda: [p["addr"] for p in n1.getpeerinfo() if p["inbound"]]
                   not in ([], old_inbound) and n0.getaddednodeinfo(n1.p2p_addr)[0]["connected"],
                   timeout=150, what="added-node thread to reconnect on a new connection")
        n0.addnode(n1.p2p_addr, "remove")
        assert_raises_rpc_error(-24, None, n0.addnode, n1.p2p_addr, "remove")
        assert_raises_rpc_error(-29, None, n0.disconnectnode, "10.0.0.1:1")

        self.log("getnodeaddresses lists the address manager, not just live peers")
        assert_raises_rpc_error(-8, None, n0.getnodeaddresses, -1)
        known = n0.getnodeaddresses(0)
        for entry in known:
            assert_equal(sorted(entry), ["address", "port", "services", "time"])
        assert_equal(len(n0.getnodeaddresses(1)), min(1, len(known)))
        assert len(n0.getnodeaddresses()) <= 1

        self.log("setban drops the peer and blocks it")
        n1.setban("127.0.0.1", "add", 600)
        wait_until(lambda: n1.getconnectioncount() == 0, what="ban to disconnect")
        [ban] = n1.listbanned()
        assert_equal(ban["address"], "127.0.0.1")
        assert 590 <= ban["banned_until"] - time.time() <= 610
        assert_raises_rpc_error(-23, None, n1.setban, "127.0.0.1", "add")
        assert_raises_rpc_error(-30, None, n1.setban, "not-an-ip", "add")

        self.log("absolute bans and unban")
        n1.setban("127.0.0.1", "remove")
        assert_raises_rpc_error(-1, None, n1.setban, "127.0.0.1", "remove")
        until = int(time.time()) + 3600
        n1.setban("10.1.2.3", "add", until, True)
        assert_equal(n1.listbanned(), [{"address": "10.1.2.3", "banned_until": until}])
        assert_raises_rpc_error(-8, None, n1.setban, "10.9.9.9", "add", 1000, True)
        self.log("bans survive a restart (banlist.dat)")
        n1.stop()
        n1.start()
        assert_equal(n1.listbanned(), [{"address": "10.1.2.3", "banned_until": until}])

        self.log("clearbanned is persisted too")
        n1.clearbanned()
        assert_equal(n1.listbanned(), [])
        n1.stop()
        n1.start()
        assert_equal(n1.listbanned(), [])

        self.log("peers can reconnect after unban")
        self.connect_nodes(0, 1)


if __name__ == "__main__":
    P2PNetworkRPCTest().main()
