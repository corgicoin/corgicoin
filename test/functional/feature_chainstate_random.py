#!/usr/bin/env python3
"""The unspent-output set stays equal to what the blocks give across a random run of payments, forks and reorganisations, and across a kill -9.

Two nodes (both this build), connected. Each round does payments, blocks, or a partition in which each side mines a different number of
blocks (so one reorganises when they are joined again). After every round both nodes' sets (gettxoutsetinfo "coins") equal what their blocks
give ("blocks"), with no check failures. Half way one node is killed with SIGKILL and started again: it must come back to the chain with the
set repaired by taking up from where it was (the catch-up), not rebuilt from the first block. CORGI_DIFF_SEED sets the run, CORGI_DIFF_ROUNDS
its length (default 10).

What makes it fail: a set that does not undo a block exactly on a reorganisation, an output lost or kept after a spend, or a restart that
trusts a set that is behind the index, would show as a hash that differs from the blocks' hash; a restart that rebuilds from the first block
would show in the log.
"""
import os
import random

from test_framework import CorgiTestFramework, JSONRPCException, assert_equal


class ChainstateRandomTest(CorgiTestFramework):
    num_nodes = 2

    def log_text(self, node):
        with open(node.debug_log, errors="replace") as f:
            return f.read()

    def check(self, what):
        self.sync_blocks(timeout=120)
        hashes = set()
        for i, n in enumerate(self.nodes):
            coins, blocks = n.gettxoutsetinfo("coins"), n.gettxoutsetinfo("blocks")
            assert_equal(coins["hash_serialized"], blocks["hash_serialized"], "%s: node %d: the set is not what the blocks give" % (what, i))
            assert_equal(coins["coins_check_failures"], 0, "%s: node %d: check failures" % (what, i))
            hashes.add(blocks["hash_serialized"])
        assert_equal(len(hashes), 1, "%s: the nodes' sets differ" % what)

    def pay(self, rng, nodes):
        for _ in range(rng.randint(1, 4)):
            try:
                self.nodes[rng.choice(nodes)].sendtoaddress(self.nodes[rng.randrange(2)].getnewaddress(), round(rng.uniform(0.5, 20), 2))
            except JSONRPCException:
                pass

    def run_test(self):
        seed = int(os.environ.get("CORGI_DIFF_SEED", "1"))
        rounds = int(os.environ.get("CORGI_DIFF_ROUNDS", "10"))
        rng = random.Random(seed)
        n0, n1 = self.nodes
        self.log("seed %d, %d rounds" % (seed, rounds))
        self.connect_nodes(0, 1)
        for n in self.nodes:
            n.generate(55)
            self.sync_blocks()
        self.check("start")

        for r in range(rounds):
            if r == rounds // 2:
                self.log("round %d: node 0 is killed (SIGKILL) and started again" % r)
                self.pay(rng, [0, 1])
                n0.generate(1)
                rebuilds = self.log_text(n0).count("COINS: rebuilding")
                n0.kill()
                n0.start()
                self.connect_nodes(0, 1)
                self.sync_blocks(timeout=120)
                assert_equal(self.log_text(n0).count("COINS: rebuilding"), rebuilds, "the restart rebuilt the set from the first block")
                self.check("after the kill")
            action = rng.choice(["pay", "mine", "fork", "fork"])
            if action == "pay":
                self.pay(rng, [0, 1])
                self.nodes[rng.randrange(2)].generate(1)
                self.check("round %d: payments" % r)
            elif action == "mine":
                self.nodes[rng.randrange(2)].generate(rng.randint(1, 3))
                self.check("round %d: blocks" % r)
            else:
                self.disconnect_nodes(0, 1)
                self.pay(rng, [0])
                self.pay(rng, [1])
                a = rng.randint(1, 4)
                b = a + rng.choice([1, 2, 3])
                n0.generate(a)
                n1.generate(b)
                self.connect_nodes(0, 1)
                self.check("round %d: reorganisation (%d blocks against %d)" % (r, a, b))
        self.log("done")


if __name__ == "__main__":
    ChainstateRandomTest().main()
