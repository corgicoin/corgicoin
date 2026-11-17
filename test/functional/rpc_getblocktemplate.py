#!/usr/bin/env python3
"""getblocktemplate: works with no argument and on regtest with no peers; a submit reports duplicate, rejected, undecodable.

Before: the call needed a parameter object ("params.size() != 1"), refused to run without peers (even on regtest, where
generate and createauxblock do), threw on undecodable data, and answered "rejected" for a block it already had.
"""
from test_framework import CorgiTestFramework, assert_equal, assert_raises_rpc_error


class GetBlockTemplateTest(CorgiTestFramework):
    num_nodes = 2   # not connected: node 1 only learns of blocks through the template submit

    def run_test(self):
        miner, node = self.nodes
        miner.generate(2)

        self.log("no argument, no peers: a template comes back (regtest)")
        t = node.getblocktemplate()
        assert_equal(t["height"], 1)
        assert_equal(t["previousblockhash"], node.getbestblockhash())
        for key in ("version", "bits", "target", "coinbasevalue", "curtime", "mintime"):
            assert key in t, key

        self.log("an empty object works too, and a non-object is refused")
        assert_equal(node.getblocktemplate({})["height"], 1)
        assert_raises_rpc_error(-8, None, node.getblocktemplate, "template")

        # no longpollid: under BIP 22 a client that sees one sends it back and expects the call to wait, and this one
        # cannot (it would hold cs_main for the whole poll), so those clients would busy-loop on it
        assert "longpollid" not in t

        self.log("submit: duplicate, undecodable data, rejected")
        raw = []
        for h in (1, 2):
            bh = miner.getblockhash(h)
            header = miner.getblockheader(bh, False)
            txids = miner.getblock(bh)["tx"]
            raw.append(header + "%02x" % len(txids) + "".join(miner.getrawtransaction(x) for x in txids))
        # node 1 mined its own block 1 above, so the miner's block 1 is a different block; submit block 2 first
        assert_equal(miner.getblocktemplate({"mode": "submit", "data": raw[1]}), "duplicate")
        assert_raises_rpc_error(-22, None, node.getblocktemplate, {"mode": "submit", "data": "zz"})
        assert_raises_rpc_error(-22, None, node.getblocktemplate, {"mode": "submit", "data": "00"})
        assert_raises_rpc_error(-22, None, node.getblocktemplate, {"mode": "submit"})
        corrupt = raw[1][:-8] + ("00000000" if raw[1][-8:] != "00000000" else "ffffffff")
        assert_equal(node.getblocktemplate({"mode": "submit", "data": corrupt}), "rejected")


if __name__ == "__main__":
    GetBlockTemplateTest().main()
