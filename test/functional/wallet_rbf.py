#!/usr/bin/env python3
"""Replace-by-fee (BIP 125 rules) in the pool, and bumpfee in the wallet.

Pool: a transaction that signals it can be replaced (a sequence number below 0xfffffffe) is replaced by one that spends the same
coin and pays more; one that pays no more is refused; one that did not signal is never replaced.
Wallet: with -walletrbf the wallet's sends signal, and bumpfee raises the fee out of the change, replaces the old transaction in
the pool, and leaves the wallet's balance as it should be.
"""
from decimal import Decimal

from test_framework import CorgiTestFramework, assert_equal, assert_raises_rpc_error


class RBFTest(CorgiTestFramework):
    num_nodes = 2
    extra_args = [["-walletrbf"], []]       # node 0 sends replaceable transactions; node 1 does not

    def spend(self, node, coin, dest, fee, signal):
        """A signed transaction spending the whole coin to dest, paying fee; signalling replaceability or not."""
        raw = node.createrawtransaction([{"txid": coin["txid"], "vout": coin["vout"]}], {dest: coin["amount"] - Decimal(fee)})
        if signal:
            assert raw[84:92] == "ffffffff", raw[80:96]
            raw = raw[:84] + "fdffffff" + raw[92:]
        signed = node.signrawtransaction(raw)
        assert signed["complete"]
        return signed["hex"]

    def run_test(self):
        a, b = self.nodes
        a.generate(110)
        self.connect_nodes(1, 0)
        self.sync_blocks()
        dest = a.getnewaddress()
        coins = [c for c in a.listunspent() if c["amount"] > 100]

        self.log("a replaceable transaction is replaced by one that pays more")
        low = self.spend(a, coins[0], dest, 2, signal=True)
        low_id = a.sendrawtransaction(low)
        assert low_id in a.getrawmempool()
        same_fee = self.spend(a, coins[0], a.getnewaddress(), 2, signal=True)
        assert_raises_rpc_error(-22, "insufficient-fee-replacement", a.sendrawtransaction, same_fee)
        high_id = a.sendrawtransaction(self.spend(a, coins[0], a.getnewaddress(), 5, signal=True))
        assert_equal(a.getrawmempool(), [high_id])

        self.log("one that does not signal is never replaced, however much the newcomer pays")
        fixed_id = a.sendrawtransaction(self.spend(a, coins[1], dest, 2, signal=False))
        assert_raises_rpc_error(-22, "txn-mempool-conflict", a.sendrawtransaction, self.spend(a, coins[1], a.getnewaddress(), 50, signal=True))
        assert fixed_id in a.getrawmempool()

        self.log("a replacement may not rest on something unconfirmed that the replaced one did not")
        parent_id = a.sendrawtransaction(self.spend(a, coins[2], dest, 2, signal=False))   # an unconfirmed coin: parent:0
        victim = self.spend(a, coins[3], dest, 2, signal=True)
        a.sendrawtransaction(victim)
        raw = a.createrawtransaction([{"txid": coins[3]["txid"], "vout": coins[3]["vout"]}, {"txid": parent_id, "vout": 0}],
                                     {a.getnewaddress(): coins[3]["amount"] + coins[2]["amount"] - Decimal(10) - Decimal(2)})
        signed = a.signrawtransaction(raw)
        assert signed["complete"]
        assert_raises_rpc_error(-22, "replacement-adds-unconfirmed", a.sendrawtransaction, signed["hex"])

        self.log("the other node follows: the pool it has is the replaced state")
        self.sync_blocks()
        a.generate(1)
        self.sync_blocks()
        assert_equal(a.getrawmempool(), [])

        self.log("wallet: a send with -walletrbf signals, bumpfee replaces it and raises the fee out of the change")
        balance = a.getbalance()
        sent = a.sendtoaddress(b.getnewaddress(), 10)
        info = a.gettransaction(sent)
        old_fee = -info["fee"]
        result = a.bumpfee(sent)
        assert result["txid"] != sent
        assert result["fee"] > result["origfee"] == old_fee, result
        assert_equal(a.getrawmempool(), [result["txid"]])
        assert_raises_rpc_error(-5, "Invalid or non-wallet", a.gettransaction, sent)          # the old one was abandoned
        assert_equal(a.getbalance(), balance - 10 - result["fee"])
        self.sync_blocks()
        a.generate(1)
        self.sync_blocks()
        assert_equal(a.gettransaction(result["txid"])["confirmations"], 1)
        assert_equal(b.getbalance(), 10)

        self.log("a given fee is used; it must be more than the old one; a mined transaction cannot be bumped")
        sent = a.sendtoaddress(b.getnewaddress(), 5)
        old_fee = -a.gettransaction(sent)["fee"]
        assert_raises_rpc_error(-8, "more than the old one", a.bumpfee, sent, old_fee)
        again = a.bumpfee(sent, old_fee + Decimal(7))
        assert_equal(again["fee"], old_fee + Decimal(7))
        a.generate(1)
        assert_raises_rpc_error(-8, "mined", a.bumpfee, again["txid"])

        self.log("a transaction sent without -walletrbf cannot be bumped")
        b.generate(101)
        self.sync_blocks()
        plain = b.sendtoaddress(a.getnewaddress(), 3)
        assert_raises_rpc_error(-8, "does not signal", b.bumpfee, plain)


if __name__ == "__main__":
    RBFTest().main()
