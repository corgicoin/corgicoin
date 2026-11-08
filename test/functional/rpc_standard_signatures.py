#!/usr/bin/env python3
"""Signature relay policy: the wallet signs with a low S, the pool refuses a high-S twin, a block may still carry one."""
from decimal import Decimal

from test_framework import CorgiTestFramework, assert_equal, assert_raises_rpc_error

ORDER = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141


def split_signature(script_sig_hex):
    """(signature with hash type, rest of scriptSig) for a scriptSig that starts with one signature push."""
    raw = bytes.fromhex(script_sig_hex)
    length = raw[0]
    assert 0x40 <= length <= 0x49
    return raw[1:1 + length], raw[1 + length:]


def parse_rs(sig):
    """(r bytes, s as int) of a DER signature followed by a hash type byte."""
    assert sig[0] == 0x30 and sig[2] == 0x02
    len_r = sig[3]
    r = sig[4:4 + len_r]
    assert sig[4 + len_r] == 0x02
    len_s = sig[5 + len_r]
    s = int.from_bytes(sig[6 + len_r:6 + len_r + len_s], "big")
    return r, s


def encode_signature(r, s, hash_type):
    s_bytes = s.to_bytes((s.bit_length() + 7) // 8, "big")
    if s_bytes[0] & 0x80:
        s_bytes = b"\x00" + s_bytes
    body = b"\x02" + bytes([len(r)]) + r + b"\x02" + bytes([len(s_bytes)]) + s_bytes
    return b"\x30" + bytes([len(body)]) + body + bytes([hash_type])


def flip_s(tx_hex, node):
    """The same transaction with the first input's signature S replaced by n - S: still valid, different txid."""
    old_script = node.decoderawtransaction(tx_hex)["vin"][0]["scriptSig"]["hex"]
    sig, rest = split_signature(old_script)
    r, s = parse_rs(sig)
    new_sig = encode_signature(r, ORDER - s, sig[-1])
    new_script = bytes([len(new_sig)]) + new_sig + rest
    old_field = "%02x%s" % (len(old_script) // 2, old_script)
    new_field = "%02x%s" % (len(new_script), new_script.hex())
    assert tx_hex.count(old_field) == 1
    return tx_hex.replace(old_field, new_field)


class StandardSignaturesTest(CorgiTestFramework):
    num_nodes = 2
    extra_args = [["-standardsigs=0"], ["-standardsigs=1"]]     # node 0 relays anything valid; node 1 enforces the policy

    def spend_raw(self, node, utxo, fee=Decimal(1)):
        raw = node.createrawtransaction([{"txid": utxo["txid"], "vout": utxo["vout"]}],
                                        {node.getnewaddress(): utxo["amount"] - fee})
        signed = node.signrawtransaction(raw)
        assert signed["complete"]
        return signed["hex"]

    def run_test(self):
        permissive, strict = self.nodes
        self.connect_nodes(1, 0)
        strict.generate(80)     # plenty of mature coinbases: each send below spends a different one
        self.sync_blocks()
        utxos = strict.listunspent()

        self.log("every signature the wallet makes is low-S (this fails about half the time if S is left to chance)")
        for _ in range(24):
            txid = strict.sendtoaddress(strict.getnewaddress(), 1)
            script = strict.getrawtransaction(txid, 1)["vin"][0]["scriptSig"]["hex"]
            sig, _rest = split_signature(script)
            assert parse_rs(sig)[1] <= ORDER // 2, "high S in a wallet signature"
        strict.generate(1)
        self.sync_blocks()
        utxos = [u for u in strict.listunspent() if u["confirmations"] > 0 and u["amount"] > 10][:4]

        self.log("a high-S twin of a valid transaction is refused by a -standardsigs=1 pool")
        good = self.spend_raw(strict, utxos[0])
        twin = flip_s(good, strict)
        good_id = strict.decoderawtransaction(good)["txid"]
        twin_id = strict.decoderawtransaction(twin)["txid"]
        assert good_id != twin_id
        assert_raises_rpc_error(-22, None, strict.sendrawtransaction, twin)
        assert_equal(strict.getrawmempool(), [])
        assert_equal(strict.sendrawtransaction(good), good_id)       # the original is fine
        strict.generate(1)
        self.sync_blocks()

        self.log("-standardsigs=0 admits the twin, and a block carrying it is valid for everyone")
        twin2 = flip_s(self.spend_raw(strict, utxos[1]), strict)
        twin2_id = strict.decoderawtransaction(twin2)["txid"]
        assert_raises_rpc_error(-22, None, strict.sendrawtransaction, twin2)
        assert_equal(permissive.sendrawtransaction(twin2), twin2_id)
        assert_equal(strict.getrawmempool(), [])                     # not relayed on to the strict node
        permissive.generate(1)
        self.sync_blocks()
        assert_equal(strict.getrawtransaction(twin2_id, 1)["confirmations"], 1)

        self.log("restarting the strict node with the policy off lets it take the twin as well")
        twin3 = flip_s(self.spend_raw(strict, utxos[2]), strict)
        strict.stop()
        strict.start(["-standardsigs=0"])
        assert_equal(strict.sendrawtransaction(twin3), strict.decoderawtransaction(twin3)["txid"])


if __name__ == "__main__":
    StandardSignaturesTest().main()
