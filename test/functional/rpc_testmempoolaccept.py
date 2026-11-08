#!/usr/bin/env python3
"""testmempoolaccept: the verdict and the reason, with no change to the memory pool or the wallet."""
from decimal import Decimal

from test_framework import CorgiTestFramework, assert_equal, assert_raises_rpc_error


class TestMempoolAcceptTest(CorgiTestFramework):
    num_nodes = 1

    def raw_spend(self, node, utxo, dest, fee, sign=True):
        raw = node.createrawtransaction([{"txid": utxo["txid"], "vout": utxo["vout"]}], {dest: utxo["amount"] - fee})
        if not sign:
            return raw
        signed = node.signrawtransaction(raw)
        assert signed["complete"]
        return signed["hex"]

    def run_test(self):
        node = self.nodes[0]
        node.generate(53)       # three mature coinbases
        utxos = node.listunspent()
        dest = node.getnewaddress()

        self.log("a good transaction is allowed, with its fee, and nothing is stored")
        good = self.raw_spend(node, utxos[0], dest, Decimal(1))
        before = (node.getmempoolinfo(), len(node.listtransactions("*", 1000)))
        res = node.testmempoolaccept([good])
        assert_equal(len(res), 1)
        assert_equal(res[0]["allowed"], True)
        assert_equal(res[0]["fee"], Decimal(1))
        assert "reject-reason" not in res[0]
        assert_equal(res[0]["txid"], node.decoderawtransaction(good)["txid"])
        assert_equal(node.getrawmempool(), [])
        assert_equal((node.getmempoolinfo(), len(node.listtransactions("*", 1000))), before)

        self.log("the test did not use the transaction up: it can still be sent, and is then a duplicate")
        txid = node.sendrawtransaction(good)
        assert_equal(txid, res[0]["txid"])
        dup = node.testmempoolaccept([good])[0]
        assert_equal((dup["allowed"], dup["reject-reason"]), (False, "txn-already-in-mempool"))

        self.log("a different spend of the same output conflicts with the pooled one")
        clash = node.testmempoolaccept([self.raw_spend(node, utxos[0], node.getnewaddress(), Decimal(2))])[0]
        assert_equal((clash["allowed"], clash["reject-reason"]), (False, "txn-mempool-conflict"))

        self.log("once mined the transaction is known")
        node.generate(1)
        known = node.testmempoolaccept([good])[0]
        assert_equal((known["allowed"], known["reject-reason"]), (False, "txn-already-known"))

        self.log("a small transaction with a tiny fee is allowed (free relay) and reports its fee")
        low = node.testmempoolaccept([self.raw_spend(node, utxos[1], dest, Decimal("0.0001"))])[0]
        assert_equal(low["allowed"], True)
        assert "reject-reason" not in low
        assert_equal(low["fee"], Decimal("0.0001"))

        self.log("missing inputs")
        ghost = dict(utxos[2], txid="ab" * 32)
        missing = node.testmempoolaccept([self.raw_spend(node, ghost, dest, Decimal(1), sign=False)])[0]
        assert_equal((missing["allowed"], missing["reject-reason"]), (False, "missing-inputs"))
        assert "fee" not in missing

        self.log("an unsigned transaction fails its script check")
        unsigned = node.testmempoolaccept([self.raw_spend(node, utxos[2], dest, Decimal(1), sign=False)])[0]
        assert_equal((unsigned["allowed"], unsigned["reject-reason"]), (False, "bad-txns-inputs"))

        self.log("a coinbase is not a loose transaction")
        coinbase_tx = node.getrawtransaction(node.getblock(node.getbestblockhash())["tx"][0])
        cb = node.testmempoolaccept([coinbase_tx])[0]
        assert_equal((cb["allowed"], cb["reject-reason"]), (False, "coinbase"))

        self.log("the pool and the wallet are still as the real send left them")
        assert_equal(node.getrawmempool(), [])

        self.log("bad input is an error, not a verdict")
        assert_raises_rpc_error(-22, None, node.testmempoolaccept, ["zz"])
        assert_raises_rpc_error(-22, None, node.testmempoolaccept, ["00"])
        assert_raises_rpc_error(-22, None, node.testmempoolaccept, [good + "00"])
        assert_raises_rpc_error(-8, None, node.testmempoolaccept, [good, good])
        assert_raises_rpc_error(-8, None, node.testmempoolaccept, [])
        assert_raises_rpc_error(-3, None, node.testmempoolaccept, [5])
        assert_raises_rpc_error(-3, None, node.testmempoolaccept, good)
        assert_raises_rpc_error(-1, None, node.testmempoolaccept)


if __name__ == "__main__":
    TestMempoolAcceptTest().main()
