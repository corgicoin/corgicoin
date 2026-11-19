#!/usr/bin/env python3
"""sendrawtransaction says why a transaction was refused, not only that it was.

It used to answer "TX rejected" for every reason. The reason the pool gave (the one testmempoolaccept reports as
reject-reason) is now in the message, with "(missing inputs)" when the inputs were not found.
"""
from test_framework import CorgiTestFramework, JSONRPCException, assert_equal


class SendRawTransactionReasonTest(CorgiTestFramework):
    num_nodes = 1

    def run_test(self):
        node = self.nodes[0]
        node.generate(51)

        self.log("a transaction whose input does not exist: refused, with the reason")
        bogus = node.createrawtransaction([{"txid": "11" * 32, "vout": 0}], {node.getnewaddress(): 1})
        try:
            node.sendrawtransaction(bogus)
            raise AssertionError("the transaction was accepted")
        except JSONRPCException as e:
            assert "TX rejected" in str(e), str(e)
            assert "missing inputs" in str(e), "the message does not say why: %s" % e

        self.log("a good transaction is still accepted")
        coin = node.listunspent()[0]
        good = node.signrawtransaction(node.createrawtransaction([{"txid": coin["txid"], "vout": coin["vout"]}],
                                                                 {node.getnewaddress(): coin["amount"] - 1}))["hex"]
        assert_equal(len(node.sendrawtransaction(good)), 64)


if __name__ == "__main__":
    SendRawTransactionReasonTest().main()
