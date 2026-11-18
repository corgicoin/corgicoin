#!/usr/bin/env python3
"""feefilter (BIP 133, protocol 70013).

The node tells a peer that speaks 70013 the fee rate it wants announced, and says nothing to an older peer. A peer that sends
a feefilter is then not told of transactions that pay less per kB than it asked for, but is told of those that pay at least that.
"""
import time
from decimal import Decimal

from mininode import P2PConnection
from test_framework import CorgiTestFramework, assert_equal, wait_until


class FeeFilterTest(CorgiTestFramework):
    num_nodes = 1
    extra_args = [["-feefilter=100000000"]]

    def spend(self, node, coin, fee):
        raw = node.createrawtransaction([{"txid": coin["txid"], "vout": coin["vout"]}], {node.getnewaddress(): coin["amount"] - Decimal(fee)})
        signed = node.signrawtransaction(raw)
        assert signed["complete"]
        return signed["hex"]

    def run_test(self):
        node = self.nodes[0]
        node.generate(110)
        coins = [c for c in node.listunspent() if c["amount"] > 100]

        self.log("a peer at 70013 is sent what -feefilter says; an older peer is sent nothing")
        new = P2PConnection(node.p2p_port)
        old = P2PConnection(node.p2p_port, protocol_version=70001)
        wait_until(lambda: new.got_verack and old.got_verack)
        wait_until(lambda: new.feefilter is not None)
        assert_equal(new.feefilter, 100000000)
        assert_equal(old.counts.get("feefilter", 0), 0)

        self.log("the peer asks for 10 coins per kB: a transaction paying about 5 is not announced to it, one paying far more is")
        new.send("feefilter", (10 ** 9).to_bytes(8, "little", signed=True))
        time.sleep(1)                                                            # let the node read it before anything is announced
        cheap = node.sendrawtransaction(self.spend(node, coins[0], 1))
        rich = node.sendrawtransaction(self.spend(node, coins[1], 50))
        wait_until(lambda: rich in new.inv_txids and cheap in old.inv_txids and rich in old.inv_txids, what="announcements")
        assert cheap not in new.inv_txids, "the cheap transaction was announced to a peer that filtered it out"


if __name__ == "__main__":
    FeeFilterTest().main()
