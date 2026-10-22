#!/usr/bin/env python3
"""Coin control: lockunspent / listlockunspent keep outputs out of coin selection."""
from test_framework import CorgiTestFramework, assert_equal, assert_raises_rpc_error


def outpoint(u):
    return {"txid": u["txid"], "vout": u["vout"]}


class LockUnspentTest(CorgiTestFramework):
    num_nodes = 1

    def run_test(self):
        node = self.nodes[0]
        node.generate(52)  # three coinbases past the 50-confirmation wallet maturity
        utxos = node.listunspent()
        assert_equal(len(utxos), 3)
        assert_equal(node.listlockunspent(), [])

        self.log("locked outputs leave listunspent and show in listlockunspent")
        assert_equal(node.lockunspent(False, [outpoint(utxos[0])]), True)
        assert_equal(node.listlockunspent(), [outpoint(utxos[0])])
        assert outpoint(utxos[0]) not in [outpoint(u) for u in node.listunspent()]

        self.log("bad lock/unlock requests are rejected without partial changes")
        assert_raises_rpc_error(-8, "already locked", node.lockunspent, False, [outpoint(utxos[0])])
        assert_raises_rpc_error(-8, "expected locked", node.lockunspent, True, [outpoint(utxos[1])])
        assert_raises_rpc_error(-8, "unknown transaction", node.lockunspent, False,
                                [{"txid": "00" * 32, "vout": 0}])
        assert_raises_rpc_error(-8, "out of bounds", node.lockunspent, False,
                                [{"txid": utxos[1]["txid"], "vout": 99}])
        assert_raises_rpc_error(-8, "already locked", node.lockunspent, False,
                                [outpoint(utxos[1]), outpoint(utxos[0])])
        assert_equal(node.listlockunspent(), [outpoint(utxos[0])])

        self.log("coin selection can't spend locked coins")
        node.lockunspent(False, [outpoint(utxos[1]), outpoint(utxos[2])])
        assert_equal(node.listunspent(), [])
        dest = node.getnewaddress()
        assert_raises_rpc_error(-4, None, node.sendtoaddress, dest, 1)

        self.log("an unlocked coin funds the next send")
        node.lockunspent(True, [outpoint(utxos[1])])
        txid = node.sendtoaddress(dest, 1)
        spent = [(i["txid"], i["vout"]) for i in node.getrawtransaction(txid, 1)["vin"]]
        assert_equal(spent, [(utxos[1]["txid"], utxos[1]["vout"])])

        self.log("unlock with no list releases everything")
        assert_equal(node.lockunspent(True), True)
        assert_equal(node.listlockunspent(), [])

        self.log("locks are memory-only and cleared on restart")
        node.lockunspent(False, [outpoint(utxos[0])])
        node.stop()
        node.start()
        assert_equal(node.listlockunspent(), [])


if __name__ == "__main__":
    LockUnspentTest().main()
