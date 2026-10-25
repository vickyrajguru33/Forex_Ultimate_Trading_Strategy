from datetime import datetime

from state_store import StateStore


def test_duplicate_alert_suppression(tmp_path):
    db_path = tmp_path / "scanner_state.db"
    store = StateStore(db_path)
    now = datetime(2024, 1, 1, 9, 45)
    inserted = store.insert_or_ignore_alert("eurusd-bearish-2024-01-01T09:45:00", "EURUSD", "BEARISH", now, '{"x": 1}')
    duplicate = store.insert_or_ignore_alert("eurusd-bearish-2024-01-01T09:45:00", "EURUSD", "BEARISH", now, '{"x": 1}')
    assert inserted is True
    assert duplicate is False
    assert store.is_delivered("eurusd-bearish-2024-01-01T09:45:00") is False


def test_duplicate_prevention_across_restarts(tmp_path):
    db_path = tmp_path / "scanner_state.db"
    first = StateStore(db_path)
    second = StateStore(db_path)
    now = datetime(2024, 1, 1, 9, 45)
    assert first.insert_or_ignore_alert("gbpusd-bullish-2024-01-01T09:45:00", "GBPUSD", "BULLISH", now, '{"x": 2}') is True
    assert second.insert_or_ignore_alert("gbpusd-bullish-2024-01-01T09:45:00", "GBPUSD", "BULLISH", now, '{"x": 2}') is False
