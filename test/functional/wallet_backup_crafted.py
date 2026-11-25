#!/usr/bin/env python3
"""importwalletencrypted with files the node would not write itself: crafted, valid encryptions of awkward contents.

The backup is read from a file someone may have talked you into restoring, so every field is untrusted. Each case below is a correctly
encrypted file (made here, see backup_crafter.py) and the node must refuse it or take only what is safe, and never fall over:
  - a control file with two good keys is imported (so the files made here are what the node reads);
  - keys that are not keys (garbage, a zero secret, a secret at or above the curve order) are skipped, the good one beside them is kept;
  - a backup of another network, a cost parameter outside what the wallet will do, a file too big to be a backup, a truncated one;
  - a different recovery phrase is refused by a wallet that has its own, and the same phrase with other spacing (extra blanks, tabs, a newline) is not "different";
  - a label for an address the wallet has already labelled does not rename it;
  - an hdindex far above the keys in the file is held to what a restore from the phrase would reach;
  - a known-answer vector: this passphrase, salt, nonce and plain text must give exactly these bytes, and the node must open them, so that a
    change in the format (or in the scrypt or AES-GCM used) is noticed.
"""
import os

from backup_crafter import b58check_decode, craft, payload, require_crypto, wif
from test_framework import CorgiTestFramework, assert_equal, assert_raises_rpc_error

PASS = "a long backup passphrase"
PHRASE = "legal winner thank year wave sausage worth useful legal winner thank yellow"
OTHER_PHRASE = "letter advice cage absurd amount doctor acoustic avoid letter advice cage above"
CURVE_ORDER = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141

# the known-answer vector: passphrase, salt = 00..0f, nonce = 10..1b, log2N = 14, and a plain text with one key (regtest WIF prefix 0xf1)
KAT_PASS = "known answer passphrase"
KAT_SECRET = bytes(range(1, 33))
KAT_PLAIN = (b'{"version":1,"created":1700000000,"chain":"regtest","hdmnemonic":"","hdindex":0,"keys":[{"secret":"%s","time":1700000000,"hdkeypath":""}],'
             b'"labels":[],"watchonly":[],"cscript":[]}')
KAT_FILE_HEX = ("434f524749424b310e000102030405060708090a0b0c0d0e0f1011121314"
                "15161718191a1b2816393e72e5663821abe3215d435d2a5d1a9297b58cae76110ff42d4217ad3c06e319f891f04db16bb210ff532892e905dd36f3056691627e4186d66ca8233a66a520b99e3e42deed447887404fb61dbb0aeac167a3bb4109953ac6be43faaed244aa96b3ac697fa6bf4fcc043499e648f7757c234b13d933f528856f2b85d882f8610e2e39c535c1cf3723ac6520c6566670a7c415db612a09f61e359d267a1801e82bcd5eea0ca510a291308a2744d591ba8cf3dd2473b42b3b5abbaafa50f347a6e35e538861e8d83fa641dc2c58b30063b01426db67ceefb7b47f8ec5f58135a2c4a97b93d85298a0005a647213f788eae7")


class CraftedBackupTest(CorgiTestFramework):
    num_nodes = 3

    def setup_nodes(self):
        super().setup_nodes()
        require_crypto(self)

    def write(self, node, name, data):
        path = os.path.join(node.datadir, name)
        with open(path, "wb") as f:
            f.write(data)
        return path

    def alive(self, node):
        node.getblockcount()          # raises if the daemon is gone

    def run_test(self):
        a, b, c = self.nodes        # a: no phrase; b: has a phrase of its own; c: adopts a phrase
        for n in (a, b, c):
            n.generate(1)
        src = self.nodes[0]
        # keys to put in files: made in node b's wallet, so that a and c do not have them
        addrs = [b.getnewaddress() for _ in range(3)]
        wifs = [b.dumpprivkey(x) for x in addrs]
        prefix = b58check_decode(wifs[0])[0]
        key = lambda w, **kw: dict({"secret": w, "time": 1700000000, "hdkeypath": ""}, **kw)

        self.log("control: a file with two good keys is imported")
        f = self.write(a, "control.backup", craft(PASS, payload(keys=[key(wifs[0]), key(wifs[1])])))
        r = a.importwalletencrypted(f, PASS)
        assert_equal(r["keys_added"], 2)
        assert a.validateaddress(addrs[0])["ismine"] and a.validateaddress(addrs[1])["ismine"]

        self.log("keys that are not keys are skipped and the good one beside them is kept: garbage, a zero secret, a secret at or above the order")
        zero = wif(b"\x00" * 32, prefix)
        order = wif(CURVE_ORDER.to_bytes(32, "big"), prefix)
        above = wif(((1 << 256) - 1).to_bytes(32, "big"), prefix)
        bad = [key("not a key at all"), key(zero), key(order), key(above), {"secret": 12345}, "a string", None, key(wifs[2])]
        f = self.write(c, "bad_keys.backup", craft(PASS, payload(keys=bad)))
        r = c.importwalletencrypted(f, PASS)
        assert_equal(r["keys_added"], 1)
        assert c.validateaddress(addrs[2])["ismine"]
        self.alive(c)

        self.log("a backup of another network is refused")
        f = self.write(a, "main.backup", craft(PASS, payload(chain="main")))
        assert_raises_rpc_error(-8, "another network", a.importwalletencrypted, f, PASS)
        f = self.write(a, "nochain.backup", craft(PASS, {"version": 1, "keys": []}))
        assert_raises_rpc_error(-8, "another network", a.importwalletencrypted, f, PASS)

        self.log("a cost parameter outside what the wallet will do is refused before any key derivation, and a plain text that is not an object is not understood")
        for bad_log2n in (13, 19, 40, 0):
            raw = bytearray(craft(PASS, payload()))
            raw[8] = bad_log2n
            f = self.write(a, "cost%d.backup" % bad_log2n, bytes(raw))
            assert_raises_rpc_error(-8, "will not do", a.importwalletencrypted, f, PASS)
        for plain in (b"[1, 2, 3]", b"\"a string\"", b"42", b"not json at all", b""):
            f = self.write(a, "plain.backup", craft(PASS, plain))
            assert_raises_rpc_error(-8, "not understood", a.importwalletencrypted, f, PASS)
        self.alive(a)

        self.log("a truncated file, a file of zeros and one that is too big to be a backup are refused")
        good = craft(PASS, payload())
        for name, data in (("trunc1", good[:20]), ("trunc2", good[:len(good) - 1]), ("zeros", b"\x00" * 1000), ("magic", b"CORGIBK1"), ("empty", b"")):
            f = self.write(a, name + ".backup", data)
            assert_raises_rpc_error(-8, None, a.importwalletencrypted, f, PASS)
        f = self.write(a, "huge.backup", b"CORGIBK1" + b"\x00" * (65 * 1024 * 1024))
        assert_raises_rpc_error(-8, "too big", a.importwalletencrypted, f, PASS)
        os.remove(f)
        self.alive(a)

        self.log("a different recovery phrase is refused by a wallet that has its own; the same phrase with other spacing is not a different one")
        b.sethdseed(PHRASE, False)          # (no rescan: nothing to find, and the look-ahead is slow on a loaded machine)
        assert_equal(b.gethdseed(True)["mnemonic"], PHRASE)
        f = self.write(b, "other.backup", craft(PASS, payload(hdmnemonic=OTHER_PHRASE)))
        assert_raises_rpc_error(-8, "different recovery phrase", b.importwalletencrypted, f, PASS)
        assert_equal(b.gethdseed(True)["mnemonic"], PHRASE)
        shouty = "  " + PHRASE.replace(" ", "  \t ") + " \n"
        f = self.write(b, "same.backup", craft(PASS, payload(hdmnemonic=shouty)))
        r = b.importwalletencrypted(f, PASS)
        assert_equal(r["phrase_adopted"], False)

        self.log("a label for an address the wallet has already labelled does not rename it; one for an address the wallet neither owns nor watches is not taken (no planted contacts)")
        mine = b.getnewaddress("mine")
        fresh = a.getnewaddress()
        b.setaccount(addrs[0], "kept")
        labels = [{"address": mine, "label": "attacker's name"}, {"address": addrs[0], "label": "renamed"},
                  {"address": fresh, "label": "new label"}, {"address": "not an address", "label": "x"}]
        f = self.write(b, "labels.backup", craft(PASS, payload(labels=labels)))
        b.importwalletencrypted(f, PASS)
        assert_equal(b.getaccount(mine), "mine")
        assert_equal(b.getaccount(addrs[0]), "kept")
        assert_equal(b.getaccount(fresh), "")          # not the wallet's own, so not a contact a file can plant

        self.log("an hdindex far above the keys in the file is not taken: only a key that derives from the phrase at its path counts, and this one does not")
        path_of = lambda i: "m/44'/%s'/0'/0/%d" % (self.coin_type(b), i)
        f = self.write(c, "index.backup", craft(PASS, payload(hdmnemonic=OTHER_PHRASE, hdindex=900000000,
                                                              keys=[key(wifs[0], hdkeypath=path_of(5))])))
        r = c.importwalletencrypted(f, PASS, True)
        assert_equal(r["phrase_adopted"], True)
        index = self.next_hd_index(c)
        assert index <= 1, "the next address is at index %d: nothing in the file proves a key that far up, so the index must stay low" % index
        for huge in (2 ** 31, 2 ** 40, -5):
            f = self.write(c, "index2.backup", craft(PASS, payload(hdmnemonic=OTHER_PHRASE, hdindex=huge)))
            c.importwalletencrypted(f, PASS)
            nxt = self.next_hd_index(c)
            assert nxt <= 5 + 1 + 1000 + 50, nxt
        self.alive(c)

        self.log("known answer: this passphrase, salt, nonce and plain text give exactly these bytes, and the node opens them")
        secret_wif = wif(KAT_SECRET, prefix)
        assert_equal(prefix, 0xf1)
        kat = craft(KAT_PASS, KAT_PLAIN % secret_wif.encode(), log2n=14, salt=bytes(range(16)), nonce=bytes(range(16, 28)))
        assert_equal(kat.hex(), KAT_FILE_HEX)
        f = self.write(a, "kat.backup", bytes.fromhex(KAT_FILE_HEX))
        before = a.getblockchaininfo()["blocks"]
        r = a.importwalletencrypted(f, KAT_PASS)
        assert_equal(r["keys_added"], 1)
        assert_equal(before, a.getblockchaininfo()["blocks"])

    def next_hd_index(self, node):
        """The index of the next address the wallet makes from its phrase. (Addresses already in the key pool come first, and a pool made before the
        phrase was adopted holds keys that are not from it: see wallet_backup_untrusted.py. They are skipped here.)"""
        for _ in range(60):
            info = node.validateaddress(node.getnewaddress())
            if "hdkeypath" in info:
                return int(info["hdkeypath"].rsplit("/", 1)[1])
        raise AssertionError("no address from the phrase in 60 addresses")

    def coin_type(self, node):
        path = node.validateaddress(node.getnewaddress())
        return "99" if "hdkeypath" not in path else path["hdkeypath"].split("/")[2].rstrip("'")


if __name__ == "__main__":
    CraftedBackupTest().main()
