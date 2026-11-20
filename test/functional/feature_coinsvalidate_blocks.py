#!/usr/bin/env python3
"""-coinsvalidate=1 (regtest) refuses the same bad blocks as the index does, and a set that is wrong never marks a valid block failed.

Node 0 runs with -coinsvalidate=1 (a block's inputs are checked against the unspent set), node 1 without it, and each is handed the same
hand-made blocks (block_builder.py), each breaking one rule: an input that does not exist, a double spend inside the block, a spend of an
immature coinbase, a coinbase that repeats an unspent one (BIP30), a coinbase paying more than allowed, a wrong merkle root. Both must refuse
every one and stay on the same tip (so the set judges the way the index does); then a good block with a payment, which both take, after which
the set is what the blocks give.

Node 2 runs -coinsvalidate=1 with -testcoinsbreak=45, which puts the set out of step at block 45. It must go on following the chain past it (the
set is only a witness: a wrong one must not mark a valid block failed, and must not stop the node to rebuild), and a restart without the
option repairs it.

What makes it fail: if the set judged a block differently from the index (accepting what the index refuses, or the reverse), the two nodes'
answers or tips would differ; if a wrong set marked a valid block failed, node 2 would stop at 45.
"""
from decimal import Decimal

from block_builder import COIN, build_block, next_block_value, txid_of
from test_framework import CorgiTestFramework, assert_equal, wait_until


class CoinsValidateBlocksTest(CorgiTestFramework):
    num_nodes = 3
    extra_args = [["-coinsvalidate=1"], [], ["-coinsvalidate=1", "-testcoinsbreak=45"]]

    def log_text(self, node):
        with open(node.debug_log, errors="replace") as f:
            return f.read()

    def both(self, hexblock, what):
        """Hand a block to node 0 and node 1: both answer the same, and (for a bad block) neither moves."""
        n0, n1 = self.nodes[0], self.nodes[1]
        tip0, tip1 = n0.getbestblockhash(), n1.getbestblockhash()
        assert_equal(tip0, tip1)
        r0, r1 = n0.submitblock(hexblock), n1.submitblock(hexblock)
        assert_equal(r0, r1, "%s: the set and the index answered differently (%r, %r)" % (what, r0, r1))
        return r0, tip0

    def refused(self, hexblock, what):
        r, tip = self.both(hexblock, what)
        assert r is not None and r != "duplicate", "%s: the block was accepted (%r)" % (what, r)
        assert_equal(self.nodes[0].getbestblockhash(), tip)
        assert_equal(self.nodes[1].getbestblockhash(), tip)
        self.log("  %s: refused (%s) by both" % (what, r))

    def run_test(self):
        n0, n1, n2 = self.nodes
        self.connect_nodes(1, 0)
        self.connect_nodes(1, 2)
        n1.generate(40)
        self.sync_blocks()
        self.disconnect_nodes(1, 0)
        self.disconnect_nodes(1, 2)
        assert_equal(n0.getblockcount(), 40)
        assert_equal(n2.getblockcount(), 40)

        coins = n1.listunspent()
        assert len(coins) >= 3
        addr = n1.getnewaddress()

        def spend(coin, to, fee=Decimal("0.001")):
            raw = n1.createrawtransaction([{"txid": coin["txid"], "vout": coin["vout"]}], {to: coin["amount"] - fee})
            return bytes.fromhex(n1.signrawtransaction(raw)["hex"])

        self.log("blocks that break one rule each")
        ghost = bytes.fromhex(n1.createrawtransaction([{"txid": "ab" * 32, "vout": 0}], {addr: Decimal(1)}))
        self.refused(build_block(n1, [ghost]), "an input that does not exist")

        a, b = spend(coins[0], n1.getnewaddress()), spend(coins[0], n1.getnewaddress())
        self.refused(build_block(n1, [a, b]), "a double spend inside the block")

        tip_cb = n1.getblock(n1.getbestblockhash())["tx"][0]
        cb = n1.getrawtransaction(tip_cb, 1)
        raw = n1.createrawtransaction([{"txid": tip_cb, "vout": 0}], {n1.getnewaddress(): cb["vout"][0]["value"] - Decimal("0.001")})
        immature = bytes.fromhex(n1.signrawtransaction(raw)["hex"])
        self.refused(build_block(n1, [immature]), "an immature coinbase spent")

        old_cb = bytes.fromhex(n1.getrawtransaction(n1.getblock(n1.getblockhash(5))["tx"][0]))
        self.refused(build_block(n1, coinbase_raw=old_cb), "a coinbase that repeats an unspent one (BIP30)")

        self.refused(build_block(n1, coinbase_value=next_block_value(n1) + 1), "a coinbase paying one satoshi too much")
        self.refused(build_block(n1, bad_merkle=True), "a wrong merkle root")

        self.log("a good block with a payment is taken by both, and the set is what the blocks give")
        good = spend(coins[1], n1.getnewaddress(), Decimal("0.01"))
        value = next_block_value(n1) + int(Decimal("0.01") * COIN)
        r, _ = self.both(build_block(n1, [good], coinbase_value=value), "the good block")
        assert_equal(r, None)
        assert_equal(n0.getblockcount(), 41)
        assert_equal(n1.getbestblockhash(), n0.getbestblockhash())
        assert n0.getrawtransaction(txid_of(good)), "the payment is not in the chain"
        info = n0.gettxoutsetinfo("coins")
        assert_equal(info["hash_serialized"], n0.gettxoutsetinfo("blocks")["hash_serialized"])
        assert_equal(info["hash_serialized"], n1.gettxoutsetinfo("blocks")["hash_serialized"])
        assert_equal(info["coins_check_failures"], 0)

        self.log("a wrong set does not mark a valid block failed: node 2 goes out of step at 45 and follows the chain to the end")
        self.connect_nodes(1, 2)
        n1.generate(9)                                # 42 .. 50, one of them with a payment
        n1.sendtoaddress(n1.getnewaddress(), 1)
        n1.generate(5)
        self.sync_blocks([n1, n2], timeout=120)
        assert_equal(n2.getblockcount(), 55)
        assert_equal(n2.getbestblockhash(), n1.getbestblockhash())
        assert "it will be rebuilt at the next start" in self.log_text(n2), "the set was not reported out of step"
        assert "COINS: rebuilding" not in self.log_text(n2), "the node stopped to rebuild the set inline"

        self.log("a restart without the break repairs it")
        n2.stop()
        n2.extra_args = [a for a in n2.extra_args if not a.startswith("-testcoinsbreak")]
        n2.start()
        assert_equal(n2.getblockcount(), 55)
        wait_until(lambda: "COINS: rebuilt" in self.log_text(n2), what="the rebuild at the start")
        assert_equal(n2.gettxoutsetinfo("coins")["hash_serialized"], n2.gettxoutsetinfo("blocks")["hash_serialized"])


if __name__ == "__main__":
    CoinsValidateBlocksTest().main()
