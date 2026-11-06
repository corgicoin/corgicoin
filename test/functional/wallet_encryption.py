#!/usr/bin/env python3
"""Wallet encryption: encryptwallet, unlock across a restart, wrong passphrases, passphrase change, signing.

Derivation method 0 must be Bitcoin's EVP_BytesToKey(SHA-512) on every build (wallet_crypto_tests.cpp pins the
derivations, including the PBKDF2 one v4.2-v4.7 wrote under method 0 and that unlock still accepts).
"""
from test_framework import CorgiTestFramework, assert_equal, assert_raises_rpc_error


class WalletEncryptionTest(CorgiTestFramework):
    num_nodes = 1

    def run_test(self):
        node = self.nodes[0]
        addr = node.getnewaddress()
        key = node.dumpprivkey(addr)

        self.log("encryptwallet stops the node; it restarts locked")
        node.encryptwallet("first passphrase")
        node.process.wait(timeout=60)
        node.start()
        assert_raises_rpc_error(-13, None, node.dumpprivkey, addr)

        self.log("wrong passphrases are refused, the right one unlocks")
        assert_raises_rpc_error(-14, None, node.walletpassphrase, "First passphrase", 60)
        node.walletpassphrase("first passphrase", 60)
        assert_equal(node.dumpprivkey(addr), key)
        sig = node.signmessage(addr, "corgi")
        assert node.verifymessage(addr, sig, "corgi")
        node.walletlock()
        assert_raises_rpc_error(-13, None, node.dumpprivkey, addr)

        self.log("walletpassphrasechange: old passphrase stops working, new one survives a restart")
        assert_raises_rpc_error(-14, None, node.walletpassphrasechange, "not it", "second passphrase")
        node.walletpassphrasechange("first passphrase", "second passphrase")
        assert_raises_rpc_error(-14, None, node.walletpassphrase, "first passphrase", 60)
        node.stop()
        node.start()
        node.walletpassphrase("second passphrase", 60)
        assert_equal(node.dumpprivkey(addr), key)


if __name__ == "__main__":
    WalletEncryptionTest().main()
