#!/usr/bin/env python3
"""A node whose block index will not load must stop, not carry on and start its network and RPC server.

Before, the error was only noted and acted on after the wallet, the peers, the node threads and the RPC server had all been
started ("Done loading" was logged first), so a broken data directory ran with an empty chain until the very end of init.
"""
import os

from test_framework import CorgiTestFramework, AssertionFailed


class InitErrorTest(CorgiTestFramework):
    num_nodes = 1

    def run_test(self):
        node = self.nodes[0]
        node.generate(5)
        node.stop()

        index = os.path.join(node.datadir, "regtest", "blkindex.dat")
        assert os.path.exists(index), index
        with open(index, "wb") as f:
            f.write(os.urandom(200000))

        self.log("start on a damaged blkindex.dat: the node must exit without having said it is done loading")
        try:
            node.start()
        except AssertionFailed as e:
            assert "exited during startup" in str(e), str(e)
        else:
            raise AssertionFailed("a node with a damaged block index kept running")
        log = open(node.debug_log, errors="replace").read()
        tail = log[log.rfind("CorgiCoin version"):]
        assert "Done loading" not in tail, "init went on to the end with a damaged block index"
        assert "ThreadRPCServer started" not in tail, "the RPC server was started"


if __name__ == "__main__":
    InitErrorTest().main()
