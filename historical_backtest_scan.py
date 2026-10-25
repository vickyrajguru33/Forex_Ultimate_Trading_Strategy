from __future__ import annotations

import logging
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from candle_validation import Candle
from config import get_settings, validate_required_settings
from mt5_client import MT5Client, MT5ClientError
from sweep_detector import detect_sweep_signal
from telegram_alerts import send_telegram_message

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")
INSTRUMENTS = ("EURUSD", "GBPUSD", "XAUUSD")
CONTEXT_INSTRUMENT = "DXY"


def _format_ist(value: datetime) -> str:
    return value.astimezone(IST).strftime("%Y-%m-%d %H:%M:%S IST")


def _to_candle(row: dict[str, Any]) -> Candle:
    return Candle(
        time=row["time"],
        open=float(row["open"]),
        high=float(row["high"]),
        low=float(row["low"]),
        close=float(row["close"]),
        volume=int(row.get("volume", 0)),
    )


def fetch_1y_m15_history(client: MT5Client, symbol_name: str) -> list[Candle]:
    mt5 = client.mt5
    end = datetime.now(timezone.utc).replace(microsecond=0)
    start = end - timedelta(days=365)
    rates = mt5.copy_rates_range(symbol_name, mt5.TIMEFRAME_M15, start, end)
    if rates is None:
        raise MT5ClientError(f"No M15 data returned for {symbol_name} in the last 365 days.")
    candles = [_to_candle({
        "time": datetime.fromtimestamp(int(rate[0]), tz=timezone.utc),
        "open": rate[1],
        "high": rate[2],
        "low": rate[3],
        "close": rate[4],
        "volume": int(rate[5]),
    }) for rate in rates]
    candles.sort(key=lambda candle: candle.time)
    return candles


def scan_1y_signals() -> list[Any]:
    settings = validate_required_settings()
    client = MT5Client(settings=settings)
    histories: dict[str, list[Candle]] = {}

    for instrument in INSTRUMENTS + (CONTEXT_INSTRUMENT,):
        symbol = client.resolve_symbol(instrument)
        logger.info("Scanning %s (%s) for last 365 days", instrument, symbol)
        histories[instrument] = fetch_1y_m15_history(client, symbol)

    hits: list[Any] = []
    for instrument in INSTRUMENTS:
        bars = histories[instrument]
        dxy = histories[CONTEXT_INSTRUMENT]
        for index in range(1, min(len(bars), len(dxy))):
            signal = detect_sweep_signal(
                instrument_name=instrument,
                instrument_current=bars[index],
                instrument_previous=bars[index - 1],
                dxy_current=dxy[index],
                dxy_previous=dxy[index - 1],
                invert_dxy_scale=settings.dxy_invert_scale,
            )
            if signal is not None:
                hits.append(signal)

    return sorted(hits, key=lambda item: item.candle_time_utc)


def format_signal_line(signal: Any) -> str:
    return (
        f"{signal.instrument} {signal.direction} | "
        f"{_format_ist(signal.candle_time_utc)} | "
        f"DXY prev H/L {signal.dxy_previous_high:.5f}/{signal.dxy_previous_low:.5f} | "
        f"DXY signal H/L {signal.dxy_signal_high:.5f}/{signal.dxy_signal_low:.5f} | "
        f"Inst prev H/L {signal.instrument_previous_high:.5f}/{signal.instrument_previous_low:.5f} | "
        f"Inst signal H/L {signal.instrument_signal_high:.5f}/{signal.instrument_signal_low:.5f} | "
        f"Condition: {signal.condition}"
    )


def build_backtest_message(signals: list[Any]) -> str:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=365)
    counts = Counter(signal.instrument for signal in signals)

    lines = [
        "A+ 15M DXY Sweep Backtest (Last 12 Months)",
        f"Window: {_format_ist(start)} to {_format_ist(end)}",
        "Instruments scanned: EURUSD, GBPUSD, XAUUSD, DXY",
        f"Total setups found: {len(signals)}",
    ]

    if counts:
        lines.append("Breakdown: " + " | ".join(f"{instrument}={count}" for instrument, count in sorted(counts.items())))
    else:
        lines.append("Breakdown: none")

    if not signals:
        lines.append("No valid A+ 15M DXY sweep setups were detected in the last 365 days.")
        lines.append("DETECTION ONLY — NO ORDER PLACED.")
        return "\n".join(lines)

    lines.append("Recent signals:")
    for signal in signals[-5:]:
        lines.append(f"- {format_signal_line(signal)}")
    lines.append("Data source: MT5 M15 candles at 15-minute closes.")
    lines.append("DETECTION ONLY — NO ORDER PLACED.")
    return "\n".join(lines)


def main() -> int:
    settings = get_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    try:
        signals = scan_1y_signals()
        message = build_backtest_message(signals)
        print(message)
        if settings.dry_run:
            logger.info("Dry-run enabled; Telegram send skipped.")
            return 0
        send_telegram_message(message)
        logger.info("Backtest summary message sent to Telegram.")
        return 0
    except Exception as exc:  # pragma: no cover - environment-specific runtime guard
        logger.exception("Historical backtest failed: %s", exc)
        fallback = (
            "A+ 15M DXY Sweep Backtest (Last 12 Months)\n"
            "Scan blocked: MetaTrader5 data is not available in this environment or the MT5 terminal is not connected.\n"
            "This is informational only. No order was placed."
        )
        print(fallback)
        if not settings.dry_run:
            try:
                send_telegram_message(fallback)
            except Exception:
                logger.warning("Telegram fallback message also failed.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
