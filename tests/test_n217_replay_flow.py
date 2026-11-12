"""n217, revised by n224: where the data flow is shown.

n217 (11 November 2026) drew the data flow (bronze -> silver -> gold -> built) in the home page's replay card. The
founder, 12 November 2026, on his phone: the data flows belong in the floating "Try a demo" chat, not in the replay card,
which stays short (a suggestion typed, the send button pressed, the answer). So the card has no flow any more
(replay_flow.py is gone), and the chat has a step "See the data flow": data_flow.flow(), the function the Model editor's
build calls, on the chat's demo plan for one build (the silver notebook, the gold views and the chat's semantic model),
drawn with the dbt step's boxes (each one opens its code). These tests check that the chat's flow is the engine's, that
the step is offered as a clickable suggestion, and that the card is back to its turns only. The browser half runs
tests/n224_chat_flow_browser.js at 375, 768, 1280 and 1440 px, light and dark, with and without reduced motion.
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

from fabric_backend import data_flow, demo, pages, seed, semantic_model, server
from fabric_backend.infer import plan

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "fabric_backend" / "static"
CHAT_JS = (STATIC / "chat-demo.js").read_text(encoding="utf-8")
SITE_CSS = (STATIC / "site.css").read_text(encoding="utf-8")
QUESTIONS = ["How are the tables in my lakehouse connected?", "Check the plan against the data.",
             "Create an ontology from my shop data.", "Build a Power BI model from my lakehouse."]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PRODUCT_NAME", "Krusgraph")
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://krusgraph.test/mcp")
    with TestClient(server.build_app()) as c:
        yield c


def _session(html: str) -> str:
    return html[html.index('<figure class="session"'):html.index("</figure>", html.index('<figure class="session"'))]


def _engine(confirmed=None) -> dict:
    """data_flow.py's output for the chat's build on the demo plan, computed here, independently of demo.py."""
    sys.path.insert(0, str(ROOT / "workload" / "scripts"))
    import build_flow_fixture
    info = build_flow_fixture.INFO                                     # the editor's fixture describes the same lakehouse
    p = plan(seed.schema("shop"), keys=demo.DEMO_KEYS, confirmed=confirmed)
    parts = semantic_model.draft(p, info, "shop_model")["parts"]
    items = [{"output": "semantic_model", "label": "Semantic model", "name": "shop_model",
              "reads": "reads the source tables in shop (bronze) directly, not the gold views built in this run",
              "code": data_flow.tmdl_excerpt(parts), "language": "tmdl", "code_title": "shop_model: relationships and measures"}]
    return data_flow.flow(p, info, {"silver_notebook": "silver_shop", "gold_views": "gold_shop", "semantic_model": "shop_model"},
                          items=items)


def _confirmed():
    return [h["confirmed"] for h in demo.demo_suggestions() if h["table"] == "orders" and h["column"] == "ship_to_id"]


# ------------------------------------------------------------------ the replay card: turns only ---------------------

def test_the_replay_card_has_no_data_flow_and_keeps_its_four_turns(client):
    session = _session(client.get("/").text)
    assert re.findall(r'<p class="session-sent">([^<]+)</p>', session) == QUESTIONS
    for gone in ("session-flow", "kgr", "bronze", "Bronze", "silver", "Silver", "gold view", "Gold:", "<svg"):
        assert gone not in session, gone
    turns = session[:session.index("</ol>")].split('<li class="session-turn">')[1:]
    assert len(turns) == 4 and all('class="session-ask"' in t and 'class="session-send"' in t for t in turns)   # typed, sent, answered
    assert "{{HOME_REPLAY_FLOW}}" not in pages._read("home.html") and "HOME_REPLAY_FLOW" not in pages._home_vars()
    assert not (ROOT / "fabric_backend" / "replay_flow.py").exists()
    assert ".session-flow" not in SITE_CSS and ".kgr-" not in SITE_CSS and "@keyframes kgr-in" not in SITE_CSS


# ------------------------------------------------------------------ the chat: the flow is the engine's -------------

@pytest.mark.parametrize("variant", ["as_is", "with_suggestion"])
def test_the_chat_s_flow_is_data_flow_py_s_output_for_the_shop_sample(variant):
    f = demo.demo_drafts()[variant]["flow"]
    e = _engine(_confirmed() if variant == "with_suggestion" else None)
    assert f["columns"] == e["columns"] and f["said"] == e["said"] and f["notes"] == e["notes"]
    keep = ("id", "column", "label", "kind_label", "lines", "built", "code", "code_title")
    assert f["nodes"] == [{k: n[k] for k in keep if k in n} for n in e["nodes"]]
    assert f["edges"] == [{"from": x["from"], "to": x["to"], "built": x["built"]} for x in e["edges"]]


def test_the_stages_of_the_chat_s_build():
    f = demo.demo_drafts()["as_is"]["flow"]
    cols = {c: [n for n in f["nodes"] if n["column"] == c] for c in ("bronze", "silver", "gold", "built")}
    assert len(cols["bronze"]) == 7 and len(cols["silver"]) == 7 and all(n["built"] for n in f["nodes"])
    assert [n["label"] for n in cols["gold"]] == ["gold.audit_log", "gold.order_items", "gold.orders"]
    assert [(n["kind_label"], n["label"]) for n in cols["built"]] == [("Semantic model", "shop_model")]
    assert all(n["code"] for n in cols["silver"] + cols["gold"] + cols["built"]) and not any(n["code"] for n in cols["bronze"])
    assert not any(n["column"] == "pipeline" for n in f["nodes"])     # no pipeline in this build


def test_the_flow_rides_in_plan_json_and_in_check_s_inline_plan(client):
    j = client.get("/demo/plan.json").json()
    assert j["drafts"]["as_is"]["flow"] == demo.demo_drafts()["as_is"]["flow"]
    html = client.get("/check").text
    inline = re.search(r'<script type="application/json" id="kgcPlan">(.*?)</script>', html, re.S).group(1)
    assert json.loads(inline.replace("\\u007b\\u007b", "{{"))["drafts"]["as_is"]["flow"]["tool"] == "data_flow"


def test_the_step_is_a_clickable_suggestion_after_the_model_and_is_remembered():
    assert "var STEPS = ['scan', 'yes', 'no', 'model', 'flow', 'ontology', 'domains', 'fixes', 'dbt'];" in CHAT_JS
    picks = re.findall(r"\{ key: '(\w+)', label: '([^']+)', why: '[^']*', go: (\w+) \}", CHAT_JS[CHAT_JS.index("function suggestions()"):])[:4]
    assert picks == [("model", "Create a semantic model", "model"), ("flow", "See the data flow", "dataFlow"),
                     ("ontology", "Create an ontology", "ontology"), ("domains", "Draft data products", "products")]
    body = CHAT_JS[CHAT_JS.index("function dataFlow()"):CHAT_JS.index("function question()")]
    assert "drafts().flow" in body and "KGF.build(document, flowView(f))" in body and "done('flow'" in body
    assert "innerHTML" not in body                                     # the boxes are KGF's: createElement and textContent
    assert ("flow", "gold_views_draft", "create_gold_views") in pages.CHAT_RESULTS


def test_the_launch_button_carries_the_flow_s_status(client):
    html = client.get("/").text
    assert 'data-status-flow="' in html and re.search(r'data-does-flow="(creates|drafts-gated|drafts)"', html)


def test_no_claims_of_speed_certification_partnership_or_endorsement():
    body = CHAT_JS[CHAT_JS.index("function flowView("):CHAT_JS.index("function question()")].lower()
    for w in ("fast", "second", "certif", "partner", "endorse", "official", "guarantee"):
        assert w not in body, w


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
        run = subprocess.run(["node", str(ROOT / "tests" / "n224_chat_flow_browser.js"), base], capture_output=True, text=True, timeout=900)
        assert run.returncode == 0, run.stderr[-3000:]
        yield json.loads(run.stdout.strip().splitlines()[-1])
    finally:
        proc.terminate(); proc.wait(timeout=10)


KEYS = sorted(f"{w}-{s}-{m}" for w in (375, 768, 1280, 1440) for s in ("light", "dark") for m in ("reduce", "no-preference"))


def test_browser_no_overflow_no_console_error_and_no_flow_in_the_card(browser):
    assert browser["errors"] == []
    assert sorted(browser["sizes"]) == KEYS
    for key, s in browser["sizes"].items():
        assert s["overflow"] == 0, key
        assert s["cardFlow"] == 0, key
        assert s["dark"] == ("-dark-" in key), key


def test_browser_suggestions_first_then_the_flow_with_the_engine_s_boxes(browser):
    f = demo.demo_drafts()["as_is"]["flow"]
    for key, s in browser["sizes"].items():
        assert s["firstPicks"] == ["Check the tables", "See the check on sample files"], key
        assert s["offered"][:2] == ["Create a semantic model", "See the data flow"], key
        assert s["heads"] == [c["title"] for c in f["columns"]], key
        want = [n["kind_label"] + ": " + n["label"] if n.get("kind_label") else n["label"] for n in f["nodes"]]
        assert s["boxes"] == want, key
        assert s["inBubble"], key
        assert s["opened"] and "silver" in s["openedCode"].lower(), key
        assert s["afterNext"], key
