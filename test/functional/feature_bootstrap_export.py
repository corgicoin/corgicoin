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

        if os.name != "nt":
            self.log("nor through a symlink that points nowhere, nor over a file the node cannot read")
            target = os.path.join(source.datadir, "elsewhere.dat")
            link = os.path.join(source.datadir, "link.dat")
            os.symlink(target, link)
            assert_raises_rpc_error(-8, "exists already", source.exportblocks, link, 0, 5)
            assert not os.path.exists(target), "the export followed the symlink"
            locked = os.path.join(source.datadir, "locked.dat")
            with open(locked, "w") as f:
                f.write("keep me")
            os.chmod(locked, 0o200)
            assert_raises_rpc_error(-8, "exists already", source.exportblocks, locked, 0, 5)
            os.chmod(locked, 0o600)
            with open(locked) as f:
                assert_equal(f.read(), "keep me")

        self.log("a relative name is in the data directory")
        info = source.exportblocks("relative.dat", 0, 5)
        assert_equal(os.path.normpath(info["file"]), os.path.normpath(os.path.join(source.datadir, "regtest", "relative.dat")))
        assert os.path.exists(info["file"])

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
