"""Scanner + data-provider tests. Everything runs offline (no network)."""

import pandas as pd
import pytest

import jadentradebot.scanner as scanner_mod
from jadentradebot.data import (
    _standardize,
    _stooq_symbol,
    fetch_daily,
    sample_daily,
    validate_symbol,
)
from jadentradebot.scanner import DEFAULT_WATCHLIST, scan, scan_symbol


class TestValidateSymbol:
    def test_accepts_real_world_symbols(self):
        for raw, expected in [
            ("aapl", "AAPL"), (" spy ", "SPY"), ("brk.b", "BRK.B"),
            ("bf-b", "BF-B"), ("^gspc", "^GSPC"), ("es=f", "ES=F"),
        ]:
            assert validate_symbol(raw) == expected

    def test_rejects_injection_and_garbage(self):
        for bad in ["", "  ", "<script>", "AAPL;rm", "a" * 20, "../etc", "A B"]:
            with pytest.raises(ValueError, match="invalid ticker"):
                validate_symbol(bad)

    def test_fetch_daily_rejects_bad_symbol(self):
        with pytest.raises(ValueError, match="invalid ticker"):
            fetch_daily("<img src=x>", source="offline")


class TestSampleData:
    def test_deterministic(self):
        a = sample_daily("AAPL", end=pd.Timestamp("2026-07-15").date())
        b = sample_daily("AAPL", end=pd.Timestamp("2026-07-15").date())
        pd.testing.assert_frame_equal(a, b)

    def test_ohlc_invariants(self):
        df = sample_daily("TSLA")
        assert (df["high"] >= df[["open", "close"]].max(axis=1) - 1e-9).all()
        assert (df["low"] <= df[["open", "close"]].min(axis=1) + 1e-9).all()
        assert (df["low"] > 0).all()

    def test_unknown_symbol_works(self):
        df = sample_daily("ZZZZTEST")
        assert len(df) > 60
        assert set(df.columns) == {"open", "high", "low", "close", "volume"}

    def test_known_profile_price_level(self):
        df = sample_daily("AAPL")
        assert df["close"].iloc[-1] == pytest.approx(210.0)

    def test_tiny_lookback_still_yields_two_bars(self):
        assert len(sample_daily("AAPL", lookback_days=1)) >= 2


class TestStandardize:
    def test_multiindex_columns_flattened(self):
        idx = pd.date_range("2026-01-05", periods=3)
        cols = pd.MultiIndex.from_product([["Open", "High", "Low", "Close"], ["AAPL"]])
        df = pd.DataFrame(
            [[1, 2, 0.5, 1.5], [1, 2, 0.5, 1.5], [1, 2, 0.5, 1.5]],
            index=idx, columns=cols,
        )
        out = _standardize(df, "AAPL")
        assert list(out.columns) == ["open", "high", "low", "close", "volume"]
        assert len(out) == 3

    def test_empty_raises(self):
        with pytest.raises(LookupError):
            _standardize(pd.DataFrame(), "X")

    def test_duplicate_dates_keep_last(self):
        idx = pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-06"])
        df = pd.DataFrame(
            {"open": [1, 2, 3], "high": [2, 3, 4], "low": [0.5, 1, 2],
             "close": [1.5, 2.5, 3.5]},
            index=idx,
        )
        out = _standardize(df, "DUP")
        assert len(out) == 2
        assert out["close"].iloc[-1] == 3.5

    def test_stooq_symbol_mapping(self):
        assert _stooq_symbol("AAPL") == "aapl.us"
        assert _stooq_symbol("BRK.B") == "brk-b.us"
        assert _stooq_symbol("AAPL.US") == "aapl.us"
        assert _stooq_symbol("BF-B") == "bf-b.us"
        assert _stooq_symbol("^GSPC") == "^gspc"      # indices: no .us suffix
        assert _stooq_symbol("EURUSD=X") == "eurusd"  # FX: strip Yahoo's =X

    def test_unknown_source_rejected(self):
        with pytest.raises(ValueError, match="unknown source"):
            fetch_daily("AAPL", source="bloomberg")


class TestScanner:
    def test_offline_scan_default_watchlist(self):
        rows = scan(source="offline")
        assert [r.symbol for r in rows if r.ok]  # everything resolves offline
        assert len(rows) == len(DEFAULT_WATCHLIST)
        for row in rows:
            assert row.ok, row.error
            assert row.result.status.value in ("GREEN", "ORANGE", "RED")
            assert row.result.atr > 0

    def test_sorted_green_first_then_by_pct(self):
        rows = [r for r in scan(source="offline") if r.ok]
        order = {"GREEN": 0, "ORANGE": 1, "RED": 2}
        keys = [(order[r.result.status.value], r.result.dtr_pct) for r in rows]
        assert keys == sorted(keys)

    def test_dedupes_and_uppercases(self):
        rows = scan(["aapl", "AAPL", " aapl "], source="offline")
        assert [r.symbol for r in rows] == ["AAPL"]

    def test_empty_watchlist(self):
        assert scan([" ", ""], source="offline") == []

    def test_failed_symbol_sorts_last(self, monkeypatch):
        real_fetch = scanner_mod.fetch_daily

        def flaky(symbol, **kwargs):
            if symbol == "BAD":
                raise LookupError("BAD: no data")
            return real_fetch(symbol, **kwargs)

        monkeypatch.setattr(scanner_mod, "fetch_daily", flaky)
        rows = scan(["BAD", "AAPL"], source="offline")
        assert rows[-1].symbol == "BAD" and not rows[-1].ok
        assert "no data" in rows[-1].error
        assert rows[0].symbol == "AAPL" and rows[0].ok

    def test_max_workers_clamped(self):
        rows = scan(["AAPL", "TSLA"], source="offline", max_workers=0)
        assert all(r.ok for r in rows)

    def test_atr_length_changes_result(self):
        short = scan_symbol("TSLA", atr_length=2, source="offline")
        long = scan_symbol("TSLA", atr_length=50, source="offline")
        assert short.ok and long.ok
        assert short.result.atr != pytest.approx(long.result.atr)

    def test_scan_symbol_keep_series(self):
        row = scan_symbol("NVDA", source="offline", keep_series=True)
        assert row.ok
        series = row.result.series
        assert series is not None
        assert {"atr", "dtr", "dtr_pct", "status"} <= set(series.columns)
        # The last series row must agree with the headline result.
        assert float(series["atr"].iloc[-1]) == pytest.approx(row.result.atr)
