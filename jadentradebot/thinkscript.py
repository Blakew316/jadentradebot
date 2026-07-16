"""Python ports of the ThinkScript built-ins used by the DTR vs ATR study.

Each function mirrors the thinkorswim behaviour it is named after:

- ``true_range``     -> ``TrueRange(high, close, low)``
- ``wilders_average``-> ``WildersAverage(data, length)``
- ``highest``        -> ``Highest(data, length)``
- ``lowest``         -> ``Lowest(data, length)``
- ``ts_round``       -> ``Round(value, numberOfDigits)``

All series functions accept and return ``pandas.Series`` aligned to the input
index (one value per daily bar), matching how ThinkScript evaluates a ``def``
on every bar of the chart.
"""

from __future__ import annotations

import math
from decimal import ROUND_HALF_UP, Decimal

import pandas as pd


def true_range(high: pd.Series, close: pd.Series, low: pd.Series) -> pd.Series:
    """ThinkScript ``TrueRange(high, close, low)``.

    TR = max(high, close[1]) - min(low, close[1])
       = max(high - low, abs(high - close[1]), abs(close[1] - low))

    thinkorswim yields the plain high-low range on the first bar (where
    ``close[1]`` does not exist), which is also Wilder's original convention.
    """
    prev_close = close.shift(1)
    hl = high - low
    hc = (high - prev_close).abs()
    cl = (prev_close - low).abs()
    tr = pd.concat([hl, hc, cl], axis=1).max(axis=1, skipna=True)
    # First bar: no previous close -> plain range.
    return tr.fillna(hl)


def wilders_average(data: pd.Series, length: int) -> pd.Series:
    """ThinkScript ``WildersAverage(data, length)``.

    Wilder's smoothing is a recursive exponential average with
    ``alpha = 1 / length``::

        wa[i] = wa[i-1] + (data[i] - wa[i-1]) / length

    seeded with the first data value, which is exactly
    ``Series.ewm(alpha=1/length, adjust=False)``. Feed it a comfortable
    warm-up window (>= 3 * length bars) so the seed has fully decayed —
    the scanner fetches ~6 months of daily bars for the default length 14.
    """
    if length < 1:
        raise ValueError(f"length must be >= 1, got {length}")
    return data.ewm(alpha=1.0 / length, adjust=False, ignore_na=True).mean()


def highest(data: pd.Series, length: int) -> pd.Series:
    """ThinkScript ``Highest(data, length)`` — rolling max of the last
    ``length`` bars including the current bar. ``Highest(x, 1)`` is ``x``."""
    if length < 1:
        raise ValueError(f"length must be >= 1, got {length}")
    return data.rolling(window=length, min_periods=1).max()


def lowest(data: pd.Series, length: int) -> pd.Series:
    """ThinkScript ``Lowest(data, length)`` — rolling min of the last
    ``length`` bars including the current bar. ``Lowest(x, 1)`` is ``x``."""
    if length < 1:
        raise ValueError(f"length must be >= 1, got {length}")
    return data.rolling(window=length, min_periods=1).min()


def ts_round(value: float, digits: int = 0) -> float:
    """ThinkScript ``Round(value, numberOfDigits)``.

    thinkorswim rounds halves away from zero (Round(0.5) == 1,
    Round(-0.5) == -1), unlike Python's banker's rounding.
    """
    if value is None:
        return float("nan")
    value = float(value)  # accept numpy scalars
    if math.isnan(value) or math.isinf(value):
        return value if math.isinf(value) else float("nan")
    quant = Decimal(1).scaleb(-digits)
    return float(Decimal(repr(value)).quantize(quant, rounding=ROUND_HALF_UP))
