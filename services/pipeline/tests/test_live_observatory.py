"""Live Observatory: operational layer only — truthful labels, attribution, read-only public API, private admin,
local-only collector, and a hard boundary from the frozen science."""

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WEB = ROOT / "apps/web"
OBS = [*(WEB / "lib/observatory").glob("*.ts"), *(WEB / "components/observatory").glob("*.ts*"), *(WEB / "app/api/live").rglob("route.ts"),
       WEB / "app/data-stream/page.tsx", *(ROOT / "services/collector").glob("*.ts")]
SCIENCE = ["artifacts/", "data/manifests", "config/phase3", "docs/release", "@/data/", "release.json", "mission-control.json", "home-summary.json"]


def test_observatory_never_reads_or_writes_science():
    for p in OBS:
        src = p.read_text()
        for bad in SCIENCE:
            assert bad not in src, f"{p.relative_to(ROOT)} references {bad}"


def test_no_fake_live_wording():
    for p in OBS:
        up = p.read_text().upper()
        for bad in ("LIVE FROM MARS", "LIVE ROVER CAMERA", "LIVE CURIOSITY TELEMETRY", "LIVE PERSEVERANCE CAMERA", "LIVE CURIOSITY CAMERA", "LIVE MARS FEED"):
            assert bad not in up, f"{p.name}: {bad}"


def test_truthful_classifications_and_attribution():
    reg = (WEB / "lib/observatory/registry.ts").read_text()
    for sid, cls in [("dsn", "LIVE"), ("noaa", "NEAR REAL-TIME"), ("donki", "NEAR REAL-TIME EVENTS"), ("horizons", "CURRENT COMPUTED"), ("perseverance", "NEWLY PUBLISHED"), ("curiosity", "NEWLY PUBLISHED")]:
        assert re.search(rf'id: "{sid}".*?classification: "{re.escape(cls)}"', reg, re.S), sid
    ui = (WEB / "components/observatory/Observatory.tsx").read_text()
    assert "Not affiliated with or endorsed by NASA, JPL, NOAA or mission teams." in ui
    assert "EARTH / L1 SPACE ENVIRONMENT — NOT MARS CONDITIONS" in ui
    assert "COMPUTED BY JPL HORIZONS" in ui and "NOT TELEMETRY" in ui
    assert "MARS-LINKED DSN ACTIVITY" in ui
    assert "never claimed to carry any specific image" in ui
    assert "RESEARCH ARCHIVE" in ui and "ARCHIVAL / RESEARCH" in ui


def test_public_routes_read_only_and_no_secrets():
    for p in (WEB / "app/api/live").rglob("route.ts"):
        src = p.read_text()
        assert "POST" not in src and "NEXT_PUBLIC_" not in src, p
    proxy = (WEB / "app/api/live/collector/[...path]/route.ts").read_text()
    assert "ALLOWED" in proxy and '"admin' not in proxy, "the public proxy cannot reach collector admin endpoints"
    assert "COLLECTOR_ADMIN_TOKEN" not in proxy
    for p in (WEB / "components/observatory").glob("*.ts*"):
        assert "COLLECTOR_ADMIN_TOKEN" not in p.read_text() and "process.env" not in p.read_text(), p


def test_collector_local_only_and_token_protected():
    c = (ROOT / "services/collector/collector.ts").read_text()
    assert 'server.listen(PORT, "127.0.0.1"' in c
    assert 'auth !== `Bearer ${ADMIN_TOKEN}`' in c and "!ADMIN_TOKEN ||" in c
    assert '"/admin/refresh"' in c and 'req.method === "POST"' in c


def test_admin_live_data_is_private():
    page = (WEB / "app/admin/live-data/page.tsx").read_text()
    assert "adminAccess(" in page and "await auth()" in page and "noindex" not in page or "index: false" in page
    proxy = (WEB / "proxy.ts").read_text()
    assert '"/admin/:path*"' in proxy
    nav = (WEB / "components/release/NavLinks.tsx").read_text()
    assert '"/data-stream"' in nav and "/admin" not in nav


def test_runtime_store_is_gitignored_and_outside_science():
    assert "/live_observatory/data/" in (ROOT / ".gitignore").read_text()
    tracked = subprocess.run(["git", "ls-files", "live_observatory/data"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    assert tracked == ""
    rec = json.loads((ROOT / "docs/release/science-artifacts.json").read_text())["sha256"]
    assert not any(k.startswith(("live_observatory", "services/collector", "apps/web/lib/observatory")) for k in rec)


def test_fixture_tests_never_hit_the_network():
    for t in (WEB / "tests").glob("observatory-*.test.ts"):
        src = t.read_text()
        assert "fetch(" not in src and "fetchDsn" not in src and "https://eyes" not in src, t
