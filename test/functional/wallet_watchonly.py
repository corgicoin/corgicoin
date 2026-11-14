#!/usr/bin/env python3
"""Watch-only: a wallet can follow an address it holds no key for, and never spends it.

Node 0 holds the keys. Node 1 imports node 0's address (and a public key) as watch-only: it sees what is paid there and
what is spent from it, finds the history by rescanning, keeps the import across a restart, and cannot spend it.
"""
from decimal import Decimal

from test_framework import CorgiTestFramework, assert_equal, assert_raises_rpc_error


class WatchOnlyTest(CorgiTestFramework):
    num_nodes = 2

    def run_test(self):
        keys, watcher = self.nodes
        keys.generate(101)
        self.connect_nodes(1, 0)
        self.sync_blocks()

        cold = keys.getnewaddress()
        paid = keys.sendtoaddress(cold, 5)           # before the import: history that a rescan must find
        keys.generate(1)
        self.sync_blocks()

        self.log("an address the wallet does not hold is not watched, and the watcher's balance is not touched")
        assert_equal(watcher.validateaddress(cold)["iswatchonly"], False)
        assert_equal(watcher.getwatchonlybalance(), 0)

        self.log("import it with a rescan: the earlier payment shows")
        watcher.importaddress(cold)
        assert_equal(watcher.validateaddress(cold)["iswatchonly"], True)
        assert_equal(watcher.validateaddress(cold)["ismine"], False)
        assert_equal(watcher.getwatchonlybalance(), Decimal(5))
        unspent = watcher.listwatchonlyunspent()
        assert_equal(len(unspent), 1)
        assert_equal((unspent[0]["txid"], unspent[0]["address"], unspent[0]["amount"]), (paid, cold, Decimal(5)))

        self.log("it is not the watcher's money: not in its balance, and not spent when it sends")
        assert_equal(watcher.getbalance(), 0)
        assert_raises_rpc_error(-6, None, watcher.sendtoaddress, keys.getnewaddress(), 1)

        self.log("a payment after the import is followed live")
        keys.sendtoaddress(cold, 2)
        keys.generate(1)
        self.sync_blocks()
        assert_equal(watcher.getwatchonlybalance(), Decimal(7))

        self.log("and so is a spend from the address: the watched coin goes")
        raw_in = [{"txid": paid, "vout": unspent[0]["vout"]}]
        spend = keys.signrawtransaction(keys.createrawtransaction(raw_in, {keys.getnewaddress(): Decimal(4)}))["hex"]
        keys.sendrawtransaction(spend)
        keys.generate(1)
        self.sync_blocks()
        assert_equal(watcher.getwatchonlybalance(), Decimal(2))
        assert_equal(len(watcher.listwatchonlyunspent()), 1)

        self.log("the import survives a restart")
        watcher.stop()
        watcher.start()
        assert_equal(watcher.validateaddress(cold)["iswatchonly"], True)
        assert_equal(watcher.getwatchonlybalance(), Decimal(2))

        self.log("a public key is imported as both of its forms")
        addr2 = keys.getnewaddress()
        pub = keys.validateaddress(addr2)["pubkey"]
        keys.sendtoaddress(addr2, 3)
        keys.generate(1)
        self.sync_blocks()
        watcher.importpubkey(pub)
        assert_equal(watcher.getwatchonlybalance(), Decimal(5))

        self.log("an address the wallet holds the key for is refused; so is nonsense")
        assert_raises_rpc_error(-4, None, keys.importaddress, cold)
        assert_raises_rpc_error(-5, None, watcher.importaddress, "not an address")


if __name__ == "__main__":
    WatchOnlyTest().main()
