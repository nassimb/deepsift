"""Site footer: GitHub link in the footer (not the header), contact address not present in page HTML, updates form."""

import re
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[3] / "apps/web"
ADDRESS = "nassimmontreal@gmail.com"


def test_contact_address_not_written_in_source():
    for p in list((WEB / "components").rglob("*.tsx")) + list((WEB / "app").rglob("*.tsx")) + list((WEB / "lib").rglob("*.ts")):
        assert ADDRESS not in p.read_text(), p


def test_github_link_moved_to_footer():
    nav = (WEB / "components/release/NavLinks.tsx").read_text()
    assert "GitHub" not in nav and "GITHUB_URL" not in nav
    assert "usePathname" in nav  # active page highlighted on every page, not only Mission Control
    footer = (WEB / "components/site/SiteFooter.tsx").read_text()
    assert "https://github.com/nassimb/deepsift" in footer and "/api/subscribe" in footer


def test_subscribe_route_is_server_only_and_validates():
    route = (WEB / "app/api/subscribe/route.ts").read_text()
    assert "process.env.DATABASE_URL" in route and "NEXT_PUBLIC" not in route
    assert "ON CONFLICT" in route and "website" in route  # idempotent insert + honeypot


@pytest.mark.parametrize("page", ["index.html", "mission-control.html", "final-test.html", "research.html"])
def test_rendered_pages_have_footer_and_no_address(page):
    html = WEB / ".next/server/app" / page
    if not html.exists():
        pytest.skip("web app not built")
    text = html.read_text()
    assert ADDRESS not in text
    assert "Get DEEPSIFT updates" in text and "https://github.com/nassimb/deepsift" in text
    header = re.search(r"<header.*?</header>", text, re.S)
    assert header and "github.com/nassimb/deepsift" not in header.group(0)
