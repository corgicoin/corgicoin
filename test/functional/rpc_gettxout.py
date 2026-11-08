#!/usr/bin/env python3
"""gettxout: confirmed, unconfirmed and spent outputs, with and without the memory pool."""
from decimal import Decimal

from test_framework import CorgiTestFramework, assert_equal, assert_raises_rpc_error


class GetTxOutTest(CorgiTestFramework):
    num_nodes = 1

    def spend(self, node, utxo, dest, fee=Decimal(1)):
        """Spend one wallet output to dest in full (less fee); returns the txid."""
        raw = node.createrawtransaction([{"txid": utxo["txid"], "vout": utxo["vout"]}], {dest: utxo["amount"] - fee})
        signed = node.signrawtransaction(raw)
        assert signed["complete"]
        return node.sendrawtransaction(signed["hex"])

    def run_test(self):
        node = self.nodes[0]
        node.generate(51)
        utxo = node.listunspent()[0]

        self.log("an unspent confirmed output: value, script, depth and the best block")
        out = node.gettxout(utxo["txid"], utxo["vout"])
        assert out is not None
        assert_equal(out["value"], utxo["amount"])
        assert_equal(out["bestblock"], node.getbestblockhash())
        assert_equal(out["confirmations"], utxo["confirmations"])
        assert_equal(out["scriptPubKey"]["hex"], utxo["scriptPubKey"])
        assert_equal(out["coinbase"], node.getrawtransaction(utxo["txid"], 1)["vin"][0].get("coinbase") is not None)
        assert_equal(out, node.gettxout(utxo["txid"], utxo["vout"], True))
        assert_equal(out["confirmations"] + 1, node.gettxout(utxo["txid"], utxo["vout"], False)["confirmations"] + 1)

        self.log("outputs that do not exist")
        assert_equal(node.gettxout("00" * 32, 0), None)
        assert_equal(node.gettxout(utxo["txid"], 99), None)
        assert_raises_rpc_error(-8, None, node.gettxout, utxo["txid"], -1)

        self.log("an output spent by a transaction in the pool: gone with the pool, there without it")
        dest = node.getnewaddress()
        spend_txid = self.spend(node, utxo, dest)
        assert_equal(node.gettxout(utxo["txid"], utxo["vout"]), None)
        assert_equal(node.gettxout(utxo["txid"], utxo["vout"], True), None)
        still = node.gettxout(utxo["txid"], utxo["vout"], False)
        assert still is not None and still["value"] == utxo["amount"]

        self.log("an output of an unconfirmed transaction: depth 0, only found with the pool")
        spent_tx = node.getrawtransaction(spend_txid, 1)
        n = [i for i, o in enumerate(spent_tx["vout"]) if dest in o["scriptPubKey"].get("addresses", [])][0]
        pooled = node.gettxout(spend_txid, n)
        assert pooled is not None
        assert_equal(pooled["confirmations"], 0)
        assert_equal(pooled["value"], utxo["amount"] - 1)
        assert_equal(pooled["coinbase"], False)
        assert_equal(node.gettxout(spend_txid, n, False), None)

        self.log("once mined it is confirmed, and the spent output is gone either way")
        node.generate(1)
        mined = node.gettxout(spend_txid, n)
        assert mined is not None
        assert_equal(mined["confirmations"], 1)
        assert_equal(node.gettxout(spend_txid, n, False)["confirmations"], 1)
        assert_equal(node.gettxout(utxo["txid"], utxo["vout"]), None)
        assert_equal(node.gettxout(utxo["txid"], utxo["vout"], False), None)

        self.log("the output that was spent comes back when the spending block is invalidated")
        tip = node.getbestblockhash()
        node.invalidateblock(tip)
        back = node.gettxout(utxo["txid"], utxo["vout"], False)
        assert back is not None and back["value"] == utxo["amount"]
        assert_equal(node.gettxout(spend_txid, n, False), None)

        self.log("argument checks")
        assert_raises_rpc_error(-1, None, node.gettxout, utxo["txid"])
        assert_raises_rpc_error(-1, None, node.gettxout, utxo["txid"], 0, True, "extra")
        assert_raises_rpc_error(-3, None, node.gettxout, utxo["txid"], "zero")


if __name__ == "__main__":
    GetTxOutTest().main()
