#!/usr/bin/env python3
"""-maxtxfee: the wallet refuses to make a transaction that pays more fee than the limit.

A fee computed from a huge transaction, or a -paytxfee set a decimal place wrong, could otherwise be paid
without a word. The limit is on the fee the wallet would add, not on the amount sent.
"""
from test_framework import CorgiTestFramework, assert_equal, assert_raises_rpc_error


class MaxTxFeeTest(CorgiTestFramework):
    num_nodes = 1

    def run_test(self):
        node = self.nodes[0]
        node.generate(110)
        addr = node.getnewaddress()

        self.log("with the default limit an ordinary send works")
        node.sendtoaddress(addr, 1)
        node.generate(1)

        self.log("a limit under the lowest fee refuses it, and says why")
        node.stop()
        node.start(["-maxtxfee=0.00000001"])
        try:
            node.sendtoaddress(addr, 1)
        except Exception as e:
            assert "maxtxfee" in str(e), str(e)
        else:
            raise AssertionError("a transaction was made with a fee over -maxtxfee")
        assert_equal(node.getmempoolinfo()["size"], 0)

        self.log("and without the limit again it works")
        node.stop()
        node.start()
        node.sendtoaddress(addr, 1)


if __name__ == "__main__":
    MaxTxFeeTest().main()
