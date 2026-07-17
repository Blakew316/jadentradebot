"""Command-line interface.

Examples::

    # Scan the default watchlist with live data
    python -m jadentradebot scan

    # Scan specific tickers
    python -m jadentradebot scan -t AAPL -t TSLA -t NVDA

    # No network? Deterministic demo data:
    python -m jadentradebot scan --source offline

    # Single-symbol label, exactly like the thinkorswim study
    python -m jadentradebot label AAPL

    # Launch the web dashboard
    python -m jadentradebot web --source offline --port 8000
"""

from __future__ import annotations

import argparse
import json
import sys

from jadentradebot import __version__
from jadentradebot.data import DEFAULT_LOOKBACK_DAYS
from jadentradebot.indicator import DEFAULT_ATR_LENGTH
from jadentradebot.scanner import DEFAULT_WATCHLIST, ScanRow, scan

_ANSI = {
    "GREEN": "\033[92m",
    "ORANGE": "\033[93m",
    "RED": "\033[91m",
    "DIM": "\033[2m",
    "BOLD": "\033[1m",
    "RESET": "\033[0m",
}


def _paint(text: str, color: str, enabled: bool) -> str:
    if not enabled:
        return text
    return f"{_ANSI.get(color, '')}{text}{_ANSI['RESET']}"


def _print_table(rows: list[ScanRow], color: bool) -> None:
    header = (
        f"{'SYMBOL':<8}{'STATUS':<8}{'DTR%':>6}  {'DTR':>9}  {'ATR':>9}  "
        f"{'LEFT $':>8}  {'LEFT %':>7}  {'CLOSE':>10}  LABEL"
    )
    print(_paint(header, "BOLD", color))
    print("-" * len(header))
    for row in rows:
        if not row.ok:
            print(f"{row.symbol:<8}" + _paint(f"ERROR   {row.error}", "DIM", color))
            continue
        r = row.result
        line = (
            f"{r.symbol:<8}{r.status.value:<8}{r.dtr_pct:>5.0f}%  "
            f"{r.dtr:>9.2f}  {r.atr:>9.2f}  {r.range_left:>8.2f}  "
            f"{r.range_left_pct:>6.0f}%  {r.last_close:>10.2f}  {r.label}"
        )
        print(_paint(line, r.status.value, color))


def _rows_to_json(rows: list[ScanRow]) -> str:
    payload = []
    for row in rows:
        if row.ok:
            r = row.result
            payload.append(
                {
                    "symbol": r.symbol,
                    "date": r.date.date().isoformat() if r.date is not None else None,
                    "status": r.status.value,
                    "label": r.label,
                    "dtr": round(r.dtr, 4),
                    "atr": round(r.atr, 4),
                    "dtr_pct": r.dtr_pct,
                    "range_left": round(r.range_left, 4),
                    "range_left_pct": r.range_left_pct,
                    "last_close": round(r.last_close, 4),
                    "today_high": round(r.today_high, 4),
                    "today_low": round(r.today_low, 4),
                    "atr_buy_target": round(r.atr_buy_target, 4),
                    "atr_sell_target": round(r.atr_sell_target, 4),
                }
            )
        else:
            payload.append({"symbol": row.symbol, "error": row.error})
    return json.dumps(payload, indent=2)


def _add_common_args(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--atr-length", type=int, default=DEFAULT_ATR_LENGTH,
        help=f"ATR averaging length (default {DEFAULT_ATR_LENGTH}, as in the study)",
    )
    p.add_argument(
        "--lookback-days", type=int, default=DEFAULT_LOOKBACK_DAYS,
        help=f"calendar days of history to fetch (default {DEFAULT_LOOKBACK_DAYS})",
    )
    p.add_argument(
        "--source", choices=["auto", "yfinance", "stooq", "offline"], default="auto",
        help="data source (default auto: yfinance then stooq; "
             "'offline' uses deterministic sample data)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jadentradebot",
        description="DTR vs ATR trading & stock identifier "
                    "(port of the thinkorswim Custom ATR Plot by 7of9).",
    )
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command")

    p_scan = sub.add_parser("scan", help="scan a watchlist and rank by range left")
    p_scan.add_argument(
        "-t", "--ticker", action="append", dest="tickers", metavar="SYM",
        help="ticker to scan (repeatable); default watchlist: "
             + ", ".join(DEFAULT_WATCHLIST),
    )
    p_scan.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    p_scan.add_argument("--no-color", action="store_true", help="disable ANSI colors")
    _add_common_args(p_scan)

    p_label = sub.add_parser("label", help="print the study label for one symbol")
    p_label.add_argument("symbol", help="ticker symbol, e.g. AAPL")
    p_label.add_argument("--no-color", action="store_true", help="disable ANSI colors")
    _add_common_args(p_label)

    p_site = sub.add_parser(
        "sitegen", help="build a static dashboard snapshot (for GitHub Pages)"
    )
    p_site.add_argument("--out", default="site", help="output directory (default: site)")
    p_site.add_argument(
        "-t", "--ticker", action="append", dest="tickers", metavar="SYM",
        help="ticker to include (repeatable); defaults to the built-in watchlist",
    )
    _add_common_args(p_site)

    p_web = sub.add_parser("web", help="launch the web dashboard")
    p_web.add_argument("--host", default="127.0.0.1")
    p_web.add_argument("--port", type=int, default=8000)
    p_web.add_argument(
        "-t", "--ticker", action="append", dest="tickers", metavar="SYM",
        help="initial watchlist ticker (repeatable)",
    )
    _add_common_args(p_web)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "scan":
        rows = scan(
            args.tickers,
            atr_length=args.atr_length,
            lookback_days=args.lookback_days,
            source=args.source,
        )
        if args.json:
            print(_rows_to_json(rows))
        else:
            color = sys.stdout.isatty() and not args.no_color
            _print_table(rows, color)
        return 0 if any(r.ok for r in rows) else 1

    if args.command == "label":
        from jadentradebot.scanner import scan_symbol

        row = scan_symbol(
            args.symbol,
            atr_length=args.atr_length,
            lookback_days=args.lookback_days,
            source=args.source,
        )
        if not row.ok:
            print(f"{row.symbol}: {row.error}", file=sys.stderr)
            return 1
        color = sys.stdout.isatty() and not args.no_color
        print(_paint(row.result.label, row.result.status.value, color))
        print(row.result.status.meaning)
        return 0

    if args.command == "sitegen":
        from jadentradebot.sitegen import build_site

        data = build_site(
            args.out,
            symbols=args.tickers,
            atr_length=args.atr_length,
            lookback_days=args.lookback_days,
            source=args.source,
        )
        ok = sum(1 for r in data["rows"] if r.get("ok"))
        print(
            f"wrote {args.out}/index.html — {ok}/{len(data['rows'])} symbols "
            f"scanned ({data['generated_at']})"
        )
        return 0 if ok else 1

    if args.command == "web":
        from jadentradebot.web.app import create_app

        app = create_app(
            watchlist=args.tickers,
            source=args.source,
            atr_length=args.atr_length,
            lookback_days=args.lookback_days,
        )
        app.run(host=args.host, port=args.port, debug=False)
        return 0

    build_parser().print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
