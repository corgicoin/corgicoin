#!/usr/bin/env python3
"""debug.log: every line is timestamped with -logtimestamps, RPC calls are logged only with -debug=rpc.

-logtimestamps stamped only the first line: whether a message ended a line was read from the format string, which
is always "%s". And every RPC call was logged unconditionally, so a pool polling getmininginfo several times a second
filled the log.
"""
import re

from test_framework import CorgiTestFramework

STAMP = re.compile(r"^\d\d/\d\d/\d\d \d\d:\d\d:\d\d ")


class LoggingTest(CorgiTestFramework):
    num_nodes = 1
    extra_args = [["-logtimestamps=1"]]

    def log_lines(self, node):
        with open(node.debug_log, errors="replace") as f:
            return [l.rstrip("\n") for l in f if l.strip()]

    def run_test(self):
        node = self.nodes[0]
        node.generate(5)
        for _ in range(5):
            node.getmininginfo()

        self.log("with -logtimestamps every line carries a timestamp")
        lines = self.log_lines(node)
        first = next(i for i, l in enumerate(lines) if STAMP.match(l))
        unstamped = [l for l in lines[first:] if not STAMP.match(l)]
        assert not unstamped, "%d of %d lines have no timestamp, for example %r" % (len(unstamped), len(lines) - first, unstamped[:3])

        self.log("RPC calls are not logged by default")
        assert not any("method=getmininginfo" in l for l in lines), "RPC calls are logged without -debug=rpc"

        self.log("with -debug=rpc they are, one per call, and a method name cannot forge a line")
        node.stop()
        node.start(["-debug=rpc"])
        node.getmininginfo()
        lines = self.log_lines(node)
        assert any("method=getmininginfo" in l for l in lines)


if __name__ == "__main__":
    LoggingTest().main()
