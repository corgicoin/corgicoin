#!/usr/bin/env python3
"""-minimumchainwork: a chain with less work than the floor is never taken for a finished sync.

With a floor above the chain's work the node reports initialblockdownload (and so does not serve templates on a real network
or count itself synced), however recent its blocks are; with the floor at or below the chain's work, or none, it does not.
"""
from test_framework import CorgiTestFramework, assert_equal


class MinimumChainWorkTest(CorgiTestFramework):
    num_nodes = 1

    def run_test(self):
        node = self.nodes[0]
        node.generate(20)
        info = node.getblockchaininfo()
        assert_equal(info["initialblockdownload"], False)
        assert_equal(int(info["minimumchainwork"], 16), 0)
        work = int(info["chainwork"], 16)
        assert work > 0

        self.log("a floor above this chain's work: the node counts itself as still catching up")
        node.stop()
        node.start(["-minimumchainwork=%x" % (work + 1)])
        info = node.getblockchaininfo()
        assert_equal(info["initialblockdownload"], True)
        assert_equal(int(info["minimumchainwork"], 16), work + 1)

        self.log("more work on the chain lifts it")
        node.generate(5)
        assert_equal(node.getblockchaininfo()["initialblockdownload"], False)

        self.log("a floor at the chain's work is met")
        floor = int(node.getblockchaininfo()["chainwork"], 16)
        node.stop()
        node.start(["-minimumchainwork=%x" % floor])
        assert_equal(node.getblockchaininfo()["initialblockdownload"], False)

        self.log("a floor that is not hex stops the node starting")
        node.stop()
        try:
            node.start(["-minimumchainwork=zz"])
        except Exception as e:
            assert "exited during startup" in str(e), str(e)
        else:
            raise AssertionError("a bad -minimumchainwork was accepted")
        node.start()


if __name__ == "__main__":
    MinimumChainWorkTest().main()
