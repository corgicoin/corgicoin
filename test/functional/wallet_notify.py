#!/usr/bin/env python3
"""-walletnotify runs a command with the transaction id when a wallet transaction is new or changes.

The command here records each notification as its own file (a shared file appended to by commands running at the same time
loses lines on Windows, where the second cannot open it while the first has it). A transaction sent from the wallet is announced when it is made, and again when
it confirms (it changed).
"""
import os
import sys

from test_framework import CorgiTestFramework, wait_until


class WalletNotifyTest(CorgiTestFramework):
    num_nodes = 1

    # Run by the node for each notification: makes <txid>.<n> with the first free n. Exclusive create is atomic, so commands
    # running at the same time never collide.
    RECORDER = (
        "import os, sys\n"
        "txid, out = sys.argv[1], sys.argv[2]\n"
        "n = 0\n"
        "while True:\n"
        "    try:\n"
        "        os.close(os.open(os.path.join(out, '%s.%d' % (txid, n)), os.O_CREAT | os.O_EXCL | os.O_WRONLY))\n"
        "        break\n"
        "    except FileExistsError:\n"
        "        n += 1\n"
    )

    def lines(self, path):
        """The txids notified, once per notification."""
        if not os.path.isdir(path):
            return []
        return [name.split(".")[0] for name in os.listdir(path)]

    def run_test(self):
        node = self.nodes[0]
        out = os.path.join(node.datadir, "walletnotify")
        os.makedirs(out)
        recorder = os.path.join(self.tmpdir, "record_notify.py")
        with open(recorder, "w") as f:
            f.write(self.RECORDER)
        node.stop()
        # unquoted: on Windows system() goes through cmd.exe, which strips the outer quotes of a command that starts with one;
        # none of these paths has a space
        assert " " not in sys.executable + recorder + out, "a path with a space: quote it for this platform"
        node.start(["-walletnotify=%s %s %%s %s" % (sys.executable, recorder, out)])

        self.log("mining pays the wallet: each coinbase is announced")
        node.generate(101)
        wait_until(lambda: len(self.lines(out)) >= 101, timeout=120, what="a notification for each of 101 coinbases")
        before = len(self.lines(out))

        self.log("a send is announced with its id")
        txid = node.sendtoaddress(node.getnewaddress(), 1)
        wait_until(lambda: txid in self.lines(out), timeout=60, what="the notification for the send")
        assert all(len(l) == 64 and set(l) <= set("0123456789abcdef") for l in self.lines(out)), "a line that is not a txid"

        self.log("and again when it confirms")
        count = self.lines(out).count(txid)
        node.generate(1)
        wait_until(lambda: self.lines(out).count(txid) > count, timeout=60, what="the notification when it confirmed")
        assert len(self.lines(out)) > before


if __name__ == "__main__":
    WalletNotifyTest().main()
