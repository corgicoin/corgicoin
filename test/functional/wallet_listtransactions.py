#!/usr/bin/env python3
"""listtransactions: paging, and counts and offsets as large as an int allows (their sum used to overflow)."""
from test_framework import CorgiTestFramework, assert_equal, assert_raises_rpc_error

INT_MAX = 2147483647


class ListTransactionsTest(CorgiTestFramework):
    num_nodes = 1

    def run_test(self):
        node = self.nodes[0]
        node.generate(5)
        total = len(node.listtransactions("*", 1000))
        assert total >= 5

        self.log("paging: count and from select a window, oldest to newest")
        allrows = node.listtransactions("*", 1000)
        assert_equal(node.listtransactions("*", 2), allrows[-2:])
        assert_equal(node.listtransactions("*", 2, 1), allrows[-3:-1])
        assert_equal(node.listtransactions("*", 1000, total), [])

        self.log("a count as large as an int returns everything, and the node stays up")
        assert_equal(node.listtransactions("*", INT_MAX), allrows)
        assert_equal(node.listtransactions("*", INT_MAX, 1), allrows[:-1])
        node.getblockcount()

        self.log("an offset as large as an int returns nothing, and the node stays up")
        assert_equal(node.listtransactions("*", 1, INT_MAX), [])
        assert_equal(node.listtransactions("*", INT_MAX, INT_MAX), [])
        node.getblockcount()

        self.log("negative values are still refused")
        assert_raises_rpc_error(-8, None, node.listtransactions, "*", -1)
        assert_raises_rpc_error(-8, None, node.listtransactions, "*", 1, -1)


if __name__ == "__main__":
    ListTransactionsTest().main()
