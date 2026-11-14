#!/usr/bin/env python3
"""-walletnotify runs a command with the transaction id when a wallet transaction is new or changes.

The command here appends the id to a file. A transaction sent from the wallet is announced when it is made, and again when
it confirms (it changed). A transaction that is not the wallet's is not announced.
"""
import os

from test_framework import CorgiTestFramework, wait_until


class WalletNotifyTest(CorgiTestFramework):
    num_nodes = 1

    def lines(self, path):
        if not os.path.exists(path):
            return []
        with open(path) as f:
            return [l.strip() for l in f if l.strip()]

    def run_test(self):
        node = self.nodes[0]
        out = os.path.join(node.datadir, "walletnotify.txt")
        node.stop()
        node.start(["-walletnotify=echo %s >> " + out])

        self.log("mining pays the wallet: each coinbase is announced")
        node.generate(101)
        wait_until(lambda: len(self.lines(out)) >= 101, timeout=30, what="a notification for each of 101 coinbases")
        before = len(self.lines(out))

        self.log("a send is announced with its id")
        txid = node.sendtoaddress(node.getnewaddress(), 1)
        wait_until(lambda: txid in self.lines(out), timeout=30, what="the notification for the send")
        assert all(len(l) == 64 and set(l) <= set("0123456789abcdef") for l in self.lines(out)), "a line that is not a txid"

        self.log("and again when it confirms")
        count = self.lines(out).count(txid)
        node.generate(1)
        wait_until(lambda: self.lines(out).count(txid) > count, timeout=30, what="the notification when it confirmed")
        assert len(self.lines(out)) > before


if __name__ == "__main__":
    WalletNotifyTest().main()
