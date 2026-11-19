#!/usr/bin/env python3
"""Headers-first: merged-mined headers are checked, side-branch headers are capped, and a low-work chain cannot shut out the honest one.

Each case has its own node and peer (a refused peer is scored, and a banned address would shut out the next case):
  a  a header with the AuxPoW bit and a bad proof is refused;
  b  a header after the AuxPoW fork with a valid proof but another chain's ID is refused (the proof is good, the rule is the chain ID);
  c  side-branch headers (siblings of the tip, each with valid work) are kept up to the cap, then the lowest-work are dropped, and no peer
     is scored. The cap is 50000 for real: regtest lowers it with -testmaxbranchheaders;
  d  a header that forks off our own chain further back than the fork depth is not followed and not scored; one that forks off at the tip
     is kept. The depth is 2000 for real: regtest lowers it with -testmaxforkdepth;
  e  a peer sends a chain of low-work headers from genesis, longer than the fork depth, to a node that has no blocks; the honest chain
     of a second peer (heavier) is still accepted and the node syncs it. (When the depth was measured from the best header, that blob
     moved the best header and every header of the honest chain was refused.)
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
DEPTH = 5


def varint(n):
    return bytes([n]) if n < 253 else b"\xfd" + struct.pack("<H", n)


def raw_header(version, prev_hex, merkle, time, bits, nonce):
    return struct.pack("<i32s32sIII", version, bytes.fromhex(prev_hex)[::-1], merkle, time, bits, nonce)


def grind(version, prev_hex, merkle, time, bits, first_nonce=0):
    """A header, with a nonce that meets the work (regtest is easy: about half of the nonces do)."""
    target = compact_to_target(bits)
    nonce = first_nonce
    while True:
        h = raw_header(version, prev_hex, merkle, time, bits, nonce)
        if scrypt_pow(h) <= target:
            return h
        nonce += 1


def header_hash(h):
    return sha256d(h)[::-1].hex()


class HeadersFirstLimitsTest(CorgiTestFramework):
    num_nodes = 6
    extra_args = [["-headersfirst=1"], ["-headersfirst=1"], ["-headersfirst=1", "-testmaxbranchheaders=%d" % CAP],
                  ["-headersfirst=1", "-testmaxforkdepth=%d" % DEPTH], ["-headersfirst=1", "-testmaxforkdepth=%d" % DEPTH], []]

    def log_text(self, node):
        with open(node.debug_log, errors="replace") as f:
            return f.read()

    def aux_header(self, node, chain_id, valid_proof):
        tip = node.getblock(node.getbestblockhash())
        version = (tip["version"] & 0xFF) | VERSION_AUXPOW_BIT | (chain_id << 16)
        bits = int(tip["bits"], 16)
        header = raw_header(version, tip["hash"], b"\x42" * 32, tip["time"] + 1, bits, 0)
        proof = bytes.fromhex(build_auxpow(header_hash(header), bits, chain_id, meet_target=valid_proof))
        return header + proof + b"\x00"

    def connect_peer(self, node):
        peer = P2PConnection(node.p2p_port, start_height=0)
        wait_until(lambda: peer.got_verack, what="verack")
        return peer

    def send_one(self, node, payload):
        peer = self.connect_peer(node)
        peer.send("headers", varint(1) + payload)
        return peer

    def sibling(self, node, height, count=1):
        """Headers with valid work that are children of the block at height - 1, as the block at `height` is."""
        blk = node.getblock(node.getblockhash(height))
        bits = int(blk["bits"], 16)
        out, nonce = [], blk["nonce"] + 1
        for _ in range(count):
            h = grind(blk["version"], blk["previousblockhash"], bytes.fromhex(blk["merkleroot"])[::-1], blk["time"], bits, nonce)
            out.append(h + b"\x00")
            nonce = struct.unpack("<I", h[76:80])[0] + 1
        return out

    def run_test(self):
        a, b, c, d, e, f = self.nodes
        for n in (a, b):
            n.generate(AUXPOW_FORK_REGTEST + 5)
        c.generate(6)
        d.generate(30)
        f.generate(15)

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

        self.log("side-branch headers are kept up to the cap, then the lowest-work are dropped, and nobody is scored")
        tipinfo = c.getblock(c.getbestblockhash())
        siblings = self.sibling(c, c.getblockcount(), CAP + 3)
        peer = self.connect_peer(c)
        for s in siblings[:CAP]:
            peer.send("headers", varint(1) + s)
        wait_until(lambda: c.getblockchaininfo()["header_only_entries"] == CAP, what="%d side headers to be kept" % CAP)
        assert "side branches dropped" not in self.log_text(c)
        peer.send("headers", varint(1) + siblings[CAP])
        wait_until(lambda: "side branches dropped" in self.log_text(c), what="the side branches to be dropped at the cap")
        wait_until(lambda: c.getblockchaininfo()["header_only_entries"] == CAP, what="the dropped headers to make room for the new one")
        assert_equal(c.getbestblockhash(), tipinfo["hash"])
        assert "misbehaving" not in self.log_text(c), "a full cap is not the peer's fault"
        peer.send("ping", b"\x00" * 8)
        wait_until(lambda: peer.counts.get("pong", 0) >= 1, what="the node to carry on")

        self.log("a header that forks off our chain deeper than the fork depth is not followed, and not scored; one at the tip is kept")
        tip_height = d.getblockcount()
        deep = self.sibling(d, tip_height - DEPTH - 2)[0]            # a child of block tip-DEPTH-3: its parent is deeper than the depth
        near = self.sibling(d, tip_height)[0]                        # a child of the tip's parent
        peer = self.connect_peer(d)
        peer.send("headers", varint(1) + deep)
        wait_until(lambda: "not followed" in self.log_text(d), what="the deep fork to be refused")
        assert_equal(d.getblockchaininfo()["header_only_entries"], 0)
        peer.send("headers", varint(1) + near)
        wait_until(lambda: d.getblockchaininfo()["header_only_entries"] == 1, what="the near fork to be kept")
        assert "misbehaving" not in self.log_text(d)

        self.log("a long chain of low-work headers from genesis does not shut out the honest chain")
        genesis = e.getblock(e.getblockhash(0))
        bits = int(genesis["bits"], 16)
        blob, prev, t = [], genesis["hash"], genesis["time"]
        for i in range(DEPTH * 3):
            t += 1
            h = grind(genesis["version"], prev, bytes([i + 1]) * 32, t, bits)
            blob.append(h + b"\x00")
            prev = header_hash(h)
        blobpeer = self.connect_peer(e)
        blobpeer.send("headers", varint(len(blob)) + b"".join(blob))
        wait_until(lambda: e.getblockchaininfo()["header_only_entries"] == len(blob), what="the blob to be held as headers")
        self.connect_nodes(4, 5)
        wait_until(lambda: e.getblockcount() == f.getblockcount(), timeout=120, what="the honest chain (%d) to sync past the blob" % f.getblockcount())
        assert_equal(e.getbestblockhash(), f.getbestblockhash())


if __name__ == "__main__":
    HeadersFirstLimitsTest().main()
