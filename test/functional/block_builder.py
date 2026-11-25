"""Build and mine regtest blocks by hand, so that a test can hand a node a block that breaks exactly one rule.

A block is the 80-byte header, a transaction count and the transactions. Regtest work is cheap (about half of all nonces meet it), so a
block is mined here in a few scrypt hashes. Transactions are opaque bytes (as the node's own RPCs give them in hex), except for the
coinbase, which is built here.
"""
import hashlib
import struct

from auxpow_builder import compact_to_target, scrypt_pow

COIN = 100000000


def dsha256(b):
    return hashlib.sha256(hashlib.sha256(b).digest()).digest()


def ser_compact(n):
    if n < 0xFD:
        return bytes([n])
    if n <= 0xFFFF:
        return b"\xfd" + struct.pack("<H", n)
    return b"\xfe" + struct.pack("<I", n)


def txid_of(raw):
    return dsha256(raw)[::-1].hex()


def coinbase_tx(script_sig, value, script_pubkey=b"\x51"):
    """A coinbase paying `value` satoshi to script_pubkey (default OP_TRUE). script_sig is 2 to 100 bytes."""
    return (struct.pack("<i", 1) + ser_compact(1) + b"\x00" * 32 + b"\xff\xff\xff\xff" + ser_compact(len(script_sig)) + script_sig
            + b"\xff\xff\xff\xff" + ser_compact(1) + struct.pack("<q", value) + ser_compact(len(script_pubkey)) + script_pubkey
            + struct.pack("<I", 0))


def merkle_root(txids_internal):
    level = list(txids_internal)
    if not level:
        return b"\x00" * 32
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [dsha256(level[i] + level[i + 1]) for i in range(0, len(level), 2)]
    return level[0]


def mine_header(version, prev_hex, root, time, bits):
    target = compact_to_target(bits)
    prev = bytes.fromhex(prev_hex)[::-1]
    nonce = 0
    while True:
        h = struct.pack("<i32s32sIII", version, prev, root, time, bits, nonce)
        if scrypt_pow(h) <= target:
            return h
        nonce += 1


def next_block_value(node):
    """What the next block may pay in its coinbase, with an empty pool: block rewards here are not constant, the node knows."""
    return int(node.getblocktemplate()["coinbasevalue"])


def build_block(node, txs=(), coinbase_value=None, coinbase_raw=None, bad_merkle=False, script_sig=None, version=1):
    """Raw hex of a block on top of node's tip: a coinbase, then txs (raw bytes each).

    coinbase_value (satoshi) defaults to the most the node allows with an empty pool (fees of txs are the caller's to add);
    coinbase_raw uses that coinbase as it is (to repeat an old one); bad_merkle puts a wrong root in the header."""
    tip = node.getblock(node.getbestblockhash())
    height = tip["height"] + 1
    if coinbase_raw is None:
        if coinbase_value is None:
            coinbase_value = next_block_value(node)
        coinbase_raw = coinbase_tx(script_sig or (b"\x04" + struct.pack("<I", height) + b"\x00\x01"), coinbase_value)
    all_txs = [coinbase_raw] + list(txs)
    root = merkle_root([dsha256(t) for t in all_txs])
    if bad_merkle:
        root = bytes([root[0] ^ 1]) + root[1:]
    header = mine_header(version, tip["hash"], root, tip["time"] + 1, int(tip["bits"], 16))
    return (header + ser_compact(len(all_txs)) + b"".join(all_txs)).hex()
