#!/usr/bin/env python3
"""Keys carry their creation time, and HD keys their path; it survives a restart and encryption.

validateaddress shows `timestamp` (seconds since the epoch) and, for an HD key, `hdkeypath`. A wallet restored from a file made
before this was recorded has no time for those keys: the field is simply absent, never a made-up date.
"""
import time

from test_framework import CorgiTestFramework, assert_equal


class KeyMetadataTest(CorgiTestFramework):
    num_nodes = 2

    def run_test(self):
        node = self.nodes[0]
        # keys of a wallet that is not HD yet, to import later (once it has a phrase, its new keys are derived ones the first wallet would already hold)
        foreign = self.nodes[1].getnewaddress()
        foreign_secret = self.nodes[1].dumpprivkey(foreign)
        foreign2 = self.nodes[1].getnewaddress()
        foreign2_secret = self.nodes[1].dumpprivkey(foreign2)

        self.log("a new key has the time it was made, and no HD path in a non-HD wallet")
        before = int(time.time())
        addr = node.getnewaddress()
        after = int(time.time())
        info = node.validateaddress(addr)
        assert before - 2 <= info["timestamp"] <= after + 2, info
        assert "hdkeypath" not in info

        self.log("an HD wallet gives its keys their path: m/44'/99'/0'/0/<index>, in order")
        node.sethdseed()
        paths = []
        for _ in range(3):
            a = node.getnewaddress()
            i = node.validateaddress(a)
            assert i["hdkeypath"].startswith("m/44'/99'/0'/0/"), i
            assert i["timestamp"] > 0
            paths.append(int(i["hdkeypath"].rsplit("/", 1)[1]))
        assert paths == sorted(paths) and len(set(paths)) == 3, paths

        self.log("restoring the phrase the wallet already uses keeps what each key already carries (times and paths)")
        phrase = node.gethdseed(True)["mnemonic"]
        kept = {x: node.validateaddress(x) for x in (addr, a)}
        node.sethdseed(phrase)
        for x, was in kept.items():
            now = node.validateaddress(x)
            assert_equal(now.get("timestamp"), was.get("timestamp"))
            assert_equal(now.get("hdkeypath"), was.get("hdkeypath"))

        self.log("a wallet restored from the phrase gives the keys it derives their path, and no made-up date")
        other_node = self.nodes[1]
        other_node.sethdseed(phrase)
        restored = other_node.validateaddress(a)
        assert_equal(restored["ismine"], True)
        assert_equal(restored["hdkeypath"], kept[a]["hdkeypath"])
        assert "timestamp" not in restored, restored

        self.log("an imported key has no date unless it is given one (never the day it was imported), and no HD path")
        node.importprivkey(foreign_secret, "undated")
        undated = node.validateaddress(foreign)
        assert "timestamp" not in undated and "hdkeypath" not in undated, undated
        node.importprivkey(foreign2_secret, "dated", 1700000000)
        assert_equal(node.validateaddress(foreign2)["timestamp"], 1700000000)

        self.log("and the times survive a restart")
        node.stop()
        node.start()
        assert_equal(node.validateaddress(addr)["timestamp"], info["timestamp"])      # survived a restart

        self.log("and the time survives encrypting the wallet")
        keep = node.validateaddress(a)
        node.encryptwallet("meta passphrase")
        node.process.wait(timeout=60)
        node.start()
        again = node.validateaddress(a)
        assert_equal((again["timestamp"], again["hdkeypath"]), (keep["timestamp"], keep["hdkeypath"]))
        assert_equal(node.validateaddress(addr)["timestamp"], info["timestamp"])


if __name__ == "__main__":
    KeyMetadataTest().main()
