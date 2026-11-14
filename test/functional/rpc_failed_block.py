#!/usr/bin/env python3
"""A block that cannot be connected is marked failed, and a block built on it is not tried again.

The block below is well formed and carries valid proof of work, but its coinbase pays one satoshi too much, which only
ConnectBlock notices. Before the failed flag, every block built on it started a whole reorganisation that ended at the same
invalid block again.
"""
import struct

from auxpow_builder import compact_to_target, dsha256, scrypt_pow
import hashlib
from test_framework import CorgiTestFramework, assert_equal

MSG = "coinbase pays too much"


def read_compact(b, i):
    n = b[i]
    if n < 0xFD:
        return n, i + 1
    if n == 0xFD:
        return struct.unpack_from("<H", b, i + 1)[0], i + 3
    return struct.unpack_from("<I", b, i + 1)[0], i + 5


class FailedBlockTest(CorgiTestFramework):
    num_nodes = 1

    def block_on(self, node, prev_internal, when, extra, too_rich):
        """Header and coinbase of a block on prev_internal (a hash in internal byte order), modelled on block 1."""
        model = node.getblock(node.getblockhash(1))
        cb = bytearray(bytes.fromhex(node.getrawtransaction(model["tx"][0])))
        header = bytearray(bytes.fromhex(node.getblockheader(node.getblockhash(1), False)))
        i = 4
        nin, i = read_compact(cb, i)
        assert nin == 1
        i += 36
        slen, i = read_compact(cb, i)
        cb[i + slen - 1] = extra          # unique coinbase for each block
        i += slen + 4
        nout, i = read_compact(cb, i)
        if too_rich:
            struct.pack_into("<q", cb, i, struct.unpack_from("<q", cb, i)[0] + 1)
        header[4:36] = prev_internal
        header[36:68] = dsha256(bytes(cb))
        header[68:72] = struct.pack("<I", when)
        target = compact_to_target(struct.unpack_from("<I", header, 72)[0])
        for nonce in range(1 << 24):
            struct.pack_into("<I", header, 76, nonce)
            digest = hashlib.scrypt(bytes(header), salt=bytes(header), n=1024, r=1, p=1, dklen=32)
            if int.from_bytes(digest, "little") <= target:
                return (bytes(header) + b"\x01" + bytes(cb)).hex(), digest
        raise AssertionError("no nonce found")

    def count(self, node):
        with open(node.debug_log, errors="replace") as f:
            return f.read().count(MSG)

    def run_test(self):
        node = self.nodes[0]
        node.generate(3)
        tip = node.getbestblockhash()
        tip_time = node.getblock(tip)["time"]
        tip_internal = bytes.fromhex(tip)[::-1]

        self.log("a block whose coinbase pays too much is not connected")
        raw4, hash4 = self.block_on(node, tip_internal, tip_time + 60, 0x44, True)
        node.submitblock(raw4)
        assert_equal(node.getblockcount(), 3)
        assert_equal(node.getbestblockhash(), tip)
        assert_equal(self.count(node), 1)

        self.log("a block built on it is not tried: no second attempt at the invalid block")
        raw5, hash5 = self.block_on(node, hash4, tip_time + 120, 0x55, False)
        node.submitblock(raw5)
        assert_equal(node.getblockcount(), 3)
        assert_equal(self.count(node), 1)

        self.log("honest blocks still extend the real tip")
        node.generate(1)
        assert_equal(node.getblockcount(), 4)


if __name__ == "__main__":
    FailedBlockTest().main()
