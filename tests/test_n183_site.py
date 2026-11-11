"""Round n183: the product diagram as a data flow, a calmer home page, mascot pictures per product, and the Krusgraph
Model's Fluent-style item icon. The browser half (order and stacking at 1280 and 375 px, the closed <details>, the pictures'
alt text) is in tests/test_n177_offering.py's browser tests, which run tests/n177_browser.js."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from fabric_backend import offering, server

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "fabric_backend" / "static"
WORKLOAD = ROOT / "workload" / "Workload"
IMAGES = WORKLOAD / "Manifest" / "assets" / "images"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PRODUCT_NAME", "Krusgraph")
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://krusgraph.test/mcp")
    monkeypatch.setenv("CONTACT_EMAIL", "hello@krusgraph.test")
    monkeypatch.setenv("ENTRA_CLIENT_ID", "cid-123")
    with TestClient(server.build_app()) as c:
        yield c


def _box(html: str) -> str:
    box = html[html.index('id="offering"'):]
    return box[:box.index("</section>")]


def _plain(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


# ------------------------------------------------------------------ 1. the diagram as a data flow ---------------------

@pytest.mark.parametrize("path", ["/", "/choose"])
def test_the_diagram_is_a_data_flow_in_the_founders_order(client, path):
    box = _box(client.get(path).text)
    # the HTML order is the phone's order: ways in, tables, engine, built
    order = [box.index(c) for c in ('class="off-in"', 'class="off-src"', 'class="off-engine"', 'class="off-built"')]
    assert order == sorted(order)
    assert "Choose how you work" in box and "Your tables in Fabric" in box and "One Krusgraph engine" in box
    assert "Keys and links, checked against your rows" in box and ">Built in Fabric<" in box
    src = re.findall(r"<li>([^<]+?) <span", box[box.index('class="off-src"'):box.index('class="off-engine"')])
    assert src == ["Lakehouse", "Warehouse", "SQL database"]        # n206: from tool_status.SOURCES (test_n206_home_tidy.py)
    built = re.findall(r"<li>([^<]+)</li>", box[box.index('class="off-built"'):box.index("</figure>")])
    assert built == ["Semantic model", "Report", "Ontology", "API for GraphQL", "Pipeline and notebooks", "Data agent",
                     "App (Rayfin, preview)", "Data product"]
    # each product keeps its "Data passes:" line
    ways = box[box.index('class="off-ways"'):box.index('class="off-src"')]
    assert ways.count('<span class="off-k">Data passes:</span>') == 4
    # the words, for screen readers, in a collapsed <details> under the diagram
    det = re.search(r'<details class="off-words">\s*<summary id="offering-words-h" class="off-words-h">The diagram in words</summary>'
                    r'(.*?)</details>', box, re.S)
    assert det and box.index("</figure>") < box.index("<details") and "<details open" not in box
    assert 'aria-describedby="offering-words"' in box and 'id="offering-words"' in det.group(1)
    assert "lakehouse (tested end to end)" in det.group(1) and "irrored" not in det.group(1) and "app (rayfin, preview)" not in det.group(1)


def test_the_css_stacks_in_html_order_on_phones_and_flows_left_to_right_on_wide_screens():
    css = (STATIC / "site.css").read_text(encoding="utf-8")
    assert 'grid-template-areas:"in in in in in" ". . a0 . ." "src a1 eng a2 built"' in css
    assert 'grid-template-areas:"in" "a0" "src" "a1" "eng" "a2" "built"' in css


def test_the_app_is_said_to_come_from_krusgraph_for_fabric_only():
    assert "App (Rayfin, preview)" in offering.BUILT
    assert offering.APP_NOTE.startswith("The App (Rayfin, preview) is built by Krusgraph for Fabric only")
    assert "App (Rayfin, preview)" in offering.way("fabric")["builds"]
    assert "App" not in offering.way("claude")["builds"]
    assert offering.APP_NOTE in offering.choose_md()


# ------------------------------------------------------------------ 2. a calmer home page -----------------------------

def test_home_keeps_hero_diagram_short_guide_and_demo_and_one_status_line(client):
    h = client.get("/").text
    main = h[h.index("<main"):h.index("</main>")]
    assert 'id="build-on"' not in main and "Build on the relationships you’ve reviewed" not in main
    assert 'class="muted tiny build-status"' not in main and "LIVE_RUN" not in main and "registry.modelcontextprotocol.io" not in main
    # n196: the short guide and the status line left the home page; the status is in every page's footer, the guide on
    # /docs and /choose (tests/test_n196_home_film.py)
    assert 'id="which"' not in main and 'id="status"' not in main
    order = [main.index(m) for m in ('class="hero"', 'id="demo"', 'id="offering"')]
    assert order == sorted(order)
    foot = h[h.index('<footer class="site-footer">'):]
    assert 'Krusgraph is a preview service. <a href="/docs#test-status">Test status per tool</a>' in foot
    choose = _plain(client.get("/choose").text)
    assert "“We code in VS Code or Cursor” → Krusgraph for Claude (" in choose
    assert "any MCP client" not in choose                   # n216: the clients that sign in today are named, or none


@pytest.mark.parametrize("registration", ["", "1"])
def test_the_vs_code_row_never_claims_more_than_the_hosted_service_signs_in(monkeypatch, registration):
    monkeypatch.setenv("KRUSGRAPH_CLIENT_REGISTRATION", registration)
    from fabric_backend import pages
    suffix = offering.decide_suffix("We code in VS Code or Cursor")
    if pages._registration_on():
        assert suffix == " (VS Code and Cursor sign in at /mcp/connect)"
    else:
        assert "cannot sign VS Code or Cursor in today" in suffix
    assert "any MCP client" not in suffix                   # n216: never more than the hosted service signs in
    assert offering.decide_suffix("I already use Claude") == ""


def test_the_moved_blocks_are_in_the_docs(client):
    from conftest import docs_all
    docs = docs_all(client)
    assert "Build on the relationships you've reviewed." in docs or "Build on the relationships you’ve reviewed." in docs
    assert "a tool that has not run against a live Fabric workspace is marked experimental" in docs
    assert "registry.modelcontextprotocol.io" in docs and "com.krusgraph/krusgraph" in docs
    t = _plain(docs)
    # the status is true today: the Model item creates these, App included; nothing beyond the tests and docs
    assert ("creates a semantic model, a report, an ontology, an API for GraphQL, a pipeline, notebooks, a data agent and, "
            "since round n181, an App (Rayfin, preview)") in t
    assert "covered by unit tests against test doubles of Fabric" in t
    assert "data agent and App (Rayfin, preview)" in t and "Enable Fabric App Items (preview)" in t


def test_every_link_on_the_home_diagram_guide_and_status_answers(client):
    h = client.get("/").text
    part = h[h.index('id="offering"'):h.index('id="paths"')] + h[h.index('<footer class="site-footer">'):]   # n196: status in the footer
    hrefs = sorted({x.split("#")[0] for x in re.findall(r'href="(/[^"]*)"', part)})
    assert "/docs" in hrefs and "/choose" in hrefs
    for href in hrefs:
        assert client.get(href).status_code == 200, href


# ------------------------------------------------------------------ 3. mascot pictures per product --------------------

def test_each_product_card_has_its_3d_mascot_and_our_own_symbol_with_alt_text(client):
    # n216: the figure is the 3D render cut from the overview film (static/mascots/), the symbol a badge we draw
    box = _box(client.get("/choose").text)
    pics = re.findall(r'<span class="off-pic mascot-only"><span class="off-pic-fig" role="img" aria-label="([^"]+)">'
                      r'<img class="off-pic-img" src="(/static/mascots/(?:onto|thinker|builder)\.webp)" width="56" height="56" alt=""[^>]*>'
                      r'<svg class="off-pic-prop" [^>]*>(.*?)</svg></span><span class="off-pic-for" aria-hidden="true">([^<]+)</span>',
                      box, re.S)
    assert [f for *_, f in pics] == ["for Fabric", "for Claude", "for Lovable", "Open Source"]
    for (label, src, body, _f), w in zip(pics, offering.WAYS):
        kind = offering.PICTURES[w["key"]][0]
        assert label.endswith(w["name"]) and label.startswith(kind.capitalize()) and " with " in label, label
        assert src == offering.render_src(kind)
        assert client.get(src).status_code == 200
        assert "<image" not in body and "href" not in body and "url(" not in body       # drawn here: no file, no shared id
    assert [offering.PICTURES[k][1] for k in ("fabric", "claude", "lovable", "self")] == ["table", "bubble", "screen", "code"]


def test_no_third_party_logo_file_or_mark_next_to_the_mascots_or_our_logo(client):
    names = [p.name.lower() for p in STATIC.rglob("*") if p.is_file()]
    assert not [n for n in names if re.search(r"microsoft|anthropic|claude|lovable|fabric-logo|copilot", n)], names
    for path in ("/", "/choose"):
        box = _box(client.get(path).text)
        # n216: the only images are the mascots' 3D renders
        assert set(re.findall(r'<img [^>]*src="([^"]+)"', box)) <= {offering.render_src(k) for k in ("onto", "thinker", "builder")}
        refs = re.findall(r'(?:src|href)="([^"]+)"', box)
        assert not [r for r in refs if re.search(r"microsoft|anthropic|lovable\.(?:dev|app)|logo", r, re.I)], refs
    # partner names stay plain text in the pictures' captions
    assert all(re.fullmatch(r"(for [A-Z][a-z]+|Open Source)", p[3]) for p in offering.PICTURES.values())


def test_the_mascot_switch_hides_the_pictures():
    css = (STATIC / "site.css").read_text(encoding="utf-8")
    assert "html[data-mascots=off] .mascot-only{display:none!important}" in css
    assert "html[data-mascots=off] .off-way-a{grid-template-columns:minmax(0,1fr)}" in css


# ------------------------------------------------------------------ 4. the Fluent-style item icon ----------------------

def _size(p: Path) -> tuple[int, int]:
    b = p.read_bytes()
    assert b[:8] == b"\x89PNG\r\n\x1a\n", p.name
    return int.from_bytes(b[16:20], "big"), int.from_bytes(b[20:24], "big")


def test_the_manifest_icons_exist_at_the_sizes_it_asks_for():
    product = json.loads((WORKLOAD / "Manifest" / "Product.json").read_text(encoding="utf-8"))
    item = json.loads((WORKLOAD / "Manifest" / "items" / "ModelItem" / "ModelItem.json").read_text(encoding="utf-8"))
    card = product["createExperience"]["cards"][0]
    want = {item["icon"]["name"]: (48, 48), item["activeIcon"]["name"]: (48, 48), card["icon"]["name"]: (48, 48),
            card["icon_small"]["name"]: (24, 24), product["icon"]["name"]: (64, 64), product["favicon"]: (32, 32)}
    for name, size in want.items():
        p = WORKLOAD / "Manifest" / name
        assert p.exists() and _size(p) == size, name
    # Microsoft's guideline sizes (publishing-requirements-item 1.2): 20 / 24 / 32 / 40 / 48 / 64
    assert all(w in (20, 24, 32, 40, 48, 64) for w, _ in want.values())
    assert (IMAGES / "ModelItem_Icon.png").read_bytes() != (IMAGES / "ModelItem_Icon_Active.png").read_bytes()


def test_the_item_icon_is_krusgraphs_own_shape_and_colours_with_the_guideline_cited():
    src = (ROOT / "workload" / "scripts" / "build_manifest_images.py").read_text(encoding="utf-8")
    assert "publishing-requirements-item" in src and "28px in 48px container" in src and "14px in 24px container" in src
    fluent = src[src.index("def fluent_item("):src.index("def _page(")]
    for c in ("CORAL", "GREEN", "VIOLET"):
        assert c in src
    # no Microsoft colour sequence (Fabric's teal-green-blue, the Microsoft logo's four colours) in the item icon
    for c in ("#F25022", "#7FBA00", "#00A4EF", "#FFB900", "#117865", "#0078D4"):
        assert c.lower() not in fluent.lower(), c
    assert "rx=\"10\"" in fluent and "radialGradient" in fluent and "linearGradient" in fluent


def test_the_editor_shows_the_item_icon_top_left():
    app = WORKLOAD / "app"
    logo = app / "assets" / "krusgraph-item-icon.png"
    assert logo.read_bytes() == (IMAGES / "ModelItem_Icon.png").read_bytes()
    editor = (app / "items" / "ModelItem" / "ModelItemEditor.tsx").read_text(encoding="utf-8")
    assert 'logo={<img src="/assets/krusgraph-item-icon.png" alt="Krusgraph Model"' in editor
    ribbon = (app / "components" / "ItemEditor" / "Ribbon.tsx").read_text(encoding="utf-8")
    left = ribbon.index('<div className="ribbon-header__left">')
    assert ribbon.index('<div className="ribbon-logo">', left) < ribbon.index("isDetailView ?", left)


# ------------------------------------------------------------------ 5. the banner without text ------------------------

def test_the_banner_leaves_the_left_side_to_fabrics_own_text():
    pytest.importorskip("PIL")
    from PIL import Image
    im = Image.open(IMAGES / "Workload_Hub_Banner.png").convert("RGB")
    assert im.size == (1920, 240)
    left = im.crop((0, 0, 1100, 240))
    colours = left.getcolors(maxcolors=4096)
    assert colours is not None and len(colours) <= 64, "no text or logo on the banner's left side"
    src = (ROOT / "workload" / "scripts" / "build_manifest_images.py").read_text(encoding="utf-8")
    banner = src[src.index("def banner("):src.index("def getting_started(")]
    assert 'class="word"' not in banner.split("body = ", 1)[1] and "mark(" not in banner.split("body = ", 1)[1]
