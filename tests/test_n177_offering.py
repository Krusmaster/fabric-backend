"""Round n177: Krusgraph for Fabric in the docs, which Krusgraph to use when (/choose), the product offering diagram on the
home page and /choose, /start's "Use it in Fabric", and the founder's site fixes of 8-9 November 2026 (the film in full
screen on a phone, the chat demo's end and status words, the /check map, the dbt flow in the chat and on the card).
The browser half runs tests/n177_browser.js against a local server and the card."""
from __future__ import annotations

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

from fabric_backend import dbt, dbt_flow, demo, evidence, mcp_apps, mcp_apps_build, offering, pages, seed, server
from fabric_backend import tool_status as ts
from fabric_backend.infer import plan

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "fabric_backend" / "static"
WAY_NAMES = ["Krusgraph for Fabric", "Krusgraph for Claude", "Krusgraph for Lovable", "Krusgraph Open Source"]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PRODUCT_NAME", "Krusgraph")
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://krusgraph.test/mcp")
    monkeypatch.setenv("CONTACT_EMAIL", "hello@krusgraph.test")
    monkeypatch.setenv("ENTRA_CLIENT_ID", "cid-123")
    with TestClient(server.build_app()) as c:
        yield c


def _plain(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


# ------------------------------------------------------------------ the four ways, as data ------------------------------

def test_the_four_ways_in_the_founders_order_with_every_question_answered():
    assert [w["name"] for w in offering.WAYS] == WAY_NAMES
    for w in offering.WAYS:
        for key, _label in offering.ROWS:
            v = offering.val(w, key)
            assert v and (isinstance(v, str) or all(isinstance(x, str) and x for x in v)), (w["key"], key)
    # the decision guide, in the founder's words, each to its way
    assert offering.DECIDE == (("I already use Claude", "claude"), ("We work in Fabric and do not want an AI chat", "fabric"),
                               ("We build an app in Lovable", "lovable"), ("We code in VS Code or Cursor", "claude"),
                               ("Nothing may leave our Azure", "self"))


def test_the_fabric_item_says_plainly_it_uses_no_ai_and_where_data_passes():
    f = offering.way("fabric")
    assert "no AI" in f["data_short"] and "uses no AI model" in f["data"] and "No AI." in f["how"]
    assert offering.NO_AI.startswith("Krusgraph for Fabric (the Krusgraph Model item) uses no AI model")
    assert "Anthropic" in offering.way("claude")["data"] and "AI provider" in offering.way("lovable")["data"]
    assert offering.way("self")["data"].startswith("Only your environment")
    # the workload's own code calls no AI model
    for f in ("workload_api.py", "workload_host.py"):
        text = (ROOT / "fabric_backend" / f).read_text(encoding="utf-8").lower()
        assert "anthropic" not in text and "openai" not in text, f


def test_status_lines_say_no_more_than_tool_status_and_live_test():
    claude = next(c for c in ts.CLIENTS if c.name == "Claude")
    assert offering.val(offering.way("claude"), "status").startswith(f"Claude: {claude.status} since {claude.works_since} (docs/LIVE-TEST.md).")
    fabric = offering.val(offering.way("fabric"), "status")
    assert "Not yet among the runs docs/LIVE-TEST.md records" in fabric and "planned, not available" in fabric
    live = (ROOT / "docs" / "LIVE-TEST.md").read_text(encoding="utf-8")
    assert "Krusgraph Model" not in live and "workload" not in live.lower()      # if a run is recorded, say it here too
    me = offering.val(offering.way("self"), "status")
    assert ts.LOCAL_TRIED_NOTE in me and all(t in me for t in ts.LOCAL_TRIED_TOOLS)
    claude_status = offering.val(offering.way("claude"), "status")
    if not offering._mcp_clients():                                           # client registration off: only Claude signs in
        assert "Other MCP clients" not in claude_status
    lovable = offering.val(offering.way("lovable"), "status")
    assert "Lovable's own Fabric connector: Tested end to end" in lovable
    # no speed or compliance claims anywhere in the offering
    text = offering.choose_md().lower()
    for word in ("faster", "fast ", "seconds", "gdpr", "compliant", "compliance", "certified", "secure", "soc 2", "iso"):
        assert word not in text, word


def test_prices_say_only_what_pricing_says(client):
    pricing = _plain(client.get("/pricing").text)
    assert "Free, open source (MIT)" in pricing                                    # the connector in Claude
    assert offering.way("claude")["price"].startswith("Free; open source (MIT)")
    assert "workload" not in pricing.lower() and "Krusgraph Model" not in pricing
    assert offering.way("fabric")["price"] == "Not on /pricing yet: the pilot is on request."
    assert "Team offer on /pricing" in offering.way("self")["price"] and "Team" in pricing


# ------------------------------------------------------------------ the pages -------------------------------------------

def test_choose_page_has_the_guide_the_diagram_and_the_comparison(client):
    r = client.get("/choose")
    assert r.status_code == 200 and "{{" not in r.text
    h = r.text
    assert "<h1>Which Krusgraph should I use?</h1>" in h
    for q, k in offering.DECIDE:
        assert f"“{q}”" in h
    assert 'id="offering"' in h and 'class="table-wrap choose-table"' in h and "No AI in Krusgraph for Fabric." in h
    table = h[h.index("choose-table"):]
    for _key, label in offering.ROWS:
        assert f'<th scope="row">{label}</th>' in table
    md = client.get("/choose.md")
    assert md.status_code == 200 and md.text.startswith("# Which Krusgraph should I use?") and "<" not in md.text.replace("<-", "")
    assert "/choose.md" in client.get("/llms.txt").text and "/choose" in client.get("/sitemap.xml").text
    assert "# Which Krusgraph should I use?" in client.get("/llms-full.txt").text


def test_the_diagram_lists_the_four_ways_in_words_and_links_each_to_its_docs(client):
    for path in ("/", "/choose"):
        h = client.get(path).text
        box = h[h.index('id="offering"'):]
        box = box[:box.index("</section>")]
        ways = re.findall(r'<a href="([^"]+)" class="off-way-a">.*?<span class="off-way-n">([^<]+)</span>', box)
        assert [n for _, n in ways] == WAY_NAMES, path
        words = box[box.index('class="off-words-l"'):]
        assert [re.sub(r"<[^>]+>", "", x) for x in re.findall(r'<li><a href="[^"]+">([^<]+)</a>', words)] == WAY_NAMES
        for href, _ in ways:
            assert client.get(href).status_code == 200, href
        built = re.findall(r"<li>([^<]+)</li>", box[box.index('class="off-built"'):box.index('class="off-words"')])
        assert built == list(offering.BUILT)
        assert 'aria-describedby="offering-words"' in box and 'aria-hidden="true"' in box    # n183: the words in a <details>
    # the trademark line stays in the footer, and the diagram uses no logo file
    assert "Microsoft Fabric and Fabric IQ are trademarks of Microsoft Corporation" in client.get("/choose").text
    assert not re.search(r"<img[^>]+(microsoft|fabric)", client.get("/choose").text, re.I)


def test_home_has_the_offering_and_a_link_to_choose(client):
    h = client.get("/").text
    # n196: the short guide left the home page (it is on /docs, /choose and /start); the offering still links /choose
    assert 'id="offering"' in h and 'id="which"' not in h and 'href="/choose"' in h[h.index('id="offering"'):]


def test_start_has_use_it_in_fabric_next_to_claude_and_other_agents(client):
    h = client.get("/start").text
    paths = re.findall(r'<a class="card soft path-card[^"]*" href="([^"]+)"[^>]*><h2 class="h3">([^<]+)</h2>', h)
    assert [t for _, t in paths] == ["Explore without an account", "Connect Claude or another agent", "Use it in Fabric"]
    assert dict((t, href) for href, t in paths)["Use it in Fabric"] == "/docs/krusgraph-for-fabric"
    assert 'connect-fabric' not in h                     # the client chooser keeps the founder's order of n80 (Claude, Lovable, others)
    assert 'id="which"' in h
    md = client.get("/start.md").text
    assert "Which Krusgraph should I use?" in md and "{{" not in md


def test_docs_have_krusgraph_in_fabric_with_its_pages(client):
    paths = [p["path"] for p in pages.docs_pages() if p["gpath"] == "/docs/krusgraph-for-fabric"]
    assert paths == ["/docs/krusgraph-for-fabric", "/docs/krusgraph-for-fabric/what-the-krusgraph-model-item-does",
                     "/docs/krusgraph-for-fabric/add-it-to-your-fabric", "/docs/krusgraph-for-fabric/permissions-in-plain-words",
                     "/docs/krusgraph-for-fabric/network-hosts", "/docs/krusgraph-for-fabric/troubleshooting"]
    group = _plain(client.get(paths[0]).text)
    assert "uses no AI model" in group and "Workload Hub is planned and not available" in group
    add = client.get(paths[2]).text
    assert 'href="/pilot/fabric"' in add and "planned, not available" in add and "up to 20" in _plain(client.get(paths[0]).text)
    perms = client.get(paths[3]).text
    from fabric_backend.workload_api import KINDS
    for v in KINDS.values():
        assert f"<td>{v['label']}</td>" in perms
        for alt in v["needs"]:
            assert " or ".join(alt) in perms
    hosts = _plain(client.get(paths[4]).text)
    assert "workload.krusgraph.com" in hosts and "krusgraph.com" in hosts and "TLS 1.2" in hosts
    trouble = _plain(client.get(paths[5]).text)
    for needle in ("keeps loading", "consent", "schema list", "not turned on for your organisation yet"):
        assert needle in trouble, needle
    for p in paths:
        assert client.get(p).status_code == 200
    # the docs menu lists the group, and the "more" list has /choose
    assert 'href="/docs/krusgraph-for-fabric"' in client.get("/docs").text and 'href="/choose"' in client.get("/docs").text


def test_the_screenshots_are_the_editors_labelled_synthetic_and_served(client):
    h = client.get("/docs/krusgraph-for-fabric/what-the-krusgraph-model-item-does").text
    imgs = re.findall(r'<img src="(/static/workload-shots/[^"]+\.webp)" alt="([^"]+)"', h)
    assert [Path(s).stem for s, _ in imgs] == [n for n, _ in offering.SHOTS]
    for src, alt in imgs:
        assert alt.endswith("Synthetic data."), alt
        r = client.get(src)
        assert r.status_code == 200 and r.headers["content-type"] == "image/webp" and r.content[:4] == b"RIFF", src
        assert len(r.content) < 350_000, src
    assert h.count('<span class="shot-tag">Synthetic data</span>') == len(offering.SHOTS)
    # the images are in the package (pyproject package-data), and the harness that made them is in the repository
    assert '"static/workload-shots/*"' in (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    for f in ("build_fixtures.py", "harness.tsx", "shoot.js", "README.md"):
        assert (ROOT / "workload" / "scripts" / "screens" / f).exists(), f


# ------------------------------------------------------------------ the fixes -------------------------------------------

def test_the_film_in_full_screen_is_letterboxed_and_follows_the_orientation():
    css = (STATIC / "site.css").read_text(encoding="utf-8")
    assert ".film-frame video:fullscreen{aspect-ratio:auto;object-fit:contain" in css
    assert ".film-frame video:-webkit-full-screen{aspect-ratio:auto;object-fit:contain" in css
    film = pages.film_html()
    assert f'data-film-wide="{pages.FILM_MP4}"' in film and f'data-film-tall="{pages.FILM_MP4_4X5}"' in film
    js = (STATIC / "site.js").read_text(encoding="utf-8")
    assert "function filmFit(v)" in js and "(orientation: landscape)" in js and "fullscreenchange" in js


def test_the_map_keeps_linked_tables_close_and_says_what_interfaces_and_suggestions_are():
    js = (STATIC / "map.js").read_text(encoding="utf-8")
    assert "function place(rels)" in js and "place(s.relationships);" in js
    assert '"interface · " + (x.source_cols || []).join(" + ")' in js
    assert 'add(g, "title", {}, "Suggested, not in the plan yet: "' in js and '"m-hit"' in js


def test_the_dbt_card_draws_the_flow_with_the_chat_demos_renderer():
    """n177: dbt_schema has the build card; its structuredContent carries the flow (code by file, not repeated); the card
    inlines the chat demo's dbt-flow block, so both draw the same."""
    assert "dbt_schema" in mcp_apps.STRUCTURED and mcp_apps_build.FLOW_CARD_TOOLS == ("dbt_schema",)
    assert mcp_apps.registration("dbt_schema", on=True)["meta"] == mcp_apps_build.tool_meta(on=True)
    assert mcp_apps.registration("dbt_schema", on=False) == {}
    p = plan(seed.schema("shop"))
    answer = {"summary": "x", **dbt.project(p, "shop", "shop", "shop", evidence.validate(p, demo._demo_db()))}
    res = mcp_apps.structured(lambda: json.dumps(answer), "dbt_schema")()
    f = res.structured_content["dbt_flow"]
    assert f == dbt_flow.flow(answer["files"]) and not any("code" in n and n["column"] in ("staging", "marts") for n in f["nodes"])
    assert all(n["file"] in answer["files"] for n in f["nodes"] if n["column"] in ("staging", "marts"))
    card = mcp_apps_build.card_html()
    block = mcp_apps_build.dbt_flow_js()
    assert block.strip().startswith("/* dbt-flow:start") and block in card and "var KGF" in card
    assert block.strip() in (STATIC / "chat-demo.js").read_text(encoding="utf-8")
    # a sources file alone (project=false) has no flow
    plain = mcp_apps.structured(lambda: json.dumps({"path": "models/sources/shop.yml", "yaml": "version: 2"}), "dbt_schema")()
    assert "dbt_flow" not in plain.structured_content


# ------------------------------------------------------------------ in a browser ----------------------------------------

def _playwright() -> bool:
    if not shutil.which("node"):
        return False
    return subprocess.run(["node", "-e", "require('playwright')"], capture_output=True).returncode == 0


@pytest.fixture(scope="module")
def browser_site():
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
        run = subprocess.run(["node", str(ROOT / "tests" / "n177_browser.js"), "site", base], capture_output=True, text=True, timeout=400)
        assert run.returncode == 0, run.stderr[-3000:]
        yield json.loads(run.stdout)
    finally:
        proc.terminate(); proc.wait(timeout=10)


def test_browser_no_errors_and_no_request_elsewhere(browser_site):
    assert browser_site["errors"] == [] and browser_site["external"] == []


def test_browser_the_film_in_full_screen_on_a_phone(browser_site):
    """The founder, 8 November 2026: on a phone the film in full screen was cropped. In full screen the frame is
    letterboxed (contain) and fills the screen; turned to landscape it plays the 16:9 file, back upright the 4:5 one."""
    b = browser_site
    assert b["filmBefore"]["fit"] == "cover"                               # in the page, the 4:5 frame as before
    for k in ("filmPortrait", "filmLandscape", "filmBack"):
        f = b[k]
        assert f["full"] and f["fit"] == "contain" and (f["w"], f["h"]) == (f["vw"], f["vh"]), (k, f)
    assert b["filmLandscape"]["src"] == pages.FILM_MP4 and b["filmBack"]["src"] == pages.FILM_MP4_4X5


def test_browser_the_diagram_renders_stacks_on_a_phone_and_every_way_is_a_focusable_link(browser_site):
    for key, d in browser_site.items():
        if not key.startswith("/"):
            continue
        path, width, scheme = key.split("@")
        assert [w["name"] for w in d["ways"]] == WAY_NAMES, key
        assert [w["text"].split(":")[0] for w in d["words"]] == WAY_NAMES and [w["href"] for w in d["words"]] == [w["href"] for w in d["ways"]], key
        assert d["built"] == list(offering.BUILT) and d["img"] == 0 and d["overflow"] <= 0, key
        # n183: a data flow; at 1280 the ways in sit above the engine and tables -> engine -> built run left to right; at
        # 375 everything stacks in the same order: ways in, tables, engine, built
        assert (d["flow"], d["stacked"]) == ((True, False) if width == "1280" else (False, True)), (key, d["rects"])
        assert d["details"] == {"open": False, "summary": "The diagram in words", "items": 4}, key
        assert len(d["pics"]) == 4 and all(p["role"] == "img" and p["label"] and p["w"] >= 48 for p in d["pics"]), key
        assert [f["href"] for f in d["focus"]] == [w["href"] for w in d["ways"]] and all(f["ring"] for f in d["focus"]), key
        assert d["bg"] == ("rgb(31, 27, 25)" if scheme == "dark" else "rgb(251, 248, 245)"), key
    assert set(browser_site["linkStatus"].values()) == {200}, browser_site["linkStatus"]
    c = browser_site["choose"]
    assert c["heads"][1:] == WAY_NAMES and c["rows"] == [label for _, label in offering.ROWS]
    assert c["decide"][1] == "“We work in Fabric and do not want an AI chat” → Krusgraph for Fabric"


def test_browser_start_and_the_docs_screenshots(browser_site):
    s = browser_site["start"]
    assert s["paths"][-1] == "Use it in Fabric" and s["fabricHref"] == "/docs/krusgraph-for-fabric" and s["short"]
    shots = browser_site["shots"]
    assert [Path(x["src"]).stem for x in shots] == [n for n, _ in offering.SHOTS]
    assert all(x["w"] == 1280 and "Synthetic data" in x["cap"] for x in shots)


def test_browser_the_check_map_places_linked_tables_close(browser_site):
    """The founder, 9 November 2026: order_items -> products ran as a long line through the map. Now the two sit closer
    than the median distance between two tables; the interface line is labelled; the dashed "?" has hover text and takes
    the pointer."""
    m = browser_site["map"]
    assert m["orderItemsProducts"] < m["median"], m
    assert m["labels"] == ["interface · product_id"], m
    assert m["title"].startswith("Suggested, not in the plan yet: orders.ship_to_id → addresses") and m["hitUnder"] and m["hitEvents"] == "stroke", m


def test_browser_the_dbt_card_draws_the_flow_and_opens_one_box_at_a_time(tmp_path):
    if not _playwright():
        pytest.skip("node + playwright not available")
    p = plan(seed.schema("shop"))
    answer = {"summary": "x", **dbt.project(p, "shop", "shop", "shop", evidence.validate(p, demo._demo_db()))}
    res = mcp_apps.structured(lambda: json.dumps(answer), "dbt_schema")()
    (tmp_path / "card.html").write_text(mcp_apps_build.card_html(), encoding="utf-8")
    (tmp_path / "data.json").write_text(json.dumps({"args": {"workspace": "demo", "source": "demo_lh", "schema": "shop", "project": True},
                                                    "result": {"content": [{"type": "text", "text": json.dumps(answer)}],
                                                               "structuredContent": res.structured_content}}), encoding="utf-8")
    run = subprocess.run(["node", str(ROOT / "tests" / "n177_browser.js"), "card", str(tmp_path / "card.html"), str(tmp_path / "data.json")],
                         capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, run.stderr[-2000:]
    out = json.loads(run.stdout)
    assert out["errors"] == []
    b = out["before"]
    assert b["title"] == "dbt project" and b["verdict"].startswith(f"A draft: {len(answer['files'])} files; nothing was created or run.")
    assert [c["h"] for c in b["cols"]] == [label for _, label in dbt_flow.COLUMNS] and b["open"] == 0
    assert [c["boxes"] for c in b["cols"]] == [7, 7, 2, 1]
    a = out["after"]
    assert a["expanded"] == ["customers"] and len(a["open"]) == 1                # one box at a time: the second closed the first
    assert "- name: customers" in a["open"][0] and "unique" in a["open"][0]


def test_with_client_registration_on_krusgraph_for_claude_names_the_other_mcp_clients(monkeypatch):
    monkeypatch.setenv("KRUSGRAPH_CLIENT_REGISTRATION", "1")
    if not offering._mcp_clients():
        pytest.skip("client registration could not be turned on here")
    s = offering.val(offering.way("claude"), "status")
    names = set(offering._mcp_clients())
    for c in ts.CLIENTS:
        if c.path == "/mcp/connect" and c.status == "Tested end to end" and c.works_since and c.name in names:
            assert f"{c.name} (since {c.works_since})" in s
        elif c.path == "/mcp/connect" and c.status != "Tested end to end":
            assert c.name in s and "Experimental" in s
    assert "/mcp/connect" in offering.val(offering.way("claude"), "who")
    assert "In Lovable's chat (MCP): Tested end to end since 30 October 2026." in offering.val(offering.way("lovable"), "status")


# ------------------------------------------------------------------ n177 follow-up: the four product names -------------

def test_the_four_product_names_appear_on_the_which_krusgraph_page(client):
    """The founder, 9 November 2026 (evening): Krusgraph for Fabric, Krusgraph for Claude, Krusgraph for Lovable and
    Krusgraph Open Source, on /choose (the guide, the diagram, the table), its Markdown twin and the workload docs; the old
    names are gone; one logo (the site's own), no product logo, and no partner logo."""
    h = client.get("/choose").text
    plain = _plain(h)
    for name in WAY_NAMES:
        assert name in plain, name
        assert plain.count(name) >= 3, name                             # the guide or the text, the diagram, the table
    md = client.get("/choose.md").text
    assert all(f"## {n}" in md for n in WAY_NAMES)
    for old in ("Krusgraph in Claude", "Krusgraph in other agents", "Run Krusgraph yourself", "Krusgraph in Fabric"):
        assert old not in plain and old not in md, old
    assert "ways to try Krusgraph, not products" in plain and "features of the products" in plain and "Marketplace" in plain
    box = h[h.index('id="offering"'):]
    box = box[:box.index("</section>")]
    assert box.count('class="logo-mark"') == 1 and pages._LOGO in box       # the one Krusgraph logo, on the engine
    assert 'class="off-i ' not in box and "<img" not in box       # n183: the product cards' mascots are inline SVG
    for path in [p["path"] for p in pages.docs_pages() if p["gpath"] == "/docs/krusgraph-for-fabric"]:
        t = _plain(client.get(path).text)
        assert "Krusgraph in Fabric" not in t, path
    assert "Krusgraph for Fabric" in _plain(client.get("/docs/krusgraph-for-fabric").text)
    # partner names are plain text: no file on the site is a Microsoft, Anthropic or Lovable logo
    names = [p.name.lower() for p in STATIC.rglob("*") if p.is_file()]
    assert not [n for n in names if re.search(r"microsoft|anthropic|claude|lovable|fabric-logo", n)], names
