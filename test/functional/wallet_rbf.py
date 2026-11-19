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
    # node 0 sends replaceable transactions, and always pays a fee (a coin old enough sends for nothing, and a fee of 0 cannot be bumped "to the old one"); node 1 does not
    extra_args = [["-walletrbf", "-paytxfee=0.001"], []]

    def spend(self, node, coin, dest, fee, signal):
        """A signed transaction spending the whole coin to dest, paying fee; signalling replaceability or not."""
        raw = node.createrawtransaction([{"txid": coin["txid"], "vout": coin["vout"]}], {dest: coin["amount"] - Decimal(fee)})
        if signal:
            assert raw[84:92] == "ffffffff", raw[80:96]
            raw = raw[:84] + "fdffffff" + raw[92:]
        signed = node.signrawtransaction(raw)
        assert signed["complete"]
        return signed["hex"]

    def chain(self, node, parent_id, parent_amount, count):
        """count transactions, each spending the output of the one before (the first of parent_id), each paying a fee of 1. Returns their txids."""
        ids = []
        amount = parent_amount
        prev = parent_id
        for _ in range(count):
            amount -= Decimal(1)
            raw = node.createrawtransaction([{"txid": prev, "vout": 0}], {node.getnewaddress(): amount})
            signed = node.signrawtransaction(raw)
            assert signed["complete"]
            prev = node.sendrawtransaction(signed["hex"])
            ids.append(prev)
        return ids

    def run_test(self):
        a, b = self.nodes
        a.generate(130)
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
        self.log("the replacement's fee rate must beat the replaced one's, not only its fee")
        old_id = a.sendrawtransaction(self.spend(a, coins[4], dest, 2, signal=True))
        two_in = lambda fee: a.signrawtransaction(a.createrawtransaction(
            [{"txid": coins[4]["txid"], "vout": coins[4]["vout"]}, {"txid": coins[5]["txid"], "vout": coins[5]["vout"]}],
            {a.getnewaddress(): coins[4]["amount"] + coins[5]["amount"] - Decimal(fee)}))["hex"]
        assert_raises_rpc_error(-22, "replacement-feerate-too-low", a.sendrawtransaction, two_in(3))     # more fee, but a bigger transaction: a lower rate
        assert old_id in a.getrawmempool()
        new_id = a.sendrawtransaction(two_in(5))
        assert old_id not in a.getrawmempool() and new_id in a.getrawmempool()
        a.generate(1)

        self.log("what is built on the replaced transaction goes with it; the other node follows")
        root = a.sendrawtransaction(self.spend(a, coins[6], dest, 2, signal=True))
        kids = self.chain(a, root, coins[6]["amount"] - Decimal(2), 2)
        assert_equal(len(a.getrawmempool()), 3)
        self.sync_mempools()
        replacement = a.sendrawtransaction(self.spend(a, coins[6], a.getnewaddress(), 20, signal=True))
        assert_equal(a.getrawmempool(), [replacement])
        self.sync_mempools()
        assert_equal(b.getrawmempool(), [replacement])
        a.generate(1)
        self.sync_blocks()

        self.log("a replacement may push out 100 transactions, not 101 (and is refused before any signature is checked)")
        root = a.sendrawtransaction(self.spend(a, coins[7], dest, 2, signal=True))
        self.chain(a, root, coins[7]["amount"] - Decimal(2), 99)           # the root and 99 more: 100
        assert_equal(len(a.getrawmempool()), 100)
        replacement = a.sendrawtransaction(self.spend(a, coins[7], a.getnewaddress(), 150, signal=True))
        assert_equal(a.getrawmempool(), [replacement])
        a.generate(1)
        root = a.sendrawtransaction(self.spend(a, coins[8], dest, 2, signal=True))
        self.chain(a, root, coins[8]["amount"] - Decimal(2), 100)          # 101
        assert_equal(len(a.getrawmempool()), 101)
        assert_raises_rpc_error(-22, "too-many-replacements", a.sendrawtransaction, self.spend(a, coins[8], a.getnewaddress(), 300, signal=True))
        assert_equal(len(a.getrawmempool()), 101)
        a.generate(1)

        self.log("bip125-replaceable: yes for one that signals, or rests on one that does; no for one that does not, and once mined")
        sig = a.sendrawtransaction(self.spend(a, coins[9], dest, 2, signal=True))
        assert_equal(a.gettransaction(sig)["bip125-replaceable"], "yes")
        child = self.chain(a, sig, coins[9]["amount"] - Decimal(2), 1)[0]
        assert_equal(a.gettransaction(child)["bip125-replaceable"], "yes")
        fixed = a.sendrawtransaction(self.spend(a, coins[10], dest, 2, signal=False))
        assert_equal(a.gettransaction(fixed)["bip125-replaceable"], "no")
        listed = {t["txid"]: t["bip125-replaceable"] for t in a.listtransactions("*", 50)}
        assert_equal(listed[sig], "yes")
        assert_equal(listed[fixed], "no")
        a.generate(1)
        assert_equal(a.gettransaction(sig)["bip125-replaceable"], "no")

        self.log("a replacement made by someone else: the wallet stops counting the transaction it replaced")
        before = a.getbalance()
        sent = a.sendtoaddress(b.getnewaddress(), 1)
        raw = a.decoderawtransaction(a.getrawtransaction(sent))
        total_in = Decimal(0)
        for vin in raw["vin"]:
            total_in += Decimal(str(a.getrawtransaction(vin["txid"], 1)["vout"][vin["vout"]]["value"]))
        spent_fee = total_in - sum(Decimal(str(o["value"])) for o in raw["vout"])
        outside = a.signrawtransaction(a.createrawtransaction([{"txid": v["txid"], "vout": v["vout"]} for v in raw["vin"]],
                                                              {a.getnewaddress(): total_in - spent_fee - 20}))
        assert outside["complete"]
        replacement = a.sendrawtransaction(outside["hex"])
        assert_equal(a.getrawmempool(), [replacement])
        assert_raises_rpc_error(-5, "Invalid or non-wallet", a.gettransaction, sent)
        # its change is no longer an output the wallet can spend (before, it stayed in the balance and its coins stayed marked spent)
        assert all(u["txid"] != sent for u in a.listunspent(0)), "the replaced transaction's change is still counted"
        a.generate(1)
        self.sync_blocks()


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
