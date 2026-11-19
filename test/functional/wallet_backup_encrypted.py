#!/usr/bin/env python3
"""exportwalletencrypted / importwalletencrypted: a backup that is safe to keep, and restores everything.

Node a has an HD wallet with labelled addresses, a plain imported key, a watch-only entry and a multisig redeem script. Its
backup restores into node d, an empty wallet, when told to adopt the phrase (adoptphrase=true): the same addresses are spendable
there, the labels and recovery phrase are back, and the next new address is not one that a had already given out. Without that
flag a wallet that has no phrase gets the keys and not the phrase (node b): a backup someone talked you into restoring cannot
choose where your next deposits go. A label that the wallet already has for an address is not replaced. The file shows nothing
(no key, no word of the phrase), a wrong passphrase and a changed byte are both refused, a backup is not written over a file, and
a backup of another recovery phrase is not poured into a wallet that has its own.
"""
import os

from test_framework import CorgiTestFramework, assert_equal, assert_raises_rpc_error

PASS = "a long backup passphrase"
OTHER_PHRASE = "legal winner thank year wave sausage worth useful legal winner thank yellow"


class EncryptedBackupTest(CorgiTestFramework):
    num_nodes = 4

    def run_test(self):
        a, b, c, d = self.nodes     # a: backed up; b: imports without adopting the phrase; c: a source of foreign keys; d: adopts the phrase
        a.generate(101)

        self.log("a wallet with an HD seed, labelled addresses, an imported key, a watch-only entry and a redeem script")
        a.sethdseed()
        phrase = a.gethdseed(True)["mnemonic"]
        labelled = a.getnewaddress("savings")
        plain = a.getnewaddress("tips")
        lone = c.getnewaddress()
        lone_secret = c.dumpprivkey(lone)
        a.importprivkey(lone_secret, "imported")
        watch = c.getnewaddress()
        a.importaddress(watch, False)
        multisig = a.addmultisigaddress(2, [a.validateaddress(labelled)["pubkey"], a.validateaddress(plain)["pubkey"]])
        path = os.path.join(a.datadir, "wallet.backup")

        info = a.exportwalletencrypted(path, PASS)
        assert_equal(info["filename"], path)
        raw = open(path, "rb").read()
        assert raw.startswith(b"CORGIBK1")

        self.log("the file shows nothing: no key, no word of the phrase, no address, no label")
        needles = [lone_secret.encode(), labelled.encode(), b"savings", b"imported"] + [w.encode() for w in phrase.split()[:4]]
        for needle in needles:
            assert needle not in raw, needle

        self.log("it refuses an existing file and a short passphrase, and leaves no temporary file behind")
        assert_raises_rpc_error(-8, "already exists", a.exportwalletencrypted, path, PASS)
        assert_raises_rpc_error(-8, "at least 8", a.exportwalletencrypted, path + ".2", "short")
        assert not os.path.exists(path + ".2")
        assert [f for f in os.listdir(a.datadir) if ".tmp" in f and "backup" in f] == []
        if os.name != "nt":
            assert_equal(os.stat(path).st_mode & 0o777, 0o600)       # owner only, from the moment it was made

        self.log("a wrong passphrase, a file with one byte changed, and a file that is not a backup are refused, and change nothing")
        assert_raises_rpc_error(-8, "Wrong passphrase", b.importwalletencrypted, path, "not the passphrase")
        tampered = bytearray(raw)
        tampered[len(tampered) // 2] ^= 1
        bad = os.path.join(a.datadir, "tampered.backup")
        open(bad, "wb").write(bytes(tampered))
        assert_raises_rpc_error(-8, "Wrong passphrase", b.importwalletencrypted, bad, PASS)
        assert_raises_rpc_error(-8, "not a CorgiCoin", b.importwalletencrypted, os.path.join(a.datadir, "corgicoin.conf"), PASS)
        assert_equal(b.validateaddress(labelled)["ismine"], False)

        self.log("a wallet with no phrase, told nothing: the keys come in, the phrase does not, and new addresses are its own")
        b.setaccount(plain, "trusted contact")      # a label b already has for an address that is in the backup
        r = b.importwalletencrypted(path, PASS)
        assert_equal(r["phrase_adopted"], False)
        assert r["keys_added"] >= 3, r
        assert_raises_rpc_error(None, None, b.gethdseed, True)      # no phrase was adopted
        assert_equal(b.validateaddress(labelled)["ismine"], True)
        assert_equal(b.getaccount(plain), "trusted contact")        # a backup does not rename an address the wallet has labelled
        assert_equal(b.getaccount(labelled), "savings")             # and an address that had no label takes the backup's
        for _ in range(3):
            assert b.getnewaddress() not in (labelled, plain)

        self.log("with adoptphrase=true the phrase is taken: keys, labels, the watch-only entry and the recovery phrase are there")
        r = d.importwalletencrypted(path, PASS, True)
        assert_equal(r["phrase_adopted"], True)
        assert r["keys_added"] >= 3, r
        for addr in (labelled, plain, lone):
            assert_equal(d.validateaddress(addr)["ismine"], True)
        assert_equal(d.validateaddress(watch)["iswatchonly"], True)
        assert_equal(d.gethdseed(True)["mnemonic"], phrase)
        assert_equal(d.dumpprivkey(lone), lone_secret)
        assert d.validateaddress(labelled)["hdkeypath"].startswith("m/44'/99'/0'/0/")
        assert_equal(d.getaccount(labelled), "savings")

        self.log("the redeem script came too: the multisig address is the wallet's")
        assert_equal(d.validateaddress(multisig)["ismine"], True)

        self.log("the next addresses d makes are new ones, not any a had already given out")
        given = {labelled, plain}
        for _ in range(3):
            assert d.getnewaddress() not in given

        self.log("the same backup again adds nothing and changes nothing")
        r = d.importwalletencrypted(path, PASS)
        assert_equal(r["keys_added"], 0)
        assert_equal(r["phrase_adopted"], False)

        self.log("a backup of a different recovery phrase is not poured into a wallet that has its own")
        c.sethdseed(OTHER_PHRASE)
        other = os.path.join(c.datadir, "other.backup")
        c.exportwalletencrypted(other, PASS)
        assert_raises_rpc_error(-8, "different recovery phrase", d.importwalletencrypted, other, PASS)


if __name__ == "__main__":
    EncryptedBackupTest().main()
