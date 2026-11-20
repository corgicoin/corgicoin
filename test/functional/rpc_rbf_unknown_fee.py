#!/usr/bin/env python3
"""A transaction put back in the pool without its inputs being looked at has no known fee, and cannot be replaced for nothing.

Two ways a transaction gets into the pool that way: a reorganisation puts back what was in the blocks it disconnected, and the wallet puts its
own transactions back at start. The rule that a replacement must pay for what it throws out cannot be applied to a fee that is not known, so a
conflict with such a transaction is refused (txn-mempool-conflict) although it signals replaceability.
"""
from decimal import Decimal

from test_framework import CorgiTestFramework, assert_equal, assert_raises_rpc_error, wait_until


class RBFUnknownFeeTest(CorgiTestFramework):
    num_nodes = 2
    extra_args = [["-walletrbf", "-paytxfee=0.001", "-mempoolreplacement"], ["-mempoolreplacement"]]

    def signal_spend(self, node, coin, dest, fee):
        raw = node.createrawtransaction([{"txid": coin["txid"], "vout": coin["vout"]}], {dest: coin["amount"] - Decimal(fee)})
        raw = raw[:84] + "fdffffff" + raw[92:]
        signed = node.signrawtransaction(raw)
        assert signed["complete"]
        return signed["hex"]

    def run_test(self):
        a, b = self.nodes
        a.generate(130)
        self.connect_nodes(1, 0)
        self.sync_blocks()
        self.disconnect_nodes(1, 0)
        coins = [c for c in a.listunspent() if c["amount"] > 100]

        self.log("a reorganisation puts T back in the pool: its fee is not known, so a better-paying conflict is refused")
        t = a.sendrawtransaction(self.signal_spend(a, coins[0], a.getnewaddress(), 2))
        a.generate(1)                                           # T is in node 0's chain
        assert_equal(a.getrawmempool(), [])
        b.generate(3)                                           # a longer chain without T
        self.connect_nodes(0, 1)
        self.sync_blocks()
        assert_equal(a.getrawmempool(), [t])                    # put back by the reorganisation
        rich = self.signal_spend(a, coins[0], a.getnewaddress(), 500)
        assert_raises_rpc_error(-22, "txn-mempool-conflict", a.sendrawtransaction, rich)
        assert_equal(a.getrawmempool(), [t])
        a.generate(1)                                           # and it confirms as it was
        assert_equal(a.getrawmempool(), [])
        self.sync_blocks()

        self.log("the wallet puts its own transaction back at start: the same")
        sent = a.sendtoaddress(b.getnewaddress(), 10)           # signals (-walletrbf)
        raw = a.decoderawtransaction(a.getrawtransaction(sent))
        ins = [{"txid": v["txid"], "vout": v["vout"]} for v in raw["vin"]]
        total = Decimal(0)
        for v in raw["vin"]:
            total += Decimal(str(a.getrawtransaction(v["txid"], 1)["vout"][v["vout"]]["value"]))
        a.stop()
        a.process.wait(timeout=60)
        a.start()
        wait_until(lambda: sent in a.getrawmempool(), timeout=60, what="the wallet to put its transaction back in the pool")
        conflict = a.signrawtransaction(a.createrawtransaction(ins, {a.getnewaddress(): total - 1000}))
        assert conflict["complete"]
        assert_raises_rpc_error(-22, "txn-mempool-conflict", a.sendrawtransaction, conflict["hex"])
        assert_equal(a.getrawmempool(), [sent])


if __name__ == "__main__":
    RBFUnknownFeeTest().main()
