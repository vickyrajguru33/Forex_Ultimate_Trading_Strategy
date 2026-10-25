from datetime import datetime, timedelta

from candle_validation import Candle, is_bearish_sweep, is_bullish_sweep, validate_consecutive_m15


def _bar(ts: datetime, o: float, h: float, l: float, c: float) -> Candle:
    return Candle(time=ts, open=o, high=h, low=l, close=c)


def test_valid_bearish_setup():
    current_time = datetime(2024, 1, 1, 10, 0)
    previous_time = datetime(2024, 1, 1, 9, 45)
    dxy_current = _bar(current_time, 100, 101, 99, 100)
    dxy_previous = _bar(previous_time, 99, 100, 98, 99)
    instrument_current = _bar(current_time, 1.095, 1.096, 1.092, 1.093)
    instrument_previous = _bar(previous_time, 1.097, 1.098, 1.091, 1.094)
    assert is_bearish_sweep(instrument_current, instrument_previous, dxy_current, dxy_previous, invert_dxy_scale=False)


def test_valid_bullish_setup():
    current_time = datetime(2024, 1, 1, 10, 0)
    previous_time = datetime(2024, 1, 1, 9, 45)
    dxy_current = _bar(current_time, 100, 101, 99, 100)
    dxy_previous = _bar(previous_time, 100, 101, 100, 101)
    instrument_current = _bar(current_time, 1.096, 1.098, 1.094, 1.097)
    instrument_previous = _bar(previous_time, 1.095, 1.097, 1.092, 1.094)
    assert is_bullish_sweep(instrument_current, instrument_previous, dxy_current, dxy_previous, invert_dxy_scale=False)


def test_dxy_high_equality_does_not_trigger_bearish_sweep():
    current_time = datetime(2024, 1, 1, 10, 0)
    previous_time = datetime(2024, 1, 1, 9, 45)
    dxy_current = _bar(current_time, 100, 100, 99, 100)
    dxy_previous = _bar(previous_time, 99, 100, 98, 99)
    instrument_current = _bar(current_time, 1.095, 1.096, 1.092, 1.093)
    instrument_previous = _bar(previous_time, 1.097, 1.098, 1.091, 1.094)
    assert not is_bearish_sweep(instrument_current, instrument_previous, dxy_current, dxy_previous, invert_dxy_scale=False)


def test_dxy_low_equality_does_not_trigger_bullish_sweep():
    current_time = datetime(2024, 1, 1, 10, 0)
    previous_time = datetime(2024, 1, 1, 9, 45)
    dxy_current = _bar(current_time, 100, 101, 100, 101)
    dxy_previous = _bar(previous_time, 99, 100, 98, 99)
    instrument_current = _bar(current_time, 1.096, 1.098, 1.094, 1.097)
    instrument_previous = _bar(previous_time, 1.095, 1.097, 1.092, 1.094)
    assert not is_bullish_sweep(instrument_current, instrument_previous, dxy_current, dxy_previous, invert_dxy_scale=False)


def test_instrument_breaks_previous_high_bearish_condition_fails():
    current_time = datetime(2024, 1, 1, 10, 0)
    previous_time = datetime(2024, 1, 1, 9, 45)
    dxy_current = _bar(current_time, 100, 101, 99, 100)
    dxy_previous = _bar(previous_time, 99, 100, 98, 99)
    instrument_current = _bar(current_time, 1.099, 1.101, 1.093, 1.095)
    instrument_previous = _bar(previous_time, 1.097, 1.098, 1.091, 1.094)
    assert not is_bearish_sweep(instrument_current, instrument_previous, dxy_current, dxy_previous, invert_dxy_scale=False)


def test_instrument_breaks_previous_low_bullish_condition_fails():
    current_time = datetime(2024, 1, 1, 10, 0)
    previous_time = datetime(2024, 1, 1, 9, 45)
    dxy_current = _bar(current_time, 100, 101, 99, 100)
    dxy_previous = _bar(previous_time, 100, 101, 100, 101)
    instrument_current = _bar(current_time, 1.091, 1.093, 1.089, 1.092)
    instrument_previous = _bar(previous_time, 1.095, 1.097, 1.092, 1.094)
    assert not is_bullish_sweep(instrument_current, instrument_previous, dxy_current, dxy_previous, invert_dxy_scale=False)


def test_forming_candle_exclusion():
    current_time = datetime(2024, 1, 1, 10, 0)
    previous_time = datetime(2024, 1, 1, 9, 45)
    dxy_current = _bar(current_time, 100, 101, 99, 100)
    dxy_previous = _bar(previous_time, 99, 100, 98, 99)
    instrument_current = _bar(current_time + timedelta(minutes=5), 1.095, 1.096, 1.092, 1.093)
    instrument_previous = _bar(previous_time, 1.097, 1.098, 1.091, 1.094)
    assert not is_bearish_sweep(instrument_current, instrument_previous, dxy_current, dxy_previous, invert_dxy_scale=False)


def test_mismatched_timestamps_rejected():
    current_time = datetime(2024, 1, 1, 10, 0)
    previous_time = datetime(2024, 1, 1, 9, 45)
    dxy_current = _bar(current_time, 100, 101, 99, 100)
    dxy_previous = _bar(previous_time, 99, 100, 98, 99)
    instrument_current = _bar(current_time + timedelta(minutes=15), 1.095, 1.096, 1.092, 1.093)
    instrument_previous = _bar(previous_time, 1.097, 1.098, 1.091, 1.094)
    assert not is_bearish_sweep(instrument_current, instrument_previous, dxy_current, dxy_previous, invert_dxy_scale=False)


def test_nonconsecutive_bars_rejected():
    current_time = datetime(2024, 1, 1, 10, 0)
    previous_time = datetime(2024, 1, 1, 9, 30)
    dxy_current = _bar(current_time, 100, 101, 99, 100)
    dxy_previous = _bar(previous_time, 99, 100, 98, 99)
    instrument_current = _bar(current_time, 1.095, 1.096, 1.092, 1.093)
    instrument_previous = _bar(previous_time, 1.097, 1.098, 1.091, 1.094)
    assert not is_bearish_sweep(instrument_current, instrument_previous, dxy_current, dxy_previous, invert_dxy_scale=False)


def test_validate_consecutive_m15():
    t1 = datetime(2024, 1, 1, 9, 45)
    t2 = datetime(2024, 1, 1, 10, 0)
    assert validate_consecutive_m15(_bar(t2, 1, 2, 0.5, 1.5), _bar(t1, 1, 2, 0.5, 1.5))
