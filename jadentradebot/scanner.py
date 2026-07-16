"""Multi-ticker scanner: run DTR vs ATR across a watchlist and rank results.

This is the "stock identifier" part — the thinkorswim study labels one chart;
the scanner evaluates a whole watchlist and sorts by how much average daily
range each stock has left (GREEN first), the same way traders use the label to
pick which symbol is still worth trading today.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Iterable, Optional

from jadentradebot.data import DEFAULT_LOOKBACK_DAYS, fetch_daily
from jadentradebot.indicator import DEFAULT_ATR_LENGTH, DtrVsAtrResult, dtr_vs_atr

log = logging.getLogger(__name__)

DEFAULT_WATCHLIST = [
    "AAPL", "MSFT", "NVDA", "TSLA", "AMZN",
    "META", "GOOGL", "AMD", "SPY", "QQQ",
]

_STATUS_ORDER = {"GREEN": 0, "ORANGE": 1, "RED": 2}


@dataclass
class ScanRow:
    """Result for one ticker, or the error that prevented one."""

    symbol: str
    result: Optional[DtrVsAtrResult] = None
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.result is not None


def scan_symbol(
    symbol: str,
    atr_length: int = DEFAULT_ATR_LENGTH,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    source: str = "auto",
    keep_series: bool = False,
) -> ScanRow:
    symbol = symbol.strip().upper()
    try:
        daily = fetch_daily(symbol, lookback_days=lookback_days, source=source)
        result = dtr_vs_atr(
            daily, symbol=symbol, atr_length=atr_length, keep_series=keep_series
        )
        return ScanRow(symbol=symbol, result=result)
    except Exception as exc:
        log.warning("scan %s failed: %s", symbol, exc)
        return ScanRow(symbol=symbol, error=str(exc))


def scan(
    symbols: Iterable[str] | None = None,
    atr_length: int = DEFAULT_ATR_LENGTH,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    source: str = "auto",
    keep_series: bool = False,
    max_workers: int = 8,
) -> list[ScanRow]:
    """Scan a watchlist. Returns rows sorted GREEN -> ORANGE -> RED, and by
    ascending DTR% within each colour (most room to move first); failed
    symbols sort last."""
    watch = [s.strip().upper() for s in (symbols or DEFAULT_WATCHLIST) if s.strip()]
    # De-dupe, preserving order.
    watch = list(dict.fromkeys(watch))
    if not watch:
        return []

    rows: list[ScanRow] = []
    with ThreadPoolExecutor(max_workers=min(max_workers, len(watch))) as pool:
        futures = {
            pool.submit(
                scan_symbol, sym, atr_length, lookback_days, source, keep_series
            ): sym
            for sym in watch
        }
        for fut in as_completed(futures):
            rows.append(fut.result())

    def sort_key(row: ScanRow):
        if not row.ok:
            return (9, 0, row.symbol)
        return (
            _STATUS_ORDER[row.result.status.value],
            row.result.dtr_pct,
            row.symbol,
        )

    rows.sort(key=sort_key)
    return rows
