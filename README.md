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

## Web app — Jaden's Risk Calculator (JRC)

```bash
python -m jadentradebot web                 # http://127.0.0.1:8000
python -m jadentradebot web --source offline --port 8000   # demo data
```

The site is a single-purpose **Jaden's Risk Calculator**: account size, risk
dropdown (0.25% / 0.5% / 1% / 2%), entry, and stop in — **shares to buy** at
that risk out, with the dollar risk and per-share cost shown under the
result. Professional **light and dark modes** (toggle in the header, follows
the system preference, persists), fully **iOS-friendly** (safe-area insets,
16px inputs so Safari doesn't zoom, 44px touch targets), and completely
self-contained — no CDNs.

The scanner itself remains available through the CLI and the JSON API.

**Install it as an app (PWA).** The site ships a web-app manifest, **JRC**
monogram home-screen icons, and a service worker, so it installs like a
native app and **works fully offline**. On iPhone/iPad: open the site in
Safari → Share → **Add to Home Screen** — it launches full-screen
(standalone, no browser chrome) as "JRC". On Android/desktop Chrome, use the
"Install app" prompt. Both the Render app and the GitHub Pages build are
installable.

### JSON API

- `GET /api/scan?tickers=AAPL,TSLA&atr_length=14&source=auto`
- `GET /api/chart/AAPL?atr_length=14&source=auto`
- `GET /api/symbols` · `GET /healthz`

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

## Deploying with GitHub Actions + GitHub Pages

GitHub Pages only serves static files, so the Flask server can't run there.
Instead, the included workflows publish an **auto-refreshing static snapshot**
of the dashboard — GitHub's Actions runners have internet access, so they can
pull live Yahoo/Stooq data even though your machine may not:

- `.github/workflows/ci.yml` — runs the test suite and an offline site build
  on every push and pull request.
- `.github/workflows/pages.yml` — scans the watchlist with **live data**,
  renders the dashboard with the results embedded (`sitegen`), and deploys it
  to GitHub Pages on every push, every 30 minutes during US market hours, and
  on demand.

**One-time setup** (after these files are on your default branch):

1. Repo **Settings → Pages → Build and deployment → Source: “GitHub Actions”**.
2. Trigger the first deploy: **Actions → “Deploy dashboard to GitHub Pages” →
   Run workflow** (optionally passing custom tickers), or just push a commit.
3. Your dashboard appears at `https://<user>.github.io/<repo>/`, with the raw
   scan JSON at `.../data/scan.json`.

**Troubleshooting deploys**

- If the deploy job fails with *"Branch … is not allowed to deploy to
  github-pages due to environment protection rules"*, allow the branch under
  **Settings → Environments → github-pages → Deployment branches**.
- Scheduled (cron) runs only execute the workflow on the repository's
  **default branch** — if you change the default branch, make sure
  `pages.yml` exists there, then confirm runs appear in the Actions tab.
  GitHub also pauses cron schedules after ~60 days without repo activity;
  a manual "Run workflow" revives them.
- If live data has a total outage, the build fails on purpose and the
  previous snapshot stays live; partial failures still deploy, with the
  failed symbols listed in the table.

To change the deployed watchlist permanently, edit `DEFAULT_WATCHLIST` in
`jadentradebot/scanner.py` (or pass `-t` flags in the workflow's sitegen step).
The snapshot page keeps the chips, sortable table, and per-symbol charts —
only the live re-scan controls are removed. You can build the same snapshot
locally with:

```bash
python -m jadentradebot sitegen --out site            # live data
python -m jadentradebot sitegen --out site --source offline   # demo data
```

## Deploying the interactive app on Render (live search)

GitHub Pages serves a snapshot; **Render runs the real app**, where visitors
can search any stock — by ticker or company name — and scan it live. The repo
ships a ready-made blueprint (`render.yaml`):

1. Sign in at [render.com](https://render.com) → **New + → Blueprint** →
   connect the `jadentradebot` GitHub repo (pick the branch you deploy from).
2. Render reads `render.yaml` and creates the web service automatically:
   gunicorn serving the Flask app on the free plan, with a `/healthz` health
   check. Click **Apply** and wait for the first deploy.
3. Your app is live at `https://jadentradebot.onrender.com` (name may vary).

Configuration lives in environment variables (Render dashboard → Environment):
`WATCHLIST` (default tickers shown on load), `DATA_SOURCE` (`auto`),
`ATR_LENGTH`, `LOOKBACK_DAYS`, and `DATA_CACHE_TTL` — seconds that fetched
market data is cached in-process (default 300) so a busy site doesn't hammer
the providers.

**Custom domain:** in Render → Settings → Custom Domains add e.g.
`app.jadenstradebot.com`, then create the CNAME it shows you in Namecheap
(Host `app` → the `.onrender.com` target). Keep GitHub Pages on the apex
domain and the interactive app on the subdomain.

**Free-tier note:** Render's free instances sleep after ~15 idle minutes; the
first visit afterwards takes ~30-60 s to wake. Paid instances stay warm.

### Live search

The dashboard's search bar accepts a ticker or a company name ("PLTR" or
"Palantir"), with autocomplete suggestions from a bundled directory of ~190
liquid stocks, ETFs, and indices (`jadentradebot/web/symbols.json` — edit to
taste; `GET /api/symbols` serves it). Enter or **Add to scan** fetches the
symbol live, adds it to the watchlist, and opens its chart. Any symbol the
data providers know works, including ones not in the directory. On the static
GitHub Pages snapshot the same bar filters the scanned symbols instead.

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
