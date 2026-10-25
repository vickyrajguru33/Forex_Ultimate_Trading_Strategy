from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from telegram_alerts import alert_id_for, build_signal_alert_text, send_alert_with_retry


class FakeResponse:
    def __init__(self, ok=True):
        self._ok = ok

    def raise_for_status(self):
        return None

    def json(self):
        return {"ok": self._ok}


def test_telegram_failure_and_retry_behavior(monkeypatch, tmp_path):
    from state_store import StateStore

    signal = SimpleNamespace(
        instrument="EURUSD",
        direction="BEARISH",
        candle_time_utc=datetime(2024, 1, 1, 10, 0),
        dxy_previous_high=100.0,
        dxy_previous_low=98.0,
        dxy_signal_high=101.0,
        dxy_signal_low=99.0,
        instrument_previous_high=1.098,
        instrument_previous_low=1.091,
        instrument_signal_high=1.096,
        instrument_signal_low=1.092,
        condition="DXY current high > previous high and instrument current high <= previous high",
    )

    calls = {"count": 0}

    def fake_send(text: str, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("temporary failure")
        return None

    monkeypatch.setattr("telegram_alerts.send_telegram_message", fake_send)
    store = StateStore(tmp_path / "telegram.db")
    result = send_alert_with_retry(signal, store=store, max_attempts=3)
    assert result is True
    assert calls["count"] == 2
    assert store.is_delivered(alert_id_for(signal)) is True


def test_signal_alert_contains_required_statement():
    signal = SimpleNamespace(
        instrument="GBPUSD",
        direction="BULLISH",
        candle_time_utc=datetime(2024, 1, 1, 10, 0),
        dxy_previous_high=100.0,
        dxy_previous_low=98.0,
        dxy_signal_high=101.0,
        dxy_signal_low=99.0,
        instrument_previous_high=1.098,
        instrument_previous_low=1.091,
        instrument_signal_high=1.096,
        instrument_signal_low=1.092,
        condition="DXY current low < previous low and instrument current low >= previous low",
    )
    text = build_signal_alert_text(signal)
    assert "DETECTION ONLY — NO ORDER PLACED." in text
    assert "A+ 15M DXY Sweep" in text
