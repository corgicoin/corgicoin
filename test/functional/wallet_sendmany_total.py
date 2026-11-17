#!/usr/bin/env python3
"""sendmany with amounts whose total is more than there can be is refused with an amount error.

The running total was added in a signed 64-bit integer with no check, so enough large amounts wrapped it
(undefined behaviour) and the request failed later with a confusing transaction error.
"""
from decimal import Decimal

from test_framework import CorgiTestFramework, assert_raises_rpc_error


class SendManyTotalTest(CorgiTestFramework):
    num_nodes = 1

    def run_test(self):
        node = self.nodes[0]
        node.generate(60)
        addrs = [node.getnewaddress() for _ in range(230)]

        self.log("230 outputs of the largest single amount: the total is far beyond the amount of money there can be")
        assert_raises_rpc_error(-3, None, node.sendmany, "", {a: Decimal(500000000) for a in addrs})

        self.log("an ordinary sendmany still works")
        txid = node.sendmany("", {addrs[0]: Decimal(2), addrs[1]: Decimal(3)})
        assert len(txid) == 64


if __name__ == "__main__":
    SendManyTotalTest().main()
