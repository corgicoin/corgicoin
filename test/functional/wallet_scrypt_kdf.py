#!/usr/bin/env python3
"""-walletkdf=scrypt: the wallet passphrase is turned into a key with scrypt, and the wallet says so.

An ordinary encrypted wallet still uses the iterated hash and still opens with any release. With the option, the master key is
derived with scrypt, the wallet's minimum version rises so that an older release says what is wrong instead of "incorrect
passphrase", the wallet unlocks with or without the option afterwards, and a passphrase change keeps scrypt (and a plain wallet
moves to it when the option is given at the change).
"""
from test_framework import CorgiTestFramework, assert_equal, assert_raises_rpc_error

SCRYPT_VERSION = 4090000


class ScryptKDFTest(CorgiTestFramework):
    num_nodes = 2
    extra_args = [[], ["-walletkdf=scrypt"]]

    def log_text(self, node):
        with open(node.debug_log, errors="replace") as f:
            return f.read()

    def run_test(self):
        node, fresh = self.nodes

        self.log("encrypting a new wallet with the option: scrypt from the start, version raised, opens without the option")
        fresh.encryptwallet("fresh passphrase")
        fresh.process.wait(timeout=60)
        assert "Encrypting Wallet with scrypt" in self.log_text(fresh)
        fresh.start(["-walletkdf="])           # an empty value is not 'scrypt': the option is off
        assert_equal(fresh.getwalletinfo()["walletversion"], SCRYPT_VERSION)
        assert_raises_rpc_error(-14, None, fresh.walletpassphrase, "wrong", 60)
        fresh.walletpassphrase("fresh passphrase", 60)

        self.log("a plain encrypted wallet: the iterated hash, and the version is not raised")
        node.encryptwallet("first passphrase")
        node.process.wait(timeout=60)
        node.start()
        plain_version = node.getwalletinfo()["walletversion"]
        assert plain_version < SCRYPT_VERSION, plain_version
        assert "scrypt" not in self.log_text(node)
        node.walletpassphrase("first passphrase", 60)
        node.walletlock()

        self.log("changing its passphrase with -walletkdf=scrypt moves it to scrypt, and raises the version")
        node.stop()
        node.start(["-walletkdf=scrypt"])
        node.walletpassphrasechange("first passphrase", "second passphrase")
        assert "Wallet passphrase changed, derived with scrypt" in self.log_text(node)
        assert_equal(node.getwalletinfo()["walletversion"], SCRYPT_VERSION)

        self.log("it opens without the option, with the new passphrase only")
        node.stop()
        node.start()
        assert_raises_rpc_error(-14, None, node.walletpassphrase, "first passphrase", 60)
        node.walletpassphrase("second passphrase", 60)
        node.sethdseed()
        assert node.getnewaddress()
        node.walletlock()

        self.log("a later change, without the option, stays on scrypt")
        before = self.log_text(node).count("derived with scrypt")
        node.walletpassphrasechange("second passphrase", "third passphrase")
        assert self.log_text(node).count("derived with scrypt") == before + 1
        node.stop()
        node.start()
        node.walletpassphrase("third passphrase", 60)
        assert_equal(node.getwalletinfo()["walletversion"], SCRYPT_VERSION)


if __name__ == "__main__":
    ScryptKDFTest().main()
