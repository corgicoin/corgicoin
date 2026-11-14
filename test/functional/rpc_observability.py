#!/usr/bin/env python3
"""getrpcinfo and logging: look at the RPC server, and turn debug log categories on and off without a restart."""
import time

from test_framework import CorgiTestFramework, assert_equal, assert_raises_rpc_error


class ObservabilityTest(CorgiTestFramework):
    num_nodes = 1

    def run_test(self):
        node = self.nodes[0]

        self.log("getrpcinfo lists the call that is asking, and where the log is")
        info = node.getrpcinfo()
        assert_equal([c["method"] for c in info["active_commands"]], ["getrpcinfo"])
        assert info["active_commands"][0]["duration"] >= 0
        assert info["logpath"].endswith("debug.log"), info["logpath"]

        self.log("logging with no arguments says what is on: nothing, by default")
        state = node.logging()
        for name in ("net", "mempool", "rpc", "db", "wallet", "mining", "addrman", "selectcoins"):
            assert_equal(state[name], False)

        self.log("a category can be switched on, and it takes effect at once (the net category logs the inventory it gets)")
        state = node.logging(["mempool"])
        assert_equal(state["mempool"], True)
        assert_equal(node.logging()["mempool"], True)
        assert_equal(node.logging()["net"], False)

        self.log("and off again, with the exclude list")
        state = node.logging([], ["mempool"])
        assert_equal(state["mempool"], False)
        state = node.logging(["net", "wallet"], [])
        assert_equal((state["net"], state["wallet"]), (True, True))
        state = node.logging([], ["net", "wallet"])
        assert_equal((state["net"], state["wallet"]), (False, False))

        self.log("an unknown category and a bad argument are errors")
        assert_raises_rpc_error(-8, "unknown", node.logging, ["nonsense"])
        assert_raises_rpc_error(-8, "arrays", node.logging, "net")


if __name__ == "__main__":
    ObservabilityTest().main()
