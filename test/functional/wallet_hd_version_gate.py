#!/usr/bin/env python3
"""A wallet with an HD seed requires a client that has HD (4.5.0.0 or later).

The minimum version recorded in the wallet used to be 130000, below the client version of every 4.x release, so a
release from before HD opened an HD wallet, skipped the HD records, and topped the key pool up with random keys
that the recovery phrase does not cover. The check that refuses such a wallet cannot be run here without an old
binary; this test checks the recorded version, on a new HD wallet and on one that is reloaded.
"""
from test_framework import CorgiTestFramework, assert_equal

FEATURE_HD = 4050000
FEATURE_HD_LEGACY = 130000


class HDVersionGateTest(CorgiTestFramework):
    num_nodes = 1

    def run_test(self):
        node = self.nodes[0]
        self.log("every new wallet records the first release with HD as its minimum version (it is the wallet format's latest)")
        assert_equal(node.getwalletinfo()["walletversion"], FEATURE_HD)

        self.log("setting an HD seed keeps it there")
        node.sethdseed()
        assert_equal(node.getwalletinfo()["hdenabled"], True)
        assert_equal(node.getwalletinfo()["walletversion"], FEATURE_HD)

        self.log("it stays there across a restart")
        node.stop()
        node.start()
        assert_equal(node.getwalletinfo()["walletversion"], FEATURE_HD)
        assert_equal(node.getwalletinfo()["hdenabled"], True)

        self.log("-walletcompat puts the old number back, so that an older release can open the wallet on purpose")
        node.stop()
        node.start(["-walletcompat"])
        assert_equal(node.getwalletinfo()["walletversion"], FEATURE_HD_LEGACY)
        assert_equal(node.getwalletinfo()["hdenabled"], True)

        self.log("without it the gate comes back")
        node.stop()
        node.start()
        assert_equal(node.getwalletinfo()["walletversion"], FEATURE_HD)


if __name__ == "__main__":
    HDVersionGateTest().main()
