#!/usr/bin/env python3
"""A wallet transaction that a different transaction in the chain conflicts with is not counted as confirmed.

Node 0 sends T1. A conflicting T2 (the same coin, paid elsewhere, signed with the same wallet) is mined on node 1's longer
chain, and node 0 takes that chain. T1 can never confirm now. Its payment to the wallet used to stay in the balance (a
transaction from the wallet whose inputs are confirmed counts as confirmed) and be picked for later sends, which then
failed; gettransaction now names the conflict, and neither the balance nor coin selection counts T1.
"""
from decimal import Decimal

from test_framework import CorgiTestFramework, assert_equal


class WalletConflictsTest(CorgiTestFramework):
    num_nodes = 2

    def run_test(self):
        n0, n1 = self.nodes
        n0.generate(51)
        self.connect_nodes(1, 0)
        self.sync_blocks()
        self.disconnect_nodes(1, 0)

        coin = n0.listunspent()[0]
        inputs = [{"txid": coin["txid"], "vout": coin["vout"]}]
        t1_hex = n0.signrawtransaction(n0.createrawtransaction(inputs, {n0.getnewaddress(): coin["amount"] - 1}))["hex"]
        t2_hex = n0.signrawtransaction(n0.createrawtransaction(inputs, {n1.getnewaddress(): coin["amount"] - 5}))["hex"]

        self.log("T1 is sent from node 0; T2 is mined on node 1's chain, which becomes the longer one")
        t1 = n0.sendrawtransaction(t1_hex)
        t2 = n1.sendrawtransaction(t2_hex)
        assert t1 != t2
        n1.generate(3)
        assert_equal(n0.gettransaction(t1)["confirmations"], 0)
        assert_equal(n0.gettransaction(t1)["conflicted"], False)

        self.connect_nodes(0, 1)
        self.sync_blocks()
        assert_equal(n0.getblockcount(), 54)
        assert_equal(n0.gettransaction(t2)["confirmations"] > 0, True)

        self.log("T1 is named as conflicted, with T2 as its conflict")
        info = n0.gettransaction(t1)
        assert_equal(info["confirmations"], 0)
        assert_equal(info["conflicted"], True)
        assert_equal(info["walletconflicts"], [t2])
        assert_equal(n0.gettransaction(t2)["conflicted"], False)

        self.log("the balance is what the chain gives the wallet, and counts nothing of T1")
        spendable = sum(u["amount"] for u in n0.listunspent(1))
        assert_equal(n0.getbalance(), spendable)

        self.log("a new send works: coin selection does not pick T1's output")
        n0.sendtoaddress(n1.getnewaddress(), 10)
        n0.generate(1)
        assert_equal(n0.getbalance(), sum(u["amount"] for u in n0.listunspent(1)))


if __name__ == "__main__":
    WalletConflictsTest().main()
