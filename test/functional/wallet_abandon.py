#!/usr/bin/env python3
"""abandontransaction: coins come back, descendants go with it, the choice survives a restart, a mined copy is tracked again."""
from decimal import Decimal

from test_framework import CorgiTestFramework, assert_equal, assert_raises_rpc_error


class WalletAbandonTest(CorgiTestFramework):
    num_nodes = 1

    def spend(self, node, txid, vout, amount, fee=Decimal(1)):
        """Spend one output in full (less fee) to a new wallet address; returns (txid, hex)."""
        raw = node.createrawtransaction([{"txid": txid, "vout": vout}], {node.getnewaddress(): amount - fee})
        signed = node.signrawtransaction(raw)
        assert signed["complete"]
        return node.sendrawtransaction(signed["hex"]), signed["hex"]

    def outpoints(self, node):
        return {(u["txid"], u["vout"]) for u in node.listunspent(0)}

    def run_test(self):
        node = self.nodes[0]
        node.generate(51)
        utxo = node.listunspent()[0]
        coin = (utxo["txid"], utxo["vout"])
        before_balance = node.getbalance()
        before_coins = self.outpoints(node)

        self.log("a transaction and one that spends its output, both unconfirmed")
        a_txid, a_hex = self.spend(node, utxo["txid"], utxo["vout"], utxo["amount"])
        b_txid, _ = self.spend(node, a_txid, 0, utxo["amount"] - 1)
        assert_equal(set(node.getrawmempool()), {a_txid, b_txid})
        assert coin not in self.outpoints(node)
        assert node.getbalance() != before_balance

        self.log("abandoning the first removes both, returns the coin and the balance")
        assert_equal(node.abandontransaction(a_txid), None)
        assert_equal(node.getrawmempool(), [])
        assert_equal(node.getbalance(), before_balance)
        assert_equal(self.outpoints(node), before_coins)
        for t in (a_txid, b_txid):
            assert_raises_rpc_error(-5, None, node.gettransaction, t)
        assert_raises_rpc_error(-5, None, node.abandontransaction, a_txid)   # no longer in the wallet

        self.log("the choice survives a restart: nothing comes back into the pool or the wallet")
        node.stop()
        node.start()
        assert_equal(node.getrawmempool(), [])
        assert_equal(node.getbalance(), before_balance)
        assert_equal(self.outpoints(node), before_coins)
        assert_raises_rpc_error(-5, None, node.gettransaction, a_txid)

        self.log("the coin can be spent again and that spend confirms")
        c_txid, _ = self.spend(node, utxo["txid"], utxo["vout"], utxo["amount"], Decimal(2))
        node.generate(1)
        assert_equal(node.gettransaction(c_txid)["confirmations"], 1)

        self.log("a confirmed transaction, an unknown id and a malformed id are refused")
        assert_raises_rpc_error(-5, None, node.abandontransaction, c_txid)
        assert_raises_rpc_error(-5, None, node.abandontransaction, "00" * 32)
        assert_raises_rpc_error(-8, None, node.abandontransaction, "zz")
        assert_raises_rpc_error(-1, None, node.abandontransaction)

        self.log("a copy relayed back after abandoning is pooled but not taken into the wallet")
        utxo2 = node.listunspent()[0]
        d_txid, d_hex = self.spend(node, utxo2["txid"], utxo2["vout"], utxo2["amount"])
        node.abandontransaction(d_txid)
        assert_equal(node.sendrawtransaction(d_hex), d_txid)
        assert_equal(node.getrawmempool(), [d_txid])
        assert_raises_rpc_error(-5, None, node.gettransaction, d_txid)

        self.log("if it is mined after all, the wallet tracks it again")
        node.generate(1)
        mined = node.gettransaction(d_txid)
        assert_equal(mined["confirmations"], 1)
        assert (utxo2["txid"], utxo2["vout"]) not in self.outpoints(node)
        node.stop()
        node.start()
        assert_equal(node.gettransaction(d_txid)["confirmations"], 1)


if __name__ == "__main__":
    WalletAbandonTest().main()
