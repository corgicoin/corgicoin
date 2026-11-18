#!/usr/bin/env python3
"""walletpassphrase: the timeout is validated, and unlocking an unlocked wallet extends the unlock.

A negative timeout used to relock at once, a huge one overflowed the millisecond arithmetic (undefined behaviour),
and a second walletpassphrase on an unlocked wallet was refused with -17, so two payout runs that each unlock the
wallet failed against each other.
"""
import time

from test_framework import CorgiTestFramework, assert_equal, assert_raises_rpc_error, wait_until

PASSPHRASE = "unlock timeout passphrase"
INT64_MAX = 9223372036854775807


class UnlockTimeoutTest(CorgiTestFramework):
    num_nodes = 1

    def run_test(self):
        node = self.nodes[0]
        node.encryptwallet(PASSPHRASE)
        node.process.wait(timeout=60)
        node.start()
        addr = node.getnewaddress()

        self.log("a negative timeout is refused and leaves the wallet locked")
        assert_raises_rpc_error(-8, None, node.walletpassphrase, PASSPHRASE, -1)
        assert_raises_rpc_error(-13, None, node.dumpprivkey, addr)

        self.log("a wrong passphrase is still refused")
        assert_raises_rpc_error(-14, None, node.walletpassphrase, "wrong", 60)

        self.log("a huge timeout is capped, not overflowed: the wallet stays unlocked")
        node.walletpassphrase(PASSPHRASE, INT64_MAX)
        node.dumpprivkey(addr)
        until = node.getwalletinfo()["unlocked_until"]
        assert until > time.time() + 86400 * 365, until
        node.walletlock()
        assert_raises_rpc_error(-13, None, node.dumpprivkey, addr)

        self.log("unlocking an unlocked wallet checks the passphrase and extends the unlock")
        node.walletpassphrase(PASSPHRASE, 2)
        assert_raises_rpc_error(-14, None, node.walletpassphrase, "wrong", 60)
        node.walletpassphrase(PASSPHRASE, 60)          # used to fail with -17
        time.sleep(3)                                   # past the first timeout
        node.dumpprivkey(addr)                          # still unlocked
        assert node.getwalletinfo()["unlocked_until"] > time.time() + 30

        self.log("and it relocks when the last timeout is up")
        node.walletlock()
        node.walletpassphrase(PASSPHRASE, 1)
        wait_until(lambda: self.is_locked(node, addr), timeout=30, what="the wallet to relock")

    def is_locked(self, node, addr):
        try:
            node.dumpprivkey(addr)
            return False
        except Exception as e:
            return getattr(e, "code", None) == -13


if __name__ == "__main__":
    UnlockTimeoutTest().main()
