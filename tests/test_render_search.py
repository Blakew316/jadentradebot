"""Tests for the Render deployment surface and live-search support:
env-var app config, /api/symbols, /healthz, the data TTL cache, and the
search UI markup in both template modes."""

import json
from pathlib import Path

import pandas as pd
import pytest

import jadentradebot.data as data_mod
from jadentradebot.data import fetch_daily, sample_daily
from jadentradebot.web.app import create_app

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def clean_cache():
    data_mod.clear_cache()
    yield
    data_mod.clear_cache()


class TestSymbolsDirectory:
    def test_file_is_valid_and_well_formed(self):
        entries = json.loads(
            (REPO / "jadentradebot" / "web" / "symbols.json").read_text()
        )
        assert len(entries) > 150
        seen = set()
        for e in entries:
            assert set(e) == {"symbol", "name"}
            assert e["symbol"] == e["symbol"].upper()
            assert e["symbol"] not in seen, f"duplicate {e['symbol']}"
            seen.add(e["symbol"])
            assert len(e["name"]) > 1

    def test_api_symbols_endpoint(self):
        app = create_app(watchlist=["AAPL"], source="offline")
        client = app.test_client()
        resp = client.get("/api/symbols")
        assert resp.status_code == 200
        entries = resp.get_json()
        assert any(e["symbol"] == "PLTR" for e in entries)

    def test_healthz(self):
        app = create_app(watchlist=["AAPL"], source="offline")
        resp = app.test_client().get("/healthz")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "ok"


class TestEnvConfig:
    def test_env_vars_configure_the_app(self, monkeypatch):
        monkeypatch.setenv("WATCHLIST", "pltr, coin ,")
        monkeypatch.setenv("DATA_SOURCE", "offline")
        monkeypatch.setenv("ATR_LENGTH", "21")
        monkeypatch.setenv("LOOKBACK_DAYS", "90")
        app = create_app()
        assert app.config["WATCHLIST"] == ["PLTR", "COIN"]
        assert app.config["SOURCE"] == "offline"
        assert app.config["ATR_LENGTH"] == 21
        assert app.config["LOOKBACK_DAYS"] == 90

    def test_bad_env_values_fall_back(self, monkeypatch):
        monkeypatch.setenv("DATA_SOURCE", "bloomberg")
        monkeypatch.setenv("ATR_LENGTH", "not-a-number")
        app = create_app()
        assert app.config["SOURCE"] == "auto"
        assert app.config["ATR_LENGTH"] == 14

    def test_explicit_args_beat_env(self, monkeypatch):
        monkeypatch.setenv("WATCHLIST", "PLTR")
        monkeypatch.setenv("DATA_SOURCE", "offline")
        app = create_app(watchlist=["NVDA"], source="stooq")
        assert app.config["WATCHLIST"] == ["NVDA"]
        assert app.config["SOURCE"] == "stooq"


class TestDataCache:
    def test_live_fetch_is_cached_within_ttl(self, monkeypatch):
        calls = []

        def fake_yf(symbol, lookback_days):
            calls.append(symbol)
            return sample_daily(symbol, lookback_days)

        monkeypatch.setattr(data_mod, "fetch_yfinance", fake_yf)
        monkeypatch.setattr(data_mod, "CACHE_TTL_SECONDS", 300)
        a = fetch_daily("CACHETEST", source="yfinance")
        b = fetch_daily("CACHETEST", source="yfinance")
        assert calls == ["CACHETEST"]          # second hit served from cache
        pd.testing.assert_frame_equal(a, b)
        # Returned frames are copies — mutating one must not poison the cache.
        a.iloc[0, 0] = -1
        c = fetch_daily("CACHETEST", source="yfinance")
        assert c.iloc[0, 0] != -1

    def test_ttl_zero_disables_cache(self, monkeypatch):
        calls = []

        def fake_yf(symbol, lookback_days):
            calls.append(symbol)
            return sample_daily(symbol, lookback_days)

        monkeypatch.setattr(data_mod, "fetch_yfinance", fake_yf)
        monkeypatch.setattr(data_mod, "CACHE_TTL_SECONDS", 0)
        fetch_daily("NOCACHE", source="yfinance")
        fetch_daily("NOCACHE", source="yfinance")
        assert calls == ["NOCACHE", "NOCACHE"]

    def test_offline_is_never_cached(self, monkeypatch):
        monkeypatch.setattr(data_mod, "CACHE_TTL_SECONDS", 300)
        fetch_daily("AAPL", source="offline")
        assert not data_mod._cache


class TestCalculatorOnlySite:
    """The site is now a single-purpose calculator page: no scan table,
    search bar, chips, or chart — but the JSON API remains available."""

    def test_dashboard_elements_removed(self):
        app = create_app(watchlist=["AAPL"], source="offline")
        html = app.test_client().get("/").get_data(as_text=True)
        for gone in ('id="scanBtn"', 'id="search"', 'id="addBtn"',
                     'id="tickers"', 'id="tbody"', 'id="chartPanel"'):
            assert gone not in html
        assert 'id="themeBtn"' in html   # dark-mode toggle

    def test_api_still_available(self):
        app = create_app(watchlist=["AAPL"], source="offline")
        client = app.test_client()
        assert client.get("/api/scan").status_code == 200
        assert client.get("/api/symbols").status_code == 200
        assert client.get("/healthz").status_code == 200


class TestCalculator:
    """Jaden's Risk Calculator — shares-only risk sizing (Calconic-derived
    structure with the option row, sheet link, and prefill removed)."""

    def test_dynamic_page_has_calculator(self):
        app = create_app(watchlist=["AAPL"], source="offline")
        html = app.test_client().get("/").get_data(as_text=True)
        assert "Risk Calculator" in html
        for el in ("cAccount", "cRisk", "cEntry", "cStop", "rShares"):
            assert f'id="{el}"' in html
        # Removed on request: prefill, option row, spreadsheet link.
        for gone in ('id="cSymbol"', 'id="cOption"', 'id="rOptions"',
                     "Option Value", "Options to Buy",
                     "sheet.zohopublic.com", "SAR RISK MANAGEMENT SHEET"):
            assert gone not in html, gone
        for text in ("0.25%", "0.5%", "Account Size", "Entry Price",
                     "Stop Loss Price", "Shares to Buy", "Risking 1%"):
            assert text in html, text
        assert "Account Size $" not in html   # label's trailing $ removed
        assert 'value="10,000"' not in html   # no default account size

    def test_static_page_has_calculator(self, tmp_path):
        from jadentradebot.sitegen import build_site

        build_site(tmp_path / "s", symbols=["AAPL"], source="offline")
        html = (tmp_path / "s" / "index.html").read_text()
        assert "Risk Calculator" in html
        assert 'id="cRisk"' in html


class TestRenderBlueprint:
    def test_render_yaml_is_valid_and_complete(self):
        import yaml

        cfg = yaml.safe_load((REPO / "render.yaml").read_text())
        svc = cfg["services"][0]
        assert svc["type"] == "web"
        assert "gunicorn" in svc["startCommand"]
        assert "jadentradebot.web.app:app" in svc["startCommand"]
        assert svc["healthCheckPath"] == "/healthz"
        env_keys = {e["key"] for e in svc["envVars"]}
        assert {"WATCHLIST", "DATA_SOURCE", "ATR_LENGTH"} <= env_keys

    def test_gunicorn_in_requirements(self):
        assert "gunicorn" in (REPO / "requirements.txt").read_text()
