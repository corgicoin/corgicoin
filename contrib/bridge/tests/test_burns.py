"""Tests for extract_burns: walks a tx's outputs, asks decodeburn about each,
skips outputs that aren't bridge burns."""
from decimal import Decimal
from unittest.mock import Mock

import bridge

# Real burn from the smoke test on 2026-05-01: 1 CORG to DE8VHxym...c1XP
SMOKE_TXID = "86f3c2186d65928888ad367631a020f05d83bb32e64ba8edd9510731c17e3990"
SMOKE_SOL_DEST_BASE58 = "DE8VHxymDpMupVuz8vaWhj8k9uGowXbj4kKQ7dxqc1XP"
SMOKE_PARTNER = "CORG"


def _decoded(partner=SMOKE_PARTNER, dest=SMOKE_SOL_DEST_BASE58):
    return {"magic": "SOL", "partner": partner, "sol_dest_base58": dest, "sol_dest_hex": "00" * 32}


def test_single_burn_output_yields_one_burn():
    rpc = Mock(spec=bridge.CorgiRPC)
    rpc.call.side_effect = [
        # getrawtransaction → tx with one OP_RETURN burn output
        {"vout": [{"scriptPubKey": {"hex": "6a27..."}, "value": 1.0}]},
        # decodeburn → success
        _decoded(),
    ]
    burns = bridge.extract_burns(rpc, SMOKE_TXID, height=18391)

    assert len(burns) == 1
    b = burns[0]
    assert b.txid == SMOKE_TXID
    assert b.height == 18391
    assert b.partner == SMOKE_PARTNER
    assert str(b.sol_dest) == SMOKE_SOL_DEST_BASE58
    assert b.amount_corg == Decimal("1.0")


def test_non_burn_output_is_skipped():
    rpc = Mock(spec=bridge.CorgiRPC)
    rpc.call.side_effect = [
        {"vout": [{"scriptPubKey": {"hex": "76a914..."}, "value": 5.0}]},
        bridge.RPCError("scriptPubKey is not a valid bridge burn payload", -3),
    ]
    assert bridge.extract_burns(rpc, "abc", height=1) == []


def test_mixed_outputs_returns_only_burn():
    """Real burn TXs have a change output (P2PKH, non-burn) plus the OP_RETURN burn."""
    rpc = Mock(spec=bridge.CorgiRPC)
    rpc.call.side_effect = [
        {"vout": [
            {"scriptPubKey": {"hex": "76a914..."}, "value": 1234.5},   # change
            {"scriptPubKey": {"hex": "6a27..."}, "value": 1.0},         # burn
        ]},
        bridge.RPCError("not a bridge burn", -3),  # change output
        _decoded(),                          # burn output
    ]
    burns = bridge.extract_burns(rpc, SMOKE_TXID, height=18391)
    assert len(burns) == 1
    assert burns[0].amount_corg == Decimal("1.0")


def test_other_rpc_errors_are_not_mistaken_for_a_non_burn():
    """A node that is loading or erroring says nothing about the output. Skipping it would lose a burn for good (the
    scan moves on), so the error ends the tick instead and the same blocks are scanned again."""
    import pytest
    rpc = Mock(spec=bridge.CorgiRPC)
    rpc.call.side_effect = [
        {"vout": [{"scriptPubKey": {"hex": "6a27..."}, "value": 1.0}]},
        bridge.RPCError("Loading block index...", -28),
    ]
    with pytest.raises(bridge.RPCError):
        bridge.extract_burns(rpc, SMOKE_TXID, height=18391)


def test_several_burns_in_one_transaction_have_separate_keys():
    rpc = Mock(spec=bridge.CorgiRPC)
    rpc.call.side_effect = [
        {"vout": [{"scriptPubKey": {"hex": "6a27a"}, "value": 1.0}, {"scriptPubKey": {"hex": "76a9"}, "value": 5.0},
                  {"scriptPubKey": {"hex": "6a27b"}, "value": 2.0}]},
        _decoded(),
        bridge.RPCError("not a bridge burn", -3),
        _decoded(),
    ]
    burns = bridge.extract_burns(rpc, SMOKE_TXID, height=1)
    assert [b.vout for b in burns] == [0, 2]
    assert len({b.key for b in burns}) == 2
