#!/usr/bin/env python3
"""The memory pool has a size limit (-maxmempoolkb): over it, the lowest fee rate goes first.

Without a limit a peer (or a wallet) could grow the pool without bound. The pool is held to about 10 kB here; transactions
paying 5 coins each fill it, one paying 50 pushes one of them out, and one paying the least that relays is turned away.
"""
from decimal import Decimal

from test_framework import CorgiTestFramework, assert_equal

CAP = 10000


class MempoolCapTest(CorgiTestFramework):
    num_nodes = 1
    extra_args = [["-maxmempoolkb=10"]]

    def spend(self, node, utxo, dest, fee):
        raw = node.createrawtransaction([{"txid": utxo["txid"], "vout": utxo["vout"]}], {dest: utxo["amount"] - Decimal(fee)})
        signed = node.signrawtransaction(raw)
        assert signed["complete"]
        return signed["hex"]

    def run_test(self):
        node = self.nodes[0]
        node.generate(300)
        utxos = node.listunspent()
        assert len(utxos) >= 150, len(utxos)
        dest = node.getnewaddress()

        self.log("fill the pool with transactions that pay 5 coins and a bit")
        for i, u in enumerate(utxos[:80]):
            node.sendrawtransaction(self.spend(node, u, dest, Decimal("5") + Decimal(i) / 100))   # each pays a little more
        info = node.getmempoolinfo()
        assert info["bytes"] <= CAP, info
        assert info["size"] < 80, "nothing was dropped: %r" % info
        assert info["size"] > 20, info
        assert_equal(info["maxmempoolbytes"], CAP)
        assert info["leaves_consistent"], info          # the index of the entries nothing spends from, after many evictions
        assert_equal(info["leaves"], info["size"])      # none of these spends another
        full = info["size"]

        self.log("a transaction that pays more is accepted, and one goes out to make room")
        rich = self.spend(node, utxos[80], dest, 50)
        txid = node.sendrawtransaction(rich)
        assert txid in node.getrawmempool()
        info = node.getmempoolinfo()
        assert info["bytes"] <= CAP, info
        assert_equal(info["size"], full)

        self.log("one that pays the least that relays is turned away")
        try:
            node.sendrawtransaction(self.spend(node, utxos[81], dest, 2))
        except Exception as e:
            assert "mempool" in str(e).lower() or "reject" in str(e).lower() or "-" in str(e), str(e)
        else:
            raise AssertionError("a transaction at the lowest fee rate was accepted into a full pool")
        assert node.getmempoolinfo()["bytes"] <= CAP

        assert node.getmempoolinfo()["leaves_consistent"]

        self.log("a block takes them and the pool empties")
        node.generate(1)
        info = node.getmempoolinfo()
        assert_equal(info["size"], 0)
        assert_equal(info["leaves"], 0)
        assert info["leaves_consistent"], info

        self.log("a parent and its child: only the child is a leaf; a block takes both and the index is empty again")
        u = utxos[82]
        parent = node.sendrawtransaction(self.spend(node, u, dest, 5))
        child_coin = {"txid": parent, "vout": 0, "amount": u["amount"] - Decimal(5)}
        child = node.sendrawtransaction(self.spend(node, child_coin, dest, 6))
        info = node.getmempoolinfo()
        assert_equal(info["size"], 2)
        assert_equal(info["leaves"], 1)
        assert info["leaves_consistent"], info
        node.generate(1)
        info = node.getmempoolinfo()
        assert_equal((info["size"], info["leaves"]), (0, 0))
        assert info["leaves_consistent"], info


if __name__ == "__main__":
    MempoolCapTest().main()
