#!/usr/bin/env python3
"""Free transactions that fail the input and signature checks do not use up the free-relay allowance.

The limiter (-limitfreerelay) counted a free transaction before its signatures were checked, so a peer sending free
transactions with bad signatures (nothing to pay, cheap to make) used up the allowance, and a good free transaction was then
refused as rate-limited. It counts a transaction once it has passed. (The coins belong to node 1, not to the node under test:
the limiter does not apply to a transaction that is from the node's own wallet.)
"""
from mininode import P2PConnection
from test_framework import CorgiTestFramework, assert_equal, wait_until


class FreeRelayLimitTest(CorgiTestFramework):
    num_nodes = 2
    extra_args = [["-limitfreerelay=1"], []]        # node 0: 1 kB per minute, about 10 kB in the window

    def log_text(self):
        with open(self.nodes[0].debug_log, errors="replace") as f:
            return f.read()

    def run_test(self):
        node, owner = self.nodes
        owner.generate(60)
        self.connect_nodes(0, 1)
        self.sync_blocks()
        self.disconnect_nodes(0, 1)
        coins = owner.listunspent()
        assert len(coins) >= 2

        def free_tx(coin):
            raw = owner.createrawtransaction([{"txid": coin["txid"], "vout": coin["vout"]}], {owner.getnewaddress(): coin["amount"]})
            return owner.signrawtransaction(raw)["hex"]

        bad_source = bytes.fromhex(free_tx(coins[0]))
        good = bytes.fromhex(free_tx(coins[1]))
        # the signature is in the scriptSig, after the input's 36-byte outpoint and a length byte: damage one byte of it, a different one each time
        start = 4 + 1 + 36 + 1 + 8

        peer = P2PConnection(node.p2p_port)
        wait_until(lambda: peer.got_verack, what="verack")
        self.log("free transactions with a bad signature, well past the allowance (about 10 kB)")
        for i in range(100):                         # about 190 bytes each
            t = bytearray(bad_source)
            t[start + (i % 40)] ^= (1 + i // 40)
            peer.send("tx", bytes(t))
        peer.send("ping", b"\x00" * 8)
        wait_until(lambda: peer.counts.get("pong", 0) >= 1, what="the bad transactions to be processed")
        assert self.log_text().count("VerifySignature failed") >= 90, "the bad transactions did not reach the signature check"
        assert "rate limiter" not in self.log_text(), "the bad transactions were counted: the limiter filled"
        assert_equal(node.getrawmempool(), [])

        self.log("a good free transaction is still accepted")
        peer.send("tx", good)
        wait_until(lambda: len(node.getrawmempool()) == 1, what="the good free transaction to be accepted")


if __name__ == "__main__":
    FreeRelayLimitTest().main()
