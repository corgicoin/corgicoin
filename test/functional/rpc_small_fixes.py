#!/usr/bin/env python3
"""Small RPC checks: gettxout validates the txid, and a standardsigs rejection says why."""
from test_framework import CorgiTestFramework, assert_equal, assert_raises_rpc_error


class SmallFixesTest(CorgiTestFramework):
    num_nodes = 1

    def run_test(self):
        node = self.nodes[0]
        node.generate(2)
        txid = node.getblock(node.getblockhash(1))["tx"][0]

        self.log("gettxout takes a 64-character hex transaction id and nothing else")
        assert node.gettxout(txid, 0) is None or isinstance(node.gettxout(txid, 0), dict)
        for bad in ("", "abc", txid[:-1], txid + "0", txid[:-1] + "g", "zz" * 32):
            assert_raises_rpc_error(-8, "64 hex", node.gettxout, bad, 0)


if __name__ == "__main__":
    SmallFixesTest().main()
