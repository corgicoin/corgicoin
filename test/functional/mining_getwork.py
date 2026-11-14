#!/usr/bin/env python3
"""getwork: work comes back on regtest with no peers, a solved one is accepted as a block, and a bad one is refused.

Before, getwork (like getblocktemplate) answered "CorgiCoin is not connected!" on a regtest node, so external-miner support could
not be tested at all. The work is 128 bytes in which every 4-byte word is byte-reversed; the header is the first 80 of them.
"""
import struct

from test_framework import CorgiTestFramework, assert_equal
from auxpow_builder import scrypt_pow


def swap_words(b):
    return b"".join(b[i:i + 4][::-1] for i in range(0, len(b), 4))


class GetWorkTest(CorgiTestFramework):
    num_nodes = 1

    def solve(self, work):
        data = swap_words(bytes.fromhex(work["data"]))
        header = bytearray(data[:80])
        target = int.from_bytes(bytes.fromhex(work["target"]), "little")
        for nonce in range(1 << 22):
            struct.pack_into("<I", header, 76, nonce)
            if scrypt_pow(bytes(header)) <= target:
                return swap_words(bytes(header) + data[80:]).hex()
        raise AssertionError("no nonce found")

    def run_test(self):
        node = self.nodes[0]
        node.generate(2)

        self.log("work comes back with no peers (regtest)")
        work = node.getwork()
        for key in ("data", "target", "midstate", "hash1"):
            assert key in work, key
        assert_equal(len(work["data"]), 256)

        self.log("a solved piece of work becomes the next block")
        solved = self.solve(work)
        assert_equal(node.getwork(solved), True)
        assert_equal(node.getblockcount(), 3)

        self.log("work for a block that is no longer the tip, and made-up work, are not accepted")
        stale = node.getwork()
        solved_stale = self.solve(stale)
        node.generate(1)                       # the tip moves on
        assert_equal(node.getwork(solved_stale), False)
        assert_equal(node.getblockcount(), 4)
        garbage = bytearray(bytes.fromhex(self.solve(node.getwork())))
        garbage[8:12] = b"\xff\xff\xff\xff"     # a different merkle root than any work handed out
        try:
            assert_equal(node.getwork(bytes(garbage).hex()), False)
        except Exception as e:
            assert "Invalid" in str(e) or "-22" in str(e) or "-8" in str(e), str(e)
        assert_equal(node.getblockcount(), 4)


if __name__ == "__main__":
    GetWorkTest().main()
