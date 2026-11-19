#!/usr/bin/env python3
"""fundrawtransaction and the offline signing flow.

A wallet that only follows an address (watch-only, no keys) builds a payment from a raw transaction that has outputs and no
inputs; the machine that holds the keys signs it; the watcher broadcasts it. Also the ordinary use, on a wallet that has
the coins itself.
"""
from decimal import Decimal

from test_framework import CorgiTestFramework, assert_equal, assert_raises_rpc_error, wait_until


class FundRawTest(CorgiTestFramework):
    num_nodes = 2

    def run_test(self):
        signer, watcher = self.nodes
        signer.generate(101)
        self.connect_nodes(1, 0)
        self.sync_blocks()

        self.log("an ordinary funding: inputs and change are added, it is not signed, and signing then sending works")
        dest = signer.getnewaddress()
        raw = signer.createrawtransaction([], {dest: Decimal(3)})
        funded = signer.fundrawtransaction(raw)
        assert funded["fee"] > 0
        decoded = signer.decoderawtransaction(funded["hex"])
        assert len(decoded["vin"]) >= 1
        assert all(not vin.get("scriptSig", {}).get("hex") for vin in decoded["vin"]), "the inputs should be unsigned"
        assert_equal(decoded["vout"][0]["value"], Decimal(3))
        assert funded["changepos"] in (-1, 1), funded
        signed = signer.signrawtransaction(funded["hex"])
        assert_equal(signed["complete"], True)
        txid = signer.sendrawtransaction(signed["hex"])
        assert txid in signer.getrawmempool()
        signer.generate(1)
        self.sync_blocks()

        self.log("an output under 1 coin costs one more rate in fee (the dust rule the wallet's own sends follow)")
        small = signer.fundrawtransaction(signer.createrawtransaction([], {dest: Decimal("0.5")}))
        big = signer.fundrawtransaction(signer.createrawtransaction([], {dest: Decimal(3)}))
        assert_equal(small["fee"] - big["fee"], Decimal(1))

        self.log("a watch-only wallet funds a payment from the address it follows; the keys elsewhere sign it")
        cold = signer.getnewaddress()
        # put 40 coins at the cold address, from a coin chosen for the purpose
        signer.sendtoaddress(cold, 40)
        signer.generate(1)
        self.sync_blocks()
        watcher.importaddress(cold)
        assert_equal(watcher.getwatchonlybalance(), Decimal(40))

        payee = signer.getnewaddress()
        change = signer.getnewaddress()
        raw = watcher.createrawtransaction([], {payee: Decimal(10)})
        funded = watcher.fundrawtransaction(raw, {"includeWatching": True, "changeAddress": change})
        assert_equal(funded["changepos"], 1)
        decoded = watcher.decoderawtransaction(funded["hex"])
        assert_equal(len(decoded["vin"]), 1)
        assert_equal(decoded["vout"][0]["value"], Decimal(10))
        assert_equal(decoded["vout"][1]["value"], Decimal(40) - Decimal(10) - funded["fee"])

        # the watcher cannot sign it (it has no key); the signer can
        assert_equal(watcher.signrawtransaction(funded["hex"])["complete"], False)
        signed = signer.signrawtransaction(funded["hex"])
        assert_equal(signed["complete"], True)
        txid = watcher.sendrawtransaction(signed["hex"])
        wait_until(lambda: txid in signer.getrawmempool(), timeout=30, what="the payment to reach the signer's pool")
        signer.generate(1)
        self.sync_blocks()
        assert_equal(watcher.getwatchonlybalance(), 0)      # the cold coin is spent; the change went to another address
        assert_equal(signer.gettransaction(txid)["confirmations"], 1)

        self.log("what it refuses: nothing to pay for, inputs already there, too much, a watch-only fund without a change address")
        assert_raises_rpc_error(-8, "no outputs", watcher.fundrawtransaction, "01000000000000000000")
        assert_raises_rpc_error(-4, "Insufficient", signer.fundrawtransaction, signer.createrawtransaction([], {payee: Decimal(99999999)}))
        assert_raises_rpc_error(-8, "changeAddress", watcher.fundrawtransaction,
                                watcher.createrawtransaction([], {payee: Decimal(1)}), {"includeWatching": True})
        assert_raises_rpc_error(-22, "decode", watcher.fundrawtransaction, "zz")
        assert_raises_rpc_error(-8, "already has inputs", signer.fundrawtransaction, signed["hex"])

        self.log("a fee over -maxtxfee is refused, as the wallet's own sends refuse it")
        signer.stop()
        signer.start(["-maxtxfee=0.5"])
        assert_raises_rpc_error(-8, "maxtxfee", signer.fundrawtransaction, signer.createrawtransaction([], {payee: Decimal(3)}))


if __name__ == "__main__":
    FundRawTest().main()
