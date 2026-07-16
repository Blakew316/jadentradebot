"""CLI and web-dashboard tests (offline sources only)."""

import json

import pytest

from jadentradebot.cli import main
from jadentradebot.web.app import create_app


class TestCli:
    def test_scan_json(self, capsys):
        rc = main(["scan", "--source", "offline", "--json", "-t", "AAPL", "-t", "TSLA"])
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert {p["symbol"] for p in payload} == {"AAPL", "TSLA"}
        for p in payload:
            assert p["status"] in ("GREEN", "ORANGE", "RED")
            assert p["label"].startswith("DTR ")
            assert 0 <= p["dtr_pct"]

    def test_scan_table(self, capsys):
        rc = main(["scan", "--source", "offline", "--no-color", "-t", "NVDA"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "NVDA" in out and "SYMBOL" in out and "DTR%" in out

    def test_label_command(self, capsys):
        rc = main(["label", "AAPL", "--source", "offline", "--no-color"])
        assert rc == 0
        out = capsys.readouterr().out
        assert out.startswith("DTR ") and "vs ATR" in out and "%" in out

    def test_label_failure_exit_code(self, capsys, monkeypatch):
        import jadentradebot.scanner as scanner_mod

        def boom(symbol, **kwargs):
            raise LookupError("nope")

        monkeypatch.setattr(scanner_mod, "fetch_daily", boom)
        rc = main(["label", "GONE", "--source", "offline"])
        assert rc == 1
        assert "GONE" in capsys.readouterr().err

    def test_no_command_prints_help(self, capsys):
        assert main([]) == 2
        assert "scan" in capsys.readouterr().out


@pytest.fixture()
def client():
    app = create_app(watchlist=["AAPL", "TSLA"], source="offline")
    app.config["TESTING"] = True
    return app.test_client()

class TestWeb:
    def test_index(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "DTR vs ATR" in html
        assert "AAPL,TSLA" in html

    def test_api_scan(self, client):
        resp = client.get("/api/scan?tickers=AAPL,NVDA&source=offline")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["params"]["source"] == "offline"
        symbols = {r["symbol"] for r in data["rows"]}
        assert symbols == {"AAPL", "NVDA"}
        row = data["rows"][0]
        assert row["ok"] and row["status"] in ("GREEN", "ORANGE", "RED")
        for key in ("label", "dtr", "atr", "dtr_pct", "range_left",
                    "atr_buy_target", "atr_sell_target", "meaning"):
            assert key in row

    def test_api_scan_defaults_to_configured_watchlist(self, client):
        data = client.get("/api/scan").get_json()
        assert {r["symbol"] for r in data["rows"]} == {"AAPL", "TSLA"}

    def test_api_scan_bad_params_fall_back(self, client):
        resp = client.get("/api/scan?tickers=AAPL&source=evil&atr_length=nope")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["params"]["source"] == "offline"   # falls back to app default
        assert data["params"]["atr_length"] == 14

    def test_api_chart(self, client):
        resp = client.get("/api/chart/AAPL?source=offline")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] and data["symbol"] == "AAPL"
        assert data["bars"], "expected chart bars"
        bar = data["bars"][-1]
        for key in ("date", "open", "high", "low", "close", "atr", "dtr",
                    "dtr_pct", "status"):
            assert key in bar
        assert bar["high"] >= bar["low"]
        # Headline numbers agree with the last bar of the series.
        assert data["dtr_pct"] == bar["dtr_pct"]

    def test_api_chart_failure_404(self, client, monkeypatch):
        import jadentradebot.scanner as scanner_mod

        def boom(symbol, **kwargs):
            raise LookupError("nope")

        monkeypatch.setattr(scanner_mod, "fetch_daily", boom)
        resp = client.get("/api/chart/GONE?source=offline")
        assert resp.status_code == 404
        assert not resp.get_json()["ok"]
