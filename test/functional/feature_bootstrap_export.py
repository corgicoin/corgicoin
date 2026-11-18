#!/usr/bin/env python3
"""exportblocks writes the chain in the format -loadblock reads, and a fresh node started from the file has the same chain."""
import os

from test_framework import CorgiTestFramework, assert_equal, assert_raises_rpc_error, wait_until


class BootstrapExportTest(CorgiTestFramework):
    num_nodes = 2

    def run_test(self):
        source, fresh = self.nodes
        source.generate(130)
        path = os.path.join(source.datadir, "bootstrap.dat")

        self.log("the chain is written to a new file")
        info = source.exportblocks(path)
        assert_equal(info["blocks"], 131)             # the genesis block and 130 more
        assert_equal(info["bytes"], os.path.getsize(path))

        self.log("it will not overwrite a file, and refuses a bad range")
        assert_raises_rpc_error(-8, "exists already", source.exportblocks, path)
        assert_raises_rpc_error(-8, "out of bounds", source.exportblocks, path + ".2", 5, 9999)
        assert_raises_rpc_error(-8, "out of bounds", source.exportblocks, path + ".2", 50, 10)
        assert not os.path.exists(path + ".2")

        self.log("a range can be written: blocks 100 to 110 are 11 blocks")
        assert_equal(source.exportblocks(path + ".part", 100, 110)["blocks"], 11)

        self.log("a fresh node started with -loadblock ends up on the same chain")
        fresh.stop()
        fresh.start(["-loadblock=" + path])
        wait_until(lambda: fresh.getblockcount() == 130, timeout=120, what="the exported blocks to be loaded")
        assert_equal(fresh.getbestblockhash(), source.getbestblockhash())
        assert_equal(fresh.getblock(fresh.getblockhash(77))["hash"], source.getblockhash(77))


if __name__ == "__main__":
    BootstrapExportTest().main()
