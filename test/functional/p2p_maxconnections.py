#!/usr/bin/env python3
"""-maxconnections is capped at what select() can hold.

select() waits on descriptor numbers below FD_SETSIZE (1024). A node started with -maxconnections=2000 (pool operators
do) could get a socket numbered above that, and FD_SET on it writes outside the fd_set on the stack. The number of peers
is capped, a socket past the limit is refused, and the log says so.
"""
from test_framework import CorgiTestFramework


class MaxConnectionsTest(CorgiTestFramework):
    num_nodes = 1
    extra_args = [["-maxconnections=2000"]]

    def run_test(self):
        node = self.nodes[0]
        node.getblockcount()
        with open(node.debug_log, errors="replace") as f:
            log = f.read()
        assert "-maxconnections reduced from 2000 to " in log, "the node did not reduce -maxconnections=2000"


if __name__ == "__main__":
    MaxConnectionsTest().main()
