#!/usr/bin/env python3
"""Accounting entries (move) are written to the wallet and read back in order, by account and for all accounts.

No other test covers them. They are the one place the wallet reads records by key order from a chosen starting key (not only all of them from the
first), which is what a wallet storage backend has to support. Each move writes two records, one in each account.
"""
from decimal import Decimal

from test_framework import CorgiTestFramework, assert_equal


class WalletAccountingTest(CorgiTestFramework):
    num_nodes = 1

    def run_test(self):
        node = self.nodes[0]

        self.log("three moves between two accounts")
        node.move("", "savings", 5)
        node.move("", "savings", 7)
        node.move("savings", "ops", 2)

        self.log("each account's balance is what was moved in and out")
        assert_equal(node.getbalance("savings"), Decimal(10))
        assert_equal(node.getbalance("ops"), Decimal(2))

        self.log("an account's entries are its own, in the order they were made")
        entries = node.listtransactions("savings")
        moves = [e for e in entries if e["category"] == "move"]
        assert_equal([e["amount"] for e in moves], [Decimal(5), Decimal(7), Decimal(-2)])
        assert_equal([e["amount"] for e in node.listtransactions("ops") if e["category"] == "move"], [Decimal(2)])

        self.log("'*' lists the entries of every account: two for each move")
        allmoves = [e for e in node.listtransactions("*", 100) if e["category"] == "move"]
        assert_equal(len(allmoves), 6)
        assert_equal(sorted(e["account"] for e in allmoves), ["", "", "ops", "savings", "savings", "savings"])

        self.log("they are still there after a restart")
        node.stop()
        node.start()
        assert_equal(node.getbalance("savings"), Decimal(10))
        assert_equal(len([e for e in node.listtransactions("*", 100) if e["category"] == "move"]), 6)


if __name__ == "__main__":
    WalletAccountingTest().main()
