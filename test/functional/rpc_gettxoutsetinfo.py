#!/usr/bin/env python3
"""gettxoutsetinfo: the unspent set of the chain, worked out from the index and from the blocks, agrees, and agrees across nodes.

The set is the reference for any change to how coins are stored, so it is checked through spends in one block, change, a reorganisation
(rolled back and forward again) and a node that synced the same chain from nothing.
"""
from decimal import Decimal

from test_framework import CorgiTestFramework, assert_equal, assert_raises_rpc_error


class TxOutSetInfoTest(CorgiTestFramework):
    num_nodes = 2

    def both(self, node):
        index = node.gettxoutsetinfo("index")
        blocks = node.gettxoutsetinfo("blocks")
        assert_equal(index["bogus_spends"], 0)
        assert_equal(blocks["bogus_spends"], 0)
        for key in ("height", "bestblock", "txouts", "transactions", "total_amount", "hash_serialized"):
            assert_equal(index[key], blocks[key])
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


if __name__ == "__main__":
    TxOutSetInfoTest().main()
