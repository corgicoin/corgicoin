#!/usr/bin/env python3
"""Restoring an HD wallet from its phrase finds the coins on later keys and carries on after the last used one.

sethdseed derived only -keypool keys, did not rescan, and handed out used addresses again. A wallet with more than about 100
addresses in use (a pool's payout wallet) lost sight of the coins on the later ones, and nothing said so. Now a restore derives
keys ahead (-hdrestoregap), rescans, and starts the next address after the last one the chain shows used.
"""
from decimal import Decimal

from test_framework import CorgiTestFramework, assert_equal


class HDRestoreTest(CorgiTestFramework):
    num_nodes = 2

    def run_test(self):
        original, restored = self.nodes
        self.connect_nodes(1, 0)

        seed = original.sethdseed()
        phrase = seed["mnemonic"]
        original.generate(60)

        self.log("the original wallet uses its first 260 addresses and receives coins at the 3rd and the 260th")
        addrs = [original.getnewaddress() for _ in range(260)]
        original.sendtoaddress(addrs[2], Decimal(7))
        original.sendtoaddress(addrs[259], Decimal(11))
        original.generate(1)
        self.sync_blocks()
        total = original.getbalance()
        assert total > 0

        self.log("a restore without a rescan knows the first keys only")
        info = restored.sethdseed(phrase, False)
        assert "keys_in_use" not in info
        assert_equal(restored.validateaddress(addrs[259])["ismine"], False)
        assert_equal(restored.getbalance(), 0)

        self.log("a restore with the default rescan finds every coin, on the early keys and the late one")
        info = restored.sethdseed(phrase)
        assert info["keys_in_use"] >= 260, info
        assert_equal(restored.validateaddress(addrs[259])["ismine"], True)
        assert_equal(restored.getbalance(), total)

        self.log("and the next address it hands out has never been used")
        fresh = restored.getnewaddress()
        assert fresh not in addrs
        assert_equal(restored.getreceivedbyaddress(fresh), 0)


if __name__ == "__main__":
    HDRestoreTest().main()
