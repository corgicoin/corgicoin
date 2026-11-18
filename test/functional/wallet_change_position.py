#!/usr/bin/env python3
"""The change output lands in every position, including the last."""
from decimal import Decimal

from test_framework import CorgiTestFramework


class ChangePositionTest(CorgiTestFramework):
    num_nodes = 2

    def run_test(self):
        n0, n1 = self.nodes
        self.connect_nodes(0, 1)
        n0.generate(60)
        self.sync_blocks()
        dest = n1.getnewaddress()

        self.log("single recipient: change at index 0 and at index 1 both occur")
        seen = set()
        for _ in range(40):
            txid = n0.sendtoaddress(dest, Decimal(5))
            tx = n0.getrawtransaction(txid, 1)
            assert len(tx["vout"]) == 2, tx
            for i, out in enumerate(tx["vout"]):
                if out["scriptPubKey"]["addresses"][0] != dest:
                    seen.add(i)
            if seen == {0, 1}:
                break
        assert seen == {0, 1}, "change was only ever at index %s in 40 sends" % sorted(seen)

        self.log("two recipients: the change can be first, middle or last")
        dest2 = n1.getnewaddress()
        seen = set()
        for _ in range(60):
            txid = n0.sendmany("", {dest: Decimal(3), dest2: Decimal(4)})
            tx = n0.getrawtransaction(txid, 1)
            assert len(tx["vout"]) == 3, tx
            for i, out in enumerate(tx["vout"]):
                if out["scriptPubKey"]["addresses"][0] not in (dest, dest2):
                    seen.add(i)
            if seen == {0, 1, 2}:
                break
        assert seen == {0, 1, 2}, "change was only ever at index %s in 60 sends" % sorted(seen)


if __name__ == "__main__":
    ChangePositionTest().main()
