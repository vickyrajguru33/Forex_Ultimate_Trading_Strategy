from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Iterable


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Candle:
    """
    A completed (closed) 15M OHLC bar.

    'frozen=True' means the values are locked once created — nobody can
    accidentally overwrite the open/close after the bar has closed.

    Fields
    ------
    time   : when this 15-minute bar opened
    open   : price at the very start of the bar
    high   : highest price reached during the bar (the top of the wick)
    low    : lowest price reached during the bar  (the bottom of the wick)
    close  : price at the very end of the bar
    volume : number of units traded (optional, defaults to 0)
    """
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int = 0

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Candle":
        """
        Build a Candle from a raw dictionary (e.g. from a broker API response).
        Raises ValueError if any of the five required fields are missing.
        """
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


@dataclass
class LiveCandle:
    """
    A candle that is still forming (not yet closed).

    Why this exists
    ---------------
    The sweep rules say: "a wick beyond the high/low is sufficient —
    a candle close is NOT required."  That means we must be able to
    detect the signal the moment a price tick crosses the level,
    mid-bar, before the 15M closes.

    A plain Candle represents a finished bar.  A LiveCandle updates
    its high/low on every incoming price tick so we can check the
    sweep condition in real time.

    Usage
    -----
        live = LiveCandle(time=bar_open, open=1.1000, high=1.1000,
                          low=1.1000, last=1.1000)

        # each new tick from your feed:
        live.update(price=1.1015)

        # check sweep condition mid-bar:
        if is_bearish_sweep(live_eurusd, prev_eurusd, live_dxy, prev_dxy):
            mark_level_and_move_to_1m()
    """
    time: datetime
    open: float
    high: float     # grows upward with each new tick high
    low: float      # shrinks downward with each new tick low
    last: float     # most recent traded price (replaces 'close' while live)
    volume: int = 0

    def update(self, price: float, volume: int = 0) -> None:
        """
        Feed a new tick price into the live candle.
        Updates high/low if the new price breaks outside the current range.
        """
        if price > self.high:
            self.high = price   # new wick high
        if price < self.low:
            self.low = price    # new wick low
        self.last = price
        self.volume += volume

    def to_candle(self) -> Candle:
        """
        Snapshot the live candle as a closed Candle.
        Used internally for timestamp validation — treat 'last' as the close.
        """
        return Candle(
            time=self.time,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.last,
            volume=self.volume,
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _coerce_datetime(value: Any) -> datetime:
    """
    Accept a datetime in any common format and return a naive UTC datetime.

    Handles:
      - datetime objects (returned as-is or stripped of timezone)
      - Unix timestamps as int or float
      - ISO 8601 strings like "2024-01-15T09:00:00Z"
    """
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        # Unix timestamp → UTC datetime
        return datetime.utcfromtimestamp(float(value))
    if isinstance(value, str):
        # Parse ISO string; strip timezone info to keep everything naive UTC
        candidate = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if candidate.tzinfo is not None:
            return candidate.astimezone().replace(tzinfo=None)
        return candidate
    raise TypeError(f"Unsupported datetime value: {value!r}")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_complete_bar(bar: Candle | dict[str, Any]) -> Candle:
    """
    Confirm that a bar's OHLC values are internally consistent.

    Checks performed
    ----------------
    1. No zero values — a zero in any OHLC field means the data feed
       sent broken/missing data (prices are never literally zero in forex).
    2. high >= low — physically impossible otherwise.
    3. open and close both sit within [low, high] — the body of the candle
       must be contained within its wicks.

    Returns the validated Candle, or raises ValueError on any violation.
    """
    candle = bar if isinstance(bar, Candle) else Candle.from_dict(bar)

    # Check each field individually — the original code only caught the case
    # where ALL four values were zero, silently passing a candle with one
    # zeroed field (e.g. open=0 while the rest were normal).
    if any(v == 0 for v in (candle.open, candle.high, candle.low, candle.close)):
        raise ValueError("Candle has invalid zeroed OHLC values")

    if candle.high < candle.low:
        raise ValueError("Candle high is lower than low")

    # The candle body (open & close) must be enclosed by the wicks (high & low).
    if candle.high < max(candle.open, candle.close) or candle.low > min(candle.open, candle.close):
        raise ValueError("Candle OHLC is internally inconsistent")

    return candle


def validate_consecutive_m15(current: Candle, previous: Candle) -> bool:
    """
    Return True only if 'current' is exactly 15 minutes after 'previous'.

    This enforces that we are comparing the right pair of bars — no gaps
    (missing bars), no overlaps, and time must move forward.

    Example
    -------
        prev    = Candle(time=09:00, ...)
        current = Candle(time=09:15, ...)  → True   ✅
        current = Candle(time=09:30, ...)  → False  ❌  (30-min gap)
        current = Candle(time=09:00, ...)  → False  ❌  (same time)
        current = Candle(time=08:45, ...)  → False  ❌  (going backwards)
    """
    # Time must move forward
    if current.time <= previous.time:
        return False

    # Gap must be exactly one 15-minute bar — no missing bars allowed
    if current.time - previous.time != timedelta(minutes=15):
        return False

    return True


def validate_pair_timestamp_match(
    current_a: Candle,
    previous_a: Candle,
    current_b: Candle,
    previous_b: Candle,
) -> bool:
    """
    Confirm that EUR/USD and DXY bars are perfectly time-aligned.

    The sweep rules compare EUR/USD and DXY on the SAME 15M bar.
    If the timestamps don't match, we'd be comparing apples to oranges —
    e.g. EUR/USD at 09:15 vs DXY at 09:30.

    Returns True only when:
      - current_a and current_b share the same timestamp  (same bar)
      - previous_a and previous_b share the same timestamp (same prev bar)
      - both pairs are valid consecutive M15 candles
    """
    return (
        current_a.time == current_b.time       # current bars are the same moment
        and previous_a.time == previous_b.time  # previous bars are the same moment
        and validate_consecutive_m15(current_a, previous_a)  # EUR/USD bars are 15 min apart
        and validate_consecutive_m15(current_b, previous_b)  # DXY bars are 15 min apart
    )


def validate_bar_series(bars: Iterable[dict[str, Any] | Candle]) -> list[Candle]:
    """
    Validate an entire sequence of bars as consecutive, clean M15 candles.

    Useful for validating a history download before feeding it into
    backtesting or signal replay.  Raises ValueError at the first gap
    or invalid bar found.
    """
    candles = [validate_complete_bar(bar) for bar in bars]
    for idx in range(1, len(candles)):
        if not validate_consecutive_m15(candles[idx], candles[idx - 1]):
            raise ValueError(f"Bars are not valid consecutive M15 candles at index {idx}")
    return candles


# ---------------------------------------------------------------------------
# DXY inversion
# ---------------------------------------------------------------------------

def invert_dxy(candle: Candle | LiveCandle) -> Candle | LiveCandle:
    """
    Invert a DXY candle so it moves in the SAME direction as EUR/USD.

    Why inversion is always required
    ---------------------------------
    DXY measures US dollar strength.  EUR/USD and DXY move in OPPOSITE
    directions by nature:
      - Dollar strengthens  →  DXY rises,   EUR/USD falls
      - Dollar weakens      →  DXY falls,   EUR/USD rises

    To compare them on the same chart (as per the setup — DXY on the right,
    EUR/USD on the left), we flip DXY using the reciprocal  1 / price.
    After inversion, both charts move in the same direction and we can
    read the sweep divergence directly.

    Reciprocal inversion maths
    --------------------------
    If DXY high = 104.5 and DXY low = 103.5:
        inverted high = 1 / 103.5 = 0.009662   ← old LOW becomes new HIGH
        inverted low  = 1 / 104.5 = 0.009569   ← old HIGH becomes new LOW

    This preserves the rule that high >= low, because:
        1/low >= 1/high  when  low <= high  ✅

    The original code swapped open↔close and high↔low without taking
    reciprocals, producing candles where high < low — breaking all
    downstream OHLC consistency checks.
    """
    if isinstance(candle, LiveCandle):
        # Invert the live candle in-place style by returning a new LiveCandle.
        # Note: high and low are swapped (reciprocal) for the same reason as Candle.
        return LiveCandle(
            time=candle.time,
            open=1.0 / candle.open,
            high=1.0 / candle.low,   # reciprocal of low  → new high
            low=1.0 / candle.high,   # reciprocal of high → new low
            last=1.0 / candle.last,
            volume=candle.volume,
        )

    # Closed Candle path
    return Candle(
        time=candle.time,
        open=1.0 / candle.open,
        high=1.0 / candle.low,   # reciprocal of low  → new high
        low=1.0 / candle.high,   # reciprocal of high → new low
        close=1.0 / candle.close,
        volume=candle.volume,
    )


# ---------------------------------------------------------------------------
# Sweep detection  (Section 10.1 / 10.2)
# ---------------------------------------------------------------------------

def is_bearish_sweep(
    instrument_current: Candle | LiveCandle,
    instrument_previous: Candle,
    dxy_current: Candle | LiveCandle,
    dxy_previous: Candle,
) -> bool:
    """
    Detect a bearish sweep — Section 10.1.

    Setup (both conditions must be true at the same moment on the 15M):
    ─────────────────────────────────────────────────────────────────────
    Condition 1 — DXY (inverted) makes a new HIGH:
        The inverted DXY current wick trades STRICTLY above the inverted
        DXY previous high.  On the raw DXY chart this means DXY made a
        new low (dollar strengthening), which on the inverted chart reads
        as a new high.
        → "Merely touching the level does not count."

    Condition 2 — EUR/USD does NOT make a new HIGH:
        The EUR/USD current wick stays STRICTLY below the previous high.
        If EUR/USD exactly touches the previous high that is NOT a sweep.
        → "Merely touching the level does not count."

    Divergence logic
    ----------------
    DXY broke higher (dollar strengthened)  BUT  EUR/USD couldn't follow
    through to a new high.  That failure to push up is the bearish signal —
    smart money swept the highs on DXY while EUR/USD stalled.

    After confirmation → mark the previous EUR/USD high with a horizontal
    line and move to the 1M chart to look for an entry pattern.

    LiveCandle support
    ------------------
    Pass a LiveCandle for instrument_current and/or dxy_current to detect
    the signal mid-bar the moment a wick crosses the level, without
    waiting for the 15M bar to close.
    """
    # --- Step 1: resolve live candles to snapshots for timestamp checks ---
    # to_candle() treats 'last' as the close — only used for time validation,
    # not for the actual high/low comparison below.
    curr_inst_snap = instrument_current.to_candle() if isinstance(instrument_current, LiveCandle) else instrument_current
    curr_dxy_snap  = dxy_current.to_candle()        if isinstance(dxy_current,        LiveCandle) else dxy_current

    # --- Step 2: ensure both charts are on the exact same 15M bar ---
    if not validate_pair_timestamp_match(
        curr_inst_snap, instrument_previous,
        curr_dxy_snap,  dxy_previous,
    ):
        return False

    # --- Step 3: invert DXY so it moves in the same direction as EUR/USD ---
    # DXY is ALWAYS inverted — this is a fixed requirement of the setup,
    # not an option.  See invert_dxy() for the full explanation.
    dxy_current_inv  = invert_dxy(dxy_current)
    dxy_previous_inv = invert_dxy(dxy_previous)

    # --- Step 4: check both sweep conditions ---
    #
    # Condition 1: inverted DXY current wick is STRICTLY above inverted DXY previous high.
    #   On the raw DXY chart: current DXY made a new LOW (dollar strength).
    #   On the inverted chart we see this as a new HIGH — easier to compare with EUR/USD.
    dxy_swept_high = dxy_current_inv.high > dxy_previous_inv.high

    # Condition 2: EUR/USD current wick is STRICTLY BELOW previous EUR/USD high.
    #   EUR/USD failed to make a new high while DXY (inverted) did → divergence.
    #   Strict less-than (<) because "merely touching does not count."
    instrument_held = instrument_current.high < instrument_previous.high

    return dxy_swept_high and instrument_held


def is_bullish_sweep(
    instrument_current: Candle | LiveCandle,
    instrument_previous: Candle,
    dxy_current: Candle | LiveCandle,
    dxy_previous: Candle,
) -> bool:
    """
    Detect a bullish sweep — Section 10.2.

    Setup (both conditions must be true at the same moment on the 15M):
    ─────────────────────────────────────────────────────────────────────
    Condition 1 — DXY (inverted) makes a new LOW:
        The inverted DXY current wick trades STRICTLY below the inverted
        DXY previous low.  On the raw DXY chart this means DXY made a
        new high (dollar weakening flipped), which on the inverted chart
        reads as a new low.
        → "Merely touching the level does not count."

    Condition 2 — EUR/USD does NOT make a new LOW:
        The EUR/USD current wick stays STRICTLY above the previous low.
        If EUR/USD exactly touches the previous low that is NOT a sweep.
        → "Merely touching the level does not count."

    Divergence logic
    ----------------
    DXY broke lower (dollar weakened)  BUT  EUR/USD didn't follow through
    to a new low.  That refusal to drop is the bullish signal — smart money
    swept the lows on DXY while EUR/USD held up.

    After confirmation → mark the previous EUR/USD low with a horizontal
    line and move to the 1M chart to look for an entry pattern.

    LiveCandle support
    ------------------
    Same as is_bearish_sweep — pass LiveCandle for real-time mid-bar detection.
    """
    # --- Step 1: resolve live candles to snapshots for timestamp checks ---
    curr_inst_snap = instrument_current.to_candle() if isinstance(instrument_current, LiveCandle) else instrument_current
    curr_dxy_snap  = dxy_current.to_candle()        if isinstance(dxy_current,        LiveCandle) else dxy_current

    # --- Step 2: ensure both charts are on the exact same 15M bar ---
    if not validate_pair_timestamp_match(
        curr_inst_snap, instrument_previous,
        curr_dxy_snap,  dxy_previous,
    ):
        return False

    # --- Step 3: invert DXY — always required, not optional ---
    dxy_current_inv  = invert_dxy(dxy_current)
    dxy_previous_inv = invert_dxy(dxy_previous)

    # --- Step 4: check both sweep conditions ---
    #
    # Condition 1: inverted DXY current wick is STRICTLY below inverted DXY previous low.
    #   On the raw DXY chart: current DXY made a new HIGH (dollar weakened).
    #   On the inverted chart this shows as a new LOW — readable alongside EUR/USD.
    dxy_swept_low = dxy_current_inv.low < dxy_previous_inv.low

    # Condition 2: EUR/USD current wick is STRICTLY ABOVE previous EUR/USD low.
    #   EUR/USD held its low while DXY (inverted) made a new low → divergence.
    #   Strict greater-than (>) because "merely touching does not count."
    instrument_held = instrument_current.low > instrument_previous.low

    return dxy_swept_low and instrument_held