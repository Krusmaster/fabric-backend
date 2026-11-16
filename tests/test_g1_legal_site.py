"""G1 (15 November 2026): the site's company details, cookies and storage, the legal pages and accessibility.

- /cookies and /accessibility exist, are in the sitemap and are linked from every page's footer, with the cookie panel;
- the footer carries the company details, with a marked placeholder for what the deployment has not set;
- legal.STORAGE lists every key the site's scripts write and every cookie the service sets, and nothing else sets one;
- /privacy names the controller, legal bases, processors, the AI clients as the user's choice, transfers, retention,
  rights and the authorities (IMY, FDPIC), and links /cookies;
- /terms has refunds pointing at Microsoft Marketplace's policy, and the font licences;
- no page says it is compliant or certified;
- in a browser (tests/g1_site_browser.js, when Playwright is present): no request to another host, nothing stored before
  a click, alt text, names, AA contrast in both themes, the cookie panel from the keyboard.
"""
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from fabric_backend import legal, server
from fabric_backend.discovery import PUBLIC_PAGES

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "fabric_backend" / "static"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PRODUCT_NAME", "Krusgraph")
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://krusgraph.test/mcp")
    monkeypatch.setenv("CONTACT_EMAIL", "hello@krusgraph.test")
    for name in ("COMPANY_ORGNR", "COMPANY_ADDRESS", "COMPANY_VAT"):     # the defaults in legal.py apply
        monkeypatch.delenv(name, raising=False)
    return TestClient(server.build_app())


def _footer(html: str) -> str:
    return html.split('<footer class="site-footer">')[1]


def test_cookies_and_accessibility_pages_exist_and_are_listed(client):
    for path in ("/cookies", "/accessibility"):
        r = client.get(path)
        assert r.status_code == 200 and "{{" not in r.text, path
        assert path in PUBLIC_PAGES
    assert "https://krusgraph.test/cookies" in client.get("/sitemap.xml").text


def test_every_public_page_links_the_legal_pages_and_has_the_cookie_panel(client):
    for path in PUBLIC_PAGES:
        f = _footer(client.get(path).text)
        for href in ("/privacy", "/cookies", "/terms", "/accessibility"):
            assert f'href="{href}"' in f, (path, href)
        assert '<details class="cookie-panel">' in f and 'class="storage-list' in f and "<summary" in f and "Cookies and storage" in f, path


def test_the_cookie_button_is_the_mascot_pill_under_it_with_the_note_below(client):
    """n241 (the founder's design): 'Cookies and storage' has the 'Mascots: on' pill's classes and no card of its own,
    and the order is Mascots, Cookies, the note; on a page without mascots only the cookie pill is there."""
    f = _footer(client.get("/").text)
    assert '<summary class="btn ghost small">' in f and 'class="btn ghost small" data-mascot-toggle' in f
    assert f.index("data-mascot-toggle") < f.index('class="cookie-panel"') < f.index('id="mascot-toggle-note"')
    css = (STATIC / "site.css").read_text(encoding="utf-8")
    assert ".footer-controls .cookie-panel{background:none;border:0;border-radius:0;padding:0;margin:0}" in css
    assert "cookie-btn" not in f                                       # no class of its own: n240's mobile .btn.small rule sizes both
    f = _footer(client.get("/cookies").text)
    if "data-mascot-toggle" not in f:
        assert '<summary class="btn ghost small">' in f and "mascot-toggle-note" not in f


def test_footer_company_details_from_the_registry_overridable_and_marked_when_empty(client, monkeypatch):
    f = _footer(client.get("/").text)
    assert "Kruse Consulting AB · Org. no. 559174-8719 · Svartmangatan 4 D, 753 12 Uppsala" in f
    assert "mailto:hello@krusgraph.test" in f and "to be added" not in f and legal.missing() == []
    monkeypatch.setenv("COMPANY_ORGNR", "556000-0000")
    monkeypatch.setenv("COMPANY_ADDRESS", "Exempelgatan 1, 753 20 Uppsala")
    monkeypatch.setenv("COMPANY_VAT", "SE556000000001")
    f = _footer(client.get("/").text)
    assert "Kruse Consulting AB · Org. no. 556000-0000 · Exempelgatan 1, 753 20 Uppsala · VAT no. SE556000000001" in f
    monkeypatch.setenv("COMPANY_ADDRESS", "")                          # set but empty: a marked placeholder, never a guess
    assert "[registered address to be added]" in _footer(client.get("/").text) and legal.missing() == ["COMPANY_ADDRESS"]


def _script_keys() -> set[str]:
    keys = set()
    for js in STATIC.glob("*.js"):
        src = js.read_text(encoding="utf-8")
        if "Storage" not in src:
            continue
        keys |= set(re.findall(r"(?:local|session)Storage\.setItem\('([^']+)'", src))
        if re.search(r"(?:local|session)Storage\.setItem\(KEY", src):
            keys |= set(re.findall(r"var KEY = '([^']+)'", src))
    return keys


def test_storage_list_matches_the_scripts():
    assert _script_keys() == set(legal.SCRIPT_KEYS)
    names = " ".join(n for n, *_ in legal.STORAGE)
    for key in legal.SCRIPT_KEYS:
        assert key in names
    for js in STATIC.glob("*.js"):                                     # no cookie from a script, no IndexedDB
        src = js.read_text(encoding="utf-8")
        assert "document.cookie" not in src and "indexedDB" not in src, js.name


def test_every_cookie_the_service_sets_is_listed():
    from fabric_backend import marketplace, registration_flow
    names = [registration_flow.CSRF_COOKIE, registration_flow.USER_COOKIE, registration_flow.FLOW_COOKIE,
             marketplace.FLOW_COOKIE, marketplace.SESSION_COOKIE]
    listed = " ".join(n for n, *_ in legal.STORAGE)
    for name in names:
        assert name in legal.COOKIE_PREFIXES and name in listed, name
    setters = [p.name for p in (ROOT / "fabric_backend").glob("*.py") if "set_cookie(" in p.read_text(encoding="utf-8")]
    assert sorted(setters) == ["marketplace.py", "registration_flow.py"]


def test_cookies_page_lists_everything_and_says_no_banner_is_needed(client):
    html = client.get("/cookies").text
    for name, kind, *_ in legal.STORAGE:
        assert name in html and kind in html
    assert "no banner" in html and "Reject" in html


def test_privacy_covers_the_gdpr_points(client):
    html = client.get("/privacy").text
    for words in ("Who is responsible", "controller", "processor", "Legal basis", "Who else processes it", "Microsoft",
                  "Azure", "Transfers outside the EU", "How long it is kept", "Data processing for organisations",
                  "ChatGPT", "OpenAI", "Copilot", "Anthropic", "IMY", "FDPIC", "ICO", 'href="/cookies"',
                  "559174-8719", "Svartmangatan 4 D, 753 12 Uppsala, Sweden", "Swiss Federal Act on Data Protection"):
        assert words in html, words
    md = client.get("/privacy.md").text
    assert "Who is responsible" in md and "{{" not in md


def test_privacy_lists_what_the_usage_records_carry():
    from fabric_backend import usage
    text = (ROOT / "fabric_backend" / "page_templates" / "PRIVACY.md").read_text(encoding="utf-8")
    for field in usage.FIELDS:
        assert f"`{field}`" in text, field
    assert "four pages" in text and "five pages" not in text and len(usage.PAGE_VIEW_PATHS) == 4


def test_terms_have_refunds_and_licences(client):
    html = client.get("/terms").text
    assert 'id="refunds"' in html and "https://learn.microsoft.com/en-us/marketplace/refund-policies" in html
    assert "SIL Open Font License" in html and client.get("/static/fonts/OFL-Fredoka.txt").status_code == 200


def test_no_page_claims_compliance_or_certification(client):
    for path in PUBLIC_PAGES + ["/privacy.md"]:
        low = re.sub(r"<[^>]+>", " ", client.get(path).text).lower()
        for banned in ("gdpr compliant", "gdpr-compliant", "fully compliant", "wcag compliant", "fully accessible",
                       "100% accessible"):
            assert banned not in low, (path, banned)


def test_every_image_on_the_public_pages_has_alt_text(client):
    for path in PUBLIC_PAGES:
        for tag in re.findall(r"<img\b[^>]*>", client.get(path).text):
            assert re.search(r"\balt=", tag), (path, tag)


# ------------------------------------------------------------------ in a browser ---------------------------------

CHROMIUM = os.environ.get("PLAYWRIGHT_CHROMIUM") or ""


def _playwright() -> bool:
    return bool(shutil.which("node")) and subprocess.run(["node", "-e", "require('playwright')"], capture_output=True).returncode == 0


@pytest.mark.skipif(not _playwright(), reason="node + playwright not available")
def test_in_a_browser_nothing_third_party_nothing_stored_contrast_names_and_the_cookie_panel():
    sock = socket.socket(); sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]; sock.close()
    env = os.environ | {"PRODUCT_NAME": "Krusgraph", "MCP_PUBLIC_URL": "https://krusgraph.test/mcp", "CONTACT_EMAIL": "hello@krusgraph.test",
                        "ENTRA_CLIENT_ID": "00000000-0000-0000-0000-000000000000", "ENTRA_CLIENT_SECRET": "test-only"}
    proc = subprocess.Popen([sys.executable, "-m", "fabric_backend.server", "--host", "127.0.0.1", "--port", str(port)], env=env,
                            cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(base + "/healthz", timeout=1); break
            except Exception:
                time.sleep(0.25)
        else:
            pytest.fail("server did not start")
        out = subprocess.run(["node", str(ROOT / "tests" / "g1_site_browser.js"), base, json.dumps(PUBLIC_PAGES)] + ([CHROMIUM] if CHROMIUM else []),
                             capture_output=True, text=True, timeout=600)
        assert out.returncode == 0, out.stderr[-2000:]
        report = json.loads(out.stdout.strip().splitlines()[-1])
        assert report["pages"] == len(PUBLIC_PAGES)
        assert report["problems"] == [], report["problems"][:20]
    finally:
        proc.terminate(); proc.wait(timeout=10)


def test_no_personal_address_on_the_site(client):
    """G1 (15 November 2026): every address the site gives is the company's, hello@krusgraph.com (the test deployment's
    CONTACT_EMAIL here); no personal mailbox on a page, its Markdown twin, security.txt, llms.txt or the attestation."""
    from fabric_backend.pages import MARKDOWN_TWINS
    paths = (PUBLIC_PAGES + [p + ".md" for p in MARKDOWN_TWINS]
             + ["/.well-known/security.txt", "/llms.txt", "/llms-full.txt", "/workload/attestation", "/workload/attestation.md"])
    for path in paths:
        r = client.get(path)
        assert r.status_code == 200, path
        for address in re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", r.text):
            if "." in address.split("@")[1] and not address.endswith((".js", ".css", ".png", ".svg", ".woff2", ".webp")):
                assert address.split("@")[0] in {"hello", "security", "noreply"} and "gmail" not in address, (path, address)
