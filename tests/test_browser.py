"""Browser-level checks of the site (console errors, external requests, overflow, fonts, the explorer's
interactions, the mascot toggle, the builder sequence). Runs only where Node, Playwright and a Chromium are
available — on a developer machine with `npm i -g playwright` + `npx playwright install chromium`, or where
PLAYWRIGHT_CHROMIUM points at a browser. Skipped otherwise, so CI stays green without a browser."""
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

from fabric_backend import pages

ROOT = Path(__file__).resolve().parents[1]
CHROMIUM = os.environ.get("PLAYWRIGHT_CHROMIUM") or ("/opt/pw-browsers/chromium" if Path("/opt/pw-browsers/chromium").exists() else "")


def _playwright_available() -> bool:
    if not shutil.which("node"):
        return False
    probe = subprocess.run(["node", "-e", "require('playwright')"], capture_output=True, text=True)
    return probe.returncode == 0


pytestmark = pytest.mark.skipif(not _playwright_available(), reason="node + playwright not available")


@pytest.fixture(scope="module")
def site():
    sock = socket.socket(); sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]; sock.close()
    env = os.environ | {"PRODUCT_NAME": "Krusgraph", "MCP_PUBLIC_URL": "https://krusgraph.test/mcp", "CONTACT_EMAIL": "hello@krusgraph.test",
                        "ENTRA_CLIENT_ID": "00000000-0000-0000-0000-000000000000", "ENTRA_CLIENT_SECRET": "test-only", "COMPANY_ORGNR": "123456-7890",
                        "KRUSGRAPH_PREVIEW": "1"}
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


@pytest.fixture(scope="module")
def report(site):
    cmd = ["node", str(ROOT / "tests" / "browser_check.js"), site] + ([CHROMIUM] if CHROMIUM else [])
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    assert out.returncode == 0, out.stderr[-2000:]
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_no_console_errors_external_requests_or_overflow(report):
    assert report["errors"] == []


def test_mascot_toggle_and_builder(report):
    f = report["facts"]
    assert f["mascotsAfterReload"] == "off" and f["mascotsAfterToggleBack"] == "on"
    assert f["builderPoses"][:2] == ["working", "failure"] and "celebrate" not in f["builderPoses"]
    assert f["builderErrorShown"] is True
    assert f["motionClassUnderReducedMotion"] is False


def test_the_theme_button_switches_and_the_choice_survives_a_reload(report):
    f = report["facts"]
    assert f["themeFirst"]["theme"] is None and f["themeFirst"]["pressed"] == "false"          # the system's choice (light)
    assert f["themeAfterClick"]["theme"] == "dark" and f["themeAfterClick"]["pressed"] == "true"
    assert f["themeAfterClick"]["bg"] != f["themeFirst"]["bg"] and f["themeAfterClick"]["meta"] == "#1F1B19"
    assert f["themeAfterReload"] == f["themeAfterClick"]
    assert f["themeAfterEnter"]["theme"] == "light" and f["themeAfterEnter"]["bg"] == f["themeFirst"]["bg"]


def test_the_home_buttons_and_a_visible_focus_ring(report):
    f = report["facts"]
    for v in ("1440-light", "1440-dark", "768-light", "375-light"):
        assert f[f"homeCtas@{v}"] == ["/check", "/start"], v              # n149: "Check my tables", then "Connect to my Fabric"
        for where in ('.start-pane[data-pane="3"]',):                    # n149: the chooser is on /start, step 3
            c = f[f"connect@{v}"][where]
            assert c["open"] and c["inside"] and c["wide"] <= int(v.split("-")[0]), (v, where, c)
            assert c["links"] == ["https://claude.ai/customize/connectors"], (v, where, c)   # this server: no client registration
            assert c["copies"][:2] == ["https://krusgraph.test/mcp", pages.FIRST_QUESTION] and len(c["copies"]) == 3 and "/it" in c["copies"][2], (v, where, c)   # n80
            assert c["afterEscape"] == {"open": False, "focus": True}, (v, where, c)
    assert f["ctaFocusOutline"] not in ("none", "")


def test_use_cases_maps_are_drawn_and_marked_by_keyboard(report):
    """n59: three maps drawn with /check's renderer at every width and theme, inside the screen; a finding marked by
    keyboard and unmarked again; with reduced motion the maps are drawn at once."""
    f = report["facts"]
    assert f["useCaseTasks"] == 3
    for v in ("1440-light", "1440-dark", "1280-light", "768-light", "375-light"):
        maps = f[f"ucMaps@{v}"]
        assert len(maps) == 3 and all(m["nodes"] >= 6 and m["lines"] >= 4 and m["rules"] >= 4 and m["inside"] for m in maps), (v, maps)
        assert maps[0]["dashed"] == 1 and maps[2]["dashed"] == 1, v                 # the shop's and the CRM's suggestion
    assert f["useCaseMarked"] == {"pressed": "true", "lit": 1} and f["useCaseUnmarked"] == 0
    assert f["ucMapMotion"]["drawn"] > 0 and f["ucMapMotion"]["moving"] == 0


def test_sales_example_journey_at_phone_width(report):
    """The first customer demonstration (brief of 26 October 2026): the steps open in order, another question gets an
    honest answer, the decision changes the numbers exactly as the server computes them, the chart reads by keyboard,
    nothing but a table scrolls sideways, and a saved link reopens the same result."""
    f = report["facts"]
    assert f["salesScopeHiddenFirst"] is True and f["salesScopeHiddenAfterOther"] is True and f["salesScopeShown"] is True
    assert "answers one question" in f["salesOtherQuestion"] and "pilot" in f["salesOtherQuestion"]
    assert f["salesFocusAfterDefinition"] == "link-h"
    assert f["salesOpenTotal"] == f["salesApiOpenTotal"] and f["salesLinkedTotal"] == f["salesApiLinkedTotal"]
    assert f["salesLinkedTotal"] > f["salesOpenTotal"] and "d=B-7003%3AA-103" in f["salesUrlAfterLink"]
    assert f["salesFilteredTotal"] == f["salesApiFilteredTotal"]
    assert "forecast for week 51, 2026" in f["salesKeyboardEnd"] and "sold in week" in f["salesKeyboardHome"]
    assert f["salesWideOutsideScroll"] == []
    assert "Reopened" in f["salesReopened"] and f["salesReopenedTotal"] == f["salesFilteredTotal"]
    assert "linked to Commuter Light Set" in f["salesSavedList"] and f["salesChoiceKept"] is True



def test_home_entry_old_anchors_and_the_hub_under_the_hero(report):
    """Round n17: the start page's way in to the guided demo takes at most half the screen of a small phone (375 x 667)
    and of a laptop (1280 x 800); /#guide, /#demo and a step's anchor open the guided demo on /check (n55). The hub (brief of
    27 October 2026) keeps its three cards and the product on the screen, none on top of another and no name cut off,
    with its text version for screen readers: side by side with the lines at 1280 and 1440 px, stacked with the product
    in the middle at 768 and 375 px. (This server runs without client registration: Claude and Lovable on the right.)"""
    f = report["facts"]
    assert f["homeEntry@375x667"] <= 0.5 and f["homeEntry@1280x800"] <= 0.5
    for h in ("#guide", "#demo", "#guide-h3"):
        assert f[f"oldAnchor{h}"] == "/check?example=sample&guide=1", h          # n55: the guided demo is on /check
    for v in ("1440-light", "1440-dark", "1280-light", "768-light", "375-light"):
        c = f[f"hub@{v}"]
        assert c["cards"] == 4 and c["items"] == 11 and c["outside"] == 0 and c["overlaps"] == 0 and c["cut"] == 0, (v, c)
        assert c["srText"] > 300, v
        wide = v.startswith(("1440", "1280"))
        assert c["sideBySide"] is wide and c["stacked"] is not wide and c["lines"] == (2 if wide else 0), (v, c)


def test_the_hub_node_links_to_the_guide_and_nothing_moves(report):
    """n91 (Gustav's decision of 2 November 2026): the hub has no Connect button, the hero's chooser stays; the node in the
    middle links to /start under the name "Connect Krusgraph to Claude: the guide", the whole node is the link, and it is
    reached by Tab from the hero's Connect. At 375 and 1280 px (and the other widths) nothing runs out of the screen, the
    product stays centred between the cards on the left, and nothing in the hub moves at rest, on hover or on focus; the
    node looks the same at rest, shows a ring on hover and the focus outline on Tab."""
    f = report["facts"]
    for v in ("1440-light", "1440-dark", "1280-light", "768-light", "375-light"):
        n, w = f[f"hubNode@{v}"], int(v.split("-")[0])
        assert n["href"] == "/start" and n["name"] == "Connect Krusgraph to Claude: the guide" and n["hasMark"], (v, n)
        assert n["connectInHub"] == 0 and n["choosers"] == 0 and n["links"] == 1, (v, n)          # n149: no chooser on the home page
        assert n["hiddenAround"] == [] and n["tabIndex"] == 0 and n["tabbedTo"] == "c-hub c-hub-logo hub-go", (v, n)
        assert n["inside"] and n["wide"] <= w and n["hitIsLink"], (v, n)
        assert n["stillAfterWait"] and n["stillOnHover"] and n["stillOnFocus"], (v, n)
        assert n["rest"]["shadow"] == "none" and n["rest"]["outline"] == "none" and n["rest"]["cursor"] == "pointer", (v, n)
        assert n["hover"]["shadow"] != "none" and n["hover"]["bg"] == n["rest"]["bg"] and n["backToRest"], (v, n)
        assert n["focus"]["outline"] not in ("none", ""), (v, n)
        if v.startswith(("1440", "1280")):
            assert n["centred"], (v, n)                                    # side by side: the product between data and what is built


def test_explore_build_cards_fit_at_375_and_1280_and_hold_still_with_reduced_motion(report):
    f = report["facts"]
    for v in ("375-light", "1280-light"):
        b = f[f"build@{v}"]
        assert b["cards"] == 4 and b["outside"] == 0 and b["scrollWidth"] <= int(v.split("-")[0]), (v, b)
        assert b["steps"] == len(pages.build_path()) and b["stepsOutside"] == 0, (v, b)     # the row of steps (n34)
    assert f["build@1280-light"]["stepsInRow"] == 1 and f["build@375-light"]["stepsInRow"] == len(pages.build_path())
    assert f["buildMotion"] == 0


def test_a_tap_in_the_played_session_shows_two_links_and_keeps_it_playing(report):
    """n48: touch at 375 and mouse at 1280; Tab reaches the links, Escape hides them."""
    for w in (375, 1280):
        s = report["facts"][f"session@{w}"]
        # n154: the first turn has two animations (its first round, then the loop), each running
        assert set(s["state"].split(", ")) == {"running"} and s["pause"] == "Pause", (w, s)
        assert s["links"] == ["/check", "/start"] and s["wide"] <= w and s["hidden"], (w, s)      # n149: the two ways in
        assert s["tabbed"] == "/check" and s["tabShown"] and s["escFocus"] == "session-pause", (w, s)


# ------------------------------------------------------------------ round n52: first-time visitors' ways in ----------
@pytest.fixture(scope="module")
def first_visit(site):
    cmd = ["node", str(ROOT / "tests" / "first_visit_browser.js"), site] + ([CHROMIUM] if CHROMIUM else [])
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_the_start_page_hero_buttons_are_above_the_fold(first_visit):
    """n52: on 29 October 2026 the start page's first button sat at y 1069 (1280 x 800) and 1411 (375 x 812). Now
    "Check your files – no account" and "Connect to Claude" come right after the lede, before the replayed session,
    and both are wholly on the first screen at both sizes, light and dark, with and without reduced motion. n68: the
    second is the Connect chooser's button (one click per client; /start is the long guide, linked from the chooser)."""
    for v, ctas in ((k.split("@")[1], c) for k, c in first_visit.items() if k.startswith("hero@")):
        height = int(v.split("-")[0].split("x")[1])
        assert [(c["href"], c["text"]) for c in ctas] == [("/check", "Check my tables"), ("/start", "Connect to my Fabric")], v   # n149
        assert all(c["bottom"] <= height for c in ctas), (v, ctas)


def test_the_hero_buttons_come_early_on_the_keyboard(first_visit):
    """n73: the hero's two ways in come early on the keyboard (n149: "Check my tables", then "Connect to my Fabric")."""
    for w in (1280, 375):
        seen = first_visit[f"tab@{w}"]
        assert "/check" in seen and "/start" in seen and seen.index("/check") < seen.index("/start"), (w, seen)


def test_the_check_drop_area_comes_first_on_a_phone(first_visit):
    """n52: at 375 x 812 the examples sat at y 1078, below the drop box and the privacy note. Now the heading and all
    three examples are on the first screen (four since n78), and the privacy sentence is still next to the drop box."""
    # n149 (the UX review of 7 November 2026): on a phone the drop area and the privacy line come first, the examples
    # under them; on a wide screen the examples stay on the first screen above the drop area
    for v, e in ((k.split("@")[1], c) for k, c in first_visit.items() if k.startswith("examples@")):
        height = int(v.split("-")[0].split("x")[1])
        assert len(e["buttons"]) == 4, v
        assert 0 <= e["privacy"]["top"] - e["drop"]["bottom"] <= 40, v
        if v.startswith("375"):
            assert e["drop"]["top"] <= height and e["privacy"]["bottom"] < e["heading"]["top"], v
        else:
            assert e["heading"]["bottom"] <= height and all(b["bottom"] <= height for b in e["buttons"]), (v, e["buttons"])


# ------------------------------------------------------------------ round n92: the chat demo (n93: every ordinary page) --
CHAT_FILES = ["/static/chat-demo.css", "/static/chat-demo.js", "/demo/plan.json"]
# n93: the pages with the button, as the server renders them (tests/test_chat_demo.py checks the same list on the HTML);
# n154: the home page and /check again, and the blog and a docs sub-page (tests/test_n154_replay_and_widget.py has every page)
CHAT_PAGES = ([p for p in pages.PAGES if p not in pages.CHAT_OFF] + ["/privacy", "/docs", "/docs/reference/tools", "/lovable", "/local",
              pages.CONSENT_PATH, "/no-such-page", "/blog", pages.BLOG_TOTALS])


@pytest.fixture(scope="module")
def chat(site):
    cmd = ["node", str(ROOT / "tests" / "chat_demo_browser.js"), site] + ([CHROMIUM] if CHROMIUM else [])
    env = os.environ | {"CHAT_PAGES": json.dumps(CHAT_PAGES)}
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=900, env=env)
    assert out.returncode == 0, out.stderr[-2000:]
    return json.loads(out.stdout.strip().splitlines()[-1])


def _chat_runs(chat):
    return {k: v for k, v in chat.items() if k.split("-")[0] in ("375", "1280")}


def _stored(f):
    return json.loads(f["storeAfter"]["session"]["krusgraph.chat"])


def test_chat_the_page_loads_only_the_button_and_the_chat_never_opens_by_itself(chat):
    """Under the start page's own content security policy (nothing bypassed; no console error, so no refused request).
    At 375 and 1280 px, light and dark: before the click the page has the button and nothing of the chat (no script,
    no stylesheet, no box), 1.5 s after load included; at the bottom of the page the button covers no text or control."""
    runs = _chat_runs(chat)
    assert len(runs) == 8
    for v, f in runs.items():
        assert f["onLoad"] == {"box": False, "launch": True, "text": "Try a demo", "chatScript": False, "css": ["/static/site.css"]}, v
        assert not any("chat-demo" in u or u == "/demo/plan.json" for u in f["before"]), (v, f["before"])
        assert f["bottomCovers"] == [], (v, f["bottomCovers"])
        assert f["errors"] == [], (v, f["errors"])
        assert f["storeBefore"] == {"local": {}, "session": {}, "cookie": ""}, v          # a first visit: nothing stored
    assert chat["noJs"] == {"exists": True, "shown": False, "padded": False}
    assert chat["noJsDocs"] == {"exists": True, "shown": False}


def test_chat_makes_no_request_but_the_plan_and_keeps_only_its_steps_in_the_tab(chat):
    """After the click: the chat's two files and /demo/plan.json, nothing else of its own (the start page's own n49
    prefetch of /check's engine may run while the page is still; it is not the chat's and carries nothing). No cookie,
    nothing in localStorage; in sessionStorage only the chat's one key, with known step names and whether it is open."""
    engine = set(f"/static/pyodide/{n}" for n in pages.CHECK_DOWNLOAD)
    for v, f in _chat_runs(chat).items():
        own = [u for u in f["requests"] if u not in engine and not u.startswith("/check/engine.zip")]
        assert own == CHAT_FILES, (v, own)
        assert f["storeAfter"]["local"] == {} and f["storeAfter"]["cookie"] == "" and list(f["storeAfter"]["session"]) == ["krusgraph.chat"], v
        st = _stored(f)
        assert st == {"open": False, "steps": st["steps"]} and st["open"] is False, (v, st)
        assert st["steps"] == ["scan", "yes", "model", "ontology", "domains"], (v, st)     # n154: fix and dbt are links
        assert f["cookies"] == [], v


def test_chat_the_whole_flow_by_mouse_says_the_engines_numbers(chat):
    for v, f in _chat_runs(chat).items():
        if not v.endswith("mouse"):
            continue
        assert f["firstPicks"] == ["Check the tables", "See the check on sample files"], v
        assert f["firstLinks"] == [{"href": "/check?example=sample", "target": None}], v
        assert f["facts"] == ["7", "6", "1"] and len(f["links"]) == 6, v
        assert "All 15 of its values exist in addresses.address_id, in 60 of 60 rows." in f["question"], v
        assert "The plan now has 7 links." in f["linkAdded"], v
        assert f["nextPicks"] == ["Create a semantic model", "Create an ontology", "Draft data products", "Fix data issues", "Draft a dbt project"], v
        model, onto, products = f["results"][1:]
        assert "7 tables and 7 relationships; all 7 hold" in model and "1 inactive: addresses.customer_id → customers would close a cycle" in model, v
        assert "7 entity types (5 with a key) and 7 relationship types" in onto, v
        assert "2 data products drafted" in products and "customers and products, with an interface between them" in products, v
        assert "audit_log stays out, because it has no key" in products, v
        for r in (model, onto, products):
            assert "This is a demo, so nothing was created." in r, (v, r)
        # n94: "creates" only where tool_status says the hosted service creates it live; n146: the hosted app has
        # Item.ReadWrite.All since 28 October 2026, so the model and the ontology are created, without a permission note
        assert "your agent creates this in your Fabric workspace when you ask." in model and "Creating it needs a permission" not in model, v
        assert "your agent creates this in your Fabric workspace when you ask." in onto and "Creating it needs a permission" not in onto, v
        # n93: a plain sentence from tool_status, no tool's name
        m_note, o_note, d_note = f["notes"]
        for note in (m_note, o_note):
            assert note.endswith("Created in a live Fabric workspace and reviewed there."), (v, note)
        assert d_note.endswith("the draft creates nothing in Fabric. Tested with unit tests, not yet against a live Fabric workspace."), (v, d_note)
        for tool in ("create_semantic_model", "create_ontology", "domain_draft", "semantic_model_draft", "ontology_draft", "Status of"):
            assert tool not in f["allText"], (v, tool)
        assert "That is the demo" in f["end"] and f["endLinks"] == [{"href": "/check", "target": None}, {"href": "/start", "target": None},
                                                                   {"href": FIX_DOCS, "target": None}, {"href": DBT_DOCS, "target": None}], v
        assert f["endWhy"] == "Opens the set-up guide.", v
        assert f["afterClose"] == {"hidden": True, "launchShown": True, "focus": "kgcLaunch", "expanded": "false"}, v
        assert f["overflowX"] <= 0 and f["logOverflowX"] <= 0 and f["pageOverflowX"] <= 0, v
        low = f["allText"].lower()
        from tests.test_site import SALES
        assert not [w for w in SALES if w in low], v


def test_chat_the_pictures_show_each_step_inside_their_bubbles(chat):
    """n93: five pictures, drawn from the plan: the tables and links with audit_log without a key; the same with the new
    link marked; the semantic model with the inactive relationship dashed; the ontology's entity types with and without a
    key; the data products as two groups with the interface between them and audit_log outside. Each stays inside its
    bubble at 375 and 1280 px (no sideways scroll), its names fit their boxes at 12 px or more on screen, it has a
    description for screen readers, and the text beside it stays."""
    tables = ["customers", "categories", "products", "addresses", "orders", "order_items", "audit_log"]
    for v, f in _chat_runs(chat).items():
        if not v.endswith("mouse"):
            continue
        plan, link, model, onto, prods = f["pics"]
        for p in f["pics"]:
            assert p["role"] == "img" and len(p["desc"]) > 40 and p["inside"] and p["fit"] and not p["overlap"], (v, p)
            assert p["minFont"] >= 12, (v, p["minFont"])
            assert p["zoom"] and p["textBeside"] > 20, (v, p)
        assert sorted(plan["names"]) == sorted(tables) and plan["edges"] == 6 and plan["keys"] == 6 and plan["nokey"] == ["audit_log"], (v, plan)
        assert "7 tables" in plan["desc"] and "6 links" in plan["desc"] and "audit_log has none" in plan["desc"], v
        assert link["names"] == plan["names"] and link["edges"] == 7 and link["kinds"]["new"] == 1, (v, link)
        assert "new link from orders.ship_to_id to addresses" in link["desc"], v
        assert sorted(model["names"]) == sorted(tables) and model["edges"] == 7 and model["kinds"]["off"] == 1 and model["keys"] == 0, (v, model)
        assert "6 active relationships as solid lines and addresses.customer_id to customers, inactive, as a dashed line" in model["desc"], v
        assert sorted(onto["names"]) == sorted(["Customers", "Categories", "Products", "Addresses", "Orders", "OrderItems", "AuditLog"]), v
        assert onto["keys"] == 5 and sorted(onto["nokey"]) == ["AuditLog", "OrderItems"] and onto["edges"] == 7, (v, onto)
        assert prods["groupNames"] == ["customers", "products"] and prods["kinds"]["iface"] == 1 and prods["outside"] is False, (v, prods)
        assert prods["nokey"] == ["audit_log"] and "audit_log outside them" in prods["desc"], (v, prods)
        # the same place for every table in every picture: the map does not move between steps
        assert plan["names"] == link["names"] == model["names"] == prods["names"], v


def test_chat_larger_picture_opens_inside_the_chat(chat):
    for v, f in _chat_runs(chat).items():
        if not v.endswith("mouse"):
            continue
        b = f["big"]
        assert b["focus"] == "kgc-back" and b["covers"] and b["overflowX"] <= 0 and b["logInert"], (v, b)
        assert b["width"] > f["pics"][4]["width"], (v, b["width"], f["pics"][4]["width"])
        assert "A picture of the data products" in b["text"], v
        assert f["bigClosed"] == {"big": False, "open": True, "focus": "kgc-zoom", "pic": "4"}, (v, f["bigClosed"])


FIX_DOCS, DBT_DOCS = "/docs/explore-and-check/fix-data-issues", "/docs/build-from-a-plan/create-a-dbt-flow"


def test_chat_fix_and_dbt_link_what_exists_today(chat):
    """n154: until n154 these two were "Planned" and ran nothing; now they link the docs of what exists today."""
    for v, f in _chat_runs(chat).items():
        if v.endswith("mouse"):
            fix, dbt = f["further"]
            assert fix["tag"] == "A" and fix["href"] == FIX_DOCS and not fix["planned"] and fix["why"].startswith("Today: a proposed fix for each problem"), (v, fix)
            assert dbt["tag"] == "A" and dbt["href"] == DBT_DOCS and not dbt["planned"] and dbt["why"].startswith("Today: a dbt project"), (v, dbt)
        else:
            assert f["furtherFocused"] == {"pick": "Fix data issues", "tag": "A", "href": FIX_DOCS}, v


def test_chat_the_whole_flow_by_keyboard_with_visible_focus(chat):
    for v, f in _chat_runs(chat).items():
        if not v.endswith("keyboard"):
            continue
        assert f["tabbedToLaunch"] == "kgcLaunch" and f["launchFocus"].startswith("solid"), v
        assert f["openFocus"]["cls"] == "kgc-close" and f["openFocus"]["outline"].startswith("solid"), v
        assert f["firstTab"]["pick"] == "Check the tables" and f["firstTab"]["outline"].startswith("solid"), v
        assert f["keyboardSteps"] == ["Check the tables", "Yes, add the link", "Create a semantic model", "Create an ontology", "Draft data products"], v
        assert len(f["keyboardResults"]) == 4 and f["keyboardEndFocus"] == "Check my tables", v
        assert f["escape"] == {"hidden": True, "focus": "kgcLaunch"} and f["reopenedKept"] > 0, v
        assert f["escapeEnd"] == {"hidden": True, "focus": "kgcLaunch"}, v
        if v.startswith("375"):
            assert f["tabOutside"] == [], (v, f["tabOutside"])                 # Tab stays in the chat on a phone


def test_chat_on_a_phone_covers_the_screen_and_holds_the_page(chat):
    for scheme in ("light", "dark"):
        p = chat[f"phone@{scheme}"]
        assert p["scrolled"] == 0 and p["htmlOverflow"] == "hidden" and p["mainInert"] and p["modal"] == "true", p
        assert p["width"] == p["vw"] and p["top"] <= 41 and p["height"] >= p["vh"] - 41, p
        assert p["afterClose"] == {"inert": 0, "lock": False}, p


def test_chat_mascots_off_and_reduced_motion(chat):
    m = chat["mascotsOff"]
    assert m["launchText"] == "Try a demo" and m["launchFig"] == "none" and m["figuresShown"] == 0
    assert "All 15 of its values" in m["question"] and "Semantic model ready" in m["results"][1]
    assert chat["mascotsOffPhone"] == 0
    for w in (375, 1280):
        r = chat[f"reduced@{w}"]
        assert r["launchTransition"] == "0s" and r["launchTransform"] == "none" and r["animations"] == [] and r["bits"] == 0, (w, r)
    # n93: a restored chat with reduced motion and Mascots: off: no animation, no figure, every picture
    rr = chat["restoredReduced"]
    assert rr["state"]["open"] and rr["state"]["anims"] == [] and rr["state"]["bits"] == 0 and rr["figures"] == 0, rr
    assert len(rr["pics"]) == 2 and rr["svgShown"] == 2 and all(p["inside"] for p in rr["pics"]), rr


def test_chat_when_the_plan_does_not_load(chat):
    """The plan fails to load (the request is aborted): one sentence and a link to /check?example=sample, no button."""
    f = chat["planFails"]
    assert f["links"] == ["/check?example=sample"] and "did not load" in f["text"] and f["buttons"] == 0, f


# ------------------------------------------------------------------ n93: the memory within the tab, and every page ----
def test_chat_comes_back_after_a_page_change_as_it_was_where_it_was_without_the_focus(chat):
    """At 1280 px, light and dark: open on one page, the menu to the next: the chat is open there with the same steps and
    pictures, in the same place, without animation, confetti or the focus; its files and the plan load with that page.
    Esc on the page beside it does not close it; Close is stored, and the page after that loads only the button. At
    375 px the chat stays closed after the page change and loads nothing until the button is pressed. Either way the
    button brings the steps back, the focus on Close."""
    for scheme in ("light", "dark"):
        f = chat[f"pagechange@1280-{scheme}"]
        b, a = f["before"], f["after"]
        assert f["errors"] == [], f["errors"]
        assert json.loads(f["storedOpen"]) == {"open": True, "steps": ["scan", "yes"]}
        assert a["open"] and a["still"] and a["you"] == b["you"] == ["Check the tables", "Yes, add the link"] and a["pics"] == b["pics"] == 2, a
        assert a["rect"] == b["rect"], (a["rect"], b["rect"])
        assert not a["focusInChat"] and a["anims"] == [] and a["bits"] == 0 and not a["launchShown"], a
        assert sorted(set(f["afterRequests"])) == sorted(CHAT_FILES), f["afterRequests"]
        assert all(p["inside"] and p["fit"] for p in f["afterPics"]) and len(f["afterPics"]) == 2
        assert f["escOnPage"] is True
        assert json.loads(f["closedStored"]) == {"open": False, "steps": ["scan", "yes"]}
        c = f["closedNext"]
        assert not c["loaded"] and not c["box"] and c["launchShown"] and f["closedRequests"] == [], (c, f["closedRequests"])
        r = f["reopened"]
        assert r["open"] and r["you"] == ["Check the tables", "Yes, add the link"] and r["pics"] == 2, r
        assert r["focusInChat"] and r["bits"] == 0, r
    for scheme in ("light", "dark"):
        f = chat[f"pagechange@375-{scheme}"]
        a = f["after"]
        assert f["errors"] == [] and json.loads(f["storedOpen"])["open"] is True
        assert not a["loaded"] and not a["box"] and a["launchShown"] and f["afterRequests"] == [], (a, f["afterRequests"])
        r = f["reopened"]
        assert r["open"] and r["you"] == ["Check the tables", "Yes, add the link"] and r["focusInChat"], r


def test_chat_a_link_inside_closes_it_and_connect_goes_to_the_set_up_guide(chat):
    for w in (1280, 375):
        f = chat[f"link@{w}"]
        assert f["url"] == "/start" and "set-up guide" in f["title"], f
        assert f["stored"] == {"open": False, "steps": ["scan", "yes", "model", "ontology", "domains"]}, f["stored"]
        assert not f["after"]["open"] and not f["after"]["loaded"], f["after"]
        assert f["reopened"]["open"] and f["reopened"]["pics"] == 5 and f["endPicks"][:2] == ["Check my tables", "Connect to my Fabric"], f


def test_chat_start_over_empties_the_steps(chat):
    f = chat["startOver"]
    assert f["before"] == {"open": True, "steps": ["scan", "yes"]}
    assert f["stored"] == {"open": True, "steps": []} and f["after"]["you"] == [] and f["after"]["msgs"] == 1 and f["after"]["pics"] == 0
    assert f["focus"] == "Check the tables"
    assert f["next"]["open"] and f["next"]["you"] == [] and f["next"]["msgs"] == 1


def test_chat_ignores_a_corrupt_stored_value(chat):
    """Anything under the key that is not what the chat writes is ignored: the chat does not open by itself, nothing of
    the value is shown or run, and the button opens it fresh."""
    c = chat["corrupt"]
    assert c["errors"] == [], c["errors"]
    for r in c["results"]:
        assert not r["state"]["open"] and r["state"]["you"] == [], r
        assert r["opened"]["open"] and r["opened"]["you"] == [] and r["opened"]["msgs"] == 1, r
        assert r["injected"] == {"img": 0, "flag": False}, r
        assert json.loads(r["storedAfter"]) == {"open": True, "steps": []}, r
    # extra keys beside a valid value: the steps come back, the rest is ignored
    assert c["extra"]["open"] and c["extra"]["you"] == ["Check the tables", "Yes, add the link"] and c["extraInjected"] == 0


def test_chat_works_without_storage(chat):
    f = chat["blocked"]
    assert f["errors"] == [], f["errors"]
    assert len(f["results"]) == 2 and "Semantic model ready" in f["results"][1] and f["pics"] == 3
    assert f["afterStartOver"]["you"] == [] and f["afterStartOver"]["msgs"] == 1
    assert not f["next"]["open"] and not f["next"]["loaded"], f["next"]                  # it cannot remember: as in n92
    assert f["reopened"]["open"] and f["reopened"]["you"] == [], f["reopened"]


def test_chat_button_on_every_ordinary_page_and_it_covers_nothing(chat):
    """n93: at 375 and 1280 px, every page in CHAT_PAGES shows the button, loads nothing of the chat, and at the bottom of
    the page the button covers no text or control, with no fixed or sticky part of the page under it. n154: /check has
    it too, and /demo goes to /check."""
    res = chat["pages"]
    for w in (375, 1280):
        # the one console line is the 404 page's own status (the page at /no-such-page answers 404 on purpose)
        assert [e for e in res[f"errors@{w}"] if "404 (Not Found)" not in e] == [], res[f"errors@{w}"]
        assert len(res[f"errors@{w}"]) <= 1, res[f"errors@{w}"]
        for p in CHAT_PAGES:
            r = res[f"{p}@{w}"]
            assert r["shown"] and r["text"] == "Try a demo" and not r["chat"], (p, w, r)
            assert r["covers"] == [] and r["fixed"] == [], (p, w, r)
        r = res[f"/demo@{w}"]
        assert r["button"] and r["path"] == "/check", (w, r)


@pytest.fixture(scope="module")
def docs_run(site):
    """n86a: the docs' sub-pages (tests/docs_browser.js) under the server's own headers."""
    cmd = ["node", str(ROOT / "tests" / "docs_browser.js"), site] + ([CHROMIUM] if CHROMIUM else [])
    keep = {k: os.environ.get(k) for k in ("PRODUCT_NAME", "MCP_PUBLIC_URL")}
    os.environ.update({"PRODUCT_NAME": "Krusgraph", "MCP_PUBLIC_URL": "https://krusgraph.test/mcp"})   # as the server runs
    try:
        paths = [x["path"] for x in pages.docs_pages()]
    finally:
        for k, v in keep.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=600, env=os.environ | {"DOCS_PAGES": json.dumps(paths)})
    assert out.returncode == 0, out.stderr[-2000:]
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_docs_pages_fit_and_raise_no_error(docs_run):
    assert docs_run["overflow"] == [] and docs_run["errors"] == []


def test_docs_menu_by_width_mouse_keyboard_and_without_javascript(docs_run):
    for key, r in docs_run["runs"].items():
        wide = key.startswith("1280")
        assert r["menuWide"] is wide and r["menuPhone"] is not wide, key
        assert r["otp"] in (None, wide), key
        if not wide:
            assert r["closedLinkVisible"] is False and r["openByKey"] is True and r["focusAfter"] == "/docs"
            assert r["openOverflow"] is False and r["closedByClick"] is True
    assert docs_run["runs"]["1280-light"]["bg"] != docs_run["runs"]["1280-dark"]["bg"]
    assert docs_run["noJs"]["url"] == "/docs#test-status" and docs_run["noJs"]["links"] > 25 and docs_run["noJs"]["opens"] is True


def test_docs_old_anchors_land_on_the_page_and_heading(docs_run):
    for key, r in docs_run["runs"].items():
        assert r["oldAnchor"] == "/docs/reference/test-status#test-status" and r["headingInView"], key
        assert r["hashChange"] == "/docs/get-started/first-time-errors#first-time-errors", key
        assert r["ownAnchor"] == "/docs#why-krusgraph", key
