#!/usr/bin/env python3
"""createauxblock / submitauxblock: a merged-mined block is accepted end to end.

Regression test for blocks built by createauxblock having an empty coinbase scriptSig. CreateNewBlock() leaves it
empty and only IncrementExtraNonce() fills it in, which the RPC did not call, so every block failed the consensus
check "coinbase script size" (2..100 bytes) and submitauxblock could never succeed, whatever proof was submitted.

The test plays the part of a merged-mining pool: it asks for aux work, builds a parent-chain coinbase committing
the aux hash, finds a Scrypt proof of work for a parent header, submits the proof and checks the block is accepted
and relayed.
"""
import hashlib
import struct
import time

from test_framework import CorgiTestFramework, assert_equal, assert_raises_rpc_error

AUXPOW_CHAIN_ID = 0xC6        # src/auxpow.h
AUXPOW_FORK_REGTEST = 200     # AUXPOW_FORK_HEIGHT_TESTNET; -regtest implies testnet
COINBASE_SCRIPT_MIN, COINBASE_SCRIPT_MAX = 2, 100
WALLET_MATURITY = 50          # COINBASE_MATURITY (30) + the wallet's 20-block buffer
MM_MAGIC = b"\xfa\xbe" + b"mm"


def dsha256(b):
    return hashlib.sha256(hashlib.sha256(b).digest()).digest()


def varint(n):
    assert n < 0xFD
    return bytes([n])


def compact_to_target(bits):
    exp, mant = bits >> 24, bits & 0x007FFFFF
    return mant << (8 * (exp - 3)) if exp > 3 else mant >> (8 * (3 - exp))


def parent_coinbase(aux_hash_hex):
    """A parent-chain coinbase committing aux_hash: magic, root (display order), tree size 1, nonce 0."""
    script = MM_MAGIC + bytes.fromhex(aux_hash_hex) + struct.pack("<I", 1) + struct.pack("<I", 0)
    return (struct.pack("<i", 1)                                    # tx version
            + varint(1) + b"\x00" * 32 + b"\xff\xff\xff\xff"         # one input: null prevout
            + varint(len(script)) + script + b"\xff\xff\xff\xff"     # scriptSig, sequence
            + varint(1) + struct.pack("<q", 0) + varint(1) + b"\x51"  # one output: 0, OP_TRUE
            + struct.pack("<I", 0))                                  # locktime


def solve_parent_header(merkle_root, bits, now):
    """Parent block header (a plain Scrypt block of another chain) whose PoW meets the aux target."""
    target = compact_to_target(bits)
    for nonce in range(1 << 24):
        header = (struct.pack("<i", 1) + b"\x00" * 32 + merkle_root
                  + struct.pack("<III", now, bits, nonce))
        pow_hash = hashlib.scrypt(header, salt=header, n=1024, r=1, p=1, dklen=32)
        if int.from_bytes(pow_hash, "little") <= target:
            return header
    raise AssertionError("no parent nonce found")


def auxpow_proof(aux_hash_hex, bits):
    """Serialized CAuxPow: coinbase tx, hashBlock, coinbase merkle branch, index, chain branch, chain index, header."""
    coinbase = parent_coinbase(aux_hash_hex)
    header = solve_parent_header(dsha256(coinbase), bits, int(time.time()))
    return (coinbase + b"\x00" * 32 + varint(0) + struct.pack("<i", 0)   # CMerkleTx: hashBlock, branch, index
            + varint(0) + struct.pack("<i", 0)                           # chain merkle branch (tree of one), chain index
            + header).hex()


class CreateAuxBlockTest(CorgiTestFramework):
    """node0 hands out aux work and plays the pool; node1 receives the merged block."""
    num_nodes = 2

    def run_test(self):
        n0, n1 = self.nodes
        self.connect_nodes(0, 1)        # createauxblock refuses to run without a peer

        self.log("mine past the AuxPoW fork height")
        n0.generate(AUXPOW_FORK_REGTEST + 2)
        self.sync_blocks()
        tip = n0.getblockcount()

        self.log("createauxblock returns work for our chain ID")
        addr = n0.getnewaddress()
        work = n0.createauxblock(addr)
        assert_equal(work["chainid"], AUXPOW_CHAIN_ID)
        assert_equal(work["height"], tip + 1)
        assert_equal(work["previousblockhash"], n0.getbestblockhash())
        assert_raises_rpc_error(-5, "Invalid CorgiCoin address", n0.createauxblock, "notanaddress")

        self.log("a merged-mined block built from that work is accepted")
        proof = auxpow_proof(work["hash"], int(work["bits"], 16))
        assert_equal(n0.submitauxblock(work["hash"], proof), True)
        assert_equal(n0.getblockcount(), tip + 1)
        assert_equal(n0.getbestblockhash(), work["hash"])

        self.log("the block relays to the other node")
        self.sync_blocks()
        assert_equal(n1.getbestblockhash(), work["hash"])

        self.log("a submitted block cannot be reused, and unknown hashes are refused")
        assert_raises_rpc_error(-8, "block hash unknown", n0.submitauxblock, work["hash"], "00")
        assert_raises_rpc_error(-8, "block hash unknown", n0.submitauxblock, "00" * 32, "00")

        self.log("blocks created in the same second are distinct (extra nonce)")
        first = n0.createauxblock(addr)
        second = n0.createauxblock(addr)
        assert first["hash"] != second["hash"], "two createauxblock calls returned the same block hash"

        self.log("a transaction in a merged-mined block is indexed: getrawtransaction finds it")
        pay = n1.getnewaddress()
        work = n0.createauxblock(pay)
        assert_equal(n0.submitauxblock(work["hash"], auxpow_proof(work["hash"], int(work["bits"], 16))), True)
        self.sync_blocks()
        coinbase = n0.getrawtransaction(n0.getblock(work["hash"])["tx"][0], 1)
        assert_equal(coinbase["vout"][0]["scriptPubKey"]["addresses"], [pay])
        script_len = len(coinbase["vin"][0]["coinbase"]) // 2
        assert COINBASE_SCRIPT_MIN <= script_len <= COINBASE_SCRIPT_MAX, "coinbase script is %d bytes" % script_len

        self.log("the reward of a merged-mined block can be spent once it matures")
        n0.generate(WALLET_MATURITY)
        self.sync_blocks()
        assert n1.getbalance() > 1000       # node1's only coins are that merged-mined reward
        txid = n1.sendtoaddress(n0.getnewaddress(), 1000)
        self.sync_mempools()
        n0.generate(1)
        self.sync_blocks()
        assert_equal(n1.gettransaction(txid)["confirmations"], 1)


if __name__ == "__main__":
    CreateAuxBlockTest().main()
