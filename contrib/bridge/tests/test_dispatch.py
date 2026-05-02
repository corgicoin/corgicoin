"""Tests for process_burn: routes a Burn to the right partner's dispatcher
and records the outcome in State.

The dispatch flow is at-most-once: a 'pending' marker is written before the
Solana RPC call, so a crash between submission and result-recording is
recoverable (manually) without double-sending."""
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


def test_dispatch_failure_records_dispatch_error(tmp_path):
    """When dispatch raises, process_burn must record 'dispatch_error' so the
    next tick treats the txid as already_processed and refuses to re-dispatch.
    Operator must reconcile manually (the alternative — auto-retry — could
    double-send if the original RPC actually landed on Solana before the
    client error)."""
    partner = _make_partner()
    burn = _make_burn()
    dispatcher = Mock()
    dispatcher.send_reward.side_effect = RuntimeError("treasury empty")
    state = bridge.State(tmp_path / "state.json")

    bridge.process_burn(burn, {"CORG": partner}, dispatcher, state)

    entry = state.processed[burn.txid]
    assert entry["status"] == "dispatch_error"
    assert "treasury empty" in entry["error"]
    assert entry["partner"] == "CORG"
    # already_processed must return True so reprocess on restart is blocked
    assert state.already_processed(burn.txid)


def test_pending_recorded_before_dispatch(tmp_path):
    """The 'pending' marker must hit disk BEFORE send_reward is called —
    otherwise a crash mid-RPC could leave no marker and re-dispatch on restart."""
    partner = _make_partner()
    burn = _make_burn()
    state = bridge.State(tmp_path / "state.json")
    captured = {}

    def capture_state_at_dispatch(*_args, **_kwargs):
        # Re-read state.json from disk to verify the pending record was saved,
        # not just held in memory.
        reloaded = bridge.State(tmp_path / "state.json")
        captured["status"] = reloaded.processed.get(burn.txid, {}).get("status")
        return "fake-sig"

    dispatcher = Mock()
    dispatcher.send_reward.side_effect = capture_state_at_dispatch

    bridge.process_burn(burn, {"CORG": partner}, dispatcher, state)

    assert captured["status"] == "pending"
    assert state.processed[burn.txid]["status"] == "dispatched"


def test_reward_ratio_scales_payout(tmp_path):
    partner = _make_partner(reward_ratio="2.5")
    burn = _make_burn(amount="4.0")
    dispatcher = Mock()
    dispatcher.send_reward.return_value = "sig"
    state = bridge.State(tmp_path / "state.json")

    bridge.process_burn(burn, {"CORG": partner}, dispatcher, state)

    assert dispatcher.send_reward.call_args.args[2] == Decimal("10.0")
