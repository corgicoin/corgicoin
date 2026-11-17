#!/usr/bin/env python3
"""A wallet that relocks while the key pool is being topped up must not take the node down.

walletpassphrase starts a thread that tops the key pool up to -keypool, and another that relocks the wallet when
the timeout is up. With a big pool and a short timeout the relock used to land in the middle of the top-up: key
generation then threw, the exception left a detached thread, and the whole daemon aborted. Relocking now waits for
the top-up to finish, and an exception in a wallet thread is logged instead of ending the process.
"""
import os
import time

from test_framework import CorgiTestFramework, JSONRPCException, assert_equal, wait_until

PASSPHRASE = "relock test passphrase"


class RelockDuringTopUpTest(CorgiTestFramework):
    num_nodes = 1

    def run_test(self):
        node = self.nodes[0]
        node.sethdseed()
        node.encryptwallet(PASSPHRASE)
        node.process.wait(timeout=60)

        self.log("restart locked with a key pool far bigger than the one the wallet has")
        node.start(["-keypool=1500"])
        assert_equal(node.getwalletinfo()["hdenabled"], True)
        self.addr = node.getnewaddress()

        for i in range(3):
            self.log("unlock for 1 second, which relocks in the middle of the top-up (round %d)" % (i + 1))
            node.walletpassphrase(PASSPHRASE, 1)
            # the top-up runs under the wallet lock, so give the relock time to come and be served after it
            wait_until(lambda: node.process.poll() is not None or self.locked(node), timeout=120,
                       what="the wallet to relock or the node to die")
            assert node.process.poll() is None, "the node died (status %s)" % node.process.returncode

        self.log("the pool was topped up, and the node still works")
        assert node.getwalletinfo()["keypoolsize"] > 1000, node.getwalletinfo()
        node.walletpassphrase(PASSPHRASE, 60)
        dump = os.path.join(self.tmpdir, "relock.dump")
        node.dumpwallet(dump)
        assert os.path.exists(dump)
        assert not os.path.exists(dump + ".tmp"), "the temporary file was left behind"
        assert oct(os.stat(dump).st_mode & 0o777) in ("0o600", "0o644", "0o666"), oct(os.stat(dump).st_mode)

    def locked(self, node):
        """True once the wallet refuses to reveal a private key (RPCs wait for any top-up that is still running)."""
        try:
            node.dumpprivkey(self.addr)
            return False
        except JSONRPCException as e:
            return e.code == -13
        except Exception:
            return False   # the node is gone; the caller checks the process


if __name__ == "__main__":
    RelockDuringTopUpTest().main()
