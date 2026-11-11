"""n217: the data flow in the home page's replay (replay_flow.py). The founder, 11 November 2026: the chat demo's replay
does not show the data flow as a flow, the Model editor does. The fourth answer ("Build a Power BI model from my
lakehouse.") is the step where the chat builds: the flow of that build, drawn from data_flow.py's output on the synthetic
shop schema, not by hand, sits in the card under the turns (n203: the card keeps its longest turn's height, so no empty
band while a question is typed), its source tables shown throughout and its other stages drawn in with that answer. The browser half runs tests/n217_browser.js at 375, 768, 1280 and 1440 px, light and dark."""
import json
import re
import shutil
import socket
import subprocess
import sys
import os
import time
import urllib.request
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from fabric_backend import data_flow, pages, replay_flow, seed, server
from fabric_backend.infer import plan

ROOT = Path(__file__).resolve().parents[1]
QUESTIONS = ["How are the tables in my lakehouse connected?", "Check the plan against the data.",
             "Create an ontology from my shop data.", "Build a Power BI model from my lakehouse."]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PRODUCT_NAME", "Krusgraph")
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://krusgraph.test/mcp")
    with TestClient(server.build_app()) as c:
        yield c


def _engine() -> dict:
    """data_flow.py's output for the replay's build on the shop sample, computed here, independently of the page."""
    sys.path.insert(0, str(ROOT / "workload" / "scripts"))
    import build_flow_fixture
    info = build_flow_fixture.INFO                                     # the editor's fixture describes the same lakehouse
    items = [{"output": "semantic_model", "label": "Semantic model", "name": "shop_model_live",
              "reads": "reads the source tables in shop (bronze) directly"}]
    return data_flow.flow(plan(seed.schema("shop")), info, {"semantic_model": "shop_model_live"}, items=items)


def _session(html: str) -> str:
    return html[html.index('<figure class="session"'):html.index("</figure>", html.index('<figure class="session"'))]


def _svgs(html: str) -> list[str]:
    return re.findall(r'<svg class="kgr kgr-(?:wide|tall)".*?</svg>', html, re.S)


# ------------------------------------------------------------------ the flow is the engine's --------------------------

def test_the_replay_s_flow_is_data_flow_py_s_output_for_the_shop_sample():
    assert replay_flow.replay_flow() == _engine()


def test_the_build_is_the_replay_s_fourth_answer_and_the_card_is_the_workload_s():
    from fabric_backend import workload_api
    assert replay_flow.MODEL == "shop_model_live" and replay_flow.CHOSEN == {"semantic_model": "shop_model_live"}
    assert replay_flow.ITEMS[0]["label"] == workload_api.KINDS["semantic_model"]["label"]
    src = (ROOT / "fabric_backend" / "workload_api.py").read_text(encoding="utf-8")
    assert 'reads = f"reads the source tables in {req[\'schema\']} (bronze) directly"' in src   # the same words, no gold views here


@pytest.mark.parametrize("which", [0, 1])
def test_both_pictures_draw_every_node_and_edge_of_the_flow_solid_or_dashed_as_the_engine_says(client, which):
    f = _engine()
    svg = _svgs(_session(client.get("/").text))[which]
    boxes = re.findall(r'<g class="kgr-n kgr-(\w+) kgr-at-\w+( off)?" data-id="([^"]+)"', svg)
    assert [(i, c, not off) for c, off, i in boxes] == [(n["id"], n["column"], n["built"]) for n in f["nodes"]]
    edges = re.findall(r'<path class="kgr-e( off)? kgr-at-\w+" d="[^"]+" data-from="([^"]+)" data-to="([^"]+)"', svg)
    assert [(a, b, not off) for off, a, b in edges] == [(e["from"], e["to"], e["built"]) for e in f["edges"]]
    labels = re.findall(r"<text(?: class=\"kgr-kind\")? x=\"8\" y=\"\d+\">([^<]+)</text>", svg)
    want = []
    for n in f["nodes"]:
        want += ([n["kind_label"]] if n.get("kind_label") else []) + [n["label"]]
    assert labels == want                                              # the engine's labels, none shortened on the shop
    titles = re.findall(r'<text class="kgr-col kgr-at-(\w+)"[^>]*>([^<]+)</text>', svg)
    assert sorted(titles) == sorted((c["id"], c["title"].split(":")[0]) for c in f["columns"])
    assert not any(n["column"] == "pipeline" for n in f["nodes"])     # data_flow.py draws a pipeline only when it is built


def test_the_stages_and_what_is_built():
    f = _engine()
    cols = {c: [n for n in f["nodes"] if n["column"] == c] for c in ("bronze", "silver", "gold", "built")}
    assert [n["label"] for n in cols["bronze"]][:2] == ["shop.categories", "shop.customers"] and len(cols["bronze"]) == 7
    assert len(cols["silver"]) == 7 and not any(n["built"] for n in cols["silver"] + cols["gold"])
    assert [n["label"] for n in cols["gold"]] == ["gold.audit_log", "gold.order_items", "gold.orders"]
    assert [(n["kind_label"], n["label"], n["built"]) for n in cols["built"]] == [("Semantic model", "shop_model_live", True)]


def test_the_list_for_screen_readers_says_every_box_and_its_lines(client):
    f = _engine()
    session = _session(client.get("/").text)
    words = re.search(r'<div class="kgr-sr kgr-words">(.*?)</div>', session, re.S).group(1)
    text = re.sub(r"<[^>]+>", " ", words).replace("&gt;", ">")
    for c in f["columns"]:
        assert c["title"] in text
    for n in f["nodes"]:
        assert n["label"] in text
        for line in filter(None, n["lines"]):
            assert line in text, line
    assert "Silver: cleaned tables (not part of this build)" in text and "Built on the source (part of this build)" in text
    assert all('aria-hidden="true"' in s for s in _svgs(session))      # the pictures are drawn twice; the list is read once


# ------------------------------------------------------------------ the replay otherwise as it was --------------------

def test_the_replay_keeps_its_order_and_wording_and_the_flow_sits_under_the_turns(client):
    session = _session(client.get("/").text)
    assert re.findall(r'<p class="session-sent">([^<]+)</p>', session) == QUESTIONS
    turns = session[:session.index("</ol>")].split('<li class="session-turn">')[1:]
    assert len(turns) == 4 and not any("session-flow" in t for t in turns)       # no turn grows: n203's height holds
    after = session[session.index("</ol>"):]
    assert after.index('<div class="session-flow">') < after.index('class="session-dots"')
    assert turns[3].strip().endswith("date table. Not refreshed yet.</p></div></div>\n          <p class=\"session-ask\" aria-hidden=\"true\"><span class=\"session-text\">Build a Power BI model from my lakehouse.</span><span class=\"session-send\">↑</span></p>\n        </li>")
    assert "The data flow of the build in answer 4, as a list:" in session
    assert "synthetic shop data" in session and "Synthetic shop data" in session
    assert "{{HOME_REPLAY_FLOW}}" in pages._read("home.html")


def test_the_flow_is_static_and_csp_safe(client):
    flow = replay_flow.replay_flow_html()
    assert "<script" not in flow and "style=" not in flow and "http" not in flow and not re.search(r"\son\w+=", flow)
    assert len(flow.encode()) < 20000
    html = client.get("/").text
    assert html.count('class="session-flow"') == 1


def test_no_claims_of_speed_certification_partnership_or_endorsement():
    plain = re.sub(r"<[^>]+>", " ", replay_flow.replay_flow_html()).lower()
    for w in ("fast", "second", "certif", "partner", "endorse", "microsoft", "official"):
        assert w not in plain, w


def test_the_css_follows_the_replay_and_respects_reduced_motion():
    css = (ROOT / "fabric_backend" / "static" / "site.css").read_text(encoding="utf-8")
    assert "@media (max-width:719px){.session-flow svg.kgr-wide{display:none}.session-flow svg.kgr-tall{display:block}}" in css
    assert "@media (prefers-reduced-motion:reduce){.kgr-at-silver,.kgr-at-gold,.kgr-at-built{animation:none;opacity:1}}" in css
    # the fourth turn's cycle (24 s, 18 s delay, n165); drawn once its answer shows, kept while the next question is typed
    assert ".kgr-at-silver,.kgr-at-gold,.kgr-at-built{opacity:0;animation:24s 18s infinite}" in css
    assert ".session-turn:nth-child(4),.session-turn:nth-child(4) *{animation-delay:18s}" in css
    answer = float(re.search(r"@keyframes session-answer\{0%,([\d.]+)%", css).group(1))
    held = re.search(r"@keyframes session-turn-held\{.*?25%,([\d.]+)%", css).group(1)
    for i in (2, 3, 4):
        first, last = re.search(rf"@keyframes kgr-in-{i}\{{0%,([\d.]+)%\{{opacity:0\}}[\d.]+%,([\d.]+)%\{{opacity:1\}}", css).groups()
        assert float(first) >= answer and last == held
    assert ".session.is-paused .session-flow *{animation-play-state:paused}" in css
    colours = re.findall(r"#[0-9A-Fa-f]{3,6}\b", css[css.index("/* n217"):css.index("@keyframes kgr-in-2")])
    assert colours == []                                               # the site's tokens only, so dark follows


# ------------------------------------------------------------------ the browser ------------------------------------

def _playwright() -> bool:
    return bool(shutil.which("node")) and subprocess.run(["node", "-e", "require('playwright')"], capture_output=True).returncode == 0


@pytest.fixture(scope="module")
def browser():
    if not _playwright():
        pytest.skip("node + playwright not available")
    sock = socket.socket(); sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]; sock.close()
    env = os.environ | {"PRODUCT_NAME": "Krusgraph", "MCP_PUBLIC_URL": "https://krusgraph.test/mcp", "CONTACT_EMAIL": "hello@krusgraph.test",
                        "ENTRA_CLIENT_ID": "00000000-0000-0000-0000-000000000000", "ENTRA_CLIENT_SECRET": "test-only"}
    proc = subprocess.Popen([sys.executable, "-m", "fabric_backend.server", "--host", "127.0.0.1", "--port", str(port)], env=env,
                            cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(80):
            try:
                urllib.request.urlopen(base + "/healthz", timeout=1); break
            except Exception:
                time.sleep(0.25)
        else:
            pytest.fail("server did not start")
        run = subprocess.run(["node", str(ROOT / "tests" / "n217_browser.js"), base], capture_output=True, text=True, timeout=600)
        assert run.returncode == 0, run.stderr[-3000:]
        yield json.loads(run.stdout.strip().splitlines()[-1])
    finally:
        proc.terminate(); proc.wait(timeout=10)


def test_browser_no_overflow_and_no_console_error_at_four_widths_in_both_themes(browser):
    assert browser["errors"] == []
    assert sorted(browser["sizes"]) == sorted(f"{w}-{s}-{m}" for w in (375, 768, 1280, 1440) for s in ("light", "dark")
                                              for m in ("reduce", "no-preference"))
    for key, s in browser["sizes"].items():
        assert s["overflow"] == 0, key
        assert s["inCard"] and s["inside"], key
        assert s["dark"] == ("-dark-" in key), key


def test_browser_wide_from_720_px_and_tall_on_a_phone_with_the_engine_s_boxes(browser):
    f = _engine()
    for key, s in browser["sizes"].items():
        assert s["shown"] == (["kgr kgr-tall"] if key.startswith("375-") else ["kgr kgr-wide"]), key
        assert s["underTurns"] and s["width"] >= 280, key
        assert s["ids"] == [n["id"] for n in f["nodes"]], key
        assert s["dashed"] == [n["id"] for n in f["nodes"] if not n["built"]], key
        assert s["animation"] == ("none" if key.endswith("-reduce") else "kgr-in-2"), key
        assert "shop_model_live" in s["words"], key
