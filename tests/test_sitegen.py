"""Static-site generator tests (offline)."""

import json

from jadentradebot.cli import main
from jadentradebot.sitegen import build_site


class TestSitegen:
    def test_build_site_offline(self, tmp_path):
        out = tmp_path / "site"
        data = build_site(out, symbols=["AAPL", "TSLA"], source="offline")

        html = (out / "index.html").read_text(encoding="utf-8")
        assert "STATIC_DATA" in html
        assert "Static snapshot" in html
        assert "AAPL" in html
        # No live-scan controls in a snapshot.
        assert 'id="scanBtn"' not in html
        assert (out / ".nojekyll").exists()

        scan_json = json.loads((out / "data" / "scan.json").read_text())
        assert {r["symbol"] for r in scan_json["rows"]} == {"AAPL", "TSLA"}
        assert scan_json["params"]["source"] == "offline"
        assert "charts" not in scan_json  # charts live only in the page

        assert set(data["charts"]) == {"AAPL", "TSLA"}
        for chart in data["charts"].values():
            assert chart["bars"], "expected embedded chart bars"

    def test_cli_sitegen(self, tmp_path, capsys):
        out = tmp_path / "public"
        rc = main([
            "sitegen", "--out", str(out), "--source", "offline",
            "-t", "NVDA", "-t", "SPY",
        ])
        assert rc == 0
        assert "2/2 symbols" in capsys.readouterr().out
        assert (out / "index.html").exists()

    def test_cli_sitegen_all_failed_exit_code(self, tmp_path, monkeypatch):
        import jadentradebot.scanner as scanner_mod

        def boom(symbol, **kwargs):
            raise LookupError("nope")

        monkeypatch.setattr(scanner_mod, "fetch_daily", boom)
        rc = main(["sitegen", "--out", str(tmp_path / "s"), "--source", "offline",
                   "-t", "AAPL"])
        assert rc == 1
