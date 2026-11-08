#!/usr/bin/env python3
"""importprivkey refuses well-formed private keys whose value is not a valid secret (zero, n, above n)."""
import hashlib

from test_framework import CorgiTestFramework, assert_equal, assert_raises_rpc_error

ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
ORDER = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141


def b58decode(s):
    n = 0
    for c in s:
        n = n * 58 + ALPHABET.index(c)
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return b"\x00" * (len(s) - len(s.lstrip("1"))) + raw


def b58encode(raw):
    n = int.from_bytes(raw, "big")
    out = ""
    while n:
        n, r = divmod(n, 58)
        out = ALPHABET[r] + out
    return "1" * (len(raw) - len(raw.lstrip(b"\x00"))) + out


def checksum(payload):
    return hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]


def with_secret(wif, secret_int):
    """The same WIF (version byte and compression flag) around a different 32-byte secret."""
    raw = b58decode(wif)
    payload = raw[:-4]
    assert checksum(payload) == raw[-4:]
    body = payload[:1] + secret_int.to_bytes(32, "big") + payload[33:]
    return b58encode(body + checksum(body))


class ImportRangeTest(CorgiTestFramework):
    num_nodes = 1

    def run_test(self):
        node = self.nodes[0]
        wif = node.dumpprivkey(node.getnewaddress())

        self.log("a key that dumps and re-imports unchanged is fine")
        assert_equal(with_secret(wif, int.from_bytes(b58decode(wif)[1:33], "big")), wif)

        self.log("zero, n, n+1 and 2^256-1 are rejected, with the wallet left as it was")
        before = node.getwalletinfo()["keypoolsize"]
        for bad in (0, ORDER, ORDER + 1, 2 ** 256 - 1):
            assert_raises_rpc_error(-4, "not a valid secret", node.importprivkey, with_secret(wif, bad))
        assert_equal(node.getwalletinfo()["keypoolsize"], before)

        self.log("the smallest and the largest valid secrets are accepted")
        for good in (1, ORDER - 1):
            assert_equal(node.importprivkey(with_secret(wif, good)), None)
            addr = node.getaccountaddress("")      # keep the wallet exercised after each import
            assert node.validateaddress(addr)["isvalid"]
        node.stop()
        node.start()      # and the wallet loads with them
        assert_equal(node.getblockcount(), 0)


if __name__ == "__main__":
    ImportRangeTest().main()
