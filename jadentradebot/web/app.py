"""Flask dashboard for the DTR vs ATR stock identifier.

Endpoints:

- ``GET /``                     — dashboard UI (self-contained, no CDNs)
- ``GET /api/scan``             — scan a comma-separated watchlist
- ``GET /api/chart/<symbol>``   — daily bars + indicator series for the chart
- ``GET /api/symbols``          — bundled symbol directory (search suggestions)
- ``GET /healthz``              — liveness probe for hosting platforms

Launch locally via ``python -m jadentradebot web`` (see ``--help``), or in
production behind gunicorn: ``gunicorn 'jadentradebot.web.app:app'``. The
module-level ``app`` reads configuration from environment variables —
``WATCHLIST`` (comma-separated), ``DATA_SOURCE``, ``ATR_LENGTH``,
``LOOKBACK_DAYS`` — which is how the Render deployment is configured.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path

import pandas as pd
from flask import Flask, jsonify, render_template, request, send_from_directory

from jadentradebot import __version__
from jadentradebot.data import DEFAULT_LOOKBACK_DAYS
from jadentradebot.indicator import DEFAULT_ATR_LENGTH
from jadentradebot.scanner import DEFAULT_WATCHLIST, ScanRow, scan, scan_symbol

MAX_TICKERS = 50
CHART_BARS = 60

_SYMBOLS_FILE = Path(__file__).with_name("symbols.json")


def _env_int(name: str, fallback: int) -> int:
    try:
        return int(os.environ[name])
    except (KeyError, ValueError):
        return fallback


def _env_watchlist() -> list[str] | None:
    raw = os.environ.get("WATCHLIST", "")
    symbols = [s.strip().upper() for s in raw.split(",") if s.strip()]
    return symbols or None


def _clean(value: float) -> float | None:
    """JSON-safe float (NaN/inf -> null)."""
    f = float(value)
    return f if math.isfinite(f) else None


def _row_payload(row: ScanRow) -> dict:
    if not row.ok:
        return {"symbol": row.symbol, "ok": False, "error": row.error}
    r = row.result
    return {
        "symbol": r.symbol,
        "ok": True,
        "date": r.date.date().isoformat() if r.date is not None else None,
        "status": r.status.value,
        "meaning": r.status.meaning,
        "label": r.label,
        "dtr": _clean(round(r.dtr, 2)),
        "atr": _clean(round(r.atr, 2)),
        "dtr_pct": _clean(r.dtr_pct),
        "range_left": _clean(round(r.range_left, 2)),
        "range_left_pct": _clean(r.range_left_pct),
        "last_close": _clean(round(r.last_close, 2)),
        "today_high": _clean(round(r.today_high, 2)),
        "today_low": _clean(round(r.today_low, 2)),
        "atr_buy_target": _clean(round(r.atr_buy_target, 2)),
        "atr_sell_target": _clean(round(r.atr_sell_target, 2)),
    }


def chart_payload(row: ScanRow) -> dict:
    """Row payload plus the last CHART_BARS daily bars of the indicator
    series, for the candlestick chart. Requires a row scanned with
    ``keep_series=True``."""
    series: pd.DataFrame = row.result.series.tail(CHART_BARS)
    bars = [
        {
            "date": pd.Timestamp(idx).date().isoformat(),
            "open": _clean(rec["open"]) if "open" in series.columns else None,
            "high": _clean(rec["high"]),
            "low": _clean(rec["low"]),
            "close": _clean(rec["close"]),
            "atr": _clean(rec["atr"]),
            "dtr": _clean(rec["dtr"]),
            "dtr_pct": _clean(rec["dtr_pct"]),
            "status": rec["status"],
        }
        for idx, rec in series.iterrows()
    ]
    payload = _row_payload(row)
    payload["bars"] = bars
    return payload


def create_app(
    watchlist: list[str] | None = None,
    source: str | None = None,
    atr_length: int | None = None,
    lookback_days: int | None = None,
) -> Flask:
    """App factory. Explicit arguments win; otherwise environment variables
    (WATCHLIST, DATA_SOURCE, ATR_LENGTH, LOOKBACK_DAYS) then defaults."""
    app = Flask(__name__)
    watchlist = watchlist or _env_watchlist() or DEFAULT_WATCHLIST
    app.config["WATCHLIST"] = [s.strip().upper() for s in watchlist if s.strip()]
    source = source or os.environ.get("DATA_SOURCE") or "auto"
    if source not in ("auto", "yfinance", "stooq", "offline"):
        source = "auto"
    app.config["SOURCE"] = source
    app.config["ATR_LENGTH"] = atr_length or _env_int("ATR_LENGTH", DEFAULT_ATR_LENGTH)
    app.config["LOOKBACK_DAYS"] = lookback_days or _env_int(
        "LOOKBACK_DAYS", DEFAULT_LOOKBACK_DAYS
    )

    def _request_params():
        source_ = request.args.get("source", app.config["SOURCE"])
        if source_ not in ("auto", "yfinance", "stooq", "offline"):
            source_ = app.config["SOURCE"]
        try:
            atr_length_ = int(request.args.get("atr_length", app.config["ATR_LENGTH"]))
        except ValueError:
            atr_length_ = app.config["ATR_LENGTH"]
        atr_length_ = max(1, min(atr_length_, 200))
        return source_, atr_length_

    @app.get("/")
    def index():
        return render_template(
            "index.html",
            version=__version__,
            watchlist=",".join(app.config["WATCHLIST"]),
            source=app.config["SOURCE"],
            atr_length=app.config["ATR_LENGTH"],
        )

    @app.get("/api/scan")
    def api_scan():
        source_, atr_length_ = _request_params()
        raw = request.args.get("tickers", "")
        tickers = [t for t in (p.strip().upper() for p in raw.split(",")) if t]
        tickers = tickers or app.config["WATCHLIST"]
        tickers = tickers[:MAX_TICKERS]
        rows = scan(
            tickers,
            atr_length=atr_length_,
            lookback_days=app.config["LOOKBACK_DAYS"],
            source=source_,
        )
        return jsonify(
            {
                "params": {"source": source_, "atr_length": atr_length_},
                "rows": [_row_payload(r) for r in rows],
            }
        )

    # ---- PWA assets, served at root scope -------------------------------
    @app.get("/manifest.webmanifest")
    def manifest():
        return send_from_directory(
            app.static_folder, "manifest.webmanifest",
            mimetype="application/manifest+json",
        )

    @app.get("/sw.js")
    def service_worker():
        return send_from_directory(
            app.static_folder, "sw.js", mimetype="application/javascript"
        )

    @app.get("/icons/<path:name>")
    def icons(name: str):
        return send_from_directory(f"{app.static_folder}/icons", name)

    @app.get("/apple-touch-icon.png")
    def apple_touch_icon():
        return send_from_directory(f"{app.static_folder}/icons", "icon-180.png")

    @app.get("/bg.svg")
    def background():
        return send_from_directory(app.static_folder, "bg.svg", mimetype="image/svg+xml")

    @app.get("/api/symbols")
    def api_symbols():
        return jsonify(json.loads(_SYMBOLS_FILE.read_text(encoding="utf-8")))

    @app.get("/healthz")
    def healthz():
        return {"status": "ok", "version": __version__}

    @app.get("/api/chart/<symbol>")
    def api_chart(symbol: str):
        source_, atr_length_ = _request_params()
        row = scan_symbol(
            symbol,
            atr_length=atr_length_,
            lookback_days=app.config["LOOKBACK_DAYS"],
            source=source_,
            keep_series=True,
        )
        if not row.ok:
            return jsonify({"symbol": row.symbol, "ok": False, "error": row.error}), 404
        return jsonify(chart_payload(row))

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000)
