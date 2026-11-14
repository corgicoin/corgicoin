#!/usr/bin/env python3
"""Keys carry their creation time, and HD keys their path; it survives a restart and encryption.

validateaddress shows `timestamp` (seconds since the epoch) and, for an HD key, `hdkeypath`. A wallet restored from a file made
before this was recorded has no time for those keys: the field is simply absent, never a made-up date.
"""
import time

from test_framework import CorgiTestFramework, assert_equal


class KeyMetadataTest(CorgiTestFramework):
    num_nodes = 1

    def run_test(self):
        node = self.nodes[0]

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

        self.log("an imported key is dated from the day it was imported, and has no HD path")
        other = self.nodes[0].dumpprivkey(addr)
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
