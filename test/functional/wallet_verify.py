#!/usr/bin/env python3
"""verifywallet: checks the keys and the HD derivation, changes nothing, and needs an encrypted wallet unlocked."""
from test_framework import CorgiTestFramework, assert_equal, assert_raises_rpc_error


class VerifyWalletTest(CorgiTestFramework):
    num_nodes = 1

    def run_test(self):
        node = self.nodes[0]

        self.log("a plain wallet with some keys verifies clean")
        for _ in range(5):
            node.getnewaddress()
        r = node.verifywallet()
        assert_equal(r["ok"], True)
        assert_equal(r["problems"], [])
        assert r["keys_checked"] >= 5, r
        assert_equal(r["hd_keys_checked"], 0)

        self.log("an HD wallet: every derived key is found")
        node.sethdseed()
        for _ in range(7):
            node.getnewaddress()
        r = node.verifywallet()
        assert_equal(r["ok"], True)
        assert r["hd_keys_checked"] >= 7, r
        assert r["keys_checked"] >= r["hd_keys_checked"], r

        self.log("encrypted and locked: refused; unlocked: verifies clean, and the keys are the same ones")
        keys_before = r["keys_checked"]
        node.encryptwallet("verify passphrase")
        node.process.wait(timeout=60)
        node.start()
        assert_raises_rpc_error(-13, "locked", node.verifywallet)
        node.walletpassphrase("verify passphrase", 60)
        r = node.verifywallet()
        assert_equal(r["ok"], True)
        assert r["keys_checked"] >= keys_before, (r, keys_before)
        assert r["hd_keys_checked"] >= 7, r

        self.log("it changed nothing: the same call gives the same answer")
        assert_equal(node.verifywallet(), r)


if __name__ == "__main__":
    VerifyWalletTest().main()
