#!/usr/bin/env python3
"""getnetworkhashps / getmininginfo on a chain with no usable time span, and getnetworkinfo.relayfee.

At height 0, or when blocks share a timestamp (regtest generates many within a second), the estimate divided by
zero and converted infinity or NaN to an integer, which is undefined. It must be a plain 0. relayfee used to be
the minimum input value, not the relay fee that getmempoolinfo reports.
"""
from test_framework import CorgiTestFramework, assert_equal


class MiningInfoTest(CorgiTestFramework):
    num_nodes = 1

    def run_test(self):
        node = self.nodes[0]

        self.log("a chain of just the genesis block")
        assert_equal(node.getblockcount(), 0)
        assert_equal(node.getnetworkhashps(), 0)
        assert_equal(node.getnetworkhashps(-1), 0)
        assert_equal(node.getmininginfo()["networkhashps"], 0)

        self.log("blocks mined within the same second")
        node.generate(5)
        for blocks in (1, 5, 120, -1):
            hps = node.getnetworkhashps(blocks)
            assert isinstance(hps, int) and hps >= 0, (blocks, hps)
        assert node.getmininginfo()["networkhashps"] >= 0

        self.log("relayfee is the relay fee")
        assert_equal(node.getnetworkinfo()["relayfee"], node.getmempoolinfo()["minrelaytxfee"])


if __name__ == "__main__":
    MiningInfoTest().main()
