#!/usr/bin/env python3
"""Two-node wallet flow: a payment relays, confirms, and credits the receiver."""
from decimal import Decimal

from test_framework import CorgiTestFramework, assert_equal, assert_raises_rpc_error


class WalletSendTest(CorgiTestFramework):
    """node0 mines and pays node1; both agree on chain and balances."""
    num_nodes = 2

    def run_test(self):
        n0, n1 = self.nodes
        self.connect_nodes(0, 1)

        self.log("mine to maturity on node0; node1 follows")
        n0.generate(51)
        self.sync_blocks()
        assert_equal(n1.getbalance(), 0)

        self.log("payment relays through the mempool")
        addr1 = n1.getnewaddress()
        txid = n0.sendtoaddress(addr1, 12345)
        self.sync_mempools()
        assert txid in n1.getrawmempool()
        assert_equal(n1.getbalance(), 0)  # default minconf=1

        self.log("payment confirms on both nodes")
        n0.generate(1)
        self.sync_blocks()
        assert_equal(n1.getbalance(), Decimal(12345))
        assert_equal(n1.gettransaction(txid)["confirmations"], 1)

        self.log("receiver can spend it back")
        back = n1.sendtoaddress(n0.getnewaddress(), 12000)
        self.sync_mempools()
        n0.generate(1)
        self.sync_blocks()
        assert_equal(n0.gettransaction(back)["confirmations"], 1)
        assert n1.getbalance() < Decimal(345)

        self.log("overspend is rejected")
        assert_raises_rpc_error(-4, "Insufficient funds", n1.sendtoaddress, n0.getnewaddress(), 1000)


if __name__ == "__main__":
    WalletSendTest().main()
