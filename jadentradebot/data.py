"""Daily OHLCV data providers.

``fetch_daily`` is the single entry point. Sources:

- ``yfinance`` — Yahoo Finance via the yfinance package (primary live source).
- ``stooq``    — stooq.com free daily CSV endpoint (live fallback).
- ``offline``  — deterministic synthetic data, so the scanner, dashboard and
  tests all work with no network (and in CI sandboxes).
- ``auto``     — yfinance, then stooq, then a clear error.

All providers return a DataFrame with columns
``open, high, low, close, volume`` indexed by ascending date, covering roughly
``lookback_days`` calendar days — enough history to warm up Wilder's ATR.
"""

from __future__ import annotations

import hashlib
import io
import logging
import re
from datetime import date, timedelta

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# Real-world tickers: letters/digits plus Yahoo's ^ (indices), = (futures/FX),
# and . / - class suffixes. Also keeps garbage out of provider URLs and HTML.
_SYMBOL_RE = re.compile(r"^[A-Z0-9^][A-Z0-9.\-^=]{0,14}$")


def validate_symbol(symbol: str) -> str:
    """Uppercase, trim, and validate a ticker symbol; raises ValueError."""
    sym = (symbol or "").strip().upper()
    if not _SYMBOL_RE.match(sym):
        raise ValueError(f"invalid ticker symbol: {symbol!r}")
    return sym

DEFAULT_LOOKBACK_DAYS = 180  # ~125 trading days; ATR(14) is fully warmed up.

_STANDARD_COLS = ["open", "high", "low", "close", "volume"]

# Plausible price/volatility profiles for well-known tickers so the offline
# demo looks realistic. Anything else gets a profile derived from its name.
_SAMPLE_PROFILES = {
    "AAPL": (210.0, 0.015),
    "MSFT": (500.0, 0.013),
    "NVDA": (170.0, 0.028),
    "TSLA": (320.0, 0.035),
    "AMZN": (220.0, 0.018),
    "META": (700.0, 0.020),
    "GOOGL": (180.0, 0.016),
    "AMD": (160.0, 0.030),
    "SPY": (620.0, 0.008),
    "QQQ": (555.0, 0.010),
    "NFLX": (1250.0, 0.022),
    "COIN": (350.0, 0.045),
}


def _standardize(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Normalize provider output to lowercase OHLCV columns, ascending dates."""
    if df is None or df.empty:
        raise LookupError(f"{symbol}: provider returned no data")
    # yfinance can return MultiIndex columns like ('Close', 'AAPL').
    if isinstance(df.columns, pd.MultiIndex):
        df = df.copy()
        df.columns = [c[0] for c in df.columns]
    df = df.rename(columns={c: str(c).strip().lower() for c in df.columns})
    missing = [c for c in ("open", "high", "low", "close") if c not in df.columns]
    if missing:
        raise LookupError(f"{symbol}: data is missing columns {missing}")
    if "volume" not in df.columns:
        df["volume"] = 0
    out = df[_STANDARD_COLS].copy()
    out.index = pd.to_datetime(out.index)
    if out.index.tz is not None:
        out.index = out.index.tz_localize(None)
    out.index.name = "date"
    out = out.sort_index()
    # Providers occasionally duplicate the latest bar; keep the freshest copy.
    out = out[~out.index.duplicated(keep="last")]
    out = out.dropna(subset=["open", "high", "low", "close"])
    if out.empty:
        raise LookupError(f"{symbol}: no usable rows after cleaning")
    return out


def fetch_yfinance(symbol: str, lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> pd.DataFrame:
    import yfinance as yf

    start = date.today() - timedelta(days=lookback_days)
    df = yf.download(
        symbol,
        start=start.isoformat(),
        interval="1d",
        auto_adjust=False,
        progress=False,
        threads=False,
    )
    return _standardize(df, symbol)


_STOOQ_MARKET_SUFFIX = re.compile(r"\.(us|uk|de|jp|hk|hu|pl|fr|it)$")


def _stooq_symbol(symbol: str) -> str:
    """Map a ticker to stooq's naming: AAPL -> aapl.us, BRK.B -> brk-b.us;
    an explicit market suffix like AAPL.US is honoured as-is."""
    sym = symbol.lower()
    if _STOOQ_MARKET_SUFFIX.search(sym):
        return sym
    return sym.replace(".", "-") + ".us"


def fetch_stooq(symbol: str, lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> pd.DataFrame:
    """stooq.com free daily CSV endpoint."""
    import urllib.parse
    import urllib.request

    sym = urllib.parse.quote(_stooq_symbol(symbol))
    url = f"https://stooq.com/q/d/l/?s={sym}&i=d"
    with urllib.request.urlopen(url, timeout=30) as resp:
        text = resp.read().decode("utf-8", errors="replace")
    if not text.lstrip().lower().startswith("date"):
        raise LookupError(f"{symbol}: stooq returned no data")
    df = pd.read_csv(io.StringIO(text), parse_dates=["Date"], index_col="Date")
    df = _standardize(df, symbol)
    cutoff = pd.Timestamp(date.today() - timedelta(days=lookback_days))
    df = df.loc[df.index >= cutoff]
    if len(df) < 2:
        raise LookupError(f"{symbol}: stooq has no recent bars")
    return df


def sample_daily(
    symbol: str,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    end: date | None = None,
) -> pd.DataFrame:
    """Deterministic synthetic daily OHLCV — a seeded geometric random walk.

    The same symbol always produces the same series, so tests and demos are
    reproducible. Known tickers get realistic price levels; unknown tickers
    get a profile derived from the symbol name.
    """
    symbol = symbol.upper()
    base_price, daily_vol = _SAMPLE_PROFILES.get(
        symbol,
        (
            20.0 + (int(hashlib.md5(symbol.encode()).hexdigest(), 16) % 480),
            0.012 + (int(hashlib.sha1(symbol.encode()).hexdigest(), 16) % 25) / 1000.0,
        ),
    )
    seed = int(hashlib.md5(f"jadentradebot:{symbol}".encode()).hexdigest()[:8], 16)
    rng = np.random.RandomState(seed)

    end = end or date.today()
    days = pd.bdate_range(end=pd.Timestamp(end), periods=max(2, int(lookback_days * 5 / 7)))

    n = len(days)
    rets = rng.normal(loc=0.0003, scale=daily_vol, size=n)
    closes = base_price * np.exp(np.cumsum(rets))
    # Scale so the *latest* close sits at the profile price.
    closes *= base_price / closes[-1]

    opens = np.empty(n)
    opens[0] = closes[0] * (1 + rng.normal(0, daily_vol / 2))
    opens[1:] = closes[:-1] * (1 + rng.normal(0, daily_vol / 3, size=n - 1))

    body_hi = np.maximum(opens, closes)
    body_lo = np.minimum(opens, closes)
    wick_hi = np.abs(rng.normal(0, daily_vol / 2, size=n)) * closes
    wick_lo = np.abs(rng.normal(0, daily_vol / 2, size=n)) * closes
    highs = body_hi + wick_hi
    lows = np.maximum(body_lo - wick_lo, 0.01)
    volume = rng.randint(2_000_000, 80_000_000, size=n).astype(float)

    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": volume},
        index=pd.DatetimeIndex(days, name="date"),
    )


def fetch_daily(
    symbol: str,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    source: str = "auto",
) -> pd.DataFrame:
    """Fetch daily OHLCV for ``symbol`` from the chosen source."""
    symbol = validate_symbol(symbol)

    if source == "offline":
        return sample_daily(symbol, lookback_days)
    if source == "yfinance":
        return fetch_yfinance(symbol, lookback_days)
    if source == "stooq":
        return fetch_stooq(symbol, lookback_days)
    if source != "auto":
        raise ValueError(f"unknown source {source!r} "
                         "(expected auto, yfinance, stooq, or offline)")

    errors = []
    for name, provider in (("yfinance", fetch_yfinance), ("stooq", fetch_stooq)):
        try:
            return provider(symbol, lookback_days)
        except Exception as exc:  # network/provider failures -> try next
            log.warning("%s: %s failed: %s", symbol, name, exc)
            errors.append(f"{name}: {exc}")
    raise LookupError(
        f"{symbol}: all live data sources failed ({'; '.join(errors)}). "
        "If you are offline, rerun with source='offline' (CLI: --source offline)."
    )
