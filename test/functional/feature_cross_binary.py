#!/usr/bin/env python3
"""Two different corgicoind builds interoperate: consensus, wallets, signatures and wallet encryption.

Run it with a second build, for example one linked against a different OpenSSL:

    python3 test/functional/feature_cross_binary.py --corgicoind build/corgicoind \\
        --alt-corgicoind /path/to/other/build/corgicoind

Without --alt-corgicoind (or $CORGICOIND_ALT) the test reports SKIPPED (exit code 77, shown as SKIP by
test_runner.py). Use it before moving to a new
OpenSSL version: it checks that blocks and transactions signed by one build are accepted by the other,
that a wallet.dat opens identically in both, and that an encrypted wallet unlocks with the same
passphrase whichever build encrypted it.

Known limit: across the OpenSSL 1.1 / 3.x boundary the two encrypted-wallet checks FAIL, by design. CCrypter
derives the wallet key with a different function on each side (EVP_BytesToKey before 3.0, PBKDF2-HMAC-SHA512
from 3.0) yet records both as derivation method 0, so those wallets really are incompatible (see
crypter_tests.cpp). A pair of builds on the same side of that boundary passes.
"""
import os

from test_framework import (CorgiTestFramework, TestNode, assert_equal, assert_raises_rpc_error, wait_until)

PASSPHRASE = "correct horse battery staple"


class CrossBinaryTest(CorgiTestFramework):
    num_nodes = 2

    def node_binary(self, index):
        # node0 runs the main build, node1 the alternate one
        return self.options.alt_corgicoind if index == 1 else self.options.corgicoind

    def setup_nodes(self):
        if not self.options.alt_corgicoind:
            self.skip_test("pass --alt-corgicoind (or set CORGICOIND_ALT) to a second build")
        if not os.path.isfile(self.options.alt_corgicoind):
            self.skip_test("alternate build not found at %r" % self.options.alt_corgicoind)
        if os.path.realpath(self.options.alt_corgicoind) == os.path.realpath(self.options.corgicoind):
            self.log("warning: both builds are the same file, so this only checks the test itself")
        super().setup_nodes()

    def add_node(self, binary):
        index = len(self.nodes)
        node = TestNode(index, binary, os.path.join(self.tmpdir, "node%d" % index), None)
        self.nodes.append(node)
        node.start()
        return node

    def restart_with(self, node, binary):
        node.stop()
        node.binary = binary
        node.start()

    def wait_exit(self, node):
        node.process.wait(timeout=60)  # encryptwallet makes the daemon stop itself

    def run_test(self):
        main_bin, alt_bin = self.options.corgicoind, self.options.alt_corgicoind
        x, y = self.nodes  # x = main build, y = alternate build

        self.log("consensus: each build accepts the other's blocks")
        self.connect_nodes(1, 0)
        x.generate(60)
        self.sync_blocks()
        assert_equal(y.getblockcount(), 60)

        self.log("signatures: a payment signed by the main build is accepted by the alternate one")
        y_addr, x_addr = y.getnewaddress(), x.getnewaddress()
        x.sendtoaddress(y_addr, 100)
        self.sync_mempools()
        assert_equal(len(y.getrawmempool()), 1)
        y.generate(1)  # the alternate build mines a block containing it
        self.sync_blocks()
        assert_equal(x.getbestblockhash(), y.getbestblockhash())
        assert_equal(y.getbalance(), 100)

        self.log("signatures: a payment signed by the alternate build is accepted by the main one")
        y.sendtoaddress(x_addr, 40)
        self.sync_mempools()
        assert_equal(len(x.getrawmempool()), 1)
        x.generate(1)
        self.sync_blocks()
        assert_equal(x.getbestblockhash(), y.getbestblockhash())

        self.log("wallet file: node1's wallet.dat opens identically in the main build")
        key, balance = y.dumpprivkey(y_addr), y.getbalance()
        sig_alt = y.signmessage(y_addr, "hello corgi")
        self.restart_with(y, main_bin)
        assert_equal(y.getbalance(), balance)
        assert_equal(y.dumpprivkey(y_addr), key)
        assert y.verifymessage(y_addr, sig_alt, "hello corgi"), "main build rejects the alternate build's signature"
        sig_main = y.signmessage(y_addr, "hello corgi")
        self.restart_with(y, alt_bin)
        assert y.verifymessage(y_addr, sig_main, "hello corgi"), "alternate build rejects the main build's signature"

        self.log("encrypted wallet: encrypted by the main build, unlocked by the alternate one")
        e1 = self.add_node(main_bin)
        e1_addr = e1.getnewaddress()
        e1_key = e1.dumpprivkey(e1_addr)
        e1.encryptwallet(PASSPHRASE)
        self.wait_exit(e1)
        e1.binary = alt_bin
        e1.start()
        e1.walletpassphrase(PASSPHRASE, 60)  # raises if the passphrase is rejected
        assert_equal(e1.dumpprivkey(e1_addr), e1_key)

        self.log("encrypted wallet: encrypted by the alternate build, unlocked by the main one")
        e2 = self.add_node(alt_bin)
        e2_addr = e2.getnewaddress()
        e2_key = e2.dumpprivkey(e2_addr)
        e2.encryptwallet(PASSPHRASE)
        self.wait_exit(e2)
        e2.binary = main_bin
        e2.start()
        e2.walletpassphrase(PASSPHRASE, 60)
        assert_equal(e2.dumpprivkey(e2_addr), e2_key)

        self.log("a wrong passphrase is still refused")
        e2.walletlock()
        assert_raises_rpc_error(-14, None, e2.walletpassphrase, "wrong passphrase", 60)


if __name__ == "__main__":
    CrossBinaryTest().main()
