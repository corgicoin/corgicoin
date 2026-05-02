"""Tests for State persistence — the bridge's idempotency boundary lives here."""
import bridge


def test_new_state_starts_empty(tmp_path):
    s = bridge.State(tmp_path / "missing.json")
    assert s.last_height == 0
    assert s.processed == {}
    assert not s.already_processed("any-txid")


def test_round_trip_preserves_state(tmp_path):
    path = tmp_path / "state.json"
    s = bridge.State(path)
    s.last_height = 18391
    s.record("txid-a", {"status": "dispatched"})
    s.save()

    reloaded = bridge.State(path)
    assert reloaded.last_height == 18391
    assert reloaded.already_processed("txid-a")
    assert reloaded.processed["txid-a"]["status"] == "dispatched"


def test_already_processed_after_record(tmp_path):
    s = bridge.State(tmp_path / "state.json")
    assert not s.already_processed("txid-x")
    s.record("txid-x", {"status": "dispatched"})
    assert s.already_processed("txid-x")
