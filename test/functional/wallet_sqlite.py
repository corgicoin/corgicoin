#!/usr/bin/env python3
"""SQLite wallets (-wallet=wallet.sqlite) and the migration from a wallet.dat (-migratewallet).

A node runs on a SQLite wallet like on a wallet.dat: sends, accounts, restarts, backupwallet, encryption (after which no unencrypted key may be left in
the file or in its log). Then a wallet.dat that a node has used and encrypted is migrated: the new file holds the same wallet (balance, accounts, every
transaction, the keys), and wallet.dat is not touched. Skipped by a corgicoind built without SQLite (-DUSE_SQLITE=ON).
"""
import hashlib
import os
import shutil
import sqlite3
import subprocess
import tempfile

from test_framework import CorgiTestFramework, assert_equal, assert_raises_rpc_error

B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def secret_of_wif(wif):
    """The 32 bytes of the private key in a wallet import format string."""
    n = 0
    for c in wif:
        n = n * 58 + B58.index(c)
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return raw[1:33]


def sha256_file(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


class WalletSqliteTest(CorgiTestFramework):
    num_nodes = 2

    def setup_nodes(self):
        probe = tempfile.mkdtemp()
        try:
            r = subprocess.run([self.options.corgicoind, "-datadir=" + probe, "-regtest", "-migratewallet"],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60)
        finally:
            shutil.rmtree(probe, ignore_errors=True)
        if "no SQLite support" in r.stderr:
            self.skip_test("this corgicoind was built without SQLite (-DUSE_SQLITE=ON)")
        self.extra_args = [["-wallet=wallet.sqlite"], []]
        super().setup_nodes()

    @staticmethod
    def regtest_dir(node):
        return os.path.join(node.datadir, "regtest")

    def activity(self, node):
        """Mine, pay an address of an account, move between accounts: what a wallet is used for."""
        node.generate(101)
        addr = node.getnewaddress("savings")
        node.sendtoaddress(addr, 10)
        node.generate(1)
        node.move("", "ops", 3)
        node.move("ops", "savings", 1)
        node.sendtoaddress(node.getnewaddress("ops"), 2)
        node.generate(1)
        return addr

    def snapshot(self, node):
        txs = sorted((t.get("txid", ""), t["category"], str(t["amount"]), t["account"]) for t in node.listtransactions("*", 1000))
        return {"balance": node.getbalance(), "accounts": node.listaccounts(), "txs": txs,
                "savings": sorted(node.getaddressesbyaccount("savings"))}

    def run_test(self):
        sq, bdb = self.nodes

        self.log("a node on -wallet=wallet.sqlite: the wallet is that file, not a wallet.dat")
        d = self.regtest_dir(sq)
        assert os.path.exists(os.path.join(d, "wallet.sqlite"))
        assert not os.path.exists(os.path.join(d, "wallet.dat"))
        addr = self.activity(sq)
        before = self.snapshot(sq)
        assert before["balance"] > 0 and len(before["txs"]) > 5

        self.log("it is all still there after a restart")
        sq.stop()
        sq.start()
        assert_equal(self.snapshot(sq), before)

        self.log("backupwallet makes one file that is a wallet of its own")
        backup = os.path.join(sq.datadir, "backup")
        os.makedirs(backup)
        sq.backupwallet(backup)
        assert_equal(sorted(os.listdir(backup)), ["wallet.sqlite"])
        con = sqlite3.connect(os.path.join(backup, "wallet.sqlite"))
        assert con.execute("SELECT count(*) FROM wallet").fetchone()[0] > 10
        con.close()
        backup_file = os.path.join(backup, "backup2.sqlite")
        sq.backupwallet(backup_file)
        assert os.path.getsize(backup_file) > 0

        self.log("encryptwallet leaves no unencrypted key in the file or in its log")
        key = sq.dumpprivkey(addr)
        secret = secret_of_wif(key)
        assert_equal(len(secret), 32)
        sq.encryptwallet("a passphrase")
        sq.process.wait(timeout=60)
        for name in os.listdir(d):
            if name.startswith("wallet.sqlite"):
                with open(os.path.join(d, name), "rb") as f:
                    assert secret not in f.read(), "the private key is still in %s" % name
        con = sqlite3.connect(os.path.join(d, "wallet.sqlite"))
        assert_equal(con.execute("SELECT count(*) FROM wallet WHERE substr(key, 1, 4) = x'036b6579'").fetchone()[0], 0)
        assert con.execute("SELECT count(*) FROM wallet WHERE substr(key, 1, 5) = x'04636b6579'").fetchone()[0] > 0
        con.close()
        sq.start()
        assert_raises_rpc_error(-13, None, sq.dumpprivkey, addr)
        sq.walletpassphrase("a passphrase", 60)
        assert_equal(sq.dumpprivkey(addr), key)
        assert_equal(self.snapshot(sq), before)

        self.log("migrate a wallet.dat that a node has used and encrypted")
        d = self.regtest_dir(bdb)
        addr = self.activity(bdb)
        key = bdb.dumpprivkey(addr)
        bdb.encryptwallet("another passphrase")
        bdb.process.wait(timeout=60)
        bdb.start()
        bdb.walletpassphrase("another passphrase", 60)
        before = self.snapshot(bdb)
        bdb.stop()
        sha = sha256_file(os.path.join(d, "wallet.dat"))
        listing = sorted(os.listdir(d))

        cmd = [self.options.corgicoind, "-datadir=" + bdb.datadir, "-regtest", "-migratewallet"]
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120)
        assert_equal(r.returncode, 0, r.stdout + r.stderr)
        assert "wallet.sqlite" in r.stdout, r.stdout

        self.log("wallet.dat is as it was, and the new file is the only change in the directory")
        assert_equal(sha256_file(os.path.join(d, "wallet.dat")), sha)
        assert_equal(sorted(os.listdir(d)), sorted(listing + ["wallet.sqlite"]))

        self.log("an existing wallet.sqlite is never overwritten")
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120)
        assert r.returncode != 0
        assert "exists already" in r.stderr, r.stderr

        self.log("a node on the new file: the same wallet, still encrypted")
        bdb.extra_args = ["-wallet=wallet.sqlite"]
        bdb.start()
        assert_raises_rpc_error(-13, None, bdb.dumpprivkey, addr)
        bdb.walletpassphrase("another passphrase", 60)
        assert_equal(bdb.dumpprivkey(addr), key)
        assert_equal(self.snapshot(bdb), before)

        self.log("-wallet takes a file name, not a path")
        bdb.stop()
        bdb.extra_args = ["-wallet=../wallet.sqlite"]
        bad = subprocess.run([self.options.corgicoind, "-datadir=" + bdb.datadir, "-regtest", "-wallet=../wallet.sqlite", "-server",
                              "-port=%d" % bdb.p2p_port, "-rpcport=%d" % bdb.rpc_port, "-printtoconsole=0"],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60)
        assert "not a file name" in bad.stdout + bad.stderr, (bad.stdout + bad.stderr)[-500:]


if __name__ == "__main__":
    WalletSqliteTest().main()
