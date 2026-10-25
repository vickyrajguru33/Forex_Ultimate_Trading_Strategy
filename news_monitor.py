from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import requests

from prop_firm_rules import get_prop_firm_rule_profile_from_env
from state_store import StateStore
from telegram_alerts import send_telegram_message

logger = logging.getLogger(__name__)


@dataclass
class NewsEvent:
    name: str
    currency: str
    impact: str
    scheduled_ist: datetime
    provider_event_id: str | None = None
    source: str = "Alpha Vantage"
    country: str = ""
    forecast: str | None = None
    previous: str | None = None
    actual: str | None = None
    affected_instruments: list[str] = field(default_factory=list)
    raw_event: dict[str, Any] = field(default_factory=dict)


class NewsMonitor:
    """Optional economic news integration.

    The project uses a free-tier news provider that exposes real economic news metadata
    and timestamps. If the provider is unavailable or the key is missing, the monitor
    fails gracefully and does not block sweep detection or Telegram operation.
    """

    def __init__(self, provider: str | None = None, api_key: str | None = None) -> None:
        self.provider = (provider or os.getenv("NEWS_PROVIDER", "alpha_vantage")).strip().lower().replace("-", "_")
        self.api_key = (api_key or os.getenv("NEWS_CALENDAR_API_KEY") or os.getenv("NEWS_API_KEY") or "").strip()
        self.enabled = self.provider in {"calendar", "alpha_vantage", "news_sentiment"} and bool(self.api_key)
        self.timezone_name = os.getenv("NEWS_TIMEZONE", "Asia/Kolkata")
        self.timezone = ZoneInfo(self.timezone_name)
        self.summary_time = self._parse_time(os.getenv("NEWS_SUMMARY_TIME", "07:00"))
        self.pre_event_minutes = int(os.getenv("NEWS_PRE_EVENT_MINUTES", "60"))
        self.post_event_minutes = int(os.getenv("NEWS_POST_EVENT_MINUTES", "60"))
        self.post_event_enabled = os.getenv("NEWS_POST_EVENT_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _parse_time(value: str) -> timedelta:
        hh, mm = value.split(":", 1)
        return timedelta(hours=int(hh), minutes=int(mm))

    def fetch_events(self) -> list[NewsEvent]:
        if not self.enabled:
            logger.info("News monitoring is disabled because no provider configuration was found.")
            return []
        if self.provider in {"calendar", "alpha_vantage", "news_sentiment"}:
            return self._fetch_alpha_vantage_news()
        logger.warning("Unsupported news provider '%s'; news monitoring remains disabled.", self.provider)
        return []

    def _fetch_alpha_vantage_news(self) -> list[NewsEvent]:
        url = "https://www.alphavantage.co/query"
        params = {
            "function": "NEWS_SENTIMENT",
            "limit": 20,
            "apikey": self.api_key,
        }
        try:
            response = requests.get(url, params=params, timeout=15)
            response.raise_for_status()
            payload = response.json() or {}
        except Exception as exc:  # pragma: no cover - network guard
            logger.warning("Economic news provider failed: %s", exc)
            return []

        feed = payload.get("feed") or []
        events: list[NewsEvent] = []
        for item in feed:
            event = self._parse_alpha_vantage_entry(item)
            if event is not None:
                events.append(event)
        return events

    def _parse_alpha_vantage_entry(self, entry: dict[str, Any]) -> NewsEvent | None:
        title = str(entry.get("title") or "").strip()
        if not title:
            return None

        topic_list = [
            str(topic.get("topic") or topic.get("name") or "").strip()
            for topic in (entry.get("topics") or [])
            if isinstance(topic, dict)
        ]
        if not self._is_relevant_event(title, topic_list):
            return None

        timestamp = self._parse_event_timestamp(entry.get("time_published"))
        if timestamp is None:
            return None

        currency = self._extract_currency(entry) or self._infer_currency_from_title(title) or "USD"
        impact = self._impact_from_score(entry.get("overall_sentiment_score"), entry.get("relevance_score"))
        source_name = str(entry.get("source") or "Alpha Vantage").strip() or "Alpha Vantage"
        event_id = str(entry.get("id") or f"{title}-{currency}-{timestamp.isoformat()}")
        country = self._infer_country(currency, title)

        return NewsEvent(
            name=title,
            currency=currency,
            impact=impact,
            scheduled_ist=timestamp.astimezone(self.timezone),
            provider_event_id=event_id,
            source=source_name,
            country=country,
            forecast=str(entry.get("forecast") or entry.get("estimate") or "").strip() or None,
            previous=str(entry.get("previous") or "").strip() or None,
            actual=str(entry.get("actual") or "").strip() or None,
            affected_instruments=self._affected_instruments_for(currency, title),
            raw_event=entry,
        )

    @staticmethod
    def _parse_event_timestamp(value: Any) -> datetime | None:
        if value is None:
            return None
        if not isinstance(value, str):
            return None
        try:
            dt = datetime.strptime(value, "%Y%m%dT%H%M%S")
        except ValueError:
            try:
                dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))
        return dt.astimezone(ZoneInfo("UTC"))

    @staticmethod
    def _is_relevant_event(title: str, topics: list[str]) -> bool:
        lowered = title.lower()
        keywords = (
            "fed", "fomc", "inflation", "cpi", "rate", "rates", "gdp", "payroll",
            "jobs", "nfp", "treasury", "yield", "bank", "policy", "economy", "growth",
            "unemployment", "retail", "durable", "housing", "trade balance", "central bank"
        )
        if any(keyword in lowered for keyword in keywords):
            return True
        return any("economy" in topic.lower() or "monetary" in topic.lower() for topic in topics)

    @staticmethod
    def _extract_currency(entry: dict[str, Any]) -> str | None:
        for item in entry.get("ticker_sentiment") or []:
            if isinstance(item, dict):
                symbol = str(item.get("ticker") or "").strip().upper()
                if symbol:
                    return symbol
        return None

    @staticmethod
    def _infer_currency_from_title(title: str) -> str | None:
        lowered = title.lower()
        if "eur" in lowered and "usd" in lowered:
            return "EURUSD"
        if "gbp" in lowered and "usd" in lowered:
            return "GBPUSD"
        if "gold" in lowered or "xau" in lowered:
            return "XAUUSD"
        if "dollar" in lowered or "fed" in lowered or "treasury" in lowered:
            return "USD"
        return "USD"

    @staticmethod
    def _infer_country(currency: str, title: str) -> str:
        lowered = title.lower()
        if "fed" in lowered or "federal reserve" in lowered:
            return "United States"
        if currency.startswith("EUR"):
            return "Eurozone"
        if currency.startswith("GBP"):
            return "United Kingdom"
        if currency == "XAUUSD":
            return "United States"
        return "United States"

    @staticmethod
    def _affected_instruments_for(currency: str, title: str) -> list[str]:
        lowered = title.lower()
        instruments: list[str] = []
        if currency in {"EUR", "USD", "EURUSD"} or "eur" in lowered or "usd" in lowered:
            instruments.append("EURUSD")
        if currency in {"GBP", "USD", "GBPUSD"} or "gbp" in lowered or "usd" in lowered:
            instruments.append("GBPUSD")
        if currency in {"XAUUSD", "USD"} or "gold" in lowered or "xau" in lowered or "fed" in lowered:
            instruments.append("XAUUSD")
        if "dxy" in lowered or "federal reserve" in lowered or "usd" in lowered:
            instruments.append("DXY")
        return sorted(set(instruments))

    @staticmethod
    def _impact_from_score(overall_sentiment_score: Any, relevance_score: Any) -> str:
        try:
            score = float(overall_sentiment_score)
        except (TypeError, ValueError):
            score = 0.0
        try:
            relevance = float(relevance_score)
        except (TypeError, ValueError):
            relevance = 0.0
        if max(score, relevance) >= 0.8:
            return "high"
        if max(score, relevance) >= 0.4:
            return "medium"
        return "low"

    def summary_is_due(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(self.timezone)
        local_now = now.astimezone(self.timezone)
        return local_now.hour == 7 and local_now.minute == 0

    def daily_summary_at_0700_ist(self) -> list[NewsEvent]:
        today = datetime.now(self.timezone).date()
        events = self.fetch_events()
        return [event for event in events if event.scheduled_ist.astimezone(self.timezone).date() == today]

    def build_daily_summary_message(self, events: list[NewsEvent]) -> str:
        if not events:
            return "No relevant events found in the configured calendar."
        lines = [
            "Economic news summary (Asia/Kolkata)",
            "-" * 28,
        ]
        for event in sorted(events, key=lambda item: item.scheduled_ist):
            lines.append(
                f"{event.scheduled_ist.astimezone(self.timezone).strftime('%H:%M IST')} | {event.name} | "
                f"{event.currency} | impact={event.impact} | instruments={', '.join(event.affected_instruments) or 'n/a'} | source={event.source}"
            )
        lines.append("")
        lines.append(get_prop_firm_rule_profile_from_env().to_message_block())
        return "\n".join(lines)

    def due_job_checks(self, *, now: datetime | None = None, events: list[NewsEvent] | None = None) -> tuple[bool, list[tuple[NewsEvent, str]]]:
        now = now or datetime.now(self.timezone)
        local_now = now.astimezone(self.timezone)
        events = events or self.fetch_events()
        summary_due = self.summary_is_due(local_now)
        due_reminders: list[tuple[NewsEvent, str]] = []
        for event in events:
            for reminder_type in self.reminders_for(event, now=local_now):
                due_reminders.append((event, reminder_type))
        return summary_due, due_reminders

    def reminders_for(self, event: NewsEvent, *, now: datetime | None = None) -> list[str]:
        now = now or datetime.now(self.timezone)
        event_local = event.scheduled_ist.astimezone(self.timezone)
        delta = event_local - now
        reminders: list[str] = []
        if delta > timedelta(0) and delta <= timedelta(minutes=self.pre_event_minutes):
            reminders.append("pre")
        if self.post_event_enabled and delta <= timedelta(0) and abs(delta) <= timedelta(minutes=self.post_event_minutes):
            reminders.append("post")
        return reminders

    def reminder_payload(self, event: NewsEvent, reminder_type: str) -> str:
        local_time = event.scheduled_ist.astimezone(self.timezone).strftime("%Y-%m-%d %H:%M IST")
        rule_block = get_prop_firm_rule_profile_from_env().to_message_block()

        if reminder_type == "pre":
            return (
                f"Economic news reminder: {event.name}\n"
                f"Scheduled: {local_time}\n"
                f"Currency: {event.currency}\n"
                f"Impact: {event.impact}\n"
                f"Affected instruments: {', '.join(event.affected_instruments) or 'n/a'}\n"
                f"Source: {event.source}\n"
                f"{rule_block}\n"
                "This is informational only and is not a trade signal."
            )
        if reminder_type == "post":
            return (
                f"Post-event reminder: {event.name}\n"
                f"Scheduled: {local_time}\n"
                f"Impact: {event.impact}\n"
                f"Affected instruments: {', '.join(event.affected_instruments) or 'n/a'}\n"
                f"Source: {event.source}\n"
                f"{rule_block}\n"
                "This is a post-event reminder, not a trade signal."
            )
        return f"Economic news: {event.name} ({local_time})"

    @staticmethod
    def _deterministic_event_key(event: NewsEvent, reminder_type: str) -> str:
        key_base = event.provider_event_id or f"{event.name}-{event.currency}-{event.scheduled_ist.isoformat()}"
        safe_key = key_base.replace(" ", "_").replace("/", "-")
        return f"news::{safe_key}::{reminder_type}"

    def send_news_alert(self, event: NewsEvent, reminder_type: str, *, store: StateStore | None = None, sender: Any = None) -> bool:
        if not self.enabled:
            return False
        store = store or StateStore()
        sender = sender or send_telegram_message
        alert_key = self._deterministic_event_key(event, reminder_type)
        payload = json.dumps({
            "provider_event_id": event.provider_event_id,
            "name": event.name,
            "currency": event.currency,
            "impact": event.impact,
            "scheduled_ist": event.scheduled_ist.isoformat(),
            "reminder_type": reminder_type,
            "affected_instruments": event.affected_instruments,
            "source": event.source,
        }, default=str)
        if store.is_news_delivered(alert_key):
            return True
        if not store.insert_or_ignore_news_alert(alert_key, event.provider_event_id or event.name, reminder_type, payload):
            return store.is_news_delivered(alert_key)
        try:
            sender(self.reminder_payload(event, reminder_type))
            store.mark_news_delivered(alert_key)
            return True
        except Exception as exc:  # pragma: no cover - retry control path
            store.mark_news_failed(alert_key)
            logger.warning("Failed to send news alert '%s': %s", alert_key, exc)
            return False


def build_news_monitor() -> NewsMonitor:
    return NewsMonitor(provider=os.getenv("NEWS_PROVIDER"), api_key=os.getenv("NEWS_CALENDAR_API_KEY") or os.getenv("NEWS_API_KEY"))
