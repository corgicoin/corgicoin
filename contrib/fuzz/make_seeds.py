#!/usr/bin/env python3
"""Make a small seed corpus for the fuzz targets (src/fuzz): one directory per target.

    contrib/fuzz/make_seeds.py <out-dir>

The seeds are just well formed examples, so that the mutations start from inputs that get past the first check and into the
code behind it. The fuzzer finds the rest.
"""
import hashlib
import os
import struct
import sys


def dsha(b):
    return hashlib.sha256(hashlib.sha256(b).digest()).digest()


def compact(n):
    if n < 0xfd:
        return bytes([n])
    if n <= 0xffff:
        return b"\xfd" + struct.pack("<H", n)
    return b"\xfe" + struct.pack("<I", n)


def tx(script_sig=b"\x51", script_pub=b"\x76\xa9\x14" + bytes(range(20)) + b"\x88\xac", value=5 * 10**8, extra_in=0, extra_out=0):
    vin = [(b"\x11" * 32, 0)] + [(bytes([0x22 + i]) * 32, i + 1) for i in range(extra_in)]
    vout = [(value, script_pub)] + [(1000 + i, b"\x6a\x04test") for i in range(extra_out)]
    out = struct.pack("<I", 1) + compact(len(vin))
    for h, n in vin:
        out += h + struct.pack("<I", n) + compact(len(script_sig)) + script_sig + b"\xff\xff\xff\xff"
    out += compact(len(vout))
    for v, s in vout:
        out += struct.pack("<q", v) + compact(len(s)) + s
    return out + struct.pack("<I", 0)


def coinbase():
    return (struct.pack("<I", 1) + b"\x01" + b"\x00" * 32 + b"\xff\xff\xff\xff" + b"\x04\x01\x02\x03\x04" + b"\xff\xff\xff\xff"
            + b"\x01" + struct.pack("<q", 50 * 10**8) + b"\x23\x21" + b"\x02" + b"\x11" * 32 + b"\xac" + struct.pack("<I", 0))


def header(version=1, prev=b"\x00" * 32, merkle=b"\x33" * 32, t=1700000000, bits=0x207fffff, nonce=7):
    return struct.pack("<i", version) + prev + merkle + struct.pack("<III", t, bits, nonce)


def block(txs):
    cb = coinbase()
    body = [cb] + txs
    return header(merkle=dsha(cb)) + compact(len(body)) + b"".join(body)


def auxpow_block():
    cb = coinbase()
    parent = header(version=0x00000001, merkle=dsha(cb))
    proof = cb + b"\x00" * 32 + b"\x00" + struct.pack("<i", 0) + b"\x00" + struct.pack("<i", 0) + parent
    return header(version=0x00C60101) + proof + b"\x01" + cb


SEEDS = {
    "tx": [tx(), tx(extra_in=2, extra_out=2), coinbase()],
    "block": [block([]), block([tx(), tx(extra_in=1)])],
    "auxpow": [auxpow_block()[80:], b"\x00" * 120],
    "script": [bytes([5]) + b"\x51\x51\x93\x52\x87" + b"\x76\xa9\x14" + bytes(20) + b"\x88\xac",
               bytes([3]) + b"\x00\x4c\x01" + b"\xa9\x14" + bytes(20) + b"\x87",
               bytes([4]) + b"\x51\x52\x53" + b"\x52\x21" + b"\x02" + b"\x11" * 32 + b"\x51\xae"],
    "json": [b'{"method":"getblockcount","params":[],"id":1}', b'[{"a":[1,2,{"b":null}],"c":"\\u00e9\\n"}]', b'{"x":1.5e300,"y":-0}'],
    "base58": [b"CPaHzmUZ5c42GmFaCDEV4UsXPJGKvGhGnD", b"9BXdyKhUrtb7oAfSFRemJvTnbW6FvJrWiR", b"n" * 34],
    "bech32": [b"corg1qw508d6qejxtdg4y5r3zarvary0c5xw7k0y8cvx", b"tcorg1l" + b"q" * 38, b"corg1" + b"q" * 50],
    "burn": [b"SOL" + b"CORG" + bytes(range(32)), b"SOL" + b"AB" + b"\x00" * 34, b"\x6a\x25SOLCORG" + bytes(range(32))],
}


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    for target, seeds in SEEDS.items():
        d = os.path.join(sys.argv[1], target)
        os.makedirs(d, exist_ok=True)
        for i, s in enumerate(seeds):
            with open(os.path.join(d, "seed%d" % i), "wb") as f:
                f.write(s)
    print("wrote %d seeds for %d targets to %s" % (sum(len(v) for v in SEEDS.values()), len(SEEDS), sys.argv[1]))


if __name__ == "__main__":
    main()
