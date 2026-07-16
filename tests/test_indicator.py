"""End-to-end tests of the DTR vs ATR port against an independent reference
implementation, plus the exact colour/label semantics of the original script."""

import numpy as np
import pandas as pd
import pytest

from jadentradebot.indicator import (
    DtrVsAtrResult,
    Status,
    classify,
    compute_series,
    dtr_vs_atr,
)
from jadentradebot.thinkscript import ts_round


def make_daily(highs, lows, closes, opens=None):
    idx = pd.bdate_range("2026-01-05", periods=len(highs))
    frame = {
        "high": list(map(float, highs)),
        "low": list(map(float, lows)),
        "close": list(map(float, closes)),
    }
    if opens is not None:
        frame["open"] = list(map(float, opens))
    return pd.DataFrame(frame, index=idx)


def reference_dtr_vs_atr(highs, lows, closes, length):
    """Straight-line reimplementation of the ThinkScript, bar by bar."""
    trs = []
    for i in range(len(highs)):
        if i == 0:
            trs.append(highs[0] - lows[0])
        else:
            trs.append(max(highs[i], closes[i - 1]) - min(lows[i], closes[i - 1]))
    atr = trs[0]
    for tr in trs[1:]:
        atr = atr + (tr - atr) / length
    dtr = highs[-1] - lows[-1]
    pct = ts_round(dtr / atr * 100, 0)
    return atr, dtr, pct


class TestClassify:
    def test_thresholds_match_the_script(self):
        # if DTRpct <= 70 then GREEN else if DTRpct >= 90 then RED else ORANGE
        assert classify(0) is Status.GREEN
        assert classify(70) is Status.GREEN
        assert classify(71) is Status.ORANGE
        assert classify(89) is Status.ORANGE
        assert classify(90) is Status.RED
        assert classify(150) is Status.RED


class TestDtrVsAtr:
    def test_matches_reference_implementation(self):
        rng = np.random.RandomState(7)
        closes = 100 + np.cumsum(rng.normal(0, 1.5, size=80))
        highs = closes + np.abs(rng.normal(0, 1.0, size=80)) + 0.2
        lows = closes - np.abs(rng.normal(0, 1.0, size=80)) - 0.2
        daily = make_daily(highs, lows, closes)

        for length in (5, 14, 21):
            res = dtr_vs_atr(daily, symbol="TEST", atr_length=length)
            ref_atr, ref_dtr, ref_pct = reference_dtr_vs_atr(
                list(highs), list(lows), list(closes), length
            )
            assert res.atr == pytest.approx(ref_atr, rel=1e-12)
            assert res.dtr == pytest.approx(ref_dtr, rel=1e-12)
            assert res.dtr_pct == ref_pct
            assert res.status is classify(ref_pct)

    def test_constant_bars_pct_100(self):
        # Identical 100..104 bars every day: TR = ATR = DTR = 4 -> 100% RED
        n = 50
        daily = make_daily([104] * n, [100] * n, [102] * n)
        res = dtr_vs_atr(daily, symbol="FLAT")
        assert res.atr == pytest.approx(4.0)
        assert res.dtr == pytest.approx(4.0)
        assert res.dtr_pct == 100.0
        assert res.status is Status.RED

    def test_narrow_final_day_goes_green(self):
        # 4-point range for 60 days, then a 1-point inside day.
        highs, lows, closes = [104.0] * 60, [100.0] * 60, [102.0] * 60
        highs[-1], lows[-1], closes[-1] = 102.5, 101.5, 102.0
        res = dtr_vs_atr(make_daily(highs, lows, closes), symbol="NARROW")
        # ATR after final bar: 4 + (1-4)/14 = 3.7857; 1/3.7857 = 26.4% -> 26%
        assert res.dtr_pct == 26.0
        assert res.status is Status.GREEN
        assert res.range_left == pytest.approx(res.atr - res.dtr)
        assert res.range_left_pct == pytest.approx(100 - 26.0)

    def test_rounding_happens_before_color_thresholds(self):
        # Engineer a final bar whose raw pct is just over 70 but rounds to 70:
        # constant TR=ATR=4 history, final DTR d gives raw pct = 100*d/(4+(d-4)/14).
        # d = 2.81 -> ATR = 3.915, raw = 71.78 -> 72 ORANGE
        # d = 2.75 -> ATR = 3.9107, raw = 70.32 -> 70 GREEN (raw > 70!)
        highs, lows, closes = [104.0] * 60, [100.0] * 60, [102.0] * 60
        highs[-1], lows[-1], closes[-1] = 102.0 + 2.75 / 2, 102.0 - 2.75 / 2, 102.0
        res = dtr_vs_atr(make_daily(highs, lows, closes), symbol="EDGE")
        raw_pct = res.dtr / res.atr * 100
        assert raw_pct > 70.0          # raw value is over the line...
        assert res.dtr_pct == 70.0     # ...but the script rounds first
        assert res.status is Status.GREEN

    def test_label_matches_script_format(self):
        n = 50
        daily = make_daily([104] * n, [100] * n, [102] * n)
        res = dtr_vs_atr(daily, symbol="FLAT")
        assert res.label == "DTR 4 vs ATR 4  100%"

    def test_atr_targets(self):
        n = 50
        daily = make_daily([104] * n, [100] * n, [102] * n)
        res = dtr_vs_atr(daily, symbol="FLAT")
        assert res.atr_buy_target == pytest.approx(100 + res.atr)
        assert res.atr_sell_target == pytest.approx(104 - res.atr)

    def test_requires_two_bars(self):
        with pytest.raises(ValueError, match="at least 2"):
            dtr_vs_atr(make_daily([10], [9], [9.5]), symbol="X")

    def test_missing_columns(self):
        df = pd.DataFrame({"high": [1, 2], "low": [0, 1]})
        with pytest.raises(ValueError, match="missing columns"):
            compute_series(df)

    def test_degenerate_flat_data(self):
        n = 30
        daily = make_daily([100] * n, [100] * n, [100] * n)
        with pytest.raises(ValueError, match="degenerate"):
            dtr_vs_atr(daily, symbol="DEAD")

    def test_case_insensitive_columns_and_series(self):
        n = 40
        idx = pd.bdate_range("2026-01-05", periods=n)
        daily = pd.DataFrame(
            {"High": [104.0] * n, "Low": [100.0] * n, "Close": [102.0] * n,
             "Open": [101.0] * n},
            index=idx,
        )
        res = dtr_vs_atr(daily, symbol="CASE", keep_series=True)
        assert isinstance(res, DtrVsAtrResult)
        assert res.series is not None
        assert "open" in res.series.columns
        assert list(res.series.columns[:3]) == ["high", "low", "close"]
        assert (res.series["status"] == "RED").all()
