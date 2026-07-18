"""Static-site generator: render the dashboard as a self-contained snapshot.

This is what GitHub Actions publishes to GitHub Pages: it runs a scan, embeds
the results (and per-symbol chart data) directly into the dashboard HTML, and
writes a plain-JSON copy alongside it. The page needs no server — chips,
sortable table, and charts all work from the embedded data.

Output layout::

    <out>/index.html        the dashboard snapshot
    <out>/data/scan.json    machine-readable scan results
    <out>/.nojekyll         tells GitHub Pages to serve files as-is
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from flask import render_template

from jadentradebot import __version__
from jadentradebot.data import DEFAULT_LOOKBACK_DAYS
from jadentradebot.indicator import DEFAULT_ATR_LENGTH
from jadentradebot.scanner import DEFAULT_WATCHLIST, scan
from jadentradebot.web.app import _row_payload, create_app


def build_site(
    out_dir: str | Path,
    symbols: list[str] | None = None,
    atr_length: int = DEFAULT_ATR_LENGTH,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    source: str = "auto",
) -> dict:
    """Scan and write the static site into ``out_dir``. Returns the scan data."""
    out = Path(out_dir)
    (out / "data").mkdir(parents=True, exist_ok=True)

    watch = [s.strip().upper() for s in (symbols or DEFAULT_WATCHLIST) if s.strip()]
    rows = scan(
        watch,
        atr_length=atr_length,
        lookback_days=lookback_days,
        source=source,
    )

    # Only the scan rows are embedded: the calculator page's prefill dropdown
    # reads them, and data/scan.json republishes them. (Chart series stay out
    # of the page — they were 85% of the payload and nothing renders them.)
    static_data = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "params": {"source": source, "atr_length": atr_length},
        "rows": [_row_payload(r) for r in rows],
    }

    app = create_app(watchlist=watch, source=source, atr_length=atr_length,
                     lookback_days=lookback_days)
    with app.app_context():
        html = render_template(
            "index.html",
            version=__version__,
            watchlist=",".join(watch),
            source=source,
            atr_length=atr_length,
            static_data=static_data,
        )

    (out / "index.html").write_text(html, encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    (out / "data" / "scan.json").write_text(
        json.dumps(static_data, indent=2), encoding="utf-8"
    )

    # PWA assets: the snapshot is installable/offline-capable just like the
    # live app (manifest, service worker, icons copied to the site root).
    static_dir = Path(__file__).parent / "web" / "static"
    for name in ("manifest.webmanifest", "sw.js", "bg.svg"):
        shutil.copy2(static_dir / name, out / name)
    shutil.copytree(static_dir / "icons", out / "icons", dirs_exist_ok=True)
    shutil.copy2(static_dir / "icons" / "icon-180.png", out / "apple-touch-icon.png")
    return static_data
