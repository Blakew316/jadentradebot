"""Tests for the ThinkScript built-in ports — validated against hand-computed
values and independent reference implementations."""

import math

import pandas as pd
import pytest

from jadentradebot.thinkscript import (
    highest,
    lowest,
    true_range,
    ts_round,
    wilders_average,
)


def s(*vals):
    return pd.Series(list(vals), dtype=float)


class TestTrueRange:
    def test_first_bar_is_plain_range(self):
        tr = true_range(s(10), s(9), s(8))
        assert tr.iloc[0] == pytest.approx(2.0)

    def test_inside_day_uses_high_low(self):
        # prev close 9 sits inside today's 8..10 range -> TR = 2
        tr = true_range(s(10, 10), s(9, 9), s(8, 8))
        assert tr.iloc[1] == pytest.approx(2.0)

    def test_gap_up_uses_high_minus_prev_close(self):
        # prev close 5, today 8..10 -> TR = max(2, 10-5, 5-8) = 5
        tr = true_range(s(10, 10), s(5, 9), s(8, 8))
        assert tr.iloc[1] == pytest.approx(5.0)

    def test_gap_down_uses_prev_close_minus_low(self):
        # prev close 15, today 8..10 -> TR = max(2, |10-15|, 15-8) = 7
        tr = true_range(s(10, 10), s(15, 9), s(8, 8))
        assert tr.iloc[1] == pytest.approx(7.0)

    def test_matches_max_min_formulation(self):
        # TR == max(high, close[1]) - min(low, close[1]) on every bar
        high, close, low = s(10, 12, 9, 20), s(9, 11, 8.5, 19), s(8, 10.5, 8, 15)
        tr = true_range(high, close, low)
        for i in range(1, len(high)):
            expected = max(high[i], close[i - 1]) - min(low[i], close[i - 1])
            assert tr.iloc[i] == pytest.approx(expected)


class TestWildersAverage:
    def test_matches_recursive_definition(self):
        vals = [3.0, 5.0, 4.0, 8.0, 2.0, 6.0, 7.0, 1.0]
        n = 4
        wa = wilders_average(pd.Series(vals), n)
        ref = vals[0]
        assert wa.iloc[0] == pytest.approx(ref)
        for i in range(1, len(vals)):
            ref = ref + (vals[i] - ref) / n
            assert wa.iloc[i] == pytest.approx(ref, abs=1e-12)

    def test_constant_series_is_identity(self):
        wa = wilders_average(s(4, 4, 4, 4, 4), 14)
        assert (wa == 4.0).all()

    def test_length_one_tracks_data(self):
        vals = s(1, 9, 4)
        assert wilders_average(vals, 1).tolist() == vals.tolist()

    def test_invalid_length(self):
        with pytest.raises(ValueError):
            wilders_average(s(1, 2), 0)


class TestHighestLowest:
    def test_length_one_is_current_bar(self):
        vals = s(5, 3, 9)
        assert highest(vals, 1).tolist() == vals.tolist()
        assert lowest(vals, 1).tolist() == vals.tolist()

    def test_rolling_window(self):
        vals = s(5, 3, 9, 2)
        assert highest(vals, 2).tolist() == [5, 5, 9, 9]
        assert lowest(vals, 2).tolist() == [5, 3, 3, 2]

    def test_invalid_length(self):
        with pytest.raises(ValueError):
            highest(s(1), 0)
        with pytest.raises(ValueError):
            lowest(s(1), 0)


class TestTsRound:
    """ThinkScript Round() rounds halves away from zero, unlike Python round()."""

    def test_half_up(self):
        assert ts_round(0.5) == 1.0
        assert ts_round(1.5) == 2.0
        assert ts_round(2.5) == 3.0  # Python round(2.5) == 2

    def test_half_away_from_zero_negative(self):
        assert ts_round(-0.5) == -1.0
        assert ts_round(-2.5) == -3.0

    def test_two_digits(self):
        assert ts_round(2.675, 2) == 2.68  # Python round(2.675, 2) == 2.67
        assert ts_round(1.234, 2) == 1.23

    def test_threshold_cases_from_indicator(self):
        assert ts_round(70.4) == 70.0   # still GREEN after rounding
        assert ts_round(70.5) == 71.0   # ORANGE
        assert ts_round(89.4) == 89.0   # still ORANGE
        assert ts_round(89.5) == 90.0   # RED

    def test_nan_passthrough(self):
        assert math.isnan(ts_round(float("nan")))
