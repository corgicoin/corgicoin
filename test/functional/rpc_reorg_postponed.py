#!/usr/bin/env python3
"""A reorganisation whose last block fails to connect leaves the node on the last block that did connect (plan item 5.1).

When a branch has much more work than the tip, the node switches to part of it in one step and connects the rest afterwards, one
block at a time ("postponed" reconnects). If one of those later blocks fails, the node used to set its in-memory tip to the top
of the branch anyway: memory said B6, the database ended on B5, templates were built on a block that never connected, and a
restart came back on a different tip.

Here node 0 holds a 3-block chain, and is given a 5-block branch of valid blocks plus a sixth whose coinbase pays too much.
The branch is held back with invalidateblock so that it is acquired in one jump when it is reconsidered. The best block must be
the fifth block of the branch, in memory (getbestblockhash, a block template) and after a restart.
"""
from rpc_failed_block import FailedBlockTest
from test_framework import CorgiTestFramework, assert_equal, assert_raises_rpc_error


def raw_block(node, blockhash):
    """Serialized block: header, transaction count, transactions."""
    header = node.getblockheader(blockhash, False)
    txids = node.getblock(blockhash)["tx"]
    assert len(txids) < 253
    return header + "%02x" % len(txids) + "".join(node.getrawtransaction(t) for t in txids)


class ReorgPostponedTest(CorgiTestFramework):
    num_nodes = 2

    def run_test(self):
        victim, builder = self.nodes

        self.log("a 3-block chain on node 0; a 5-block branch of valid blocks from the same genesis on node 1")
        victim.generate(3)
        builder.generate(5)
        branch = [builder.getblockhash(h) for h in range(1, 6)]
        raws = [raw_block(builder, h) for h in branch]

        self.log("a sixth block on the branch that cannot connect: its coinbase pays far too much")
        tip5 = builder.getblock(branch[4])
        raw6, hash6 = FailedBlockTest.block_on(None, builder, bytes.fromhex(branch[4])[::-1], tip5["time"] + 60, 0x66, True)

        self.log("node 0 is given the branch while its first block is invalidated, so none of it takes over yet")
        victim.submitblock(raws[0])
        victim.invalidateblock(branch[0])
        for raw in raws[1:]:
            victim.submitblock(raw)
        victim.submitblock(raw6)
        assert_equal(victim.getblockcount(), 3)

        self.log("reconsidering it makes the node jump to the branch: five blocks connect, the sixth does not")
        try:
            victim.reconsiderblock(branch[0])
        except Exception as e:
            assert "could not switch" in str(e), str(e)     # it tried the sixth block and said so
        assert_equal(victim.getblockcount(), 5)             # the fifth block of the branch is at height 5
        assert_equal(victim.getbestblockhash(), branch[4])

        self.log("block templates are built on that block, not on the one that never connected")
        assert_equal(victim.getblocktemplate()["previousblockhash"], branch[4])

        self.log("and the same tip is there after a restart (the database ended on it)")
        victim.stop()
        victim.start()
        assert_equal(victim.getbestblockhash(), branch[4])
        assert_equal(victim.getblockcount(), 5)


if __name__ == "__main__":
    ReorgPostponedTest().main()
