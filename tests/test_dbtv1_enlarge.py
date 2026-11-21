"""DBTV1: the dbt project's flow in the demo chat opens larger, as the data flow does (the founder, 21 November 2026).

The data flow and the dbt flow share one "Open larger" button (largerButton) and one overlay (openWide) in
static/chat-demo.js; the SVG pictures (the plan, the model, the ontology, the data products) keep their "Larger
picture". The browser half runs tests/dbtv1_enlarge_browser.js at 390 px (light and dark) and 1280 px: every picture in
the chat has its button, and each opens, stays inside the window, and closes with Esc and with Back to the chat.
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHAT_JS = (ROOT / "fabric_backend" / "static" / "chat-demo.js").read_text(encoding="utf-8")
CHAT_CSS = (ROOT / "fabric_backend" / "static" / "chat-demo.css").read_text(encoding="utf-8")


def test_one_overlay_and_one_button_for_both_flows():
    # the overlay is built in one place, the button in one place
    assert CHAT_JS.count("big.className = 'kgd-big'") == 1
    assert CHAT_JS.count("'kgc-zoom kgd-larger'") == 1
    assert "function openWide(btn, title, label, content)" in CHAT_JS
    assert "openWide(btn, 'The data flow', 'The data flow, larger'" in CHAT_JS
    assert "openWide(btn, 'The dbt project\\u2019s flow', 'The dbt project\\u2019s flow, larger'" in CHAT_JS
    assert "largerButton(function (btn) { openDbtBig(btn, x.flow); })" in CHAT_JS
    assert ".kgf.kgf-wide .kgf-box" in CHAT_CSS


def test_the_dbt_flow_block_shared_with_the_mcp_card_has_no_button():
    # the dbt_schema card inlines the dbt-flow block (mcp_apps_build.dbt_flow_js); the button lives outside it
    a, b = CHAT_JS.index("/* dbt-flow:start"), CHAT_JS.index("/* dbt-flow:end */")
    assert "kgc-zoom" not in CHAT_JS[a:b] and "openWide" not in CHAT_JS[a:b]


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
        run = subprocess.run(["node", str(ROOT / "tests" / "dbtv1_enlarge_browser.js"), base], capture_output=True, text=True, timeout=600)
        assert run.returncode == 0, run.stderr[-3000:]
        yield json.loads(run.stdout.strip().splitlines()[-1])
    finally:
        proc.terminate(); proc.wait(timeout=10)


def test_browser_every_picture_has_its_button(browser):
    assert browser["errors"] == []
    assert sorted(browser["runs"]) == ["1280-light", "390-dark", "390-light"]
    for key, r in browser["runs"].items():
        kinds = [p["kind"] for p in r["pics"]]
        assert "dbt" in kinds and "flow" in kinds and kinds.count("svg") >= 4, key
        assert all(p["button"] for p in r["pics"]), (key, r["pics"])
        assert r["buttons"] == len(r["pics"]), key
        assert r["overflow"] == 0, key
        assert r["dark"] == key.endswith("-dark"), key


def test_browser_each_opens_inside_the_window_and_closes_with_esc_and_back(browser):
    for key, r in browser["runs"].items():
        assert len(r["opened"]) == 2 * r["buttons"], key
        assert {o["how"] for o in r["opened"]} == {"escape", "back"}, key
        for o in r["opened"]:
            where = (key, o["kind"], o["how"])
            assert o["focus"] == "Back to the chat", where
            assert o["inWindow"] and o["inside"], where
            assert o["overflow"] == 0, where
            assert o["closed"] and o["backTo"] and o["inertSame"], where


def test_browser_the_dbt_flow_opens_larger_as_the_data_flow_does(browser):
    for key, r in browser["runs"].items():
        flow = [o for o in r["opened"] if o["kind"] == "flow"]
        dbt = [o for o in r["opened"] if o["kind"] == "dbt"]
        assert flow and dbt, key
        for o in dbt:
            assert o["cls"] == flow[0]["cls"] == "kgd-big", key
            assert o["role"] == "dialog", key
            assert o["title"] == "The dbt project’s flow", key
            assert o["label"] == "The dbt project’s flow, larger", key
            assert o["boxOpens"], key                    # a box in the larger flow still opens its SQL or YAML
            assert o["bigText"] >= 14, key
