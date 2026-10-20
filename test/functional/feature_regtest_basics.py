#!/usr/bin/env python3
"""Regtest chain basics: genesis, generate, coinbase maturity, restart, burns."""
from decimal import Decimal

from test_framework import (CorgiTestFramework, assert_equal, assert_greater_than,
                            assert_raises_rpc_error)

REGTEST_GENESIS = "0807d4f55142e96daa02bf6a1a7e438a4007409b7ae8df8c6e17f794501f819e"
WALLET_MATURITY = 50  # COINBASE_MATURITY (30) + the wallet's 20-block buffer
SOLANA_SYSTEM_PROGRAM = "11111111111111111111111111111111"  # 32 zero bytes, base58


class RegtestBasicsTest(CorgiTestFramework):
    """Single regtest node: chain params, mining, maturity, spends, burns."""
    num_nodes = 1

    def run_test(self):
        node = self.nodes[0]

        self.log("chain identity")
        info = node.getblockchaininfo()
        assert_equal(info["chain"], "regtest")
        assert_equal(info["blocks"], 0)
        assert_equal(node.getblockhash(0), REGTEST_GENESIS)

        self.log("generate argument checks")
        assert_raises_rpc_error(-8, None, node.generate, -1)
        assert_raises_rpc_error(-5, None, node.generate, 1, "notanaddress")
        assert_equal(node.generate(0), [])

        self.log("coinbase matures after %d confirmations in the wallet" % WALLET_MATURITY)
        hashes = node.generate(WALLET_MATURITY - 1)
        assert_equal(len(hashes), WALLET_MATURITY - 1)
        assert_equal(len(set(hashes)), len(hashes))
        assert_equal(node.getbestblockhash(), hashes[-1])
        assert_equal(node.getbalance(), 0)
        node.generate(1)
        first_reward = node.getbalance()
        assert_greater_than(first_reward, 0)

        self.log("generate pays an explicit address")
        addr = node.getnewaddress()
        [h] = node.generate(1, addr)
        block = node.getblock(h)
        coinbase = node.getrawtransaction(block["tx"][0], 1)
        assert_equal(coinbase["vout"][0]["scriptPubKey"]["addresses"], [addr])

        self.log("wallet spend confirms in the next block")
        dest = node.getnewaddress()
        txid = node.sendtoaddress(dest, 1000)
        assert txid in node.getrawmempool()
        node.generate(1)
        assert_equal(node.getrawmempool(), [])
        assert_equal(node.gettransaction(txid)["confirmations"], 1)
        assert_equal(node.getreceivedbyaddress(dest), Decimal(1000))

        self.log("partner burn round-trips through decodeburn")
        burn = node.burnforpartner(250, "CORG", SOLANA_SYSTEM_PROGRAM)
        assert_equal(burn["status"], "burned")
        assert_equal(burn["partner"], "CORG")
        burn_txid = burn["txid"]
        node.generate(1)
        burn_tx = node.getrawtransaction(burn_txid, 1)
        burn_outs = [o for o in burn_tx["vout"] if o["scriptPubKey"]["hex"].startswith("6a")]
        assert_equal(len(burn_outs), 1)
        assert_equal(burn_outs[0]["value"], Decimal(250))
        decoded = node.decodeburn(burn_outs[0]["scriptPubKey"]["hex"])
        assert_equal(decoded["magic"], "SOL")
        assert_equal(decoded["partner"], "CORG")
        assert_equal(decoded["sol_dest_hex"], "00" * 32)
        assert_equal(decoded["sol_dest_base58"], SOLANA_SYSTEM_PROGRAM)
        assert_equal(burn_outs[0]["scriptPubKey"]["hex"][4:], burn["payload_hex"])

        self.log("chain survives a restart")
        height, tip = node.getblockcount(), node.getbestblockhash()
        node.stop()
        node.start()
        assert_equal(node.getblockcount(), height)
        assert_equal(node.getbestblockhash(), tip)
        assert_equal(node.getblockchaininfo()["chain"], "regtest")


if __name__ == "__main__":
    RegtestBasicsTest().main()
