#!/usr/bin/env python3
"""fundrawtransaction from pay-to-script-hash coins: the fee is for the size the inputs will really have once signed.

A 2-of-3 multisig input signs to about 300 bytes against about 150 for a plain one, so a fee sized as if every input were plain falls short and
the pool refuses the transaction. Here the only coins the wallet may use are 2-of-3 outputs: the funded transaction is signed with the wallet's
keys and must be accepted by the pool, and its fee must be at least the relay minimum for the size it signs to. Also -maxtxfee is still honoured
for such inputs.
"""
from decimal import Decimal

from test_framework import CorgiTestFramework, assert_equal, assert_raises_rpc_error


class FundRawMultisigTest(CorgiTestFramework):
    num_nodes = 1

    def run_test(self):
        node = self.nodes[0]
        node.generate(101)
        keys = [node.validateaddress(node.getnewaddress())["pubkey"] for _ in range(3)]
        ms = node.addmultisigaddress(2, keys)
        first = node.sendtoaddress(ms, 10)
        node.sendtoaddress(ms, 10)
        node.generate(1)
        # the multisig output's script: the output of the first payment that is exactly 10 (the wallet's change is not)
        ms_spk = [o["scriptPubKey"]["hex"] for o in node.decoderawtransaction(node.getrawtransaction(first))["vout"] if o["value"] == 10][0]
        locked = []

        def multisig_coins():
            return [u for u in node.listunspent() if u["scriptPubKey"] == ms_spk]

        def only_multisig_coins():
            """Everything but the multisig coins is locked, so that only they can be chosen (what is new since the last call included)."""
            if locked:
                node.lockunspent(True, list(locked))
            locked[:] = [{"txid": u["txid"], "vout": u["vout"]} for u in node.listunspent() if u["scriptPubKey"] != ms_spk]
            node.lockunspent(False, list(locked))

        def release():
            if locked:
                node.lockunspent(True, list(locked))
                del locked[:]

        def top_up(n):
            """n more 10-coin multisig outputs, paid by coins that are not the multisig ones (the existing multisig coins are kept out of it)."""
            release()
            mine = [{"txid": u["txid"], "vout": u["vout"]} for u in multisig_coins()]
            if mine:
                node.lockunspent(False, mine)
            for _ in range(n):
                node.sendtoaddress(ms, 10)
            node.generate(1)
            if mine:
                node.lockunspent(True, mine)

        def fund_sign_send(amount, label):
            only_multisig_coins()
            raw = node.createrawtransaction([], {node.getnewaddress(): amount})
            funded = node.fundrawtransaction(raw)
            signed = node.signrawtransaction(funded["hex"])
            assert_equal(signed["complete"], True)
            size = len(signed["hex"]) // 2
            vin = node.decoderawtransaction(signed["hex"])["vin"]
            per_input = [len(v["scriptSig"]["hex"]) // 2 for v in vin]
            self.log("%s: %d inputs of %s bytes of script, %d bytes in all, fee %s" % (label, len(vin), per_input, size, funded["fee"]))
            assert all(n > 200 for n in per_input), "a 2-of-3 input should sign to over 200 bytes: %s (a coin that is not multisig was used)" % per_input
            txid = node.sendrawtransaction(signed["hex"])       # the pool refuses a fee that is too low for the signed size
            fee_rate = Decimal(str(funded["fee"])) / Decimal(size) * 1000
            assert fee_rate >= Decimal("0.0001"), "the fee is %s per kB" % fee_rate
            return funded, txid, len(vin)

        assert_equal(len(multisig_coins()), 2)

        self.log("one multisig input")
        funded, txid, n_in = fund_sign_send(Decimal(3), "3 coins")
        assert_equal(n_in, 1)
        assert txid in node.getrawmempool()
        node.generate(1)

        self.log("more multisig inputs than one: all of what the wallet may use but 3 coins")
        top_up(2)
        coins = multisig_coins()
        assert len(coins) >= 3, coins
        total = sum(Decimal(str(u["amount"])) for u in coins)
        funded, txid, n_in = fund_sign_send(total - Decimal(3), "all but 3 coins")
        assert_equal(n_in, len(coins))
        node.generate(1)

        self.log("a payment that leaves only a small change (9.5 from 10-coin inputs): inputs are taken as the fee needs, and the signed transaction is accepted")
        top_up(2)
        funded, txid, n_in = fund_sign_send(Decimal("9.5"), "9.5 coins")
        assert n_in >= 1
        node.generate(1)

        self.log("-maxtxfee is honoured for such inputs")
        top_up(2)
        node.stop()
        node.start(["-maxtxfee=0.1"])
        del locked[:]                       # (locks do not survive a restart)
        only_multisig_coins()
        assert_raises_rpc_error(None, "fee", node.fundrawtransaction, node.createrawtransaction([], {node.getnewaddress(): Decimal("2")}))


if __name__ == "__main__":
    FundRawMultisigTest().main()
