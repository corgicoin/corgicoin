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

        self.log("a wallet error that does not throw (asking to downgrade the wallet): stop before the network and RPC start")
        # This takes the path the change is about: master noted the error and went on to "Done loading" and the RPC server
        # before acting on it. (The damaged block index below makes the database throw, which master caught too.)
        self.assert_stops(node, ["-upgradewallet=1000"], "Cannot downgrade wallet")

        index = os.path.join(node.datadir, "regtest", "blkindex.dat")
        assert os.path.exists(index), index
        with open(index, "wb") as f:
            f.write(os.urandom(200000))

        self.log("start on a damaged blkindex.dat: the node must exit without having said it is done loading")
        self.assert_stops(node, [], None)

    def assert_stops(self, node, args, expect):
        try:
            node.start(args)
        except AssertionFailed as e:
            assert "exited during startup" in str(e), str(e)
        else:
            raise AssertionFailed("the node kept running with %r" % args)
        log = open(node.debug_log, errors="replace").read()
        tail = log[log.rfind("CorgiCoin version"):]
        if expect:   # InitError writes to stderr, which the framework keeps
            with open(node.stderr_log, errors="replace") as f:
                assert expect in f.read(), "%r not in the node's stderr" % expect
        assert "Done loading" not in tail, "init went on to the end"
        assert "ThreadRPCServer started" not in tail, "the RPC server was started"


if __name__ == "__main__":
    InitErrorTest().main()
