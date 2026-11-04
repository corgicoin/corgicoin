"""Build AuxPoW proofs the way a merged-mining pool does, for regtest tests.

Every knob a pool (or an attacker) could turn is a keyword argument, so a test
can build a valid proof or break exactly one rule. Byte layouts follow
src/main.h (CAuxPow, CMerkleTx) and CAuxPow::Check in src/main.cpp.
"""
import hashlib
import os
import struct

MM_MAGIC = b"\xfa\xbe" + b"mm"
LITECOIN_VERSION = 0x20000000   # a BIP9-style parent version, no chain ID, no AuxPoW bit


def dsha256(b):
    return hashlib.sha256(hashlib.sha256(b).digest()).digest()


def ser_compact(n):
    if n < 0xFD:
        return bytes([n])
    if n <= 0xFFFF:
        return b"\xfd" + struct.pack("<H", n)
    return b"\xfe" + struct.pack("<I", n)


def ser_hashes(hashes):
    return ser_compact(len(hashes)) + b"".join(hashes)


def compact_to_target(bits):
    exp, mant = bits >> 24, bits & 0x007FFFFF
    return mant << (8 * (exp - 3)) if exp > 3 else mant >> (8 * (3 - exp))


def expected_index(nonce, chain_id, height):
    """GetExpectedAuxIndex(): the slot an aux chain must occupy in the merged-mining tree."""
    rand = nonce
    rand = (rand * 1103515245 + 12345) & 0xFFFFFFFF
    rand = (rand + chain_id) & 0xFFFFFFFF
    rand = (rand * 1103515245 + 12345) & 0xFFFFFFFF
    return rand % (1 << height)


def merkle_tree(leaves):
    """Return (root, branch_for(index)) over internal-byte-order leaves (power-of-two count)."""
    levels = [list(leaves)]
    while len(levels[-1]) > 1:
        cur = levels[-1]
        levels.append([dsha256(cur[i] + cur[i + 1]) for i in range(0, len(cur), 2)])

    def branch(index):
        out = []
        for level in levels[:-1]:
            out.append(level[index ^ 1])
            index >>= 1
        return out
    return levels[-1][0], branch


def scrypt_pow(header):
    return int.from_bytes(hashlib.scrypt(header, salt=header, n=1024, r=1, p=1, dklen=32), "little")


def build_auxpow(aux_hash_hex, bits, chain_id=0xC6, *,
                 tree_height=0, mm_nonce=0, chain_index=None, size_field=None,
                 magic=True, magic_count=1, gap_after_magic=b"", script_prefix=b"",
                 commit_hash_hex=None, parent_version=LITECOIN_VERSION,
                 parent_extra_txs=0, coinbase_index=0, bad_parent_merkle=False,
                 meet_target=True, now=1700000000):
    """Serialized CAuxPow (hex) committing aux_hash_hex for chain_id.

    tree_height > 0 merges other (random) chains alongside ours; our hash sits in
    the slot expected_index(mm_nonce, chain_id, tree_height) unless chain_index
    puts it elsewhere. The other keywords each break or vary one rule of CAuxPow::Check.
    """
    aux_leaf = bytes.fromhex(commit_hash_hex or aux_hash_hex)[::-1]   # internal byte order
    # Our hash goes in the expected slot, or in chain_index if a test overrides
    # it (a consistent tree, just with our hash where the rules say it can't be)
    slot = expected_index(mm_nonce, chain_id, tree_height) if chain_index is None else chain_index
    leaves = [os.urandom(32) for _ in range(1 << tree_height)]
    leaves[slot] = aux_leaf
    chain_root, chain_branch_for = merkle_tree(leaves)
    chain_branch = chain_branch_for(slot)
    chain_index = slot
    if size_field is None:
        size_field = 1 << tree_height

    # Parent coinbase scriptSig: [prefix] [magic] root(display order) size nonce
    commitment = chain_root[::-1] + struct.pack("<II", size_field, mm_nonce)
    head = (MM_MAGIC * magic_count + gap_after_magic) if magic else b""
    script = script_prefix + head + commitment
    coinbase = (struct.pack("<i", 1)
                + ser_compact(1) + b"\x00" * 32 + b"\xff\xff\xff\xff"
                + ser_compact(len(script)) + script + b"\xff\xff\xff\xff"
                + ser_compact(1) + struct.pack("<q", 0) + ser_compact(1) + b"\x51"
                + struct.pack("<I", 0))

    # Parent block transactions: the coinbase first, then filler txids
    parent_leaves = [dsha256(coinbase)] + [os.urandom(32) for _ in range(parent_extra_txs)]
    n = 1
    while n < len(parent_leaves):
        n *= 2
    parent_leaves += [parent_leaves[-1]] * (n - len(parent_leaves))   # Bitcoin duplicates the last
    parent_root, parent_branch_for = merkle_tree(parent_leaves)
    coinbase_branch = parent_branch_for(0)
    if bad_parent_merkle:
        parent_root = os.urandom(32)

    target = compact_to_target(bits)
    for nonce in range(1 << 24):
        header = (struct.pack("<i", parent_version) + b"\x00" * 32 + parent_root
                  + struct.pack("<III", now, bits, nonce))
        if (scrypt_pow(header) <= target) == meet_target:
            break
    else:
        raise AssertionError("no parent nonce found")

    proof = (coinbase + b"\x00" * 32 + ser_hashes(coinbase_branch) + struct.pack("<i", coinbase_index)
             + ser_hashes(chain_branch) + struct.pack("<i", chain_index)
             + header)
    return proof.hex()
