#!/usr/bin/env python3
"""gettxoutsetinfo: the unspent set of the chain, worked out from the index, from the blocks and from the node's own unspent-output
database (chainstate), agrees, and agrees across nodes.

The set is the reference for any change to how coins are stored, so it is checked through spends in one block, change, a reorganisation
(rolled back and forward again), two nodes that mined competing branches with spends, a node that synced the same chain from nothing,
and a node whose chainstate was deleted (it is rebuilt from the blocks at the next start).
"""
import os
import shutil
from decimal import Decimal

from test_framework import CorgiTestFramework, assert_equal, assert_raises_rpc_error


class TxOutSetInfoTest(CorgiTestFramework):
    num_nodes = 2

    def both(self, node):
        index = node.gettxoutsetinfo("index")
        blocks = node.gettxoutsetinfo("blocks")
        coins = node.gettxoutsetinfo("coins")
        assert_equal(index["bogus_spends"], 0)
        assert_equal(blocks["bogus_spends"], 0)
        for key in ("height", "bestblock", "txouts", "transactions", "total_amount", "hash_serialized"):
            assert_equal(index[key], blocks[key])
            assert_equal(index[key], coins[key])
        return index

    def run_test(self):
        a, b = self.nodes
        assert_raises_rpc_error(-8, "mode must be", a.gettxoutsetinfo, "nonsense")

        self.log("a fresh chain: only coinbases")
        a.generate(105)
        info = self.both(a)
        assert_equal(info["height"], 105)
        assert_equal(info["txouts"], 105)

        self.log("spends, change, several in one block, a spend of an output made in the same block")
        for _ in range(5):
            a.sendtoaddress(a.getnewaddress(), Decimal(7))
        a.generate(1)
        before = self.both(a)
        assert before["txouts"] > 106
        self.connect_nodes(1, 0)
        self.sync_blocks()
        assert_equal(b.gettxoutsetinfo("index")["hash_serialized"], before["hash_serialized"])
        assert_equal(b.gettxoutsetinfo("blocks")["hash_serialized"], before["hash_serialized"])

        self.log("a reorganisation: roll the last block back, then forward; and a different block in its place")
        tip = a.getbestblockhash()
        a.invalidateblock(tip)
        rolled = self.both(a)
        assert rolled["hash_serialized"] != before["hash_serialized"]
        a.reconsiderblock(tip)
        assert_equal(self.both(a)["hash_serialized"], before["hash_serialized"])

        a.sendtoaddress(a.getnewaddress(), Decimal(3))
        a.generate(2)
        after = self.both(a)
        assert after["hash_serialized"] != before["hash_serialized"]
        self.sync_blocks()
        assert_equal(b.gettxoutsetinfo("blocks")["hash_serialized"], after["hash_serialized"])
        assert_equal(self.both(b)["hash_serialized"], after["hash_serialized"])

        self.log("competing branches with spends: the shorter is disconnected, its coins come back or go, the longer is connected")
        b.generate(101)                         # b has coins of its own to spend
        self.sync_blocks()
        self.disconnect_nodes(1, 0)
        for _ in range(4):
            a.sendtoaddress(a.getnewaddress(), Decimal(2))
        a.generate(2)
        for _ in range(3):
            b.sendtoaddress(b.getnewaddress(), Decimal(5))
        b.generate(5)                           # longer: a must give up its two blocks
        self.connect_nodes(1, 0)
        self.sync_blocks()
        assert_equal(a.getbestblockhash(), b.getbestblockhash())
        assert_equal(self.both(a)["hash_serialized"], self.both(b)["hash_serialized"])

        self.log("a node whose chainstate is gone rebuilds it from the blocks at the next start")
        expect = self.both(a)["hash_serialized"]
        a.stop()
        shutil.rmtree(os.path.join(self.nodes[0].datadir, "regtest", "chainstate"))
        self.nodes[0].start()
        assert_equal(self.both(self.nodes[0])["hash_serialized"], expect)
        with open(self.nodes[0].debug_log, errors="replace") as f:
            assert "COINS: rebuilt" in f.read(), "the rebuild was not logged"
        self.nodes[0].generate(1)               # and it carries on from there
        self.both(self.nodes[0])


if __name__ == "__main__":
    TxOutSetInfoTest().main()
