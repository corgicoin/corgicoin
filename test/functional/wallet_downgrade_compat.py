#!/usr/bin/env python3
"""A wallet written by this build opens in the last release and comes back unharmed.

The build under test adds records to wallet.dat that a release does not know (key metadata: creation time and HD path; watch-only entries). A release
must skip them (and not fail to start, not drop them, not lose a key); it then works on the wallet (a new address, a payment), and when the build under test
opens the file again the new records are all still there and the wallet is consistent. Steps, on one datadir:
  1. this build: an HD wallet with labelled addresses, an imported key made with a timestamp, a watch-only address and public key, and a 2-of-3
     multisig script, with coins paid to the keys and to the script;
  2. the release (feature_cross_binary.py's alternate build): starts, shows the same balance, owns the same keys and the script, makes an address and sends a payment;
  3. this build again: the metadata of every key from step 1 is as it was, the watch-only entries are there, the release's own work (payment, new key)
     is in the wallet, and verifywallet is clean.
Needs the alternate build (--alt-corgicoind or $CORGICOIND_ALT).
"""
import os

from test_framework import CorgiTestFramework, assert_equal


class DowngradeCompatTest(CorgiTestFramework):
    num_nodes = 2

    def setup_nodes(self):
        if not self.options.alt_corgicoind:
            self.skip_test("pass --alt-corgicoind (or set CORGICOIND_ALT) to a second build")
        if not os.path.isfile(self.options.alt_corgicoind):
            self.skip_test("alternate build not found at %r" % self.options.alt_corgicoind)
        super().setup_nodes()

    def restart_with(self, node, binary):
        node.stop()
        node.binary = binary
        node.old_release = binary == self.options.alt_corgicoind
        node.start()

    def run_test(self):
        wallet, other = self.nodes
        main_bin, alt_bin = self.options.corgicoind, self.options.alt_corgicoind

        self.log("1. this build makes the wallet")
        wallet.generate(101)
        wallet.sethdseed()
        phrase = wallet.gethdseed(True)["mnemonic"]
        hd = [wallet.getnewaddress("hd%d" % i) for i in range(5)]
        info = {a: wallet.validateaddress(a) for a in hd}
        assert all("hdkeypath" in i and "timestamp" in i for i in info.values()), info
        foreign = other.getnewaddress()
        foreign_secret = other.dumpprivkey(foreign)
        wallet.importprivkey(foreign_secret, "imported", 1700000000)
        imported_info = wallet.validateaddress(foreign)
        watch_addr = other.getnewaddress()
        watch_key = other.getnewaddress()
        watch_pub = other.validateaddress(watch_key)["pubkey"]
        wallet.importaddress(watch_addr, False)
        wallet.importpubkey(watch_pub, False)
        ms = wallet.addmultisigaddress(2, [info[hd[0]]["pubkey"], info[hd[1]]["pubkey"], info[hd[2]]["pubkey"]])
        for dest in (hd[3], foreign, ms):
            wallet.sendtoaddress(dest, 5)
        wallet.generate(1)
        balance = wallet.getbalance()
        for a in (hd[0], foreign, ms):
            assert_equal(wallet.validateaddress(a)["ismine"], True)
        assert_equal(wallet.validateaddress(watch_addr)["iswatchonly"], True)
        assert wallet.verifywallet()["ok"]

        self.log("2. the release opens it: same balance, same keys and script, an address, a payment")
        self.restart_with(wallet, alt_bin)
        assert_equal(wallet.getbalance(), balance)
        for a in hd + [foreign, ms]:
            assert_equal(wallet.validateaddress(a)["ismine"], True)
        new_addr = wallet.getnewaddress("made by the release")
        assert_equal(wallet.validateaddress(new_addr)["ismine"], True)
        sent = wallet.sendtoaddress(other.getnewaddress(), 7)
        wallet.generate(1)
        assert wallet.gettransaction(sent)["confirmations"] >= 1
        balance_after = wallet.getbalance()
        assert balance_after < balance + 50 * 1000000            # (a block's reward comes in too: only that it is the same wallet matters)

        self.log("3. this build again: the metadata, the watch-only entries, the release's own work, and a clean verification")
        self.restart_with(wallet, main_bin)
        assert_equal(wallet.gethdseed(True)["mnemonic"], phrase)
        for a in hd:
            now = wallet.validateaddress(a)
            assert_equal((now["hdkeypath"], now["timestamp"]), (info[a]["hdkeypath"], info[a]["timestamp"]))
        assert_equal(wallet.validateaddress(foreign)["timestamp"], imported_info["timestamp"])
        assert_equal(wallet.validateaddress(watch_addr)["iswatchonly"], True)
        assert_equal(wallet.validateaddress(ms)["ismine"], True)
        assert_equal(wallet.validateaddress(new_addr)["ismine"], True)
        assert wallet.gettransaction(sent)["confirmations"] >= 1
        r = wallet.verifywallet()
        assert_equal(r["problems"], [])
        assert_equal(r["ok"], True)


if __name__ == "__main__":
    DowngradeCompatTest().main()
