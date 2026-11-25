#!/usr/bin/env python3
"""When a block connects, everything in the pool that conflicts with it goes, and nothing else.

Node 0's pool holds: a chain A -> B -> C where A spends coin a; D, which spends two coins (c1, c2); and E, which spends coin e and has nothing to
do with the block. Node 1 mines blocks with M1 (spends coin a otherwise) and M2 (spends c1 otherwise). When node 0 takes the blocks, A, B, C and D
are gone (A can never confirm, and B and C rest on A; D needs c1) and E is still there.
"""
from decimal import Decimal

from test_framework import CorgiTestFramework, assert_equal


class MempoolConflictMultiTest(CorgiTestFramework):
    num_nodes = 2

    def tx(self, node, coins, dest, fee):
        ins = [{"txid": c["txid"], "vout": c["vout"]} for c in coins]
        signed = node.signrawtransaction(node.createrawtransaction(ins, {dest: sum(c["amount"] for c in coins) - Decimal(fee)}))
        assert signed["complete"]
        return signed["hex"]

    def run_test(self):
        n0, n1 = self.nodes
        n0.generate(60)
        self.connect_nodes(1, 0)
        self.sync_blocks()
        self.disconnect_nodes(1, 0)
        coins = [c for c in n0.listunspent() if c["amount"] > 100]
        a, c1, c2, e = coins[0], coins[1], coins[2], coins[3]

        self.log("node 0: A -> B -> C on coin a, D on coins c1 and c2, E on coin e")
        a_id = n0.sendrawtransaction(self.tx(n0, [a], n0.getnewaddress(), 2))
        amount = a["amount"] - Decimal(2)
        ids = [a_id]
        for _ in range(2):
            amount -= Decimal(1)
            raw = n0.createrawtransaction([{"txid": ids[-1], "vout": 0}], {n0.getnewaddress(): amount})
            ids.append(n0.sendrawtransaction(n0.signrawtransaction(raw)["hex"]))
        d_id = n0.sendrawtransaction(self.tx(n0, [c1, c2], n0.getnewaddress(), 3))
        e_id = n0.sendrawtransaction(self.tx(n0, [e], n0.getnewaddress(), 2))
        assert_equal(sorted(n0.getrawmempool()), sorted(ids + [d_id, e_id]))

        self.log("node 1 mines M1 (coin a) and M2 (coin c1); node 0 takes the blocks")
        m1 = n1.sendrawtransaction(self.tx(n0, [a], n1.getnewaddress(), 5))       # (signed by node 0, which has the key, sent by node 1)
        n1.generate(1)
        m2 = n1.sendrawtransaction(self.tx(n0, [c1], n1.getnewaddress(), 5))
        n1.generate(1)
        self.connect_nodes(0, 1)
        self.sync_blocks()
        for m in (m1, m2):
            assert n0.gettransaction(m)["confirmations"] > 0
        assert_equal(n0.getrawmempool(), [e_id])

        self.log("and the same when the conflicting transactions come in a reorganisation (node 0 had its own block with A, B, C, D, E)")
        coins = [c for c in n0.listunspent() if c["amount"] > 100 and c["txid"] not in (a["txid"], c1["txid"], c2["txid"], e["txid"])]
        f, g = coins[0], coins[1]
        self.disconnect_nodes(0, 1)
        f_id = n0.sendrawtransaction(self.tx(n0, [f], n0.getnewaddress(), 2))
        raw = n0.createrawtransaction([{"txid": f_id, "vout": 0}], {n0.getnewaddress(): f["amount"] - Decimal(3)})
        f_child = n0.sendrawtransaction(n0.signrawtransaction(raw)["hex"])
        n0.generate(1)                                           # F and its child are in node 0's chain
        n1.sendrawtransaction(self.tx(n0, [f], n1.getnewaddress(), 6))   # conflicts with F
        n1.generate(3)
        self.connect_nodes(0, 1)
        self.sync_blocks()
        pool = n0.getrawmempool()
        assert f_id not in pool and f_child not in pool, "F and its child (put back by the reorganisation) are still in the pool: %s" % pool


if __name__ == "__main__":
    MempoolConflictMultiTest().main()
