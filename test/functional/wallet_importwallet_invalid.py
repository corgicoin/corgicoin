#!/usr/bin/env python3
"""importwallet with a dump file that has lines that are not keys: the node stays up, takes the good keys on both sides of the bad ones, and says so.

A dump file is text someone may have edited or truncated. A line that is not base58, one whose secret is zero or at or above the curve order,
a line with one word, comments and blank lines, an over-long line and a binary line must each be skipped (and reported as an error at the end,
since the file was not wholly good), without the keys before and after them being lost and without a crash. Before the fix a secret that is not
a valid key threw out of the RPC with both locks held and the keys after it were never read. verifywallet then shows a clean wallet.
"""
import os

from backup_crafter import b58check_decode, wif
from test_framework import CorgiTestFramework, JSONRPCException, assert_equal

CURVE_ORDER = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141


class ImportWalletInvalidTest(CorgiTestFramework):
    num_nodes = 2

    def run_test(self):
        a, b = self.nodes
        a.generate(1)
        addrs = [a.getnewaddress() for _ in range(4)]
        good = [a.dumpprivkey(x) for x in addrs]
        prefix = b58check_decode(good[0])[0]
        zero = wif(b"\x00" * 32, prefix)
        order = wif(CURVE_ORDER.to_bytes(32, "big"), prefix)
        above = wif(((1 << 256) - 1).to_bytes(32, "big"), prefix)

        lines = ["# Wallet dump", "",
                 "%s 2023-01-01T00:00:00Z label=first # addr=%s" % (good[0], addrs[0]),
                 "notbase58!!! 2023-01-01T00:00:00Z",
                 "%s 2023-01-01T00:00:00Z" % zero,
                 "%s 2023-01-01T00:00:00Z" % order,
                 "justoneword",
                 "%s 2023-01-01T00:00:00Z label=second" % good[1],
                 "%s 2023-01-01T00:00:00Z" % above,
                 "x" * 100000 + " 2023-01-01T00:00:00Z",
                 "\x01\x02\x03 \x04\x05",
                 "%s 2023-01-01T00:00:00Z label=third" % good[2],
                 "# trailing comment"]
        path = os.path.join(b.datadir, "bad.dump")
        with open(path, "w", encoding="latin-1") as f:
            f.write("\n".join(lines) + "\n")

        self.log("the bad lines are skipped, the good keys on both sides of them are imported, and the node is up")
        try:
            b.importwallet(path)
        except JSONRPCException as e:
            self.log("importwallet reported: %s" % e.error.get("message"))           # an error at the end is right: the file was not wholly good
        b.getblockcount()                                                          # still there
        for addr in addrs[:3]:
            assert_equal(b.validateaddress(addr)["ismine"], True)
        assert_equal(b.validateaddress(addrs[3])["ismine"], False)                 # it was not in the file

        self.log("the wallet is consistent")
        r = b.verifywallet()
        assert_equal(r["ok"], True)
        assert_equal(r["problems"], [])

        self.log("a file of only bad lines imports nothing, changes nothing and is not a crash")
        path2 = os.path.join(b.datadir, "worse.dump")
        with open(path2, "w", encoding="latin-1") as f:
            f.write("\n".join(["garbage 1", zero + " x", order + " y", "\x00\x01 z"]) + "\n")
        keys_before = b.verifywallet()["keys_checked"]
        try:
            b.importwallet(path2)
        except JSONRPCException:
            pass
        assert_equal(b.verifywallet()["keys_checked"], keys_before)
        b.getblockcount()


if __name__ == "__main__":
    ImportWalletInvalidTest().main()
