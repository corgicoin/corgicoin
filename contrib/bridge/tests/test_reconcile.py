"""Tests for the operator reconciliation CLI: --list-pending, --mark-dispatched,
--reset. These let an operator clean up after a crash mid-dispatch without
hand-editing state.json."""
import bridge


def _seed_state(tmp_path, entries):
    s = bridge.State(tmp_path / "state.json")
    for txid, e in entries.items():
        s.record(txid, e)
    s.save()
    return bridge.State(tmp_path / "state.json")


# ---------------------------------------------------------------------------
# --list-pending
# ---------------------------------------------------------------------------

def test_list_pending_empty(tmp_path, capsys):
    state = bridge.State(tmp_path / "state.json")
    assert bridge.reconcile_list_pending(state) == 0
    assert "no pending" in capsys.readouterr().out


def test_list_pending_shows_pending_and_errors(tmp_path, capsys):
    state = _seed_state(tmp_path, {
        "tx-pending":  {"status": "pending", "partner": "CORG", "amount_corg": "1.0",
                        "reward": "1.0", "sol_dest": "DE8VHxym...", "height": 18391},
        "tx-error":    {"status": "dispatch_error", "partner": "CORG", "amount_corg": "2.0",
                        "reward": "2.0", "sol_dest": "DE8VHxym...", "height": 18392,
                        "error": "treasury empty"},
        "tx-done":     {"status": "dispatched", "partner": "CORG", "sol_sig": "abc"},
        "tx-skipped":  {"status": "skipped_unknown_partner", "partner": "WHAT"},
    })
    assert bridge.reconcile_list_pending(state) == 0
    out = capsys.readouterr().out
    assert "tx-pending" in out
    assert "tx-error" in out
    assert "treasury empty" in out
    assert "tx-done" not in out
    assert "tx-skipped" not in out


# ---------------------------------------------------------------------------
# --mark-dispatched
# ---------------------------------------------------------------------------

def test_mark_dispatched_promotes_pending(tmp_path):
    state = _seed_state(tmp_path, {
        "tx-1": {"status": "pending", "partner": "CORG", "amount_corg": "1.0",
                 "reward": "1.0", "sol_dest": "DE8VHxym...", "height": 18391},
    })
    assert bridge.reconcile_mark_dispatched(state, "tx-1", "real-sig") == 0
    reloaded = bridge.State(tmp_path / "state.json")
    e = reloaded.processed["tx-1"]
    assert e["status"] == "dispatched"
    assert e["sol_sig"] == "real-sig"
    assert e["partner"] == "CORG"  # other fields preserved


def test_mark_dispatched_clears_error_field(tmp_path):
    state = _seed_state(tmp_path, {
        "tx-1": {"status": "dispatch_error", "partner": "CORG", "amount_corg": "1.0",
                 "reward": "1.0", "sol_dest": "DE8VHxym...", "height": 18391,
                 "error": "treasury empty"},
    })
    bridge.reconcile_mark_dispatched(state, "tx-1", "sig")
    reloaded = bridge.State(tmp_path / "state.json")
    assert "error" not in reloaded.processed["tx-1"]
    assert reloaded.processed["tx-1"]["status"] == "dispatched"


def test_mark_dispatched_refuses_missing(tmp_path, capsys):
    state = bridge.State(tmp_path / "state.json")
    assert bridge.reconcile_mark_dispatched(state, "nope", "sig") == 2
    assert "not found" in capsys.readouterr().err


def test_mark_dispatched_refuses_already_dispatched(tmp_path, capsys):
    state = _seed_state(tmp_path, {
        "tx-1": {"status": "dispatched", "partner": "CORG", "sol_sig": "old-sig"},
    })
    assert bridge.reconcile_mark_dispatched(state, "tx-1", "new-sig") == 2
    assert "already dispatched" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# --reset
# ---------------------------------------------------------------------------

def test_reset_pending_removes_entry_and_rewinds(tmp_path):
    state = _seed_state(tmp_path, {
        "tx-1": {"status": "pending", "partner": "CORG", "amount_corg": "1.0",
                 "reward": "1.0", "sol_dest": "DE8VHxym...", "height": 18391},
    })
    state.last_height = 18400
    state.save()

    assert bridge.reconcile_reset(state, "tx-1") == 0

    reloaded = bridge.State(tmp_path / "state.json")
    assert "tx-1" not in reloaded.processed
    # Rewound so next tick re-scans the block this burn was in
    assert reloaded.last_height == 18390


def test_reset_does_not_advance_last_height(tmp_path):
    """If last_height is already <= burn_height, leave it alone (don't move it forward)."""
    state = _seed_state(tmp_path, {
        "tx-1": {"status": "pending", "partner": "CORG", "amount_corg": "1.0",
                 "reward": "1.0", "sol_dest": "DE8VHxym...", "height": 18391},
    })
    state.last_height = 100
    state.save()

    bridge.reconcile_reset(state, "tx-1")

    assert bridge.State(tmp_path / "state.json").last_height == 100


def test_reset_refuses_dispatched(tmp_path, capsys):
    """Resetting a dispatched entry would re-trigger dispatch on next tick → double-send."""
    state = _seed_state(tmp_path, {
        "tx-1": {"status": "dispatched", "partner": "CORG", "sol_sig": "sig", "height": 18391},
    })
    assert bridge.reconcile_reset(state, "tx-1") == 2
    assert "double-send" in capsys.readouterr().err
    # Entry still present
    assert bridge.State(tmp_path / "state.json").already_processed("tx-1")


def test_reset_refuses_missing(tmp_path, capsys):
    state = bridge.State(tmp_path / "state.json")
    assert bridge.reconcile_reset(state, "nope") == 2
    assert "not found" in capsys.readouterr().err
