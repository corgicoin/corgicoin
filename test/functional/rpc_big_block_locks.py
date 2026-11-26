#!/usr/bin/env python3
"""A block of thousands of transactions, and a deep rollback, go through the block database (plan item 5.3).

The block database was opened with room for 10,000 locks. Connecting or disconnecting a block takes locks in proportion to the
transactions in it, and a rollback or reorganisation does it for every block in one database transaction, so a big enough block
or a deep enough reorganisation failed on a node with the small table (and on that one only, depending on how its pages fell).
The limit is now 537,000 as in Bitcoin 0.8, and can be set with -dblocks.

A chain of transactions (each spends the one before) is how a block gets many transactions out of one coin. The block is
mined from the memory pool, which holds up to the generation size limit. It is then disconnected and connected again.
"""
from decimal import Decimal

from test_framework import CorgiTestFramework, assert_equal

CHAIN = 2400


class BigBlockLocksTest(CorgiTestFramework):
    num_nodes = 1

    def run_test(self):
        node = self.nodes[0]
        node.generate(101)

        self.log("a chain of %d transactions, each spending the one before" % CHAIN)
        # each transaction gives up 1, so the coin must outlast the chain: the largest one (rewards vary, and the first big one may be only a few thousand)
        coin = max(node.listunspent(), key=lambda u: u["amount"])
        assert coin["amount"] > CHAIN + 100, coin["amount"]
        prev = {"txid": coin["txid"], "vout": coin["vout"]}
        amount = coin["amount"]
        dest = node.getnewaddress()
        for _ in range(CHAIN):
            amount -= Decimal(1)
            raw = node.createrawtransaction([prev], {dest: amount})
            signed = node.signrawtransaction(raw)
            assert signed["complete"]
            txid = node.sendrawtransaction(signed["hex"])
            prev = {"txid": txid, "vout": 0}
        assert_equal(node.getmempoolinfo()["size"], CHAIN)

        self.log("they are mined into blocks (the generation size limit splits them), all connected")
        height = node.getblockcount()
        blocks = 0
        while node.getmempoolinfo()["size"] > 0 and blocks < 6:
            node.generate(1)
            blocks += 1
        assert_equal(node.getmempoolinfo()["size"], 0)
        biggest = max(node.getblock(node.getblockhash(h))["tx"].__len__() for h in range(height + 1, height + blocks + 1))
        assert biggest > 500, biggest
        self.log("the biggest block has %d transactions" % biggest)

        self.log("rolled back to before them, and forward again, in one step each way")
        first = node.getblockhash(height + 1)
        tip = node.getbestblockhash()
        node.invalidateblock(first)
        assert_equal(node.getblockcount(), height)
        node.reconsiderblock(first)
        assert_equal(node.getbestblockhash(), tip)
        assert_equal(node.getblockcount(), height + blocks)

        self.log("and a deep rollback: 300 blocks")
        node.generate(300)
        top = node.getbestblockhash()
        deep = node.getblockhash(height + blocks + 1)
        node.invalidateblock(deep)
        assert_equal(node.getblockcount(), height + blocks)
        node.reconsiderblock(deep)
        assert_equal(node.getbestblockhash(), top)


if __name__ == "__main__":
    BigBlockLocksTest().main()
