"""n80: the Connect menu in a browser (n149: on /start, step 3, "Choose your client") with client registration on, at 375 and 1280 px, by keyboard
(tests/connect_browser.js): Claude first and open with one large button and Copy URL beside it, a first question to
copy, Lovable under it, "Other clients" closed at the bottom (VS Code, then Cursor), the admin line last with its note;
no address printed; each copy button puts its client's address, the question or the admin note on the clipboard."""
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

from test_browser import CHROMIUM, ROOT, _playwright_available
from fabric_backend import pages

pytestmark = pytest.mark.skipif(not _playwright_available(), reason="node + playwright not available")
ENV = {"PRODUCT_NAME": "Krusgraph", "MCP_PUBLIC_URL": "https://krusgraph.test/mcp", "CONTACT_EMAIL": "hello@krusgraph.test",
       "ENTRA_CLIENT_ID": "00000000-0000-0000-0000-000000000000", "ENTRA_CLIENT_SECRET": "test-only", "KRUSGRAPH_PREVIEW": "1",
       "KRUSGRAPH_CLIENT_REGISTRATION": "1", "KRUSGRAPH_REGISTRATION_KEY": "k" * 43, "KRUSGRAPH_REGISTRATION_STORE": "memory"}


@pytest.fixture(scope="module")
def report():
    sock = socket.socket(); sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]; sock.close()
    proc = subprocess.Popen([sys.executable, "-m", "fabric_backend.server", "--host", "127.0.0.1", "--port", str(port)], env=os.environ | ENV,
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
        out = subprocess.run(["node", str(ROOT / "tests" / "connect_browser.js"), base] + ([CHROMIUM] if CHROMIUM else []),
                             capture_output=True, text=True, timeout=300)
        assert out.returncode == 0, out.stderr[-2000:]
        return json.loads(out.stdout.strip().splitlines()[-1])
    finally:
        proc.terminate(); proc.wait(timeout=10)


@pytest.fixture(scope="module")
def note():
    env = os.environ.copy()
    try:
        os.environ.update(ENV)
        return pages.admin_note()
    finally:
        os.environ.clear(); os.environ.update(env)


@pytest.mark.parametrize("width", ["375", "1280"])
def test_the_menu_by_keyboard(report, note, width):
    assert report["errors"] == []
    r = report[width]
    v = r["closedView"]
    assert r["reachedByTab"] and v["open"] and v["inside"] and v["wide"] <= int(width), v
    assert v["headings"] == ["Claude", "Lovable"] and v["other"] == {"present": True, "open": False}, v      # Other clients folded
    assert v["footLast"] and v["foot"].startswith("Your admin approves Krusgraph once;"), v
    assert not v["printedUrl"], v["text"]
    assert v["mainBigger"] and v["besideCopy"], v
    assert r["tabOrder"] == ["Open Claude’s connectors", "Copy URL", "Copy a first question", "Copy URL", "Other clients", "Add to VS Code",
                             "Insiders", "Add to Cursor", "Copy a note to your admin"], r["tabOrder"]     # n149: on /start, no link to itself
    o = r["otherOpened"]
    assert o["open"] and o["outerOpen"] and o["clients"] == ["VS Code", "Cursor"] and o["inside"] and o["wide"] <= int(width), o
    assert o["links"] == ["vscode:mcp/install", "vscode-insiders:mcp/install", "cursor://anysphere.cursor-deeplink/mcp/install"], o
    assert r["otherFocusRing"] not in ("none", "")
    c = r["copies"]
    assert c["Claude: Copy URL"]["clip"] == "https://krusgraph.test/mcp/connect" and c["Claude: Copy URL"]["after"] == "Copied"
    assert c["Lovable: Copy URL"]["clip"] == "https://krusgraph.test/mcp/connect"
    assert c["Claude: Copy a first question"]["clip"] == pages.FIRST_QUESTION
    assert c["foot: Copy a note to your admin"]["clip"] == note and "adminconsent?client_id=00000000-0000-0000-0000-000000000000" in note
    assert r["afterEscape"] == {"open": False, "focus": True} or r["afterEscape2"] == {"open": False, "focus": True}, (r["afterEscape"], r["afterEscape2"])
    cd = report["consent" + width]
    assert cd["clip"] == pages.FIRST_QUESTION and cd["wide"] <= int(width) and cd["next"].startswith("Next step")


@pytest.mark.parametrize("width", ["375", "1280"])
def test_the_hub_node_by_keyboard(report, width):
    """n190: the hub left the home page. Tab on from the hero's Connect reaches the first intent tile within a few
    stops, with a visible focus ring."""
    t = report[width]["tile"]
    assert t.get("intent") == "issues" and t["href"] == "/check?example=sample&intent=issues" and t["tabs"] <= 3, t
    assert t["ring"] not in ("none", "", None)
