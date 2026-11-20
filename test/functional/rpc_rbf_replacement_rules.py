#!/usr/bin/env python3
"""Replacement rules of the pool that wallet_rbf.py does not reach.

  a replacement may not spend an output of a transaction it replaces (replacement-spends-conflict);
  100 distinct conflicting transactions can be replaced at once, 101 cannot (too-many-replacements, refused before anything is hashed or signed);
  100 transactions in a tree (a root and two chains built on it) can be replaced, 101 cannot;
  the fee rule uses modified fees (prioritisetransaction) on both sides: a delta on the newcomer lets it pay for the replacement, a delta on the
  transaction in the pool makes it cost more to replace;
  with -mempoolreplacement=0 no conflict is ever replaced, however much it pays.
"""
from decimal import Decimal

from test_framework import CorgiTestFramework, assert_equal, assert_raises_rpc_error


class RBFRulesTest(CorgiTestFramework):
    num_nodes = 2
    extra_args = [[], ["-mempoolreplacement=0"]]

    def raw(self, node, coins, outputs, signal=False):
        """A signed transaction spending whole coins (dicts with txid/vout) into outputs {address: amount}; signalling replaceability or not."""
        ins = [{"txid": c["txid"], "vout": c["vout"]} for c in coins]
        raw = node.createrawtransaction(ins, outputs)
        if signal:
            # every input's sequence is the last 4 bytes of its serialisation: ffffffff -> fdffffff (the one-input layout is 4 + 1 + 36 + 1 + 4)
            pos = 8 + 2 + 72 + 2          # version, input count, outpoint, script length (empty), in hex digits
            for _ in ins:
                assert raw[pos:pos + 8] == "ffffffff", raw[pos:pos + 8]
                raw = raw[:pos] + "fdffffff" + raw[pos + 8:]
                pos += 8 + 72 + 2
        signed = node.signrawtransaction(raw)
        assert signed["complete"]
        return signed["hex"]

    def spend(self, node, coin, dest, fee, signal=True):
        return self.raw(node, [coin], {dest: coin["amount"] - Decimal(fee)}, signal)

    def chain(self, node, parent_id, vout, parent_amount, count):
        ids, amount, prev = [], parent_amount, parent_id
        for i in range(count):
            amount -= Decimal(1)
            signed = node.signrawtransaction(node.createrawtransaction([{"txid": prev, "vout": vout if i == 0 else 0}], {node.getnewaddress(): amount}))
            assert signed["complete"]
            prev = node.sendrawtransaction(signed["hex"])
            ids.append(prev)
        return ids

    def run_test(self):
        a, b = self.nodes
        a.generate(175)
        b.generate(60)
        coins = [c for c in a.listunspent() if c["amount"] > 100]
        assert len(coins) >= 112, len(coins)
        dest = a.getnewaddress()

        self.log("a replacement that spends an output of what it replaces is refused")
        c0 = coins[0]
        parent = a.sendrawtransaction(self.spend(a, c0, dest, 2))
        both = self.raw(a, [c0, {"txid": parent, "vout": 0, "amount": c0["amount"] - Decimal(2)}], {a.getnewaddress(): c0["amount"] * 2 - Decimal(100)})
        assert_raises_rpc_error(-22, "replacement-spends-conflict", a.sendrawtransaction, both)
        assert_equal(a.getrawmempool(), [parent])
        a.generate(1)

        self.log("101 distinct conflicts: refused; 100: replaced (the newcomer spends one coin of each)")
        batch = coins[1:102]
        singles = [a.sendrawtransaction(self.spend(a, c, dest, 2)) for c in batch]
        assert_equal(len(a.getrawmempool()), 101)
        big = self.raw(a, batch, {a.getnewaddress(): sum(c["amount"] for c in batch) - Decimal(2000)})
        assert_raises_rpc_error(-22, "too-many-replacements", a.sendrawtransaction, big)
        assert_equal(len(a.getrawmempool()), 101)
        fewer = self.raw(a, batch[:100], {a.getnewaddress(): sum(c["amount"] for c in batch[:100]) - Decimal(2000)})
        new_id = a.sendrawtransaction(fewer)
        assert_equal(sorted(a.getrawmempool()), sorted([new_id, singles[100]]))
        a.generate(1)

        self.log("a tree of 100 transactions (a root and two chains on it) is replaced; one of 101 is not")
        for count_a, count_b, ok in ((49, 50, True), (50, 50, False)):
            c = coins[102] if ok else coins[103]
            half = (c["amount"] - Decimal(2)) / 2
            half = half.quantize(Decimal("0.00000001"))
            root = a.sendrawtransaction(self.raw(a, [c], {a.getnewaddress(): half, a.getnewaddress(): c["amount"] - Decimal(2) - half}, signal=True))
            self.chain(a, root, 0, half, count_a)
            self.chain(a, root, 1, c["amount"] - Decimal(2) - half, count_b)
            assert_equal(len(a.getrawmempool()), 1 + count_a + count_b)
            replacement = self.spend(a, c, a.getnewaddress(), 300)
            if ok:
                rid = a.sendrawtransaction(replacement)
                assert_equal(a.getrawmempool(), [rid])
            else:
                assert_raises_rpc_error(-22, "too-many-replacements", a.sendrawtransaction, replacement)
                assert_equal(len(a.getrawmempool()), 1 + count_a + count_b)
            a.generate(1)

        self.log("a fee delta on the newcomer counts as fee: it replaces what it could not")
        c = coins[104]
        a.sendrawtransaction(self.spend(a, c, dest, 2))
        low = self.spend(a, c, a.getnewaddress(), 2.5)
        assert_raises_rpc_error(-22, "insufficient-fee-replacement", a.sendrawtransaction, low)
        a.prioritisetransaction(a.decoderawtransaction(low)["txid"], 0, 5 * 100000000)
        low_id = a.sendrawtransaction(low)
        assert_equal(a.getrawmempool(), [low_id])
        a.generate(1)

        self.log("a fee delta on what is in the pool makes it cost more to replace (the rule compares modified fees on both sides)")
        c = coins[105]
        held = a.sendrawtransaction(self.spend(a, c, dest, 2))
        a.prioritisetransaction(held, 0, 10 * 100000000)             # counts as 12 coins when it is replaced
        assert_raises_rpc_error(-22, "insufficient-fee-replacement", a.sendrawtransaction, self.spend(a, c, a.getnewaddress(), 8))
        assert_equal(a.getrawmempool(), [held])
        rid = a.sendrawtransaction(self.spend(a, c, a.getnewaddress(), 20))
        assert_equal(a.getrawmempool(), [rid])
        a.generate(1)

        self.log("-mempoolreplacement=0: a conflict is never replaced, however much it pays")
        bcoin = [x for x in b.listunspent() if x["amount"] > 100][0]
        first = b.sendrawtransaction(self.spend(b, bcoin, b.getnewaddress(), 2))
        assert_raises_rpc_error(-22, "txn-mempool-conflict", b.sendrawtransaction, self.spend(b, bcoin, b.getnewaddress(), 1000))
        assert_equal(b.getrawmempool(), [first])


if __name__ == "__main__":
    RBFRulesTest().main()
