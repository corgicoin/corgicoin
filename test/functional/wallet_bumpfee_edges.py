#!/usr/bin/env python3
"""bumpfee: what it refuses, and that a refusal leaves the wallet and the pool as they were.

  a transaction with a descendant in the pool is refused (bump or abandon the descendant first);
  an unknown transaction id is refused;
  a fee the change cannot pay is refused (inputs are not added), and nothing changes: the transaction is still in the pool, the balance is
  what it was, and the wallet has no second transaction for the same coins.
"""
from decimal import Decimal

from test_framework import CorgiTestFramework, assert_equal, assert_raises_rpc_error


class BumpFeeEdgesTest(CorgiTestFramework):
    num_nodes = 1
    extra_args = [["-walletrbf", "-paytxfee=0.001", "-maxtxfee=5000000", "-mempoolreplacement"]]

    def run_test(self):
        node = self.nodes[0]
        node.generate(110)
        dest = node.getnewaddress()

        self.log("an id the wallet does not know")
        assert_raises_rpc_error(-5, "Invalid or non-wallet", node.bumpfee, "11" * 32)

        self.log("a transaction with a child in the pool is refused")
        parent = node.sendtoaddress(dest, 10)
        decoded = node.decoderawtransaction(node.getrawtransaction(parent))
        change = [o for o in decoded["vout"] if node.validateaddress(o["scriptPubKey"]["addresses"][0])["ismine"] and o["n"] is not None]
        mine = [o for o in change if o["scriptPubKey"]["addresses"][0] != dest] or change
        out = mine[0]
        child_raw = node.createrawtransaction([{"txid": parent, "vout": out["n"]}], {node.getnewaddress(): Decimal(str(out["value"])) - Decimal(2)})
        child = node.sendrawtransaction(node.signrawtransaction(child_raw)["hex"])
        assert_equal(sorted(node.getrawmempool()), sorted([parent, child]))
        assert_raises_rpc_error(-8, "descendants", node.bumpfee, parent)
        assert_equal(sorted(node.getrawmempool()), sorted([parent, child]))
        node.generate(1)

        self.log("a fee the change cannot pay: refused, and nothing changed")
        sent = node.sendtoaddress(dest, 10)
        balance = node.getbalance()
        pool = node.getrawmempool()
        wallet_txs = len(node.listtransactions("*", 1000))
        assert_raises_rpc_error(-6, "too small", node.bumpfee, sent, Decimal(4000000))
        assert_equal(node.getrawmempool(), pool)
        assert_equal(node.getbalance(), balance)
        assert_equal(len(node.listtransactions("*", 1000)), wallet_txs)
        assert_equal(node.gettransaction(sent)["confirmations"], 0)

        self.log("a small enough bump still works afterwards")
        result = node.bumpfee(sent)
        assert result["txid"] != sent
        assert_equal(node.getrawmempool(), [result["txid"]])


if __name__ == "__main__":
    BumpFeeEdgesTest().main()
