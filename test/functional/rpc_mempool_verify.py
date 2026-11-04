#!/usr/bin/env python3
"""getmempoolinfo and verifychain, including a verifychain run over a deliberately corrupted block."""
import os
from decimal import Decimal

from test_framework import CorgiTestFramework, assert_equal, assert_raises_rpc_error


class MempoolVerifyTest(CorgiTestFramework):
    num_nodes = 1

    def run_test(self):
        n0 = self.nodes[0]

        self.log("getmempoolinfo on an empty pool")
        info = n0.getmempoolinfo()
        assert_equal(info["size"], 0)
        assert_equal(info["bytes"], 0)
        assert_equal(info["minrelaytxfee"], Decimal(1))
        assert_raises_rpc_error(-1, None, n0.getmempoolinfo, "extra")

        self.log("size and bytes follow the transactions in the pool")
        n0.generate(51)
        txids = [n0.sendtoaddress(n0.getnewaddress(), 10), n0.sendtoaddress(n0.getnewaddress(), 20)]
        info = n0.getmempoolinfo()
        assert_equal(info["size"], 2)
        assert_equal(info["bytes"], sum(len(n0.getrawtransaction(t)) // 2 for t in txids))
        n0.generate(1)
        info = n0.getmempoolinfo()
        assert_equal((info["size"], info["bytes"]), (0, 0))

        self.log("verifychain accepts a healthy chain at every level and depth")
        assert n0.verifychain() is True
        assert n0.verifychain(1, 10) is True
        assert n0.verifychain(2, 0) is True
        assert n0.verifychain(2, 10) is True

        self.log("verifychain argument checks")
        assert_raises_rpc_error(-8, None, n0.verifychain, 3)
        assert_raises_rpc_error(-8, None, n0.verifychain, 0)
        assert_raises_rpc_error(-8, None, n0.verifychain, 1, -1)

        self.log("verifychain finds a corrupted block, and only when it is in range")
        height = 20
        coinbase = n0.getblock(n0.getblockhash(height))["tx"][0]
        raw = bytes.fromhex(n0.getrawtransaction(coinbase))
        n0.stop()
        path = os.path.join(n0.datadir, "regtest", "blk0001.dat")
        with open(path, "rb") as f:
            data = bytearray(f.read())
        offset = data.find(raw)
        assert offset != -1, "coinbase of block %d not found in blk0001.dat" % height
        assert_equal(data.count(raw), 1)
        data[offset + len(raw) // 2] ^= 0xFF  # changes the tx, so the merkle root no longer matches
        with open(path, "wb") as f:
            f.write(data)
        n0.start(["-checkblocks=1"])  # startup then only checks the tip, which is intact

        assert_equal(n0.verifychain(1, 1), True)    # tip only
        assert_equal(n0.verifychain(1, 10), True)   # block 20 is well below the last 10
        assert_equal(n0.verifychain(1, 0), False)   # whole chain
        assert_equal(n0.verifychain(2, 0), False)
        with open(n0.debug_log) as f:
            log = f.read()
        assert "verifychain: *** block %d" % height in log, "bad block not named in debug.log"


if __name__ == "__main__":
    MempoolVerifyTest().main()
