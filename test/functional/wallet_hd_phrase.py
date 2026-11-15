#!/usr/bin/env python3
"""A recovery phrase typed with unusual spacing restores the same wallet as the canonical phrase.

The BIP39 seed is a hash of the exact phrase string, so "abandon  abandon ..." (two spaces) used to pass the
checksum test and then derive a completely different, empty wallet. sethdseed now normalises the whitespace first.
"""
from test_framework import CorgiTestFramework, assert_equal, assert_raises_rpc_error

CANON = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
NBSP = " "


class WalletHDPhraseTest(CorgiTestFramework):
    num_nodes = 4

    def run_test(self):
        reference, double, mixed, unicode_spaces = self.nodes

        self.log("the canonical phrase is the reference wallet")
        out = reference.sethdseed(CANON)
        assert_equal(out["mnemonic"], CANON)
        ref_addrs = [reference.getnewaddress() for _ in range(3)]
        ref_seed_id = reference.getwalletinfo()["hdseedid"]

        variants = [
            (double, CANON.replace(" ", "  ")),
            (mixed, "  " + CANON.replace(" ", " \t") + " \n"),
            (unicode_spaces, CANON.replace(" ", NBSP)),
        ]
        for node, phrase in variants:
            self.log("restoring %r gives the same wallet" % phrase[:40])
            out = node.sethdseed(phrase)
            assert_equal(out["mnemonic"], CANON, "the reply shows the phrase as stored")
            assert_equal(out["hdseedid"], ref_seed_id)
            assert_equal([node.getnewaddress() for _ in range(3)], ref_addrs)

        self.log("the stored phrase is canonical: the wallet reloads with the same addresses")
        double.stop()
        double.start()
        assert_equal(double.getwalletinfo()["hdseedid"], ref_seed_id)

        self.log("normalising whitespace does not make a bad phrase valid")
        assert_raises_rpc_error(-4, "Invalid BIP39 mnemonic", reference.sethdseed, "abandon  abandon  abandon")
        assert_raises_rpc_error(-4, "Invalid BIP39 mnemonic", reference.sethdseed,
                                CANON.replace(" ", "​ ", 1))


if __name__ == "__main__":
    WalletHDPhraseTest().main()
