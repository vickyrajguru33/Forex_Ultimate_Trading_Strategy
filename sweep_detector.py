from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from candle_validation import Candle, is_bearish_sweep, is_bullish_sweep


@dataclass(frozen=True)
class SweepSignal:
    instrument: str
    direction: str
    candle_time_utc: datetime
    dxy_previous_high: float
    dxy_previous_low: float
    dxy_signal_high: float
    dxy_signal_low: float
    instrument_previous_high: float
    instrument_previous_low: float
    instrument_signal_high: float
    instrument_signal_low: float
    condition: str

    @property
    def candle_time_iso(self) -> str:
        return self.candle_time_utc.isoformat(timespec="seconds") + "Z"


def _to_candle(raw: dict[str, Any] | Candle) -> Candle:
    return raw if isinstance(raw, Candle) else Candle.from_dict(raw)


def detect_sweep_signal(
    instrument_name: str,
    instrument_current: dict[str, Any] | Candle,
    instrument_previous: dict[str, Any] | Candle,
    dxy_current: dict[str, Any] | Candle,
    dxy_previous: dict[str, Any] | Candle,
    invert_dxy_scale: bool = True,
) -> SweepSignal | None:
    inst_curr = _to_candle(instrument_current)
    inst_prev = _to_candle(instrument_previous)
    dxy_curr = _to_candle(dxy_current)
    dxy_prev = _to_candle(dxy_previous)

    if inst_curr.time != dxy_curr.time or inst_prev.time != dxy_prev.time:
        return None

    bearish = is_bearish_sweep(inst_curr, inst_prev, dxy_curr, dxy_prev, invert_dxy_scale=invert_dxy_scale)
    bullish = is_bullish_sweep(inst_curr, inst_prev, dxy_curr, dxy_prev, invert_dxy_scale=invert_dxy_scale)

    if bearish and bullish:
        return None

    if bearish:
        return SweepSignal(
            instrument=instrument_name,
            direction="BEARISH",
            candle_time_utc=inst_curr.time,
            dxy_previous_high=dxy_prev.high,
            dxy_previous_low=dxy_prev.low,
            dxy_signal_high=dxy_curr.high,
            dxy_signal_low=dxy_curr.low,
            instrument_previous_high=inst_prev.high,
            instrument_previous_low=inst_prev.low,
            instrument_signal_high=inst_curr.high,
            instrument_signal_low=inst_curr.low,
            condition="DXY current high > previous high and instrument current high <= previous high",
        )

    if bullish:
        return SweepSignal(
            instrument=instrument_name,
            direction="BULLISH",
            candle_time_utc=inst_curr.time,
            dxy_previous_high=dxy_prev.high,
            dxy_previous_low=dxy_prev.low,
            dxy_signal_high=dxy_curr.high,
            dxy_signal_low=dxy_curr.low,
            instrument_previous_high=inst_prev.high,
            instrument_previous_low=inst_prev.low,
            instrument_signal_high=inst_curr.high,
            instrument_signal_low=inst_curr.low,
            condition="DXY current low < previous low and instrument current low >= previous low",
        )

    return None
