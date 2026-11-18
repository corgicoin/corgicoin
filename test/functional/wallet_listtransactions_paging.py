#!/usr/bin/env python3
"""listtransactions [account] [count] [from]: the last `count` entries after skipping the `from` most recent, oldest first.

Errors for a negative count or from; a count of 0 gives nothing; asking for more than there are gives what there is.
"""
from test_framework import CorgiTestFramework, assert_equal, assert_raises_rpc_error


class ListTransactionsPagingTest(CorgiTestFramework):
    num_nodes = 1

    def key(self, tx):
        return (tx["txid"], tx["category"], tx.get("vout"))

    def run_test(self):
        node = self.nodes[0]
        node.generate(101)
        addr = node.getnewaddress()
        for _ in range(8):
            node.sendtoaddress(addr, 1)
        node.generate(1)

        everything = [self.key(t) for t in node.listtransactions("*", 10000)]
        assert len(everything) >= 20, len(everything)

        self.log("the last `count` entries, oldest first")
        assert_equal([self.key(t) for t in node.listtransactions("*", 5)], everything[-5:])
        assert_equal([self.key(t) for t in node.listtransactions("*", 1)], everything[-1:])

        self.log("`from` skips that many of the most recent")
        assert_equal([self.key(t) for t in node.listtransactions("*", 5, 3)], everything[-8:-3])
        assert_equal([self.key(t) for t in node.listtransactions("*", 4, 0)], everything[-4:])

        self.log("paging through all of it in pages of 7 gives every entry once")
        seen = []
        for page in range(0, len(everything), 7):
            seen = [self.key(t) for t in node.listtransactions("*", 7, page)] + seen
        assert_equal(seen, everything)

        self.log("more than there is gives what there is; 0 gives nothing; a skip past the end gives nothing")
        assert_equal(len(node.listtransactions("*", len(everything) + 50)), len(everything))
        assert_equal(node.listtransactions("*", 0), [])
        assert_equal(node.listtransactions("*", 5, len(everything) + 10), [])

        self.log("negative arguments are errors")
        assert_raises_rpc_error(-8, "Negative count", node.listtransactions, "*", -1)
        assert_raises_rpc_error(-8, "Negative from", node.listtransactions, "*", 3, -1)


if __name__ == "__main__":
    ListTransactionsPagingTest().main()
