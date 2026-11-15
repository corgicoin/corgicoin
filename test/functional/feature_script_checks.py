#!/usr/bin/env python3
"""The script checks of a block: run together on several threads (-par), and not made at all under an assumed-valid block (-assumevalid).

A block holds a transaction with ten inputs, one of whose signatures is wrong, and another block holds the same transaction signed
properly. With one thread or four, the bad block is refused the way it always was (the same log line) and the good one is accepted, and
with four threads the checks of the good block did run together. Then a node told to assume the bad block valid takes it, with a peer
that hands it the headers first; a node that was not told refuses it.
"""
import hashlib
import struct

from auxpow_builder import compact_to_target, dsha256
from mininode import P2PConnection
from test_framework import CorgiTestFramework, assert_equal, wait_until

BLOCKS = 45         # mature coinbases (maturity is 30), and under the merged-mining fork height (200), so a header is 80 bytes
INPUTS = 10         # at least 8, which is where the checks are handed to threads


def read_compact(b, i):
    n = b[i]
    if n < 0xFD:
        return n, i + 1
    if n == 0xFD:
        return struct.unpack_from("<H", b, i + 1)[0], i + 3
    return struct.unpack_from("<I", b, i + 1)[0], i + 5


def compact(n):
    return bytes([n]) if n < 0xFD else b"\xfd" + struct.pack("<H", n)


def merkle_root(hashes):
    while len(hashes) > 1:
        if len(hashes) % 2:
            hashes.append(hashes[-1])
        hashes = [dsha256(hashes[i] + hashes[i + 1]) for i in range(0, len(hashes), 2)]
    return hashes[0]


def corrupt_signature(raw, k):
    """The transaction with the signature of its k-th input changed by one bit (still well formed)."""
    b = bytearray(raw)
    i = 4
    nin, i = read_compact(b, i)
    for n in range(nin):
        i += 36
        slen, i = read_compact(b, i)
        if n == k:
            assert b[i] > 0x40, "not a signature push"
            b[i + 12] ^= 0x01
            return bytes(b)
        i += slen + 4
    raise AssertionError("no such input")


class ScriptChecksTest(CorgiTestFramework):
    num_nodes = 4
    extra_args = [["-par=1"], ["-par=4"], ["-headersfirst=1"], ["-headersfirst=1"]]

    def build_block(self, node, prev_internal, when, extra, txs):
        """A block on prev_internal (internal byte order) holding a coinbase paying 1 satoshi and txs: (hex, display hash)."""
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
        struct.pack_into("<q", cb, i, 1)  # the reward depends on the previous hash; one satoshi is under any of them
        header[4:36] = prev_internal
        header[36:68] = merkle_root([dsha256(bytes(cb))] + [dsha256(t) for t in txs])
        header[68:72] = struct.pack("<I", when)
        target = compact_to_target(struct.unpack_from("<I", header, 72)[0])
        for nonce in range(1 << 24):
            struct.pack_into("<I", header, 76, nonce)
            digest = hashlib.scrypt(bytes(header), salt=bytes(header), n=1024, r=1, p=1, dklen=32)
            if int.from_bytes(digest, "little") <= target:
                raw = bytes(header) + compact(1 + len(txs)) + bytes(cb) + b"".join(txs)
                return raw, dsha256(bytes(header))[::-1].hex()
        raise AssertionError("no nonce found")

    def count(self, node, text):
        with open(node.debug_log, errors="replace") as f:
            return f.read().count(text)

    def run_test(self):
        n0, n1, n2, n3 = self.nodes
        n0.generate(BLOCKS)
        self.connect_nodes(1, 0)
        self.sync_blocks([n0, n1])

        self.log("one transaction with %d inputs, signed, and the same one with the signature of one input changed" % INPUTS)
        unspent = [u for u in n0.listunspent() if u["confirmations"] >= 35][:INPUTS]
        assert_equal(len(unspent), INPUTS)
        total = sum(u["amount"] for u in unspent)
        raw = n0.createrawtransaction([{"txid": u["txid"], "vout": u["vout"]} for u in unspent], {n0.getnewaddress(): total})
        signed = n0.signrawtransaction(raw)
        assert signed["complete"]
        good_tx = bytes.fromhex(signed["hex"])
        bad_tx = corrupt_signature(good_tx, 6)

        tip = n0.getbestblockhash()
        tip_internal = bytes.fromhex(tip)[::-1]
        when = n0.getblock(tip)["time"] + 60
        bad_raw, bad_hash = self.build_block(n0, tip_internal, when, 0xB1, [bad_tx])
        good_raw, good_hash = self.build_block(n0, tip_internal, when, 0xB2, [good_tx])

        self.log("the bad block is refused with one thread and with four, and the log says the same thing")
        for node in (n0, n1):
            node.submitblock(bad_raw.hex())
            assert_equal(node.getblockcount(), BLOCKS)
            assert_equal(node.getbestblockhash(), tip)
            assert self.count(node, "VerifySignature failed") >= 1, "the plain check did not run"
        assert self.count(n1, "a script check of block") == 1, "four threads: the batch did not refuse it first"
        assert self.count(n0, "a script check of block") == 0, "one thread: there is no batch"

        self.log("the good block is accepted by both, and with four threads its checks ran together")
        for node in (n0, n1):
            node.submitblock(good_raw.hex())
            assert_equal(node.getblockcount(), BLOCKS + 1)
            assert_equal(node.getbestblockhash(), good_hash)
        assert n1.getblockchaininfo()["blocks_scripts_parallel"] >= 1
        assert_equal(n0.getblockchaininfo()["blocks_scripts_parallel"], 0)
        assert_equal(n1.getblockchaininfo()["script_check_threads"], 4)
        assert_equal(n0.getblockchaininfo()["script_check_threads"], 1)

        self.log("the chain up to the bad block, as a peer would hold it")
        chain = [bytes.fromhex(n0.getblock(n0.getblockhash(h), False)) for h in range(1, BLOCKS + 1)] + [bad_raw]
        n2.stop()
        n2.extra_args = ["-headersfirst=1", "-assumevalid=" + bad_hash, "-testassumevalidgap=0"]
        n2.start()
        assert_equal(n2.getblockchaininfo()["assumevalid"], bad_hash)

        def feed(node):
            peer = P2PConnection(node.p2p_port, start_height=len(chain))
            wait_until(lambda: peer.counts.get("getheaders", 0) >= 1, what="getheaders to the peer")
            peer.send("headers", compact(len(chain)) + b"".join(blk[:80] + b"\x00" for blk in chain))
            wait_until(lambda: peer.counts.get("getdata", 0) >= 1, what="getdata to the peer")
            for blk in chain:
                peer.send("block", blk)
            return peer

        self.log("told to assume the bad block valid, a node takes it (its scripts are not checked)")
        feed(n2)
        wait_until(lambda: n2.getblockcount() == BLOCKS + 1, timeout=90, what="the assumed-valid chain")
        assert_equal(n2.getbestblockhash(), bad_hash)
        assert_equal(n2.getblockchaininfo()["blocks_scripts_assumed"], BLOCKS + 1)

        self.log("a node that was not told refuses it, and stops one block short")
        feed(n3)
        wait_until(lambda: n3.getblockcount() == BLOCKS, timeout=90, what="the chain up to the bad block")
        wait_until(lambda: self.count(n3, "VerifySignature failed") >= 1, what="the refusal in the log")
        assert_equal(n3.getblockcount(), BLOCKS)
        assert_equal(n3.getblockchaininfo()["blocks_scripts_assumed"], 0)


if __name__ == "__main__":
    ScriptChecksTest().main()
