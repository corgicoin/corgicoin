#!/usr/bin/env python3
"""A merged-mined block whose proof is bad is fetched again from the next peer that announced it, not two minutes later.

The block hash does not cover the merged-mining proof, so a peer can send a copy of a block with a bad proof under the hash
of a good one. The node used to remember "asked for this a moment ago" and waited two minutes before asking anyone else.
Here two peers announce a block; the first answers with a copy whose parent header does not meet the target; the second must
be asked within seconds.
"""
import hashlib
import struct

from test_framework import CorgiTestFramework, wait_until
from mininode import P2PConnection
from auxpow_builder import build_auxpow


def dsha256(b):
    return hashlib.sha256(hashlib.sha256(b).digest()).digest()


class AuxPowRefetchTest(CorgiTestFramework):
    num_nodes = 1

    def run_test(self):
        node = self.nodes[0]
        node.generate(3)
        tip = bytes.fromhex(node.getbestblockhash())[::-1]

        # a merged-mined block on the tip: version carries the AuxPoW bit and chain ID 0xC6
        bits = 0x1d00ffff   # a hard target: the proof's parent header (built not to meet it) always fails the work check
        header = (struct.pack("<i", 0x00C60101) + tip + b"\x11" * 32 + struct.pack("<III", 1700000000, bits, 0))
        block_hash = dsha256(header)
        # the proof commits to this hash, but its parent header does not meet the target
        proof = bytes.fromhex(build_auxpow(block_hash[::-1].hex(), bits, meet_target=False))
        coinbase = (struct.pack("<i", 1) + b"\x01" + b"\x00" * 32 + b"\xff\xff\xff\xff" + b"\x02\x51\x51" + b"\xff\xff\xff\xff"
                    + b"\x01" + struct.pack("<q", 0) + b"\x01\x51" + struct.pack("<I", 0))
        payload = header + proof + b"\x01" + coinbase

        p1 = P2PConnection(node.p2p_port)
        p2 = P2PConnection(node.p2p_port)
        wait_until(lambda: p1.got_verack and p2.got_verack, what="both peers to finish the handshake")

        self.log("both peers announce the block; the node asks the first")
        p1.send_inv([(2, block_hash)])
        p2.send_inv([(2, block_hash)])
        wait_until(lambda: p1.counts.get("getdata", 0) >= 1, timeout=30, what="the first getdata (p1 %r, p2 %r)" % (p1.counts, p2.counts))
        assert p2.counts.get("getdata", 0) == 0, "the second peer was asked at once as well"

        self.log("the first peer answers with the bad-proof copy: the node asks the second within seconds")
        p1.send("block", payload)
        wait_until(lambda: p2.counts.get("getdata", 0) >= 1, timeout=30,
                   what="the second getdata (before the fix it came two minutes later; p1 %r, p2 %r)" % (p1.counts, p2.counts))
        p1.close()
        p2.close()


if __name__ == "__main__":
    AuxPowRefetchTest().main()
