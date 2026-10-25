from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from dotenv import load_dotenv

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")


def _get_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    mt5_eurusd_symbol: str = os.getenv("MT5_EURUSD_SYMBOL", "")
    mt5_gbpusd_symbol: str = os.getenv("MT5_GBPUSD_SYMBOL", "")
    mt5_xauusd_symbol: str = os.getenv("MT5_XAUUSD_SYMBOL", "")
    mt5_dxy_symbol: str = os.getenv("MT5_DXY_SYMBOL", "")
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
    dry_run: bool = _get_bool("DRY_RUN", False)
    app_timezone: str = os.getenv("APP_TIMEZONE", "Asia/Kolkata")
    dxy_invert_scale: bool = _get_bool("DXY_INVERT_SCALE", True)
    news_enabled: bool = _get_bool("NEWS_ALERTS_ENABLED", False) or _get_bool("NEWS_ENABLED", False)
    news_provider: str = os.getenv("NEWS_PROVIDER", "alpha_vantage")
    news_api_key: str = os.getenv("NEWS_CALENDAR_API_KEY", "") or os.getenv("NEWS_API_KEY", "")
    news_alerts_enabled: bool = _get_bool("NEWS_ALERTS_ENABLED", False)
    news_calendar_api_key: str = os.getenv("NEWS_CALENDAR_API_KEY", "")
    news_timezone: str = os.getenv("NEWS_TIMEZONE", "Asia/Kolkata")
    news_summary_time: str = os.getenv("NEWS_SUMMARY_TIME", "07:00")
    news_pre_event_minutes: int = int(os.getenv("NEWS_PRE_EVENT_MINUTES", "60"))
    news_post_event_minutes: int = int(os.getenv("NEWS_POST_EVENT_MINUTES", "60"))
    news_poll_interval_minutes: int = int(os.getenv("NEWS_POLL_INTERVAL_MINUTES", "15"))
    news_post_event_enabled: bool = _get_bool("NEWS_POST_EVENT_ENABLED", True)


def get_settings() -> Settings:
    return Settings()


def validate_required_settings(settings: Settings | None = None) -> Settings:
    settings = settings or get_settings()
    if not settings.dry_run and not settings.telegram_bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN is required unless DRY_RUN=true.")
    if not settings.dry_run and not settings.telegram_chat_id:
        raise ValueError("TELEGRAM_CHAT_ID is required unless DRY_RUN=true.")
    return settings


def symbol_mapping() -> dict[str, str]:
    settings = get_settings()
    return {
        "EURUSD": settings.mt5_eurusd_symbol,
        "GBPUSD": settings.mt5_gbpusd_symbol,
        "XAUUSD": settings.mt5_xauusd_symbol,
        "DXY": settings.mt5_dxy_symbol,
    }
