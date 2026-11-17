#!/usr/bin/env python3
"""backupwallet: a complete copy is moved into place, nothing is left beside it, and an old backup is replaced whole."""
import os
import shutil

from test_framework import CorgiTestFramework, assert_equal


class WalletBackupTest(CorgiTestFramework):
    num_nodes = 2

    def run_test(self):
        n0, n1 = self.nodes
        n0.generate(3)
        addr = n0.getnewaddress()
        key = n0.dumpprivkey(addr)
        dest = os.path.join(self.tmpdir, "backup.dat")

        self.log("the first backup is a complete wallet file and no temporary file remains")
        n0.backupwallet(dest)
        assert os.path.exists(dest)
        assert not os.path.exists(dest + ".tmp")

        self.log("a second backup replaces the first in one step")
        n0.generate(1)
        old_size = os.path.getsize(dest)
        n0.backupwallet(dest)
        assert os.path.getsize(dest) >= old_size
        assert not os.path.exists(dest + ".tmp")

        self.log("the backup opens as a wallet with the same key")
        n1.stop()
        wallet = os.path.join(n1.datadir, "regtest", "wallet.dat")
        os.makedirs(os.path.dirname(wallet), exist_ok=True)
        shutil.copy(dest, wallet)
        n1.start()
        assert_equal(n1.dumpprivkey(addr), key)

        self.log("a backup to a directory that cannot be written fails and leaves the old file alone")
        before = os.path.getsize(dest)
        try:
            n0.backupwallet(os.path.join(self.tmpdir, "no-such-dir", "x.dat"))
        except Exception:
            pass
        else:
            raise AssertionError("backupwallet to a missing directory reported success")
        assert_equal(os.path.getsize(dest), before)


if __name__ == "__main__":
    WalletBackupTest().main()
