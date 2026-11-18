"""Tests for tick: a burn is looked at once per output, and a reorganisation deeper than the wait is noticed."""
from decimal import Decimal
from unittest.mock import Mock

from solders.keypair import Keypair
from solders.pubkey import Pubkey

import bridge

DEST = "DE8VHxymDpMupVuz8vaWhj8k9uGowXbj4kKQ7dxqc1XP"


def _partner():
    return bridge.Partner(tag="CORG", token_mint=Pubkey.from_string("8xudSD6kdeFu1nu5sEiy9zBm2iYhKnnsZfyfF6HGyPq4"),
                          decimals=6, reward_ratio=Decimal("1.0"), treasury=Keypair())


class FakeChain:
    """Just enough of corgicoind for tick: blocks of transactions whose outputs are burns or not."""

    def __init__(self, blocks):
        self.blocks = blocks            # list of lists of transactions; a transaction is a list of "burn"/"plain" outputs
        self.calls = 0

    def call(self, method, *params):
        self.calls += 1
        if method == "getblockcount":
            return len(self.blocks)
        if method == "getblockhash":
            return "hash%d" % params[0]
        if method == "getblock":
            h = int(params[0][4:])
            return {"tx": ["tx%d_%d" % (h, i) for i in range(len(self.blocks[h - 1]))]}
        if method == "getrawtransaction":
            _, h, i = params[0].replace("tx", "").partition("_")[0], *params[0].replace("tx", "").split("_")
            outs = self.blocks[int(h) - 1][int(i)]
            return {"vout": [{"scriptPubKey": {"hex": o}, "value": Decimal("1.5")} for o in outs]}
        if method == "decodeburn":
            if params[0] == "burn":
                return {"magic": "SOL", "partner": "CORG", "sol_dest_base58": DEST, "sol_dest_hex": "00" * 32}
            raise bridge.RPCError("not a bridge burn", -3)
        raise AssertionError(method)


def test_every_burn_in_a_transaction_is_paid_once(tmp_path):
    chain = FakeChain([[["burn", "plain", "burn"]]] + [[] for _ in range(5)])
    dispatcher = Mock()
    dispatcher.send_reward.return_value = "sig"
    state = bridge.State(tmp_path / "state.json")

    bridge.tick(chain, {"CORG": _partner()}, dispatcher, state, confirmations=2)
    assert dispatcher.send_reward.call_count == 2
    assert sorted(state.processed) == ["tx1_0:0", "tx1_0:2"]

    # scanning the same blocks again pays nothing more
    state.last_height = 0
    bridge.tick(chain, {"CORG": _partner()}, dispatcher, state, confirmations=2)
    assert dispatcher.send_reward.call_count == 2


def test_a_reorganisation_past_the_wait_is_noticed_and_the_scan_goes_back(tmp_path):
    chain = FakeChain([[] for _ in range(60)])
    state = bridge.State(tmp_path / "state.json")
    dispatcher = Mock()
    bridge.tick(chain, {"CORG": _partner()}, dispatcher, state, confirmations=5)
    assert state.last_height == 55 and state.last_hash == "hash55"

    # the block the scan stopped at is replaced
    state.last_hash = "hash-of-a-block-that-was-replaced"
    bridge.tick(chain, {"CORG": _partner()}, dispatcher, state, confirmations=5)
    # it went back by 3 x max(confirmations, 10) = 30 and scanned forward again to the same safe tip
    assert state.last_height == 55
    assert state.last_hash == "hash55"
