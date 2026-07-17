"""DTR vs ATR — faithful port of the thinkorswim "Custom ATR Plot" by 7of9.

Original ThinkScript (usethinkscript.com, edited 3/20/19)::

    declare upper;
    input AtrAvgLength = 14;
    def ATR = WildersAverage(TrueRange(high(period = aggregationPeriod.DAY),
                                       close(period = aggregationPeriod.DAY),
                                       low(period = aggregationPeriod.DAY)),
                             AtrAvgLength);
    def TodayHigh = Highest(high(period = aggregationPeriod.DAY), 1);
    def TodayLow = Lowest(low(period = aggregationPeriod.DAY), 1);
    def DTR = TodayHigh - TodayLow;
    def DTRpct = Round((DTR / ATR) * 100, 0);
    AddLabel(yes, "DTR " + Round(DTR, 2) + " vs ATR " + Round(ATR, 2) + "  "
                  + Round(DTRpct, 0) + "%",
             (if DTRpct <= 70 then Color.GREEN
              else if DTRpct >= 90 then Color.RED
              else Color.ORANGE));

The indicator answers one question: *how much of its average daily range has
this stock already used today?*

- **GREEN  (DTR% <= 70)** — most of the average range is still unused; the
  stock has room to move, favourable for new intraday entries.
- **ORANGE (70 < DTR% < 90)** — the day's range is getting extended; caution.
- **RED    (DTR% >= 90)** — the average range is exhausted; chasing here has
  poor odds and mean-reversion risk is elevated.

Because the script computes ``Round(DTRpct, 0)`` before comparing, the colour
thresholds apply to the *rounded* percentage (70.4% still labels GREEN); this
port reproduces that exactly.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import pandas as pd

from jadentradebot.thinkscript import (
    highest,
    lowest,
    true_range,
    ts_round,
    wilders_average,
)

DEFAULT_ATR_LENGTH = 14

GREEN_MAX = 70   # DTRpct <= 70          -> GREEN
RED_MIN = 90     # DTRpct >= 90          -> RED
                 # 70 < DTRpct < 90      -> ORANGE


class Status(str, Enum):
    """Label colour from the original script, used as the identifier signal."""

    GREEN = "GREEN"
    ORANGE = "ORANGE"
    RED = "RED"

    @property
    def meaning(self) -> str:
        return {
            Status.GREEN: "Room to move — has used ≤70% of its average daily range",
            Status.ORANGE: "Extended — between 70% and 90% of its average daily range",
            Status.RED: "Range exhausted — ≥90% of its average daily range used",
        }[self]


def _fmt_price(value: float) -> str:
    """Render Round(value, 2) for the label: 12345.68 -> '12345.68',
    4.0 -> '4', 8.10 -> '8.1'."""
    r = ts_round(value, 2)
    if not math.isfinite(r):
        return str(r)
    return f"{r:.2f}".rstrip("0").rstrip(".")


def classify(dtr_pct_rounded: float) -> Status:
    """Colour logic from the original AddLabel, applied to the rounded pct."""
    if dtr_pct_rounded <= GREEN_MAX:
        return Status.GREEN
    if dtr_pct_rounded >= RED_MIN:
        return Status.RED
    return Status.ORANGE


@dataclass
class DtrVsAtrResult:
    """One evaluated bar of the study (normally the latest daily bar)."""

    symbol: str
    date: Optional[pd.Timestamp]
    atr: float                  # Wilder's ATR over atr_length daily bars
    dtr: float                  # today's high - today's low
    dtr_pct: float              # Round((DTR / ATR) * 100, 0) — as in the script
    status: Status
    # Enhancements beyond the original label:
    last_close: float
    today_high: float
    today_low: float
    range_left: float           # max(ATR - DTR, 0): dollars of avg range unused
    range_left_pct: float       # 100 - DTR%, floored at 0
    atr_buy_target: float       # TodayLow + ATR (upside room per ATR)
    atr_sell_target: float      # TodayHigh - ATR (downside room per ATR)
    series: Optional[pd.DataFrame] = field(default=None, repr=False)

    @property
    def label(self) -> str:
        """The AddLabel text from the ThinkScript (Round to 2dp, trailing
        zeros trimmed). Full precision at any magnitude — no 6-significant-
        digit truncation or scientific notation on high-priced symbols."""
        return (
            f"DTR {_fmt_price(self.dtr)} vs ATR {_fmt_price(self.atr)}"
            f"  {self.dtr_pct:.0f}%"
        )

    @property
    def color(self) -> str:
        return self.status.value


def compute_series(
    daily: pd.DataFrame, atr_length: int = DEFAULT_ATR_LENGTH
) -> pd.DataFrame:
    """Evaluate the study on every daily bar, like ThinkScript ``def``s do.

    ``daily`` must have columns ``high``, ``low``, ``close`` (case-insensitive)
    indexed by date, oldest first. Returns a DataFrame with columns
    ``atr, dtr, dtr_pct, status`` aligned to the input.
    """
    cols = {c.lower(): c for c in daily.columns}
    missing = [c for c in ("high", "low", "close") if c not in cols]
    if missing:
        raise ValueError(f"daily data is missing columns: {missing}")

    high = daily[cols["high"]].astype(float)
    low = daily[cols["low"]].astype(float)
    close = daily[cols["close"]].astype(float)

    atr = wilders_average(true_range(high, close, low), atr_length)
    today_high = highest(high, 1)
    today_low = lowest(low, 1)
    dtr = today_high - today_low
    dtr_pct = ((dtr / atr) * 100).map(lambda v: ts_round(v, 0))

    frame = {
        "high": high,
        "low": low,
        "close": close,
        "atr": atr,
        "dtr": dtr,
        "dtr_pct": dtr_pct,
    }
    if "open" in cols:  # carried through for charting; not used by the study
        frame["open"] = daily[cols["open"]].astype(float)
    out = pd.DataFrame(frame, index=daily.index)
    # A 0/0 bar (no range, no ATR yet) has no meaningful DTR% — mark it NA
    # instead of letting NaN comparisons fall through to ORANGE.
    out["status"] = out["dtr_pct"].map(
        lambda p: classify(p).value if math.isfinite(p) else "NA"
    )
    return out


def dtr_vs_atr(
    daily: pd.DataFrame,
    symbol: str = "",
    atr_length: int = DEFAULT_ATR_LENGTH,
    keep_series: bool = False,
) -> DtrVsAtrResult:
    """Evaluate the study and return the latest bar — what the chart label shows.

    ``daily`` needs at least ``high``, ``low``, ``close`` columns and should
    carry a few months of history so Wilder's average is warmed up
    (>= 3 * atr_length bars recommended; more history only sharpens it).
    """
    if len(daily) < 2:
        raise ValueError(
            f"{symbol or 'input'}: need at least 2 daily bars, got {len(daily)}"
        )
    series = compute_series(daily, atr_length=atr_length)
    last = series.iloc[-1]
    date = series.index[-1]

    atr = float(last["atr"])
    dtr = float(last["dtr"])
    dtr_pct = float(last["dtr_pct"])
    if atr <= 0 or pd.isna(dtr_pct):
        raise ValueError(f"{symbol or 'input'}: degenerate data (ATR={atr})")

    return DtrVsAtrResult(
        symbol=symbol,
        date=pd.Timestamp(date) if date is not None else None,
        atr=atr,
        dtr=dtr,
        dtr_pct=dtr_pct,
        status=classify(dtr_pct),
        last_close=float(last["close"]),
        today_high=float(last["high"]),
        today_low=float(last["low"]),
        range_left=max(atr - dtr, 0.0),
        range_left_pct=max(100.0 - dtr_pct, 0.0),
        atr_buy_target=float(last["low"]) + atr,
        atr_sell_target=float(last["high"]) - atr,
        series=series if keep_series else None,
    )
