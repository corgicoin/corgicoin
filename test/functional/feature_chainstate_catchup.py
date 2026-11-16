#!/usr/bin/env python3
"""The unspent set is brought up to date from a start point that is not on the chain: the node's own blocks are taken off, then the chain's put on.

A crash between the commit of the block index and the commit of the unspent set, in the middle of a reorganisation, leaves the set at a block
of the branch the chain has left. The test makes that state: a copy of the set made while the chain was on branch X, put back after the chain
moved to a longer branch Y. The node must end on the chain with a set equal to what the blocks give, by taking X off with its undo data and putting Y on,
without rebuilding from the first block.
"""
import os
import shutil

from test_framework import CorgiTestFramework, assert_equal


class ChainstateCatchupTest(CorgiTestFramework):
    num_nodes = 1

    def chainstate(self, node):
        d = node.datadir + "/regtest"
        return (d if os.path.isdir(d) else node.datadir) + "/chainstate"

    def log_text(self, node):
        with open(node.debug_log, errors="replace") as f:
            return f.read()

    def run_test(self):
        node = self.nodes[0]
        node.generate(40)
        node.generate(2)                            # branch X: blocks 41 and 42
        x1 = node.getblockhash(41)
        node.stop()
        saved = self.chainstate(node) + ".saved"
        shutil.rmtree(saved, ignore_errors=True)
        shutil.copytree(self.chainstate(node), saved)        # the set for X2
        node.start()

        self.log("the chain leaves branch X for a longer branch Y")
        node.invalidateblock(x1)
        assert_equal(node.getblockcount(), 40)
        node.generate(4)                            # branch Y: blocks 41 to 44
        tip = node.getbestblockhash()
        node.stop()

        self.log("the set of X2 is put back (as after a crash in the reorganisation)")
        shutil.rmtree(self.chainstate(node))
        shutil.copytree(saved, self.chainstate(node))
        before = self.log_text(node).count("COINS: rebuilding")
        node.start()
        assert_equal(node.getblockcount(), 44)
        assert_equal(node.getbestblockhash(), tip)
        text = self.log_text(node)
        assert "blocks off the chain's branch" in text, "the set was not mended by taking its own branch off"
        assert_equal(text.count("COINS: rebuilding"), before)          # and not rebuilt from the first block

        self.log("it is now the set the blocks give")
        coins = node.gettxoutsetinfo("coins")
        blocks = node.gettxoutsetinfo("blocks")
        assert_equal(coins["hash_serialized"], blocks["hash_serialized"])
        assert_equal(coins["height"], 44)


if __name__ == "__main__":
    ChainstateCatchupTest().main()
