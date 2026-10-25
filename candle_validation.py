from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Iterable


@dataclass(frozen=True)
class Candle:
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int = 0

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Candle":
        required = {"time", "open", "high", "low", "close"}
        missing = required - set(payload.keys())
        if missing:
            raise ValueError(f"Candle missing required fields: {sorted(missing)}")
        return cls(
            time=_coerce_datetime(payload["time"]),
            open=float(payload["open"]),
            high=float(payload["high"]),
            low=float(payload["low"]),
            close=float(payload["close"]),
            volume=int(payload.get("volume", 0)),
        )


def _coerce_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        return datetime.utcfromtimestamp(float(value))
    if isinstance(value, str):
        candidate = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if candidate.tzinfo is not None:
            return candidate.astimezone().replace(tzinfo=None)
        return candidate
    raise TypeError(f"Unsupported datetime value: {value!r}")


def validate_complete_bar(bar: Candle | dict[str, Any]) -> Candle:
    candle = bar if isinstance(bar, Candle) else Candle.from_dict(bar)
    if not all([candle.open, candle.high, candle.low, candle.close]) and candle.high == 0:
        raise ValueError("Candle has invalid zeroed OHLC values")
    if candle.high < candle.low:
        raise ValueError("Candle high is lower than low")
    if candle.high < max(candle.open, candle.close) or candle.low > min(candle.open, candle.close):
        raise ValueError("Candle OHLC is internally inconsistent")
    return candle


def validate_consecutive_m15(current: Candle, previous: Candle, allow_same_symbol: bool = True) -> bool:
    if current.time <= previous.time:
        return False
    expected_delta = timedelta(minutes=15)
    if current.time - previous.time != expected_delta:
        return False
    if not allow_same_symbol and current.time == previous.time:
        return False
    return True


def validate_pair_timestamp_match(current_a: Candle, previous_a: Candle, current_b: Candle, previous_b: Candle) -> bool:
    return (
        current_a.time == current_b.time
        and previous_a.time == previous_b.time
        and validate_consecutive_m15(current_a, previous_a)
        and validate_consecutive_m15(current_b, previous_b)
    )


def validate_bar_series(bars: Iterable[dict[str, Any] | Candle]) -> list[Candle]:
    candles = [validate_complete_bar(bar) for bar in bars]
    for idx in range(1, len(candles)):
        if not validate_consecutive_m15(candles[idx], candles[idx - 1]):
            raise ValueError(f"Bars are not valid consecutive M15 candles at index {idx}")
    return candles


def invert_candle_for_display(candle: Candle) -> Candle:
    return Candle(
        time=candle.time,
        open=candle.close,
        high=candle.low,
        low=candle.high,
        close=candle.open,
        volume=candle.volume,
    )


def is_bearish_sweep(
    instrument_current: Candle,
    instrument_previous: Candle,
    dxy_current: Candle,
    dxy_previous: Candle,
    invert_dxy_scale: bool = True,
) -> bool:
    if not validate_pair_timestamp_match(instrument_current, instrument_previous, dxy_current, dxy_previous):
        return False
    dxy_current_eval = invert_candle_for_display(dxy_current) if invert_dxy_scale else dxy_current
    dxy_previous_eval = invert_candle_for_display(dxy_previous) if invert_dxy_scale else dxy_previous
    return (
        dxy_current_eval.high > dxy_previous_eval.high
        and instrument_current.high <= instrument_previous.high
    )


def is_bullish_sweep(
    instrument_current: Candle,
    instrument_previous: Candle,
    dxy_current: Candle,
    dxy_previous: Candle,
    invert_dxy_scale: bool = True,
) -> bool:
    if not validate_pair_timestamp_match(instrument_current, instrument_previous, dxy_current, dxy_previous):
        return False
    dxy_current_eval = invert_candle_for_display(dxy_current) if invert_dxy_scale else dxy_current
    dxy_previous_eval = invert_candle_for_display(dxy_previous) if invert_dxy_scale else dxy_previous
    return (
        dxy_current_eval.low < dxy_previous_eval.low
        and instrument_current.low >= instrument_previous.low
    )
