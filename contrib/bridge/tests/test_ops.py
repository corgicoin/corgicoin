"""Operations: an empty treasury is not paid from, a person is told when something needs one, a key others can read is refused."""
import json
import os
import stat
import sys
from decimal import Decimal
from unittest.mock import Mock

import pytest
from solders.keypair import Keypair

import bridge
from tests.test_dispatch import _make_burn, _make_partner


def test_a_treasury_that_cannot_cover_the_reward_is_not_paid_from(tmp_path):
    partner = _make_partner()
    burn = _make_burn(amount="50")
    dispatcher = Mock()
    dispatcher.treasury_balance.return_value = Decimal("10")      # the reward is 50
    state = bridge.State(tmp_path / "state.json")

    bridge.process_burn(burn, {"CORG": partner}, dispatcher, state)

    dispatcher.send_reward.assert_not_called()
    assert state.processed[burn.key]["status"] == "treasury_low"
    assert "treasury holds 10" in state.processed[burn.key]["error"]


def test_a_funded_treasury_pays_and_an_unknown_balance_does_not_stop_it(tmp_path):
    for balance in (Decimal("1000"), None):
        partner = _make_partner()
        burn = _make_burn(amount="50")
        dispatcher = Mock()
        dispatcher.treasury_balance.return_value = balance
        dispatcher.send_reward.return_value = "sig"
        state = bridge.State(tmp_path / ("state%s.json" % balance))

        bridge.process_burn(burn, {"CORG": partner}, dispatcher, state)

        assert state.processed[burn.key]["status"] == "dispatched"


def test_treasury_low_can_be_reset_and_paid_after_funding(tmp_path):
    partner = _make_partner()
    burn = _make_burn(amount="50")
    dispatcher = Mock()
    dispatcher.treasury_balance.return_value = Decimal("1")
    state = bridge.State(tmp_path / "state.json")
    bridge.process_burn(burn, {"CORG": partner}, dispatcher, state)
    assert state.processed[burn.key]["status"] == "treasury_low"
    assert bridge.reconcile_list_pending(state) == 1            # it shows in the operator's list of what needs attention


def test_a_problem_runs_the_alert_command_with_the_message(tmp_path, monkeypatch):
    out = tmp_path / "alerts.txt"
    script = tmp_path / "alert.py"
    script.write_text("import sys\nopen(%r, 'a').write(sys.argv[-1] + '\\n')\n" % str(out))
    monkeypatch.setenv("BRIDGE_ALERT_CMD", "%s %s" % (sys.executable, script))
    partner = _make_partner()
    burn = _make_burn(amount="50")
    dispatcher = Mock()
    dispatcher.treasury_balance.return_value = Decimal("1")
    state = bridge.State(tmp_path / "state.json")

    bridge.process_burn(burn, {"CORG": partner}, dispatcher, state)

    text = out.read_text()
    assert "NOT paid" in text and burn.key in text


def test_a_failing_payment_alerts_too(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(bridge, "alert", lambda message: sent.append(message))
    partner = _make_partner()
    burn = _make_burn(amount="5")
    dispatcher = Mock()
    dispatcher.treasury_balance.return_value = None
    dispatcher.send_reward.side_effect = RuntimeError("solana is down")
    state = bridge.State(tmp_path / "state.json")

    bridge.process_burn(burn, {"CORG": partner}, dispatcher, state)

    assert state.processed[burn.key]["status"] == "dispatch_error"
    assert len(sent) == 1 and "solana is down" in sent[0]


def test_no_alert_command_is_not_an_error(monkeypatch):
    monkeypatch.delenv("BRIDGE_ALERT_CMD", raising=False)
    bridge.alert("nothing to send it to")        # must simply return


def test_an_alert_command_that_fails_does_not_stop_the_bridge(monkeypatch):
    monkeypatch.setenv("BRIDGE_ALERT_CMD", "/nonexistent/command")
    bridge.alert("this cannot be sent")            # must log and return


@pytest.mark.skipif(os.name != "posix", reason="file modes")
def test_a_treasury_key_that_others_can_read_is_refused(tmp_path):
    keys = tmp_path / "keys"
    keys.mkdir()
    secret = list(bytes(Keypair()))
    keyfile = keys / "treasury.json"
    keyfile.write_text(json.dumps(secret))
    cfg = {"token_mint": "8xudSD6kdeFu1nu5sEiy9zBm2iYhKnnsZfyfF6HGyPq4", "decimals": 6, "reward_ratio": "1.0",
           "treasury_keypair": "treasury.json"}

    os.chmod(keyfile, 0o644)
    with pytest.raises(SystemExit) as e:
        bridge.Partner.from_config("CORG", cfg, keys)
    assert "chmod 600" in str(e.value)

    os.chmod(keyfile, 0o600)
    assert bridge.Partner.from_config("CORG", cfg, keys).tag == "CORG"
