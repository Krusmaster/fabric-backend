"""BL30 (21 November 2026, backlog C-09): /scores shows docs/scores.json as it is.

- the page's numbers are the file's numbers, per corpus: keys right, wrong, missed and extra, links found, missed
  (true minus found) and wrong, read when the page is opened (a changed file changes the page without a restart);
- misses and wrong answers are shown in the same tables as the hits, and one line says the corpora are synthetic or
  public schemas and links docs/SCORES.md for how to run them again;
- the date and commit of the numbers come from git when the clone is full; otherwise the page links the file's history;
- a build without the file says so and links the repository, and never shows a number;
- the page is in the sitemap and in PUBLIC_PAGES, so the site's claim-word, alt-text and browser checks (tests/test_site.py,
  tests/test_g1_legal_site.py: contrast in light and dark at 375 and 1280 px) cover it; here, in a browser when one is
  present, it fits a 375 px phone without sideways scrolling in both themes.
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

from fabric_backend import discovery, pages, server

ROOT = Path(__file__).resolve().parents[1]
SCORES = json.loads((ROOT / "docs" / "scores.json").read_text(encoding="utf-8"))


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PRODUCT_NAME", "Krusgraph")
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://krusgraph.test/mcp")
    monkeypatch.setenv("CONTACT_EMAIL", "hello@krusgraph.test")
    monkeypatch.setenv("ENTRA_CLIENT_ID", "cid-123")
    with TestClient(server.build_app()) as c:
        yield c


def _plain(s: str) -> str:
    s = re.sub(r"<script\b.*?</script>|<style\b.*?</style>", " ", s, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)).strip()


def _rows(page: str, table_class: str) -> dict[str, list[int]]:
    table = re.search(rf'<table class="{table_class}">(.*?)</table>', page, re.S).group(1)
    out = {}
    for tr in re.findall(r"<tbody>(.*?)</tbody>", table, re.S)[0].split("</tr>"):
        name = re.search(r"<code>([\w-]+)</code>", tr)
        if name:
            out[name.group(1)] = [int(x) for x in re.findall(r"<td>(\d+)</td>", tr)]
    return out


def test_scores_is_served_and_listed(client):
    r = client.get("/scores")
    assert r.status_code == 200
    assert "/scores" in discovery.PUBLIC_PAGES
    assert "/scores</loc>" in client.get("/sitemap.xml").text
    main = re.search(r"<main.*?</main>", r.text, re.S).group(0)
    assert "{{" not in main and "}}" not in main


def test_the_numbers_are_the_files_numbers(client):
    page = client.get("/scores").text
    keys, links = _rows(page, "scores-keys"), _rows(page, "scores-links")
    names = [c["name"] for c in SCORES["corpora"]]
    assert list(keys) == names and list(links) == names
    for c in SCORES["corpora"]:
        a = c["after"]
        assert keys[c["name"]] == [a["tables"], a["keys_true"], a["keys_right"], a["keys_wrong"], a["keys_missed"], a["keys_extra"]]
        assert links[c["name"]] == [a["links_true"], a["links_found"], a["links_true"] - a["links_found"], a["links_wrong"]]
        assert c["title"] in _plain(page)


def test_misses_and_wrong_answers_are_shown(client):
    page = client.get("/scores").text
    for head in ("Wrong", "Missed", "Extra"):
        assert f'<th scope="col">{head}</th>' in page
    total_missed = sum(c["after"]["keys_missed"] + c["after"]["links_true"] - c["after"]["links_found"] for c in SCORES["corpora"])
    total_wrong = sum(c["after"]["keys_wrong"] + c["after"]["links_wrong"] for c in SCORES["corpora"])
    assert total_missed > 0 and total_wrong > 0                        # the corpus has misses today, and the page has them
    keys, links = _rows(page, "scores-keys"), _rows(page, "scores-links")
    assert sum(v[4] for v in keys.values()) + sum(v[2] for v in links.values()) == total_missed
    assert sum(v[3] for v in keys.values()) + sum(v[3] for v in links.values()) == total_wrong


def test_says_synthetic_or_public_and_links_how_to_run_again(client):
    page = client.get("/scores").text
    t = _plain(page)
    assert "The corpora are synthetic rows or public schemas, never a customer's data" in t
    assert "nothing here was run in Fabric" in t
    assert 'href="https://github.com/Krusmaster/fabric-backend/blob/main/docs/SCORES.md"' in page


def test_no_adjective_or_comparison_beyond_the_numbers(client):
    t = _plain(re.search(r"<main.*?</main>", client.get("/scores").text, re.S).group(0)).lower()
    for w in ("accurate", "accuracy", "best", "better than", "fast", "reliable", "industry", "leading", "state of the art",
              "percent", "%", "competitor", "proven", "guarantee", "excellent", "high quality"):
        assert w not in t, w


def test_the_file_is_read_when_the_page_is_opened(client, monkeypatch, tmp_path):
    changed = json.loads(json.dumps(SCORES))
    changed["corpora"] = changed["corpora"][:1]
    changed["corpora"][0]["after"]["keys_missed"] = 999
    f = tmp_path / "scores.json"
    f.write_text(json.dumps(changed), encoding="utf-8")
    monkeypatch.setattr(pages, "SCORES_JSON", f)
    keys = _rows(client.get("/scores").text, "scores-keys")
    assert list(keys) == [changed["corpora"][0]["name"]] and keys[changed["corpora"][0]["name"]][4] == 999


def test_without_the_file_the_page_says_so_and_shows_no_number(client, monkeypatch, tmp_path):
    monkeypatch.setattr(pages, "SCORES_JSON", tmp_path / "missing.json")
    page = client.get("/scores").text
    main = re.search(r"<main.*?</main>", page, re.S).group(0)
    assert "This build does not carry" in main and "/blob/main/docs/scores.json" in main
    assert "<table" not in main


def test_the_commit_and_date_from_git_or_the_history_link(client, monkeypatch):
    monkeypatch.setattr(pages, "scores_commit", lambda: ("abc1234", "2026-11-20"))
    t = _plain(client.get("/scores").text)
    assert "last changed in commit abc1234 on 2026-11-20" in t
    monkeypatch.setattr(pages, "scores_commit", lambda: None)
    page = client.get("/scores").text
    assert "The commit and date of every change to these numbers are in" in _plain(page)
    assert f'href="{pages.SCORES_HISTORY}"' in page


def test_scores_commit_is_a_short_hash_and_a_date_or_none():
    got = pages.scores_commit()
    assert got is None or (re.fullmatch(r"[0-9a-f]{4,40}", got[0]) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", got[1]))


def test_the_tables_scroll_on_their_own_from_the_keyboard(client):
    page = client.get("/scores").text
    assert page.count('<div class="table-wrap" tabindex="0" role="region" aria-label=') == 2


def test_the_template_starts_with_its_date_and_round():
    first = (ROOT / "fabric_backend" / "page_templates" / "scores.html").read_text(encoding="utf-8").splitlines()[0]
    assert first.startswith("<!-- 2026-11-21, round BL30")


# ------------------------------------------------------------------ in a browser: 375 px, light and dark ------------

CHROMIUM = os.environ.get("PLAYWRIGHT_CHROMIUM") or ""                 # as tests/test_g1_legal_site.py

PHONE_JS = r"""
const { chromium } = require('playwright');
const [base, executablePath] = process.argv.slice(1);
(async () => {
  const browser = await chromium.launch(executablePath ? { executablePath } : {});
  const out = [];
  for (const scheme of ['light', 'dark']) {
    const ctx = await browser.newContext({ viewport: { width: 375, height: 800 }, colorScheme: scheme });
    const page = await ctx.newPage();
    await page.goto(base + '/scores', { waitUntil: 'networkidle' });
    out.push(await page.evaluate((scheme) => ({
      scheme,
      overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      bg: getComputedStyle(document.body).backgroundColor,
      ink: getComputedStyle(document.querySelector('main h1')).color,
      tables: document.querySelectorAll('main table').length,
    }), scheme));
    await ctx.close();
  }
  await browser.close();
  console.log(JSON.stringify(out));
})().catch(e => { console.error(e); process.exit(1); });
"""


def _playwright() -> bool:
    return bool(shutil.which("node")) and subprocess.run(["node", "-e", "require('playwright')"], capture_output=True).returncode == 0


@pytest.mark.skipif(not _playwright(), reason="node + playwright not available")
def test_fits_a_phone_in_light_and_dark():
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
        out = subprocess.run(["node", "-e", PHONE_JS, base] + ([CHROMIUM] if CHROMIUM else []), capture_output=True, text=True,
                             timeout=300, cwd=ROOT)
        assert out.returncode == 0, out.stderr[-2000:]
        light, dark = json.loads(out.stdout.strip().splitlines()[-1])
        for r in (light, dark):
            assert r["overflow"] <= 0, r                                   # the wide tables scroll inside their own box
            assert r["tables"] == 2, r
        assert light["bg"] != dark["bg"] and light["ink"] != dark["ink"]
    finally:
        proc.terminate(); proc.wait(timeout=10)
