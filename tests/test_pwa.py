"""PWA surface tests: manifest, service worker, icons, template wiring,
and static-build asset copying."""

import json
from pathlib import Path

from jadentradebot.sitegen import build_site
from jadentradebot.web.app import create_app

REPO = Path(__file__).resolve().parents[1]
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def client():
    app = create_app(watchlist=["AAPL"], source="offline")
    return app.test_client()


class TestPwaEndpoints:
    def test_manifest(self):
        resp = client().get("/manifest.webmanifest")
        assert resp.status_code == 200
        assert resp.mimetype == "application/manifest+json"
        m = json.loads(resp.get_data(as_text=True))
        assert m["name"] == "Jaden's Risk Calculator"
        assert m["short_name"] == "JRC"
        assert m["display"] == "standalone"
        assert m["start_url"] == "./"
        assert len(m["icons"]) >= 3
        assert any(i.get("purpose") == "maskable" for i in m["icons"])

    def test_service_worker(self):
        resp = client().get("/sw.js")
        assert resp.status_code == 200
        assert resp.mimetype == "application/javascript"
        body = resp.get_data(as_text=True)
        assert "addEventListener" in body and "caches" in body

    def test_icons(self):
        c = client()
        for path in ("/icons/icon-180.png", "/icons/icon-192.png",
                     "/icons/icon-512.png", "/icons/icon-512-maskable.png",
                     "/apple-touch-icon.png"):
            resp = c.get(path)
            assert resp.status_code == 200, path
            assert resp.data.startswith(PNG_MAGIC), path

    def test_background_asset(self):
        resp = client().get("/bg.jpg")
        assert resp.status_code == 200
        assert resp.mimetype == "image/jpeg"
        assert resp.data.startswith(b"\xff\xd8\xff")  # JPEG magic

    def test_background_video(self):
        resp = client().get("/bg.mp4")
        assert resp.status_code == 200
        assert resp.mimetype == "video/mp4"
        assert resp.data[4:8] == b"ftyp"  # MP4 container magic
        # Range requests must work for Safari streaming
        partial = client().get("/bg.mp4", headers={"Range": "bytes=0-99"})
        assert partial.status_code == 206
        assert len(partial.data) == 100
        webm = client().get("/bg.webm")
        assert webm.status_code == 200
        assert webm.mimetype == "video/webm"
        assert webm.data.startswith(b"\x1a\x45\xdf\xa3")  # EBML magic

    def test_template_wiring(self):
        html = client().get("/").get_data(as_text=True)
        assert 'rel="manifest"' in html
        assert 'rel="apple-touch-icon"' in html
        assert "serviceWorker" in html and 'register("sw.js")' in html
        assert 'content="black-translucent"' in html


class TestPwaStaticBuild:
    def test_sitegen_copies_pwa_assets(self, tmp_path):
        out = tmp_path / "site"
        build_site(out, symbols=["AAPL"], source="offline")
        assert (out / "manifest.webmanifest").exists()
        assert (out / "sw.js").exists()
        assert (out / "bg.jpg").read_bytes().startswith(b"\xff\xd8\xff")
        assert (out / "bg.mp4").read_bytes()[4:8] == b"ftyp"
        assert (out / "bg.webm").read_bytes().startswith(b"\x1a\x45\xdf\xa3")
        assert (out / "apple-touch-icon.png").read_bytes().startswith(PNG_MAGIC)
        for name in ("icon-180.png", "icon-192.png", "icon-512.png",
                     "icon-512-maskable.png"):
            assert (out / "icons" / name).read_bytes().startswith(PNG_MAGIC)
