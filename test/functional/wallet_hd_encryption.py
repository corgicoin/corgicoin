#!/usr/bin/env python3
"""Encrypting an HD wallet: it must reload, keep every address it handed out, and sign for them.

Regression test for the CKey copy bug (the compression flag was lost when a key was copied). HD-derived keys went
into the key store as uncompressed, so `encryptwallet` wrote their encrypted copies under the uncompressed public key
and left the compressed plaintext `key` records behind. The node then refused to load its own wallet.dat
("LoadCryptedKey failed", "Wallet corrupted"), and the plaintext private keys were still in the file.
"""
from test_framework import CorgiTestFramework, assert_equal, assert_raises_rpc_error


class WalletHDEncryptionTest(CorgiTestFramework):
    num_nodes = 1

    def run_test(self):
        node = self.nodes[0]

        self.log("HD seed, then addresses handed out before encryption")
        node.sethdseed()
        addrs = [node.getnewaddress() for _ in range(3)]
        keys = {a: node.dumpprivkey(a) for a in addrs}
        for a in addrs:
            assert node.validateaddress(a)["isvalid"]

        self.log("encryptwallet stops the node; the encrypted HD wallet must load again")
        node.encryptwallet("hd passphrase")
        node.process.wait(timeout=60)
        node.start()  # raises if the node exits during startup, which is how the bug showed
        assert_equal(node.getwalletinfo()["hdenabled"], True)

        self.log("locked, then unlocked: every address handed out earlier still has its private key")
        assert_raises_rpc_error(-13, None, node.dumpprivkey, addrs[0])
        node.walletpassphrase("hd passphrase", 60)
        for a in addrs:
            assert_equal(node.dumpprivkey(a), keys[a])
            sig = node.signmessage(a, "corgi")
            assert node.verifymessage(a, sig, "corgi")

        self.log("addresses created after unlocking are usable and survive another restart")
        extra = node.getnewaddress()
        extra_key = node.dumpprivkey(extra)
        node.stop()
        node.start()
        node.walletpassphrase("hd passphrase", 60)
        assert_equal(node.dumpprivkey(extra), extra_key)
        assert_equal(node.dumpprivkey(addrs[1]), keys[addrs[1]])


if __name__ == "__main__":
    WalletHDEncryptionTest().main()
