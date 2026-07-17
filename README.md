# jadentradebot — DTR vs ATR Trading & Stock Identifier

A trading and stock identifier built around the **DTR vs ATR** indicator — a
faithful Python port of the thinkorswim **"Custom ATR Plot" by 7of9**, shared
on [usethinkscript.com](https://usethinkscript.com/threads/dtr-vs-atr-indicator-for-thinkorswim.387/) —
extended from a single-chart label into a full watchlist **scanner**, **CLI**,
and **web dashboard**.

## What the indicator does

Every stock has a typical daily trading range — its **ATR** (Average True
Range, Wilder's 14-day average of the daily True Range). The **DTR** (Daily
True Range) is how far the stock has actually travelled *today*
(`today's high − today's low`). Comparing them answers the day trader's
question: *how much juice is left in this stock today?*

```
DTR% = Round( (DTR / ATR) × 100 )
```

| Signal | Condition | Meaning |
|--------|-----------|---------|
| 🟢 **GREEN** | DTR% ≤ 70 | Most of the average range is unused — room to move, favourable for entries |
| 🟠 **ORANGE** | 70 < DTR% < 90 | The day is getting extended — caution |
| 🔴 **RED** | DTR% ≥ 90 | Average range exhausted — chasing has poor odds, reversal risk elevated |

The port reproduces the ThinkScript exactly, including the subtle bits:
Wilder's smoothing (`alpha = 1/length`), ThinkScript's `TrueRange` (which uses
the previous close), and `Round()`'s half-away-from-zero rounding *applied
before* the colour thresholds — so a raw 70.4% still labels GREEN, just like
on a thinkorswim chart.

## Install

```bash
pip install -r requirements.txt        # or: pip install .
```

## CLI

```bash
# Scan the default watchlist with live data (Yahoo Finance, Stooq fallback)
python -m jadentradebot scan

# Scan your own tickers
python -m jadentradebot scan -t AAPL -t TSLA -t NVDA -t AMD

# JSON output for scripting / bots
python -m jadentradebot scan --json -t SPY -t QQQ

# Single-symbol label — exactly what the thinkorswim study shows
python -m jadentradebot label AAPL
# DTR 2.15 vs ATR 4.3  50%
# Room to move — has used ≤70% of its average daily range

# No network? Deterministic demo data:
python -m jadentradebot scan --source offline
```

The scan table is sorted the way traders use the label: GREEN first (most
range left), then ORANGE, then RED, with failed symbols last, and adds
**Range Left** in dollars and percent. The `--json` output and the web
dashboard also include **ATR targets** projected from today's extremes
(`low + ATR`, `high − ATR`).

## Web dashboard

```bash
python -m jadentradebot web                 # live data, http://127.0.0.1:8000
python -m jadentradebot web --source offline --port 8000   # demo mode
```

A dark, thinkorswim-styled dashboard — completely self-contained (no CDNs):

- **Label chips** for every ticker, in the exact `DTR x vs ATR y  z%` format
  and colour of the original `AddLabel`
- **Scanner table** — sortable by any column, with a DTR% usage meter
- **Daily candlestick chart** per symbol with a per-day DTR% status strip,
  range-left readout, and ATR targets

### JSON API

- `GET /api/scan?tickers=AAPL,TSLA&atr_length=14&source=auto`
- `GET /api/chart/AAPL?atr_length=14&source=auto`

## Python API

```python
from jadentradebot import scan, dtr_vs_atr
from jadentradebot.data import fetch_daily

rows = scan(["AAPL", "TSLA", "NVDA"])          # live scan
for row in rows:
    if row.ok:
        print(row.result.label, row.result.status.value)

daily = fetch_daily("AAPL")                     # any OHLC DataFrame works
res = dtr_vs_atr(daily, symbol="AAPL")
print(res.dtr_pct, res.range_left, res.atr_buy_target)
```

## ThinkScript files

The `thinkscript/` folder contains ready-to-paste thinkorswim studies:

- `DTR_vs_ATR_original.ts` — the verbatim 7of9 script this port is tested against
- `DTR_vs_ATR_enhanced.ts` — adds a range-left label, ATR target lines, and an
  exhaustion alert
- `DTR_vs_ATR_scan.ts` — Stock Hacker scan / watchlist-column version

## Data sources

| Source | Use |
|--------|-----|
| `auto` (default) | Yahoo Finance via `yfinance`, falls back to Stooq |
| `yfinance` / `stooq` | Force a specific live provider |
| `offline` | Deterministic synthetic data — demos, tests, CI, airplanes |

## Tests

```bash
python -m pytest
```

The suite validates the math against an independent bar-by-bar
reimplementation of the ThinkScript, covers the rounding/threshold edge cases
(e.g. raw 70.3% → GREEN), and exercises the scanner, CLI, and web API fully
offline.

## Disclaimer

For education and research. Not financial advice; trade at your own risk.
