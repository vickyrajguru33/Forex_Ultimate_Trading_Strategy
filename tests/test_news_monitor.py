from __future__ import annotations

from datetime import datetime, timedelta

from zoneinfo import ZoneInfo

import news_monitor
from news_monitor import NewsEvent, NewsMonitor
from prop_firm_rules import get_default_prop_firm_rule_profile
from state_store import StateStore


class DummyResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FrozenDateTime(datetime):
    current = datetime(2026, 10, 25, 7, 0, tzinfo=ZoneInfo("Asia/Kolkata"))

    @classmethod
    def now(cls, tz=None):
        if tz is None:
            return cls.current
        return cls.current.astimezone(tz)


def test_news_monitor_parses_alpha_vantage_feed(monkeypatch):
    payload = {
        "feed": [
            {
                "title": "FOMC interest rate decision",
                "summary": "Fed expected to hold rates steady as inflation cools.",
                "time_published": "20261025T153000",
                "topics": [{"topic": "economy_monetary"}],
                "overall_sentiment_score": "0.32",
                "relevance_score": "0.81",
                "ticker_sentiment": [
                    {"ticker": "USD", "relevance_score": "0.90", "ticker_sentiment_score": "0.38"}
                ],
            }
        ]
    }

    def fake_get(url, params=None, timeout=10):
        return DummyResponse(payload)

    monkeypatch.setattr("requests.get", fake_get)
    monkeypatch.setattr(news_monitor, "datetime", FrozenDateTime)

    monitor = NewsMonitor(provider="alpha_vantage", api_key="demo")
    events = monitor.fetch_events()

    assert len(events) == 1
    event = events[0]
    assert event.name == "FOMC interest rate decision"
    assert event.currency == "USD"
    assert event.impact in {"low", "medium", "high"}
    assert event.scheduled_ist.tzinfo is not None


def test_daily_summary_7am_ist(monkeypatch):
    monkeypatch.setattr(news_monitor, "datetime", FrozenDateTime)
    monitor = NewsMonitor(provider="alpha_vantage", api_key="demo")
    events = [
        NewsEvent(
            name="US CPI",
            currency="USD",
            impact="high",
            scheduled_ist=datetime(2026, 10, 25, 7, 30, tzinfo=ZoneInfo("Asia/Kolkata")),
            provider_event_id="cpi-1",
            source="Alpha Vantage",
            affected_instruments=["EURUSD", "GBPUSD", "DXY"],
        )
    ]

    message = monitor.build_daily_summary_message(events)

    assert "Economic news summary" in message
    assert "US CPI" in message
    assert "07:30 IST" in message
    assert "RULE NOT VERIFIED" in message


def test_news_monitor_reminders_use_event_window():
    monitor = NewsMonitor(provider="alpha_vantage", api_key="demo")
    event = NewsEvent(
        name="US CPI",
        currency="USD",
        impact="high",
        scheduled_ist=datetime(2026, 10, 25, 15, 30, tzinfo=ZoneInfo("Asia/Kolkata")),
        provider_event_id="cpi-2",
        source="Alpha Vantage",
        affected_instruments=["DXY"],
    )

    pre_reminder = monitor.reminders_for(event, now=datetime(2026, 10, 25, 14, 45, tzinfo=ZoneInfo("Asia/Kolkata")))
    post_reminder = monitor.reminders_for(event, now=datetime(2026, 10, 25, 16, 00, tzinfo=ZoneInfo("Asia/Kolkata")))

    assert pre_reminder == ["pre"]
    assert post_reminder == ["post"]


def test_news_monitor_daily_summary_is_due_at_0700_ist():
    monitor = NewsMonitor(provider="alpha_vantage", api_key="demo")

    assert monitor.summary_is_due(datetime(2026, 10, 25, 7, 0, 0, tzinfo=ZoneInfo("Asia/Kolkata"))) is True
    assert monitor.summary_is_due(datetime(2026, 10, 25, 6, 59, 30, tzinfo=ZoneInfo("Asia/Kolkata"))) is False
    assert monitor.summary_is_due(datetime(2026, 10, 25, 7, 1, 0, tzinfo=ZoneInfo("Asia/Kolkata"))) is False


def test_news_alerts_are_deduplicated_across_restarts(tmp_path):
    db_path = tmp_path / "news.db"
    store = StateStore(db_path=db_path)
    monitor = NewsMonitor(provider="alpha_vantage", api_key="demo")
    event = NewsEvent(
        name="Fed statement",
        currency="USD",
        impact="high",
        scheduled_ist=datetime(2026, 10, 25, 18, 0, tzinfo=ZoneInfo("Asia/Kolkata")),
        provider_event_id="fed-001",
        source="Alpha Vantage",
        affected_instruments=["DXY"],
    )
    sent_messages = []

    first = monitor.send_news_alert(event, "pre", store=store, sender=sent_messages.append)
    second = monitor.send_news_alert(event, "pre", store=store, sender=sent_messages.append)

    assert first is True
    assert second is True
    assert len(sent_messages) == 1


def test_news_provider_failure_is_graceful(monkeypatch):
    def raise_error(*args, **kwargs):
        raise RuntimeError("rate limit")

    monkeypatch.setattr("requests.get", raise_error)
    monitor = NewsMonitor(provider="alpha_vantage", api_key="demo")

    assert monitor.fetch_events() == []


def test_default_prop_firm_rule_profile_is_unverified():
    profile = get_default_prop_firm_rule_profile()

    assert profile.verified is False
    assert "RULE NOT VERIFIED" in profile.to_message_block()
