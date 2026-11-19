#!/usr/bin/env python3
"""Headers-first: merged-mined headers are checked, and side-branch headers are capped.

Three nodes, each started with -headersfirst=1 and each given its own peer (a refused peer is scored, and a banned address would
shut out the next case):
  a  a header with the AuxPoW bit and a bad proof is refused (and the proof check says so);
  b  a header after the AuxPoW fork with a valid proof but another chain's ID is refused (the proof is good, the rule is the chain ID);
  c  side-branch headers (siblings of the tip, each with valid work) are kept up to the cap, then the branch headers are dropped and
     the peer scored. The cap is 50000 for real: regtest lowers it with -testmaxbranchheaders.
"""
import struct

from auxpow_builder import build_auxpow, compact_to_target, scrypt_pow
from mininode import P2PConnection, sha256d
from test_framework import CorgiTestFramework, assert_equal, wait_until

AUXPOW_FORK_REGTEST = 200
CHAIN_ID = 0xC6
OTHER_CHAIN_ID = 0x1234
VERSION_AUXPOW_BIT = 1 << 8
CAP = 4


def varint(n):
    return bytes([n]) if n < 253 else b"\xfd" + struct.pack("<H", n)


def raw_header(version, prev_hex, merkle, time, bits, nonce):
    return struct.pack("<i32s32sIII", version, bytes.fromhex(prev_hex)[::-1], merkle, time, bits, nonce)


class HeadersFirstLimitsTest(CorgiTestFramework):
    num_nodes = 3
    extra_args = [["-headersfirst=1"], ["-headersfirst=1"], ["-headersfirst=1", "-testmaxbranchheaders=%d" % CAP]]

    def log_text(self, node):
        with open(node.debug_log, errors="replace") as f:
            return f.read()

    def aux_header(self, node, chain_id, valid_proof):
        tip = node.getblock(node.getbestblockhash())
        version = (tip["version"] & 0xFF) | VERSION_AUXPOW_BIT | (chain_id << 16)
        bits = int(tip["bits"], 16)
        header = raw_header(version, tip["hash"], b"\x42" * 32, tip["time"] + 1, bits, 0)
        block_hash = sha256d(header)[::-1].hex()          # what the proof must commit to
        proof = bytes.fromhex(build_auxpow(block_hash, bits, chain_id, meet_target=valid_proof))
        return header + proof + b"\x00"

    def send_one(self, node, payload):
        peer = P2PConnection(node.p2p_port, start_height=0)
        wait_until(lambda: peer.got_verack, what="verack")
        peer.send("headers", varint(1) + payload)
        return peer

    def run_test(self):
        a, b, c = self.nodes
        for n in (a, b):
            n.generate(AUXPOW_FORK_REGTEST + 5)
        c.generate(6)

        self.log("an AuxPoW header with a proof that does not meet the work is refused")
        tip = a.getbestblockhash()
        peer = self.send_one(a, self.aux_header(a, CHAIN_ID, valid_proof=False))
        wait_until(lambda: "bad header from" in self.log_text(a), what="the bad header to be refused")
        assert "hash doesn't match nBits" in self.log_text(a), "the parent block's work should be what failed"
        peer.send("ping", b"\x00" * 8)
        wait_until(lambda: peer.counts.get("pong", 0) >= 1 or peer.closed, what="the node to carry on")
        assert_equal(a.getbestblockhash(), tip)
        assert_equal(a.getblockchaininfo()["header_only_entries"], 0)

        self.log("an AuxPoW header with a good proof but not this chain's ID is refused for that")
        tip = b.getbestblockhash()
        peer = self.send_one(b, self.aux_header(b, OTHER_CHAIN_ID, valid_proof=True))
        wait_until(lambda: "bad header from" in self.log_text(b), what="the wrong-chain header to be refused")
        assert "AuxPoW proof invalid" not in self.log_text(b) and "doesn't match nBits" not in self.log_text(b), \
            "the proof was good: the refusal should be the chain ID rule"
        assert_equal(b.getbestblockhash(), tip)
        assert_equal(b.getblockchaininfo()["header_only_entries"], 0)

        self.log("side-branch headers are kept up to the cap, then dropped, and the peer is scored")
        tipinfo = c.getblock(c.getbestblockhash())
        parent = tipinfo["previousblockhash"]
        bits = int(tipinfo["bits"], 16)
        target = compact_to_target(bits)
        siblings = []
        nonce = tipinfo["nonce"] + 1
        while len(siblings) < CAP + 3:
            h = raw_header(tipinfo["version"], parent, bytes.fromhex(tipinfo["merkleroot"])[::-1], tipinfo["time"], bits, nonce)
            if scrypt_pow(h) <= target:
                siblings.append(h + b"\x00")
            nonce += 1
        peer = P2PConnection(c.p2p_port, start_height=0)
        wait_until(lambda: peer.got_verack, what="verack")
        for s in siblings[:CAP]:
            peer.send("headers", varint(1) + s)
        wait_until(lambda: c.getblockchaininfo()["header_only_entries"] == CAP, what="%d side headers to be kept" % CAP)
        assert "side branches dropped" not in self.log_text(c)
        peer.send("headers", varint(1) + siblings[CAP])
        wait_until(lambda: "side branches dropped" in self.log_text(c), what="the side branches to be dropped at the cap")
        assert_equal(c.getblockchaininfo()["header_only_entries"], 0)
        assert_equal(c.getbestblockhash(), tipinfo["hash"])
        peer.send("ping", b"\x00" * 8)
        wait_until(lambda: peer.counts.get("pong", 0) >= 1, what="the node to carry on")


if __name__ == "__main__":
    HeadersFirstLimitsTest().main()
