"""Tests for process_burn: routes a Burn to the right partner's dispatcher,
records the outcome in State, and intentionally leaves no record on dispatch
failure so the next tick retries."""
from decimal import Decimal
from unittest.mock import Mock

from solders.keypair import Keypair
from solders.pubkey import Pubkey

import bridge


def _make_partner(tag="CORG", reward_ratio="1.0"):
    return bridge.Partner(
        tag=tag,
        token_mint=Pubkey.from_string("8xudSD6kdeFu1nu5sEiy9zBm2iYhKnnsZfyfF6HGyPq4"),
        decimals=6,
        reward_ratio=Decimal(reward_ratio),
        treasury=Keypair(),
    )


def _make_burn(partner_tag="CORG", amount="1.0"):
    return bridge.Burn(
        txid="86f3c2186d65928888ad367631a020f05d83bb32e64ba8edd9510731c17e3990",
        height=18391,
        partner=partner_tag,
        sol_dest=Pubkey.from_string("DE8VHxymDpMupVuz8vaWhj8k9uGowXbj4kKQ7dxqc1XP"),
        amount_corg=Decimal(amount),
    )


def test_known_partner_dispatches_and_records(tmp_path):
    partner = _make_partner()
    burn = _make_burn()
    dispatcher = Mock()
    dispatcher.send_reward.return_value = "fake-sol-sig"
    state = bridge.State(tmp_path / "state.json")

    bridge.process_burn(burn, {"CORG": partner}, dispatcher, state)

    dispatcher.send_reward.assert_called_once()
    args = dispatcher.send_reward.call_args.args
    assert args[0] is partner
    assert args[1] == burn.sol_dest
    assert args[2] == Decimal("1.0")  # 1.0 CORG * 1.0 ratio

    entry = state.processed[burn.txid]
    assert entry["status"] == "dispatched"
    assert entry["partner"] == "CORG"
    assert entry["sol_sig"] == "fake-sol-sig"


def test_unknown_partner_is_recorded_as_skipped(tmp_path):
    burn = _make_burn(partner_tag="WHAT")
    dispatcher = Mock()
    state = bridge.State(tmp_path / "state.json")

    bridge.process_burn(burn, {}, dispatcher, state)

    dispatcher.send_reward.assert_not_called()
    entry = state.processed[burn.txid]
    assert entry["status"] == "skipped_unknown_partner"
    assert entry["partner"] == "WHAT"


def test_dispatch_failure_leaves_no_record(tmp_path):
    """If Solana dispatch throws (network error, treasury underfunded, etc.),
    process_burn must NOT record the txid — the next tick will retry."""
    partner = _make_partner()
    burn = _make_burn()
    dispatcher = Mock()
    dispatcher.send_reward.side_effect = RuntimeError("treasury empty")
    state = bridge.State(tmp_path / "state.json")

    bridge.process_burn(burn, {"CORG": partner}, dispatcher, state)

    assert burn.txid not in state.processed


def test_reward_ratio_scales_payout(tmp_path):
    partner = _make_partner(reward_ratio="2.5")
    burn = _make_burn(amount="4.0")
    dispatcher = Mock()
    dispatcher.send_reward.return_value = "sig"
    state = bridge.State(tmp_path / "state.json")

    bridge.process_burn(burn, {"CORG": partner}, dispatcher, state)

    assert dispatcher.send_reward.call_args.args[2] == Decimal("10.0")
