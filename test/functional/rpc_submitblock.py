#!/usr/bin/env python3
"""submitblock: accepted, duplicate, orphan, rejected and undecodable blocks."""
from test_framework import CorgiTestFramework, assert_equal, assert_raises_rpc_error


class SubmitBlockTest(CorgiTestFramework):
    num_nodes = 2   # not connected: node 1 only learns of blocks through submitblock

    @staticmethod
    def raw_block(node, blockhash):
        """Serialized block: header, transaction count, transactions."""
        header = node.getblockheader(blockhash, False)
        txids = node.getblock(blockhash)["tx"]
        assert len(txids) < 253
        return header + "%02x" % len(txids) + "".join(node.getrawtransaction(t) for t in txids)

    def run_test(self):
        miner, node = self.nodes
        miner.generate(3)
        hashes = [miner.getblockhash(h) for h in (1, 2, 3)]
        raw = [self.raw_block(miner, h) for h in hashes]
        assert_equal(node.getblockcount(), 0)

        self.log("a block that extends the tip is accepted: null, and the chain grows")
        assert_equal(node.submitblock(raw[0]), None)
        assert_equal(node.getblockcount(), 1)
        assert_equal(node.getbestblockhash(), hashes[0])

        self.log("submitting it again reports a duplicate")
        assert_equal(node.submitblock(raw[0]), "duplicate")
        assert_equal(node.getblockcount(), 1)

        self.log("a block whose parent is missing is held as an orphan, then connected when the parent arrives")
        assert_equal(node.submitblock(raw[2]), None)
        assert_equal(node.getblockcount(), 1)
        assert_equal(node.submitblock(raw[1]), None)
        assert_equal(node.getblockcount(), 3)
        assert_equal(node.getbestblockhash(), hashes[2])

        self.log("a block that fails validation is rejected and does not change the chain")
        miner.generate(1)
        bad = self.raw_block(miner, miner.getbestblockhash())
        corrupt = bad[:-8] + ("00000000" if bad[-8:] != "00000000" else "ffffffff")   # last transaction's lock time
        assert_equal(node.submitblock(corrupt), "rejected")
        assert_equal(node.getblockcount(), 3)

        self.log("the second argument is accepted and ignored")
        assert_equal(node.submitblock(bad, {}), None)
        assert_equal(node.getblockcount(), 4)

        self.log("undecodable input is an error, not a rejection")
        assert_raises_rpc_error(-22, None, node.submitblock, "zz")
        assert_raises_rpc_error(-22, None, node.submitblock, "")
        assert_raises_rpc_error(-22, None, node.submitblock, "00" * 10)
        assert_raises_rpc_error(-22, None, node.submitblock, raw[0][:-4])      # truncated
        assert_raises_rpc_error(-22, None, node.submitblock, raw[0] + "00")    # trailing bytes
        assert_equal(node.getblockcount(), 4)

        self.log("argument checks")
        assert_raises_rpc_error(-1, None, node.submitblock)
        assert_raises_rpc_error(-1, None, node.submitblock, raw[0], {}, "extra")
        assert_raises_rpc_error(-3, None, node.submitblock, 5)


if __name__ == "__main__":
    SubmitBlockTest().main()
