#!/usr/bin/env python3
"""createauxblock hands the same work out again while nothing it was built from has changed.

Every call built a whole block (walking the memory pool under cs_main and cs_wallet) and kept it until the tip moved, so a
pool refreshing its jobs every few seconds on several parent pools made memory grow without bound on a stalled chain. The
work is now reused for the same payout script while the tip and the memory pool are as they were (and for at most a minute).
"""
from decimal import Decimal

from test_framework import CorgiTestFramework, assert_equal


class AuxBlockCacheTest(CorgiTestFramework):
    num_nodes = 1

    def run_test(self):
        node = self.nodes[0]
        node.generate(260)                      # past the AuxPoW fork (block 200 on regtest) and coinbase maturity
        addr = node.getnewaddress()
        other = node.getnewaddress()

        self.log("the same payout script gets the same work back while nothing changes")
        first = node.createauxblock(addr)
        for _ in range(20):
            assert_equal(node.createauxblock(addr)["hash"], first["hash"])

        self.log("another payout script gets its own work")
        assert node.createauxblock(other)["hash"] != first["hash"]
        assert_equal(node.createauxblock(addr)["hash"], first["hash"])

        self.log("a change in the memory pool makes new work")
        node.sendtoaddress(other, Decimal(5))
        changed = node.createauxblock(addr)
        assert changed["hash"] != first["hash"]
        assert_equal(node.createauxblock(addr)["hash"], changed["hash"])

        self.log("a new block makes new work, and the old work is gone")
        node.generate(1)
        assert node.createauxblock(addr)["hash"] not in (first["hash"], changed["hash"])


if __name__ == "__main__":
    AuxBlockCacheTest().main()
