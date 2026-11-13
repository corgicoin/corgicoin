#!/usr/bin/env python3
"""An encrypted HD wallet forgets its recovery phrase and master key in memory when it locks.

Before, the phrase and master key stayed in the process for as long as it ran, through every walletlock and
relock timeout, so "locked" did not protect the root secret from a core dump, swap or a crash report.
getwalletinfo.hdseed_available reports whether the seed is in memory: true only while unlocked.
"""
from test_framework import CorgiTestFramework, assert_equal, assert_raises_rpc_error

PASSPHRASE = "hd lock secrets passphrase"


class HDLockSecretsTest(CorgiTestFramework):
    num_nodes = 1

    def run_test(self):
        node = self.nodes[0]
        node.sethdseed()
        assert_equal(node.getwalletinfo()["hdseed_available"], True)   # not encrypted yet: always available

        node.encryptwallet(PASSPHRASE)
        node.process.wait(timeout=60)
        node.start()

        self.log("locked: the seed is not in memory")
        assert_equal(node.getwalletinfo()["hdseed_available"], False)

        self.log("unlocked: it is, and new addresses derive from it")
        node.walletpassphrase(PASSPHRASE, 60)
        assert_equal(node.getwalletinfo()["hdseed_available"], True)
        addr = node.getnewaddress()
        key = node.dumpprivkey(addr)

        self.log("locked again: the seed is wiped, and the address and key survive a later unlock")
        node.walletlock()
        assert_equal(node.getwalletinfo()["hdseed_available"], False)
        assert_raises_rpc_error(-13, None, node.dumpprivkey, addr)
        node.walletpassphrase(PASSPHRASE, 60)
        assert_equal(node.getwalletinfo()["hdseed_available"], True)
        assert_equal(node.dumpprivkey(addr), key)
        assert node.getnewaddress() != addr

        self.log("a timeout relock wipes it too")
        node.walletpassphrase(PASSPHRASE, 1)
        self.wait_for_wipe(node)

    def wait_for_wipe(self, node):
        import time
        deadline = time.time() + 30
        while time.time() < deadline:
            if not node.getwalletinfo()["hdseed_available"]:
                return
            time.sleep(0.25)
        raise AssertionError("the seed was still in memory 30 s after the unlock timeout")


if __name__ == "__main__":
    HDLockSecretsTest().main()
