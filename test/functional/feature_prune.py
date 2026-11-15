#!/usr/bin/env python3
"""Pruning (-prune): old block files are deleted, and the node goes on validating from the unspent set.

A pruned node follows a full node's chain while its oldest block files go (the test shrinks the files and the limits so a few hundred
blocks are enough). It still takes a transaction that spends a coin from a deleted block, and the block that confirms it; it answers
gettxout for such a coin; it says "pruned" for the block itself; it keeps all this across a restart; it does not offer old blocks to
others (it does not claim NODE_NETWORK); and a data directory that was pruned does not start without -prune.
"""
import os

from test_framework import CorgiTestFramework, AssertionFailed, assert_equal, assert_raises_rpc_error, wait_until

BLOCKS = 300
PRUNE_ARGS = ["-prune=1", "-testprunebytes=40000", "-testblockfilesize=20000", "-testpruneblocks=40"]



class PruneTest(CorgiTestFramework):
    num_nodes = 3
    extra_args = [["-testblockfilesize=20000"], PRUNE_ARGS, []]

    def datadir_of(self, node):
        d = node.datadir + "/regtest"
        return d if os.path.isdir(d) else node.datadir

    def run_test(self):
        full, pruned, fresh = self.nodes
        for _ in range(BLOCKS // 100):
            full.generate(100)
        self.connect_nodes(1, 0)
        wait_until(lambda: pruned.getblockcount() == BLOCKS, timeout=120, what="the pruned node to follow the chain")
        assert_equal(pruned.getbestblockhash(), full.getbestblockhash())

        self.log("old block files are gone, the list of them is kept, and the node says so")
        info = pruned.getblockchaininfo()
        assert info["pruned"] and info["pruned_files"] >= 1 and info["pruneheight"] > 1, info
        files = [f for f in os.listdir(self.datadir_of(pruned)) if f.startswith("blk") and f.endswith(".dat") and f not in ("blkindex.dat", "blkpruned.dat")]
        full_files = [f for f in os.listdir(self.datadir_of(full)) if f.startswith("blk") and f.endswith(".dat") and f not in ("blkindex.dat", "blkpruned.dat")]
        assert len(files) < len(full_files), (files, full_files)
        assert os.path.exists(self.datadir_of(pruned) + "/blkpruned.dat")
        assert_equal(full.getblockchaininfo()["pruned"], False)

        self.log("the first block is pruned; the last is not")
        old_hash = pruned.getblockhash(1)
        assert_raises_rpc_error(-1, "pruned", pruned.getblock, old_hash)
        assert_equal(pruned.getblock(pruned.getbestblockhash())["height"], BLOCKS)
        assert_equal(full.getblock(old_hash)["height"], 1)

        self.log("gettxout answers for a coin in a deleted block: the same as the full node")
        coinbase = full.getblock(old_hash)["tx"][0]
        a = full.gettxout(coinbase, 0)
        b = pruned.gettxout(coinbase, 0)
        assert a is not None and b is not None
        assert_equal(b["value"], a["value"])
        assert_equal(b["coinbase"], True)
        assert_equal(b["confirmations"], a["confirmations"])

        self.log("a transaction that spends it is taken into the pool and then confirmed")
        coin = max(full.listunspent(), key=lambda u: u["confirmations"])
        assert coin["confirmations"] > BLOCKS - 20, coin          # one of the first blocks' coinbases
        raw = full.createrawtransaction([{"txid": coin["txid"], "vout": coin["vout"]}], {full.getnewaddress(): coin["amount"] - 1})
        signed = full.signrawtransaction(raw)
        assert signed["complete"]
        txid = full.sendrawtransaction(signed["hex"])
        wait_until(lambda: txid in pruned.getrawmempool(), what="the pruned node to take a spend of a deleted block's coin")
        full.generate(1)
        wait_until(lambda: pruned.getblockcount() == BLOCKS + 1, what="the block with it")
        assert_equal(pruned.getbestblockhash(), full.getbestblockhash())
        assert txid not in pruned.getrawmempool()
        assert pruned.gettxout(txid, 0) is not None

        self.log("it is the same after a restart")
        info_before = pruned.getblockchaininfo()
        pruned.stop()
        pruned.start()
        info_after = pruned.getblockchaininfo()
        assert_equal(info_after["pruned_files"], info_before["pruned_files"])
        assert_equal(info_after["pruneheight"], info_before["pruneheight"])
        self.connect_nodes(1, 0)
        full.generate(5)
        wait_until(lambda: pruned.getblockcount() == BLOCKS + 6, what="the pruned node to follow after a restart")
        assert_equal(pruned.getbestblockhash(), full.getbestblockhash())

        self.log("a pruned node does not offer old blocks: it does not claim NODE_NETWORK, and a new node does not sync from it")
        peers = full.getpeerinfo()
        assert len(peers) == 1 and int(peers[0]["services"], 16) & 1 == 0, peers
        self.connect_nodes(2, 1)
        wait_until(lambda: fresh.getconnectioncount() > 0, what="the new node to connect")
        __import__("time").sleep(5)
        assert_equal(fresh.getblockcount(), 0)

        self.log("a data directory that was pruned does not start without -prune")
        pruned.stop()
        pruned.extra_args = []
        try:
            pruned.start()
        except AssertionFailed:
            pass
        else:
            raise AssertionError("a pruned data directory started without -prune")
        with open(pruned.stderr_log, errors="replace") as f:
            assert "was pruned" in f.read(), "the refusal does not say why"
        pruned.extra_args = PRUNE_ARGS
        pruned.start()
        assert_equal(pruned.getblockcount(), BLOCKS + 6)


if __name__ == "__main__":
    PruneTest().main()
