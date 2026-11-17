#!/usr/bin/env python3
"""A node that is stopped while it is busy exits with status 0, every time.

The daemon used to end its shutdown with exit() from the shutdown thread, which ran the destructors of the global objects while the other
threads (RPC, network, message handling) could still be using them: a double free on Linux, "mutex lock failed" on macOS, an abort (status -6)
that no test noticed because none of them looked at how the node ended. Here two nodes that are connected, with the wallet and the mempool in use and
a peer to talk to, are stopped over and over, and each has to exit cleanly.
"""
from test_framework import CorgiTestFramework, assert_equal

ROUNDS = 12


class ShutdownExitTest(CorgiTestFramework):
    num_nodes = 2

    def run_test(self):
        a, b = self.nodes

        for i in range(ROUNDS):
            self.log("round %d: connect, give both something to do, stop both" % (i + 1))
            self.connect_nodes(0, 1)
            if i == 0:
                a.generate(101)
                self.sync_blocks()
            addr = b.getnewaddress()
            a.sendtoaddress(addr, 1)
            a.getpeerinfo()
            b.getrawmempool()
            # stop both at once, so that each has a peer going away while it shuts down
            for n in (a, b):
                try:
                    n.rpc.stop()
                except Exception:
                    pass
            for n in (a, b):
                n.process.wait(timeout=60)
                assert_equal(n.process.returncode, 0, "node%d ended with status %s (round %d)" % (n.index, n.process.returncode, i + 1))
            for n in (a, b):
                n.start()
            if i % 3 == 2:
                self.sync_blocks()


if __name__ == "__main__":
    ShutdownExitTest().main()
