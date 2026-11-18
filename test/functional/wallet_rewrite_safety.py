#!/usr/bin/env python3
"""A wallet rewrite that fails must leave wallet.dat alone, and a start with only a backup of it must refuse to run.

CDB::Rewrite (used when a wallet is encrypted) copied wallet.dat to a new file and then removed the original and
renamed the copy into place. If it could not open a cursor on the original it copied nothing, still counted that as
success, and replaced the real wallet with an empty file. And a stop between its remove and its rename left only
the copy, so the next start created a fresh empty wallet.dat beside it. Here:
  - the rewrite is made to fail on a cursor error and on a failed move; the keys must still be there afterwards;
  - a datadir whose wallet.dat has gone, leaving wallet.dat.rewrite-orig, must refuse to start and not create a wallet.
  - a backup of the user's own called wallet.dat.bak must not stop the rewrite, and must be left as it is.
"""
import os
import shutil

from test_framework import AssertionFailed, CorgiTestFramework, assert_equal

PASSPHRASE = "rewrite safety passphrase"


class RewriteSafetyTest(CorgiTestFramework):
    num_nodes = 1

    def wallet_path(self, node, suffix=""):
        return os.path.join(node.datadir, "regtest", "wallet.dat" + suffix)

    def run_test(self):
        node = self.nodes[0]
        node.stop()

        for fault in ("cursor", "swap"):
            self.log("encrypting while the rewrite fails (%s): wallet.dat and its keys survive" % fault)
            shutil.rmtree(os.path.join(node.datadir, "regtest"), ignore_errors=True)
            node.start(["-testrewritefault=" + fault])
            node.generate(3)
            addr = node.getnewaddress()
            key = node.dumpprivkey(addr)
            node.encryptwallet(PASSPHRASE)
            node.process.wait(timeout=60)
            assert os.path.getsize(self.wallet_path(node)) > 4096, "wallet.dat was replaced by a near-empty file"
            assert not os.path.exists(self.wallet_path(node, ".rewrite-orig")), ".rewrite-orig left behind"
            assert not os.path.exists(self.wallet_path(node, ".rewrite")), ".rewrite left behind"
            node.start()
            node.walletpassphrase(PASSPHRASE, 60)
            assert_equal(node.dumpprivkey(addr), key)
            node.stop()

        self.log("a user backup named wallet.dat.bak: the rewrite after encryption still completes, the backup is untouched")
        shutil.rmtree(os.path.join(node.datadir, "regtest"), ignore_errors=True)
        node.start()
        node.generate(3)
        addr = node.getnewaddress()
        key = node.dumpprivkey(addr)
        node.stop()
        shutil.copy(self.wallet_path(node), self.wallet_path(node, ".bak"))
        with open(self.wallet_path(node, ".bak"), "rb") as f:
            user_backup = f.read()
        node.start()
        node.encryptwallet(PASSPHRASE)
        node.process.wait(timeout=60)
        with open(self.wallet_path(node, ".bak"), "rb") as f:
            assert f.read() == user_backup, "the user's wallet.dat.bak was changed"
        assert not os.path.exists(self.wallet_path(node, ".rewrite-orig")), ".rewrite-orig left behind"
        assert "Rewriting of" not in open(node.debug_log, errors="replace").read(), "the rewrite failed"
        os.remove(self.wallet_path(node, ".bak"))

        self.log("only a backup left: the node refuses to start and creates no new wallet")
        os.replace(self.wallet_path(node), self.wallet_path(node, ".rewrite-orig"))
        try:
            node.start()
        except AssertionFailed:
            pass
        else:
            raise AssertionFailed("the node started with wallet.dat missing and wallet.dat.rewrite-orig present")
        assert not os.path.exists(self.wallet_path(node)), "a new wallet.dat was created"
        assert os.path.exists(self.wallet_path(node, ".rewrite-orig"))

        self.log("with the file put back it starts and has its keys")
        os.replace(self.wallet_path(node, ".rewrite-orig"), self.wallet_path(node))
        node.start()
        node.walletpassphrase(PASSPHRASE, 60)
        assert_equal(node.dumpprivkey(addr), key)


if __name__ == "__main__":
    RewriteSafetyTest().main()
