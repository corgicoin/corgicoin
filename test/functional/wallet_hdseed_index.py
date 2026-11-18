#!/usr/bin/env python3
"""sethdseed with the phrase the wallet already uses must not hand out an address twice; gethdseed shows the phrase.

Before: setting the same phrase again reset the derivation index to 0, so the next address repeated one already given
out. gethdseed is new: it needs an explicit `true`, an HD wallet, and an unlocked wallet.
"""
from test_framework import CorgiTestFramework, assert_equal, assert_raises_rpc_error

PHRASE = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"


class WalletHDSeedIndexTest(CorgiTestFramework):
    num_nodes = 1

    def run_test(self):
        node = self.nodes[0]

        self.log("gethdseed on a wallet with no HD seed")
        assert_raises_rpc_error(-4, None, node.gethdseed, True)

        node.sethdseed(PHRASE)
        first = [node.getnewaddress() for _ in range(3)]

        self.log("setting the same phrase again keeps the index: no address repeats")
        node.sethdseed(PHRASE)
        again = [node.getnewaddress() for _ in range(3)]
        assert not set(first) & set(again), "addresses repeated after sethdseed with the same phrase"
        for a in first:
            node.dumpprivkey(a)  # still ours

        self.log("gethdseed needs the explicit confirmation")
        assert_raises_rpc_error(-8, None, node.gethdseed, False)
        r = node.gethdseed(True)
        assert_equal(r["mnemonic"], PHRASE)

        self.log("a different phrase starts a new chain")
        other = "legal winner thank year wave sausage worth useful legal winner thank yellow"
        node.sethdseed(other)
        assert_equal(node.gethdseed(True)["mnemonic"], other)

        self.log("encrypted and locked: gethdseed refuses; unlocked: it works")
        node.encryptwallet("seed passphrase")
        node.process.wait(timeout=60)
        node.start()
        assert_raises_rpc_error(-13, None, node.gethdseed, True)
        node.walletpassphrase("seed passphrase", 60)
        assert_equal(node.gethdseed(True)["mnemonic"], other)


if __name__ == "__main__":
    WalletHDSeedIndexTest().main()
