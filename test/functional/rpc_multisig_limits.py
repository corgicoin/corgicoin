#!/usr/bin/env python3
"""addmultisigaddress refuses scripts that cannot be built or could never be spent.

OP_CHECKMULTISIG counts keys with OP_1..OP_16, so a 17th key tripped an assert in EncodeOP_N (or, with asserts
compiled out, produced a script with a garbage key count). And the spender has to push the redeem script in its
scriptSig, where EvalScript rejects any push over 520 bytes: 16 compressed keys make a 547-byte script, so coins
sent to that address were lost for good. The RPC now rejects both.
"""
from test_framework import CorgiTestFramework, assert_equal, assert_raises_rpc_error

# secp256k1 generator point, uncompressed (65 bytes): 66 bytes per key inside a multisig script
G_UNCOMPRESSED = ("0479be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798"
                  "483ada7726a3c4655da4fbfc0e1108a8fd17b448a68554199c47d08ffb10d4b8")


class MultisigLimitsTest(CorgiTestFramework):
    num_nodes = 1

    def run_test(self):
        node = self.nodes[0]
        node.generate(51)
        pubkeys = [node.validateaddress(node.getnewaddress())["pubkey"] for _ in range(17)]

        self.log("15 compressed keys is the largest that fits (513-byte script) and the coins are spendable")
        p2sh = node.addmultisigaddress(1, pubkeys[:15])
        assert node.validateaddress(p2sh)["isvalid"]
        txid = node.sendtoaddress(p2sh, 1000)
        node.generate(1)
        funding = node.getrawtransaction(txid, 1)
        vout = [o["n"] for o in funding["vout"] if o["scriptPubKey"].get("addresses") == [p2sh]]
        assert_equal(len(vout), 1)
        raw = node.createrawtransaction([{"txid": txid, "vout": vout[0]}], {node.getnewaddress(): 990})
        signed = node.signrawtransaction(raw)
        assert_equal(signed["complete"], True)
        spend = node.sendrawtransaction(signed["hex"])
        node.generate(1)
        assert_equal(node.gettransaction(spend)["confirmations"], 1)

        self.log("16 compressed keys: a 547-byte script nobody could ever spend")
        assert_raises_rpc_error(-1, "redeemScript exceeds size limit", node.addmultisigaddress, 1, pubkeys[:16])

        self.log("17 keys: more than OP_16 can count")
        assert_raises_rpc_error(-1, "at most 16 keys", node.addmultisigaddress, 1, pubkeys[:17])
        assert_raises_rpc_error(-1, "at most 16 keys", node.addmultisigaddress, 17, pubkeys[:17])
        assert_equal(node.getblockcount(), 53)  # the node answered every call above and is still running

        self.log("uncompressed keys are 66 bytes each: 7 fit, 8 do not")
        node.addmultisigaddress(2, [G_UNCOMPRESSED] * 7)
        assert_raises_rpc_error(-1, "redeemScript exceeds size limit", node.addmultisigaddress, 2, [G_UNCOMPRESSED] * 8)

        self.log("the existing checks still hold")
        assert_raises_rpc_error(-1, "at least one key", node.addmultisigaddress, 0, pubkeys[:3])
        assert_raises_rpc_error(-1, "not enough keys", node.addmultisigaddress, 4, pubkeys[:3])


if __name__ == "__main__":
    MultisigLimitsTest().main()
