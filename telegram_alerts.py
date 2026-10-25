from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

from zoneinfo import ZoneInfo

import requests

from config import get_settings
from state_store import StateStore

logger = logging.getLogger(__name__)


class TelegramAlertError(RuntimeError):
    pass


def _to_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _format_ist_datetime(value: datetime) -> str:
    utc_value = _to_utc_datetime(value)
    return utc_value.astimezone(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M:%S IST")


def build_signal_alert_text(signal: Any) -> str:
    candle_time = getattr(signal, "candle_time_utc", datetime.now(timezone.utc))
    msg = [
        "A+ 15M DXY Sweep",
        f"DIRECTION: {signal.direction} SETUP",
        f"Instrument: {signal.instrument}",
        f"Completed candle time (IST): {_format_ist_datetime(candle_time)}",
        f"DXY previous high/low: {signal.dxy_previous_high} / {signal.dxy_previous_low}",
        f"DXY signal high/low: {signal.dxy_signal_high} / {signal.dxy_signal_low}",
        f"Instrument previous high/low: {signal.instrument_previous_high} / {signal.instrument_previous_low}",
        f"Instrument signal high/low: {signal.instrument_signal_high} / {signal.instrument_signal_low}",
        f"Triggered condition: {signal.condition}",
        "Reminder: manually inspect the 1-minute chart for an OB/FVG.",
        "DETECTION ONLY — NO ORDER PLACED.",
    ]
    return "\n".join(msg)


def alert_id_for(signal: Any) -> str:
    return f"{signal.instrument.lower()}-{signal.direction.lower()}-{signal.candle_time_utc.isoformat(timespec='seconds')}"


def send_telegram_message(text: str, *, bot_token: str | None = None, chat_id: str | None = None) -> None:
    settings = get_settings()
    bot_token = bot_token or settings.telegram_bot_token
    chat_id = chat_id or settings.telegram_chat_id
    if settings.dry_run:
        print(text)
        return
    if not bot_token or not chat_id:
        raise TelegramAlertError("Telegram credentials are missing.")

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    response = requests.post(url, data=payload, timeout=15)
    response.raise_for_status()
    body = response.json()
    if not body.get("ok"):
        raise TelegramAlertError(f"Telegram sendMessage failed: {body}")


def send_alert_with_retry(signal: Any, store: StateStore | None = None, *, max_attempts: int = 4) -> bool:
    settings = get_settings()
    store = store or StateStore()
    alert_key = alert_id_for(signal)
    if store.is_delivered(alert_key):
        return True
    if not store.insert_or_ignore_alert(alert_key, signal.instrument, signal.direction, signal.candle_time_utc, json.dumps(signal.__dict__, default=str)):
        return store.is_delivered(alert_key)

    text = build_signal_alert_text(signal)
    attempt = 0
    while attempt < max_attempts:
        try:
            send_telegram_message(text)
            store.mark_delivered(alert_key)
            logger.info("Telegram alert delivered: %s", alert_key)
            return True
        except Exception as exc:  # pragma: no cover - retry control path
            attempt += 1
            logger.warning("Telegram send failed (%s/%s): %s", attempt, max_attempts, exc)
            if attempt >= max_attempts:
                store.mark_failed(alert_key)
                return False
            time.sleep(2 ** attempt)
    return False


def send_startup_message(store: StateStore | None = None) -> None:
    settings = get_settings()
    if settings.dry_run:
        print("Scanner startup: dry-run mode enabled; Telegram disabled.")
        return
    attempt = 0
    while attempt < 4:
        try:
            send_telegram_message("Ultimate Trading Strategy Scanner started. Monitoring M15 DXY sweep conditions.")
            return
        except Exception:
            attempt += 1
            time.sleep(2 ** attempt)
    logger.warning("Startup Telegram message failed after retries.")
