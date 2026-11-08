"""Round n164: the mascots' names follow their new colours (the founder's decision of 7-8 November 2026).

Onto is green (maps how the data connects and says the numbers), the Thinker violet (checks against the rows, finds
what does not hold, asks the questions), the Builder coral (builds, always after a dry run). The roles stay where the
code uses them; what changed is which figure and colour each name maps to.

Checked here: the mapping (name → colour → token → figure) is in one place, `KINDS` in static/mascots.js, and site.css's
--onto, --thinker and --builder tokens agree with it; no stylesheet rule, page, note, pill or card pairs a name with
another mascot's colour; no text on the site, in the README or in docs/SITE.md describes a mascot by an old colour; the
alt texts say the new colour and role; and in Chromium the chat demo, /mascots and an MCP Apps card render each name in
its own colour, light and dark.
"""
from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from fabric_backend import discovery, mcp_apps, mcp_apps_mascots, mcp_apps_review, pages

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "fabric_backend" / "static"
TEMPLATES = ROOT / "fabric_backend" / "page_templates"
CHROMIUM = os.environ.get("PLAYWRIGHT_CHROMIUM") or ("/opt/pw-browsers/chromium" if Path("/opt/pw-browsers/chromium").exists() else "")

# The decision, written once here so the test does not read its expectation from the code it checks.
NEW = {
    "onto": {"colour": "green", "fill": "#9DB8A0", "palette": "sage", "role": ("numbers",)},
    "thinker": {"colour": "violet", "fill": "#A99AD8", "palette": "lav", "role": ("checks", "questions")},
    "builder": {"colour": "coral", "fill": "#F2735C", "palette": "coral", "role": ("builds", "dry run")},
}
# the words a text may use for a colour, by palette family
WORDS = {"sage": ("green", "sage"), "lav": ("violet", "lavender", "purple", "lilac"), "coral": ("coral",)}
CUSHION = "M60 50 C88 50 106 58"            # the wide, low figure (Onto since n164)
PEAR = "M60 29 C75 29 85 45"                # the round pear (the Thinker)
EGG = "M60 20 C79 20 92 46"                 # the upright egg (the Builder)
NAME = {"onto": "Onto", "thinker": "Thinker", "builder": "Builder"}


def _wrong(kind: str) -> set[str]:
    return {f for f in WORDS if f != NEW[kind]["palette"]}


# ------------------------------------------------------------------ the one place --------------------------------------

def test_the_mapping_is_the_new_one_in_kinds():
    k = mcp_apps_mascots.kinds()
    assert list(k) == ["onto", "thinker", "builder"]
    for kind, want in NEW.items():
        assert k[kind]["colour"] == want["colour"], kind
        assert k[kind]["fill"] == want["fill"], kind
        assert k[kind]["token"] == f"--{kind}", kind
    assert k["onto"]["body"].startswith(CUSHION)
    assert k["thinker"]["body"].startswith(PEAR)
    assert k["builder"]["body"].startswith(EGG)


def test_kinds_is_the_only_place_a_name_meets_its_colour():
    """No other file of the package names a mascot's fill: the cards read KINDS, the CSS uses the tokens."""
    fills = {w["fill"].lower() for w in NEW.values()}
    for p in [*STATIC.glob("*.js"), *STATIC.glob("*.css"), *(ROOT / "fabric_backend").glob("mcp_apps*.py")]:
        if p.name == "mascots.js" or "pyodide" in p.parts:
            continue
        text = p.read_text(encoding="utf-8").lower()
        for kind in NEW:
            for line in text.splitlines():
                if re.search(rf"(?<![\w-]){kind}(?![\w-])", line) and any(f in line for f in fills):
                    pytest.fail(f"{p.name}: {line.strip()[:160]}")


def test_the_css_tokens_follow_the_mapping_in_light_and_dark():
    css = (STATIC / "site.css").read_text(encoding="utf-8")
    for kind, want in NEW.items():
        fam = want["palette"]
        for v in ("", "-soft", "-ink", "-d"):
            decl = re.findall(rf"--{kind}{v}\s*:\s*([^;]+);", css)
            assert decl == [f"var(--{fam}{v})"], (kind, v, decl)      # once, in :root: the dark values follow the palette


# ------------------------------------------------------------------ no old colour for a name -----------------------------

def _rules(css: str):
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        yield sel.strip(), body


def _card_css() -> str:
    return mcp_apps_mascots.CSS + mcp_apps.card_html() + mcp_apps_review.card_html()


@pytest.mark.parametrize("name,css", [("site.css", (STATIC / "site.css").read_text(encoding="utf-8")),
                                      ("chat-demo.css", (STATIC / "chat-demo.css").read_text(encoding="utf-8")),
                                      ("cards", None)])
def test_no_stylesheet_rule_gives_a_name_another_colour(name, css):
    css = css if css is not None else "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", _card_css(), re.S)) or _card_css()
    seen = 0
    for sel, body in _rules(css):
        for kind in NEW:
            if not re.search(rf"\.{kind}(?![\w-])", sel):
                continue
            seen += 1
            for fam in _wrong(kind):
                assert not re.search(rf"var\(--{fam}(-|\))", body), (name, sel, body)
            for other, w in NEW.items():
                if other != kind:
                    assert w["fill"].lower() not in body.lower(), (name, sel, body)
    if name == "chat-demo.css":
        assert seen >= 3                                                    # each name has its own colour in the chat


def _sources() -> dict[str, str]:
    out = {}
    for p in [*TEMPLATES.glob("*.html"), *TEMPLATES.glob("*.md"), *STATIC.glob("*.js"),
              ROOT / "fabric_backend" / "pages.py", ROOT / "fabric_backend" / "discovery.py",
              *(ROOT / "fabric_backend").glob("mcp_apps*.py")]:
        out[str(p.relative_to(ROOT))] = p.read_text(encoding="utf-8")
    return out


@pytest.fixture(scope="module")
def client():
    env = {"PRODUCT_NAME": "Krusgraph", "MCP_PUBLIC_URL": "https://krusgraph.test/mcp", "ENTRA_CLIENT_ID": "cid-123"}
    old = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    from fabric_backend.server import build_app
    try:
        with TestClient(build_app()) as c:
            yield c
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _rendered(client) -> dict[str, str]:
    paths = sorted(set(discovery.PUBLIC_PAGES) | {"/mascots", "/llms.txt", "/docs.md"})
    out = {}
    for p in paths:
        r = client.get(p)
        if r.status_code == 200:
            out[p] = r.text
    assert "/mascots" in out and "/" in out and "/llms.txt" in out
    return out


_NOTE = re.compile(r'class="(?:note|pill)\s+([\w-]+)"[^>]*>\s*<span[^>]*data-mascot="(\w+)"')


def test_no_note_or_pill_around_a_mascot_wears_another_colour(client):
    texts = {**_sources(), **_rendered(client)}
    found = 0
    for where, text in texts.items():
        for cls, kind in _NOTE.findall(text):
            if kind not in NEW:
                pytest.fail(f"{where}: data-mascot={kind!r} is not a mascot")
            found += 1
            assert cls == kind or cls == NEW[kind]["palette"], (where, cls, kind)
    assert found >= 3                                                       # demo.js's notes
    for where, text in texts.items():                                       # n164: start.html's "maker" was no mascot
        for kind in re.findall(r'data-mascot="(\w+)"', text):
            assert kind in NEW, (where, kind)


OTHERS = "onto|thinker|builder|is|are|was"                                   # a window stops at another name or a verb


def _old_pairings(text: str) -> list[str]:
    text = re.sub(r"--[\w-]+", "", text)                                    # CSS custom properties are not prose
    text = re.sub(r'class="[^"]*"', "", text)
    bad = []
    for kind in NEW:
        for fam in _wrong(kind):
            for w in WORDS[fam]:
                for pat in (rf"\b{kind}\b(?:(?!\b(?:{OTHERS})\b)[^.\n<;]){{0,25}}\b{w}\b",
                            rf"\b{w}\b(?:(?!\b(?:{OTHERS})\b)[^.\n<;,]){{0,12}}\b{kind}\b"):
                    bad += [m.group(0) for m in re.finditer(pat, text, re.I)]
    for maker in (r"\bmaker\b",):                                           # the sketches' old name for the Builder
        bad += [m.group(0) for m in re.finditer(maker, text, re.I)]
    return bad


def test_no_text_describes_a_mascot_by_an_old_colour(client):
    texts = {**_rendered(client),
             "README.md": (ROOT / "README.md").read_text(encoding="utf-8"),
             "docs/SITE.md": (ROOT / "docs" / "SITE.md").read_text(encoding="utf-8"),
             "DOCS.md": (TEMPLATES / "DOCS.md").read_text(encoding="utf-8"),
             "mascots.html": (TEMPLATES / "mascots.html").read_text(encoding="utf-8"),
             "mascots.js": (STATIC / "mascots.js").read_text(encoding="utf-8"),
             "chat-demo.js": (STATIC / "chat-demo.js").read_text(encoding="utf-8"),
             "mcp_apps_mascots.py": (ROOT / "fabric_backend" / "mcp_apps_mascots.py").read_text(encoding="utf-8")}
    for where, text in texts.items():
        assert _old_pairings(text) == [], where


def test_the_old_pairings_are_caught():
    """The check above finds what it is for."""
    assert _old_pairings("Onto, the coral guide")
    assert _old_pairings("the sage thinker")
    assert _old_pairings("The builder, the lavender one")
    assert not _old_pairings("Onto is green, the Thinker violet, the Builder coral")


def test_the_review_page_names_each_colour_and_role(client):
    html = client.get("/mascots").text
    for kind, want in NEW.items():
        m = re.search(rf'<h2[^>]*>(?:The )?{NAME[kind]} <span class="pill ([\w-]+)">([^<]+)</span></h2><p class="muted">([^<]+)</p>', html)
        assert m, kind
        assert m.group(1) == kind and m.group(2).startswith(want["colour"]), (kind, m.groups())
    assert "glad only when every check passes" in html


# ------------------------------------------------------------------ alt texts --------------------------------------------

def test_the_alt_texts_say_the_new_colour_and_role():
    k = mcp_apps_mascots.kinds()
    for kind, want in NEW.items():
        label = k[kind]["name"]
        assert label.startswith(NAME[kind]) and want["colour"] in label, label
        assert any(r in label for r in want["role"]), label
    page = (TEMPLATES / "mascots.html").read_text(encoding="utf-8")
    assert 'data-label="The Thinker, violet: checks and asks"' in page
    assert 'data-label="The Builder, coral: builds after a dry run"' in page
    site_js = (STATIC / "site.js").read_text(encoding="utf-8")
    assert "label: M.KINDS[k].name + ', ' + p" in site_js                  # the review grid's labels come from KINDS


def test_the_cards_draw_each_name_in_its_colour():
    for card in (mcp_apps.card_html(), mcp_apps_review.card_html()):
        for kind, want in NEW.items():
            m = re.search(rf'<svg class="mascot {kind}".*?<g class="m-body"><path d="([^"]+)" fill="([^"]+)"', card, re.S)
            assert m and m.group(2) == want["fill"], kind
    assert mcp_apps_mascots.GLAD == ("celebrate", "heart")                   # glad only on a passed check (n136)


def test_the_lovable_prompt_and_the_by_hand_list():
    doc = (ROOT / "docs" / "MASCOTS-RENAME-LOVABLE.md").read_text(encoding="utf-8")
    for kind, want in NEW.items():
        assert NAME[kind] in doc and want["colour"] in doc.lower() and want["fill"] in doc
    assert "PowerPoint" in doc and "LinkedIn" in doc


# ------------------------------------------------------------------ in a browser -----------------------------------------

def _playwright() -> bool:
    import shutil
    if not shutil.which("node"):
        return False
    return subprocess.run(["node", "-e", "require('playwright')"], capture_output=True, cwd=ROOT).returncode == 0


@pytest.fixture(scope="module")
def site():
    sock = socket.socket(); sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]; sock.close()
    env = os.environ | {"PRODUCT_NAME": "Krusgraph", "MCP_PUBLIC_URL": "https://krusgraph.test/mcp", "CONTACT_EMAIL": "hello@krusgraph.test",
                        "ENTRA_CLIENT_ID": "00000000-0000-0000-0000-000000000000", "ENTRA_CLIENT_SECRET": "test-only",
                        "COMPANY_ORGNR": "123456-7890", "KRUSGRAPH_PREVIEW": "1"}
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
        yield base
    finally:
        proc.terminate(); proc.wait(timeout=10)


@pytest.mark.skipif(not _playwright(), reason="node + playwright not available")
def test_the_chat_demo_and_the_review_page_in_chromium(site):
    run = subprocess.run(["node", str(ROOT / "tests" / "n164_mascot_colours_browser.js"), site] + ([CHROMIUM] if CHROMIUM else []),
                         capture_output=True, text=True, timeout=240)
    assert run.returncode == 0, run.stderr[-2000:]
    out = json.loads(run.stdout.strip().splitlines()[-1])
    for scheme in ("light", "dark"):
        o = out[scheme]
        assert o["errors"] == [], (scheme, o["errors"])
        t = o["tokens"]
        for kind, want in NEW.items():
            for v in ("", "-soft", "-ink"):
                assert t[f"--{kind}{v}"] == t[f"--{want['palette']}{v}"], (scheme, kind, v)
        assert {m["kind"] for m in o["chat"]} == set(NEW)                   # all three speak in this run
        for m in o["chat"]:
            want = NEW[m["kind"]]
            assert m["who"] == NAME[m["kind"]] and m["figure"] == m["kind"], (scheme, m)
            assert m["whoColour"] == t[f"--{m['kind']}-ink"], (scheme, m)
            assert m["fill"] == want["fill"], (scheme, m)
            assert want["colour"] in m["label"], (scheme, m)
        assert o["head"] == {"kind": "onto", "fill": NEW["onto"]["fill"]}  # the chat's own face is Onto, now green
        for kind, want in NEW.items():
            r = o["review"][kind]
            assert r["fills"] == [want["fill"]], (scheme, kind, r)
            assert r["pill"] == f"pill {kind}" and r["pillBg"] == t[f"--{kind}-soft"] and r["pillInk"] == t[f"--{kind}-ink"], (scheme, r)
            assert want["colour"] in r["heading"] and want["colour"] in r["labels"][0], (scheme, r)
    assert out["light"]["tokens"]["--onto-ink"] != out["dark"]["tokens"]["--onto-ink"]   # dark follows the palette


@pytest.mark.skipif(not _playwright(), reason="node + playwright not available")
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_an_mcp_apps_card_in_chromium(tmp_path, scheme):
    """validate_plan's card with a passed check: Onto and the Builder speak; every figure wears its own colour."""
    from test_n136_card_mascots import _browse
    answer = json.dumps({"summary": "6 of 6 keys unique, 7 of 7 relationships hold without orphans", "needs_attention": 0,
                         "totals": {"keys": {"checked": 6, "passed": 6, "failed": 0},
                                    "relationships": {"checked": 7, "passed": 7, "failed": 0}},
                         "next_steps": [{"tool": "review_plan", "arguments": {"validate": True},
                                         "why": "keeps the plan, its checks and the decisions made about it as one file."}]})
    out = _browse(tmp_path, "validate_plan", {"workspace": "ws", "source": "shop"}, answer, 480, scheme)
    shown = {f["kind"] for f in out["on"]["figures"] if f["shown"]}
    assert shown == {"onto", "builder"}                                     # nothing needs attention: no Thinker
    figs = {f["kind"]: f for f in out["on"]["figures"]}
    assert set(figs) == set(NEW)
    for kind, want in NEW.items():
        assert figs[kind]["fill"] == want["fill"], (kind, figs[kind])
        assert figs[kind]["who"] == NAME[kind]
