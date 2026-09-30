"""Private /admin comms console: server-side auth, no public exposure, no secrets client-side, zero paid/X-API/LLM deps,
and no change to frozen science."""

import json
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
WEB = ROOT / "apps/web"
ADMIN_SRC = [*(WEB / "app/admin").rglob("*.tsx"), *(WEB / "components/comms").rglob("*.tsx"), *(WEB / "lib/comms").glob("*.ts"),
             WEB / "lib/admin/access.ts", WEB / "auth.ts", WEB / "proxy.ts"]
PUBLIC_SRC = [WEB / "components/release/NavLinks.tsx", WEB / "components/release/Shell.tsx", WEB / "components/site/SiteFooter.tsx",
              WEB / "app/page.tsx", WEB / "components/Nav.tsx", WEB / "app/layout.tsx"]


def test_admin_is_gated_server_side_by_proxy_and_layout():
    proxy = (WEB / "proxy.ts").read_text()
    assert 'matcher: ["/admin", "/admin/:path*"]' in proxy
    assert "adminAccess(" in proxy and "403" in proxy and "authConfigured(process.env)" in proxy
    layout = (WEB / "app/admin/comms/layout.tsx").read_text()
    assert "await auth()" in layout and "adminAccess(" in layout and '"use client"' not in layout
    access = (WEB / "lib/admin/access.ts").read_text()
    assert 'ADMIN_GITHUB_LOGIN = "nassimb"' in access and "ADMIN_GITHUB_ID = 3143068" in access


def test_no_auth_secret_in_client_code_or_public_env():
    for p in ADMIN_SRC:
        src = p.read_text()
        assert not re.search(r"NEXT_PUBLIC_[A-Z_]*(AUTH|GITHUB|SECRET)", src), p
        if src.lstrip().startswith('"use client"'):
            assert "process.env" not in src and "AUTH_SECRET" not in src and "GITHUB_SECRET" not in src, p
    assert not re.search(r"(ghp_|gho_|github_pat_)[A-Za-z0-9]", "".join(p.read_text() for p in ADMIN_SRC))


def test_admin_not_linked_from_public_pages_or_sitemap():
    for p in PUBLIC_SRC:
        assert "/admin" not in p.read_text(), p
    assert not (WEB / "app/sitemap.ts").exists() and not (WEB / "public/sitemap.xml").exists()
    robots = WEB / "app/robots.ts"
    assert not robots.exists() or "/admin" not in robots.read_text()


def test_zero_cost_no_x_api_no_paid_scheduler_no_llm():
    pkg = json.loads((WEB / "package.json").read_text())
    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    for bad in ("twitter-api-v2", "openai", "@anthropic-ai/sdk", "@google/generative-ai", "buffer", "hootsuite", "metricool", "openrouter"):
        assert bad not in deps, bad
    blob = "".join(p.read_text() for p in ADMIN_SRC)
    assert "api.twitter.com" not in blob and "api.x.com" not in blob
    # the only fetch is the clipboard helper reading a same-origin image; no request ever leaves the site
    fetchers = [p for p in ADMIN_SRC if "fetch(" in p.read_text() and "live-data" not in p.parts]  # /admin/live-data reads the local collector (tested in test_live_observatory)
    assert [p.name for p in fetchers] == ["clipboardImage.ts"], fetchers
    assert not re.search(r"fetch\(\s*[\"'`]https?:", blob)
    for s in ("openai", "anthropic.com", "generativelanguage", "openrouter", "TYPESAFE_API_KEY", "metricool", "buffer.com", "hootsuite"):
        assert s not in blob.lower() if s.islower() else s not in blob, s
    xi = (WEB / "lib/comms/xintent.ts").read_text()
    assert 'X_INTENT_BASE = "https://x.com/intent/tweet"' in xi


def test_editorial_state_is_browser_local_only():
    store = (WEB / "lib/comms/store.ts").read_text()
    assert "localStorage" in store and "fetch(" not in store
    assert "Editorial state is stored locally in this browser in v1." in (WEB / "components/comms/views.tsx").read_text()


def test_frozen_science_unchanged_by_this_feature():
    changed = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout
    rec = json.loads((ROOT / "docs/release/science-artifacts.json").read_text())["sha256"]
    for line in changed.splitlines():
        path = line[3:].strip()
        assert path not in rec, f"frozen science file modified: {path}"


def test_rendered_public_pages_do_not_mention_admin():
    app = WEB / ".next/server/app"
    if not app.exists():
        pytest.skip("web app not built")
    for name in ("index.html", "mission-control.html", "final-test.html", "research.html", "reproducibility.html", "limitations.html"):
        f = app / name
        if f.exists():
            assert "/admin" not in f.read_text(), name


def test_manual_only_no_social_automation_infrastructure():
    """Comms stays manual: no X API/OAuth/tokens, no scheduler, no post queue; OPEN IN X is the web intent only."""
    routes = sorted(p.parent.relative_to(WEB / "app/api").as_posix() for p in (WEB / "app/api").rglob("route.ts"))
    non_live = [r for r in routes if not r.startswith("live/")]
    assert non_live == ["auth/[...nextauth]", "subscribe"], routes
    # the Live Observatory routes are read-only (GET only) and never talk to X
    for r in (WEB / "app/api/live").rglob("route.ts"):
        src = r.read_text()
        assert "export async function POST" not in src and "export function POST" not in src, r
        assert "x.com" not in src and "twitter" not in src.lower(), r
    assert not (WEB / "vercel.json").exists() and not (ROOT / "vercel.json").exists()
    wf = ROOT / ".github/workflows"
    assert not wf.exists() or not any("schedule" in p.read_text() for p in wf.glob("*.y*ml"))
    blob = "".join(p.read_text() for p in ADMIN_SRC).lower()
    for s in ("api.x.com", "api.twitter.com", "/2/tweets", "media/upload", "refresh_token", "access_token", "oauth2/token", "cron", "x_client", "twitter_"):
        assert s not in blob, s
    assert "x.com/intent/tweet" in blob
    subscribe = (WEB / "app/api/subscribe/route.ts").read_text().lower()
    assert "tweet" not in subscribe and "x.com" not in subscribe
