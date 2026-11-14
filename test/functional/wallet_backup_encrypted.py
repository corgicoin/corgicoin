#!/usr/bin/env python3
"""exportwalletencrypted / importwalletencrypted: a backup that is safe to keep, and restores everything.

Node a has an HD wallet with labelled addresses, a plain imported key and a watch-only entry. Its backup restores into node b,
an empty wallet: the same addresses are spendable there, the labels and recovery phrase are back, and the next new address is
not one that a had already given out. The file shows nothing (no key, no word of the phrase), a wrong passphrase and a changed
byte are both refused, a backup is not written over a file, and a backup of another recovery phrase is not poured into a wallet
that has its own.
"""
import os

from test_framework import CorgiTestFramework, assert_equal, assert_raises_rpc_error

PASS = "a long backup passphrase"
OTHER_PHRASE = "legal winner thank year wave sausage worth useful legal winner thank yellow"


class EncryptedBackupTest(CorgiTestFramework):
    num_nodes = 3

    def run_test(self):
        a, b, c = self.nodes          # a: the wallet that is backed up; b: an empty wallet to restore into; c: a source of foreign keys
        a.generate(101)

        self.log("a wallet with an HD seed, labelled addresses, an imported key and a watch-only entry")
        a.sethdseed()
        phrase = a.gethdseed(True)["mnemonic"]
        labelled = a.getnewaddress("savings")
        plain = a.getnewaddress("tips")
        lone = c.getnewaddress()
        lone_secret = c.dumpprivkey(lone)
        a.importprivkey(lone_secret, "imported")
        watch = c.getnewaddress()
        a.importaddress(watch, False)
        path = os.path.join(a.datadir, "wallet.backup")

        info = a.exportwalletencrypted(path, PASS)
        assert_equal(info["filename"], path)
        raw = open(path, "rb").read()
        assert raw.startswith(b"CORGIBK1")

        self.log("the file shows nothing: no key, no word of the phrase, no address, no label")
        needles = [lone_secret.encode(), labelled.encode(), b"savings", b"imported"] + [w.encode() for w in phrase.split()[:4]]
        for needle in needles:
            assert needle not in raw, needle

        self.log("it refuses an existing file and a short passphrase")
        assert_raises_rpc_error(-8, "already exists", a.exportwalletencrypted, path, PASS)
        assert_raises_rpc_error(-8, "at least 8", a.exportwalletencrypted, path + ".2", "short")
        assert not os.path.exists(path + ".2")

        self.log("a wrong passphrase, a file with one byte changed, and a file that is not a backup are refused, and change nothing")
        assert_raises_rpc_error(-8, "Wrong passphrase", b.importwalletencrypted, path, "not the passphrase")
        tampered = bytearray(raw)
        tampered[len(tampered) // 2] ^= 1
        bad = os.path.join(a.datadir, "tampered.backup")
        open(bad, "wb").write(bytes(tampered))
        assert_raises_rpc_error(-8, "Wrong passphrase", b.importwalletencrypted, bad, PASS)
        assert_raises_rpc_error(-8, "not a CorgiCoin", b.importwalletencrypted, os.path.join(a.datadir, "corgicoin.conf"), PASS)
        assert_equal(b.validateaddress(labelled)["ismine"], False)

        self.log("restored into the empty wallet b: keys, labels, the watch-only entry and the recovery phrase are there")
        r = b.importwalletencrypted(path, PASS)
        assert r["keys_added"] >= 3, r
        for addr in (labelled, plain, lone):
            assert_equal(b.validateaddress(addr)["ismine"], True)
        assert_equal(b.validateaddress(watch)["iswatchonly"], True)
        assert_equal(b.gethdseed(True)["mnemonic"], phrase)
        assert_equal(b.dumpprivkey(lone), lone_secret)
        assert b.validateaddress(labelled)["hdkeypath"].startswith("m/44'/99'/0'/0/")

        self.log("the next addresses b makes are new ones, not any a had already given out")
        given = {labelled, plain}
        for _ in range(3):
            assert b.getnewaddress() not in given

        self.log("a backup of a different recovery phrase is not poured into a wallet that has its own")
        c.sethdseed(OTHER_PHRASE)
        other = os.path.join(c.datadir, "other.backup")
        c.exportwalletencrypted(other, PASS)
        assert_raises_rpc_error(-8, "different recovery phrase", b.importwalletencrypted, other, PASS)


if __name__ == "__main__":
    EncryptedBackupTest().main()
