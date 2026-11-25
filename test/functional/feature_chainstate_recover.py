#!/usr/bin/env python3
"""The node recovers from a missing or damaged chainstate directory, and from a downgrade and upgrade through a release that does not know it.

One node. (a) the chainstate directory is deleted: the next start rebuilds the set from the blocks and carries on. (b) its files are
overwritten with garbage: the set cannot be opened, the node runs on the block index alone (it must not refuse to start, or stop following
the chain), and once the directory is removed the next start rebuilds it. (c) the release (v4.9.0.0, which has no chainstate and ignores the
directory) is started on the same data directory and mines blocks; then this build again: the set is behind the index by those blocks and is
brought up to date by taking them up (the catch-up), not rebuilt from the first block, and equals what the blocks give.

What makes it fail: a node that will not start with a damaged directory; a set trusted although it is behind (a hash that differs from the
blocks); a rebuild from the first block where a catch-up would do (the log line count).
"""
import os
import shutil

from test_framework import CorgiTestFramework, assert_equal


class ChainstateRecoverTest(CorgiTestFramework):
    num_nodes = 1

    def chainstate(self, node):
        d = node.datadir + "/regtest"
        return (d if os.path.isdir(d) else node.datadir) + "/chainstate"

    def log_text(self, node):
        with open(node.debug_log, errors="replace") as f:
            return f.read()

    def same_set(self, node):
        coins, blocks = node.gettxoutsetinfo("coins"), node.gettxoutsetinfo("blocks")
        assert_equal(coins["hash_serialized"], blocks["hash_serialized"])
        assert_equal(coins["coins_check_failures"], 0)

    def run_test(self):
        node = self.nodes[0]
        node.generate(45)
        tip = node.getbestblockhash()

        self.log("(a) the chainstate directory is deleted: rebuilt at the next start")
        node.stop()
        shutil.rmtree(self.chainstate(node))
        before = self.log_text(node).count("COINS: rebuilt")
        node.start()
        assert_equal(node.getbestblockhash(), tip)
        assert self.log_text(node).count("COINS: rebuilt") > before, "the set was not rebuilt"
        self.same_set(node)
        node.generate(3)
        self.same_set(node)

        self.log("(b) its files are overwritten with garbage: the node still starts and follows the chain")
        node.stop()
        for name in os.listdir(self.chainstate(node)):
            path = os.path.join(self.chainstate(node), name)
            if os.path.isfile(path):
                with open(path, "wb") as f:
                    f.write(b"garbage" * 100)
        node.start()
        assert_equal(node.getblockcount(), 48)
        node.generate(2)                                 # the index decides; the chain moves on
        assert_equal(node.getblockcount(), 50)
        tip = node.getbestblockhash()
        node.stop()
        shutil.rmtree(self.chainstate(node))
        node.start()
        assert_equal(node.getbestblockhash(), tip)
        self.same_set(node)

        if not self.options.alt_corgicoind or not os.path.isfile(self.options.alt_corgicoind):
            self.log("(c) skipped: no alternate (release) build given")
            return
        self.log("(c) a release that knows nothing of the chainstate mines on the same data directory, then this build again")
        node.stop()
        main_bin = node.binary
        node.binary = self.options.alt_corgicoind
        node.old_release = True                          # a release can abort while exiting; that is not what is tested
        node.start()
        assert_equal(node.getblockcount(), 50)
        node.generate(4)
        tip = node.getbestblockhash()
        node.stop()
        node.binary = main_bin
        node.old_release = False
        rebuilds = self.log_text(node).count("COINS: rebuilding")
        node.start()
        assert_equal(node.getblockcount(), 54)
        assert_equal(node.getbestblockhash(), tip)
        self.same_set(node)
        assert_equal(self.log_text(node).count("COINS: rebuilding"), rebuilds, "the set was rebuilt from the first block, not brought up to date")


if __name__ == "__main__":
    ChainstateRecoverTest().main()
