from datetime import datetime

from sweep_detector import detect_sweep_signal


def _bar(ts: datetime, o: float, h: float, l: float, c: float) -> dict:
    return {"time": ts, "open": o, "high": h, "low": l, "close": c}


def test_detects_bearish_and_bullish_independently():
    current_time = datetime(2024, 1, 1, 10, 0)
    previous_time = datetime(2024, 1, 1, 9, 45)
    dxy_current = _bar(current_time, 100, 101, 99, 100)
    dxy_previous = _bar(previous_time, 99, 100, 98, 99)
    instrument_current = _bar(current_time, 1.095, 1.096, 1.092, 1.093)
    instrument_previous = _bar(previous_time, 1.097, 1.098, 1.091, 1.094)
    signal = detect_sweep_signal("EURUSD", instrument_current, instrument_previous, dxy_current, dxy_previous, invert_dxy_scale=False)
    assert signal is not None and signal.direction == "BEARISH"

    dxy_current2 = _bar(current_time, 100, 101, 99, 100)
    dxy_previous2 = _bar(previous_time, 100, 101, 100, 101)
    instrument_current2 = _bar(current_time, 1.096, 1.098, 1.094, 1.097)
    instrument_previous2 = _bar(previous_time, 1.095, 1.097, 1.092, 1.094)
    signal2 = detect_sweep_signal("GBPUSD", instrument_current2, instrument_previous2, dxy_current2, dxy_previous2, invert_dxy_scale=False)
    assert signal2 is not None and signal2.direction == "BULLISH"


def test_forming_candle_excluded_in_detector():
    current_time = datetime(2024, 1, 1, 10, 0)
    previous_time = datetime(2024, 1, 1, 9, 45)
    dxy_current = _bar(current_time, 100, 101, 99, 100)
    dxy_previous = _bar(previous_time, 99, 100, 98, 99)
    instrument_current = _bar(current_time + __import__('datetime').timedelta(minutes=5), 1.095, 1.096, 1.092, 1.093)
    instrument_previous = _bar(previous_time, 1.097, 1.098, 1.091, 1.094)
    assert detect_sweep_signal("EURUSD", instrument_current, instrument_previous, dxy_current, dxy_previous, invert_dxy_scale=False) is None


def test_mismatched_symbol_timestamps_rejected():
    current_time = datetime(2024, 1, 1, 10, 0)
    previous_time = datetime(2024, 1, 1, 9, 45)
    dxy_current = _bar(current_time, 100, 101, 99, 100)
    dxy_previous = _bar(previous_time, 99, 100, 98, 99)
    instrument_current = _bar(current_time + __import__('datetime').timedelta(minutes=15), 1.095, 1.096, 1.092, 1.093)
    instrument_previous = _bar(previous_time, 1.097, 1.098, 1.091, 1.094)
    assert detect_sweep_signal("EURUSD", instrument_current, instrument_previous, dxy_current, dxy_previous, invert_dxy_scale=False) is None
