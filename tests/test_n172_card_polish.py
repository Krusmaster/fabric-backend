"""Round n172: the MCP Apps cards polished before the founder records the film (tried in Claude on 8 November 2026,
demo_lh, schema shop).

1. A transient SQL error no longer changes the result: a read on the SQL analytics endpoint that fails with a transient
   connection error (0x2714, SQLSTATE 08S01, Azure SQL's transient numbers) is tried again on a fresh connection; the
   sign-in and syntax errors never are. When every try fails, the plan says the count could not run, the candidate is
   "not counted" (never "not supported"), the map draws it grey and the Thinker offers to count again.
2. The map's labels sit on their own lines, cover no table and no other label, and the map fits Claude's card width
   (640-720 px), for the 7-table shop schema and a 12-table plan.
3. The Thinker and the Builder speak plain English; no bubble shows argument syntax. Text clients keep each action's `say`.
4. The plan's summary is short sentences built from the same facts; the details stay behind "Show details".
5. No maintainer notes (how a tool was tested) and no "certainty" on a card; the rule instead.
6. No sentence three times: the title is "Plan" / "Plan check", Onto says the numbers once.
7. The Plan check card: the Builder's three builds, the drafts under "More".
8. Light and dark; the mascots switch still works.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from fabric_backend import errors, infer, mcp_apps, mcp_apps_build as build, mcp_apps_words as words, server
from fabric_backend.platforms import fabric as fabric_platform

from test_golden import SRC, fabric  # noqa: F401  (the hosted server against the synthetic shop workspace)
import golden_support as gs

TESTS = Path(__file__).parent
SHIP_TO = "orders.ship_to_id>addresses"
TCP_0x2714 = "('08S01', '[08S01] [Microsoft][ODBC Driver 18 for SQL Server]TCP Provider: Error code 0x2714 (10004) (SQLExecDirectW)')"
SYNTAX = "('42000', \"[42000] [Microsoft][ODBC Driver 18 for SQL Server][SQL Server]Incorrect syntax near 'x'. (102) (SQLExecDirectW)\")"
LOGIN = "('28000', \"[28000] [Microsoft][ODBC Driver 18 for SQL Server][SQL Server]Login failed for user '<token-identified principal>'. (18456)\")"


class OperationalError(Exception):
    """What pyodbc raises for a dropped connection (its module is pyodbc in real life)."""


def _registered(tool, /):
    fn = getattr(server, tool)
    if tool in build.ACTION_TOOLS:
        fn = build.with_actions(tool, fn, server._item_names, server._workspace_id_ctx)
    return mcp_apps.structured(fn, tool)


def _sc(tool, /, **kw):
    r = _registered(tool)(**kw)
    return r, r.structured_content


def _flaky(fabric, monkeypatch, fails: int, message: str = TCP_0x2714, match: str = "with_value"):
    """The fake endpoint's counting query for R5 fails `fails` times (-1: always) with `message`; returns the call log."""
    monkeypatch.setattr(fabric_platform, "_sleep", lambda s: waits.append(s))
    waits: list[float] = []
    real = fabric.odbc.connect
    state = {"left": fails, "tries": 0, "connects": 0, "waits": waits}

    def connect(dsn, attrs_before=None, timeout=None, **kw):
        conn = real(dsn, attrs_before=attrs_before, timeout=timeout, **kw)
        state["connects"] += 1
        cursor = conn.cursor

        def flaky_cursor():
            cur = cursor()
            run = cur.execute

            def execute(sql):
                if match in sql:
                    state["tries"] += 1
                    if state["left"] != 0:
                        state["left"] -= 1 if state["left"] > 0 else 0
                        raise OperationalError(message)
                return run(sql)
            cur.execute = execute
            return cur
        conn.cursor = flaky_cursor
        return conn
    monkeypatch.setattr(fabric.odbc, "connect", connect)
    return state


# ------------------------------------------------------------------ 1. transient errors -------------------------------

@pytest.mark.parametrize("message,want", [
    (TCP_0x2714, True),
    ("('08S01', '[08S01] [Microsoft][ODBC Driver 18 for SQL Server]Communication link failure (0) (SQLExecDirectW)')", True),
    ("[Microsoft][ODBC Driver 18 for SQL Server][SQL Server]Database 'x' on server 'y' is not currently available. Please retry the connection later. (40613)", True),
    ("[SQL Server]The service is currently busy. Retry the request after 10 seconds. Incident ID: x. Code: 1. (40501)", True),
    ("A transport-level error has occurred when sending the request to the server. (provider: TCP Provider, error: 0 - An existing connection was forcibly closed by the remote host.)", True),
    (SYNTAX, False), (LOGIN, False),
    ("('HYT00', '[HYT00] [Microsoft][ODBC Driver 18 for SQL Server]Query timeout expired (0) (SQLExecDirectW)')", False),
    ("('42S02', \"[42S02] [SQL Server]Invalid object name 'shop.ghost'. (208)\")", False),
    ("AADSTS50173: the grant has expired", False), ("division by zero", False),
])
def test_which_sql_errors_are_transient(message, want):
    assert errors.transient(OperationalError(message)) is want


def _fake_pyodbc(script):
    """A pyodbc whose reads answer from `script`: a list of exceptions or row lists, one per execute."""
    import types
    mod = types.ModuleType("pyodbc")
    mod.connects = 0

    class Cur:
        description = [("n",)]

        def execute(self, sql):
            step = script.pop(0)
            if isinstance(step, Exception):
                raise step
            self.rows = step

        def fetchall(self):
            return self.rows

    class Conn:
        timeout = 0
        closed = False

        def cursor(self):
            return Cur()

        def close(self):
            self.closed = True

    def connect(*a, **k):
        mod.connects += 1
        return Conn()
    mod.connect = connect
    return mod


ITEM = {"sql_host": "x.datawarehouse.fabric.microsoft.com", "sql_db": "demo_lh"}


def test_a_read_that_drops_once_is_tried_again_on_a_fresh_connection(monkeypatch):
    mod = _fake_pyodbc([OperationalError(TCP_0x2714), [(7,)]])
    monkeypatch.setitem(__import__("sys").modules, "pyodbc", mod)
    waits = []
    ex = fabric_platform.connect(ITEM, "tok", sleep=waits.append)
    assert ex("SELECT 1 AS n") == [{"n": 7}]
    assert ex.retries == 1 and mod.connects == 2 and waits == [fabric_platform.RETRY_DELAYS[0]]


def test_a_read_that_always_drops_is_tried_a_bounded_number_of_times_then_raised(monkeypatch):
    mod = _fake_pyodbc([OperationalError(TCP_0x2714) for _ in range(10)])
    monkeypatch.setitem(__import__("sys").modules, "pyodbc", mod)
    waits = []
    ex = fabric_platform.connect(ITEM, "tok", sleep=waits.append)
    with pytest.raises(OperationalError, match="0x2714"):
        ex("SELECT 1 AS n")
    assert waits == list(fabric_platform.RETRY_DELAYS) and ex.retries == len(fabric_platform.RETRY_DELAYS)
    assert waits == sorted(waits) and waits[-1] > waits[0]                  # backoff: each wait longer than the last


@pytest.mark.parametrize("message", [SYNTAX, LOGIN])
def test_a_syntax_or_sign_in_error_is_never_tried_again(monkeypatch, message):
    mod = _fake_pyodbc([OperationalError(message), [(1,)]])
    monkeypatch.setitem(__import__("sys").modules, "pyodbc", mod)
    waits = []
    ex = fabric_platform.connect(ITEM, "tok", sleep=waits.append)
    with pytest.raises(OperationalError):
        ex("SELECT 1 AS n")
    assert waits == [] and ex.retries == 0 and mod.connects == 1


def test_plan_backend_counts_the_link_after_a_dropped_connection(fabric, monkeypatch):
    st = _flaky(fabric, monkeypatch, fails=1)
    _, d = _sc("plan_backend", **SRC)
    assert st["tries"] == 2 and st["waits"] == [fabric_platform.RETRY_DELAYS[0]]
    assert d["summary"].splitlines()[0] == "7 tables, 6 with keys, 7 relationships"
    rel = next(r for r in d["relationships"] if r["source"] == "orders" and r["source_cols"] == ["ship_to_id"])
    assert rel["rule"] == "R5" and "proposed" not in d
    _, v = _sc("validate_plan", **SRC)                                    # the plan and the check now agree
    assert v["totals"]["relationships"]["checked"] == 7


def test_when_every_try_fails_the_plan_says_the_count_could_not_run(fabric, monkeypatch):
    st = _flaky(fabric, monkeypatch, fails=-1)
    r, d = _sc("plan_backend", **SRC)
    assert st["tries"] == len(fabric_platform.RETRY_DELAYS) + 1
    lines = d["summary"].splitlines()
    assert lines[0] == "7 tables, 6 with keys, 6 relationships"
    assert any("could not be counted because the counting query could not run: orders.ship_to_id -> addresses" in x for x in lines)
    p = next(x for x in d["proposed"] if x["source"] == "orders")
    assert p["not_counted"] == "failed" and p["reason"].startswith(infer.R5_COUNT_FAILED)
    assert "connection to the SQL endpoint dropped" in p["reason"] and "rows did not support" not in p["reason"]
    assert d["counted_in_rows"]["failed"] == 1
    # the card: the link grey, "not counted"; the Thinker offers to count again, with a button that plans again
    m = {x["id"]: x for x in d["map"]["relationships"]}
    assert m[SHIP_TO]["state"] == "not_counted" and m[SHIP_TO]["proposed"] is True
    card = d[words.KEY]
    assert card["thinker"] == "I couldn't count ship_to_id → addresses: the connection to the data dropped. Shall I count it again?"
    assert "1 more link could not be counted because the connection to the data dropped: ship_to_id → addresses. Not counted is not rejected." in card["lines"]
    assert "6 links, all found by name." in card["lines"]
    again = [a for a in d["actions"] if a["label"] == "Count again"]
    assert len(again) == 1 and again[0]["tool"] == "plan_backend" and again[0]["who"] == "thinker"
    assert again[0]["arguments"] == SRC
    # the summary form says it too
    _, s = _sc("plan_backend", **SRC, detail="summary")
    assert any(infer.R5_COUNT_FAILED in x for x in s["proposed"]) and any(a["label"] == "Count again" for a in s["actions"])


def test_a_syntax_error_in_the_count_is_not_tried_again_and_still_not_counted(fabric, monkeypatch):
    st = _flaky(fabric, monkeypatch, fails=-1, message=SYNTAX)
    _, d = _sc("plan_backend", **SRC)
    assert st["tries"] == 1 and st["waits"] == []
    p = next(x for x in d["proposed"] if x["source"] == "orders")
    assert p["not_counted"] == "failed" and "OperationalError" in p["reason"]
    assert d[words.KEY]["thinker"].startswith("I couldn't count ship_to_id → addresses: the counting query could not run.")
    assert d[words.KEY]["thinker"].startswith("I couldn't count ship_to_id \u2192 addresses: the counting query could not run.")


# ------------------------------------------------------------------ 3-6. the words -----------------------------------

def test_the_plan_cards_words_are_short_sentences_from_the_plan(fabric):
    r, d = _sc("plan_backend", **SRC)
    c = d[words.KEY]
    assert c["title"] == "Plan"
    assert c["lines"] == ["7 tables, 6 with a key.",
                          "7 links: 6 by name, 1 found from the values (ship_to_id → addresses).",
                          "audit_log has no key, so nothing can point to it."]
    assert c["onto"] == " ".join(c["lines"])
    assert c["thinker"] == "Shall I check these links against the rows?"
    assert c["builder"] == "I can build a semantic model, an ontology or an API from this plan. Each shows a dry run first."
    assert words.KEY not in json.loads(r.content[0].text)                   # structuredContent only: the text is unchanged
    text_actions = json.loads(r.content[0].text)["actions"]                 # text clients keep the full next step
    assert any('run validate_plan with workspace="demo"' in a["say"] for a in text_actions)


def test_the_plan_check_cards_words(fabric):
    r, d = _sc("validate_plan", **SRC)
    c = d[words.KEY]
    assert c["title"] == "Plan check"
    assert c["lines"][:2] == ["6 of 6 keys hold.", "7 of 7 links hold, with no orphans."]
    assert c["builder"] == words.BUILDER_PLAN
    assert c["thinker"] == "One thing needs your attention, listed below. I would look at it before building."
    assert all(c["thinker"] not in str(x) for x in d["attention"].values())          # not the attention item again
    steps = [s.get("text", "") + s.get("why", "") for s in d["next_steps"]]
    assert all(c["builder"] not in s for s in steps)


@pytest.mark.parametrize("tool,kw", [("plan_backend", {}), ("validate_plan", {}), ("create_semantic_model", {"name": "m1"}),
                                     ("create_ontology", {"name": "o1"}), ("create_backend", {"name": "a1"}),
                                     ("domain_draft", {}), ("create_semantic_model", {"name": "m1", "dry_run": False})])
def test_no_bubble_says_argument_syntax(fabric, tool, kw):
    _, d = _sc(tool, **SRC, **kw)
    c = d.get(words.KEY) or {}
    for k in ("onto", "thinker", "builder"):
        if k in c:
            assert not words.WORDS_WITH_ARGUMENTS.search(c[k]), (k, c[k])
            assert "=" not in c[k] and "dry_run" not in c[k] and "workspace" not in c[k]
    for a in d.get("actions") or []:                                       # the arguments are on the buttons
        assert a.get("url") or isinstance(a.get("arguments"), dict)


def test_the_argument_pattern_finds_what_the_founder_saw():
    seen = ['Check against the rows: run validate_plan with workspace="demo", source="demo_lh", schema="shop".',
            'Build a semantic model named shop_model_2: run create_semantic_model as a dry run with workspace="demo"',
            'Run semantic_model_draft(workspace="demo")']
    assert all(words.WORDS_WITH_ARGUMENTS.search(s) for s in seen)
    plain = [words.THINKER_CHECK, words.BUILDER_PLAN, "7 links: 6 by name, 1 found from the values (ship_to_id → addresses).",
             "audit_log has no key, so nothing can point to it."]
    assert not any(words.WORDS_WITH_ARGUMENTS.search(s) for s in plain)


def test_the_cards_drop_maintainer_notes_and_certainty():
    for html in (mcp_apps.card_html(), build.card_html()):
        assert "MAINTAINER = /unit-tested|unit tests|tested end to end" in html
        assert "the active path has certainty" in html                         # the pattern that rewrites it
    for tool, src in (("validate_plan", mcp_apps.card_html()), ("build", build.card_html())):
        assert "Next steps (each reads or drafts; nothing is created)" not in src, tool


def test_the_semantic_models_inactive_link_carries_its_rule(fabric):
    _, d = _sc("create_semantic_model", **SRC, name="m1")
    inactive = d["summary"]["inactive"]
    assert inactive and all(x["rule"] for x in inactive)
    assert next(x for x in inactive if x["source"] == "orders" and x["columns"] == ["ship_to_id"])["rule"] == "R5"


# ------------------------------------------------------------------ in Chromium at Claude's width ---------------------

def _playwright() -> bool:
    return bool(shutil.which("node")) and subprocess.run(["node", "-e", "require('playwright')"], capture_output=True).returncode == 0


def _show(tmp_path, card, sc, tool, theme="light", width=680, args=None, shot=None):
    (tmp_path / "card.html").write_text(card, encoding="utf-8")
    (tmp_path / "sc.json").write_text(json.dumps({**sc, "__args": args or {}}, default=str), encoding="utf-8")
    cmd = ["node", str(TESTS / "mcp_apps_n172_browser.js"), str(tmp_path / "card.html"), str(tmp_path / "sc.json"), tool, theme, str(width)]
    if shot:
        cmd.append(str(shot))
    run = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, run.stderr[-2000:]
    return json.loads(run.stdout)


def _no_overlaps(out, width):
    assert out["errors"] == []
    assert out["overlaps"] == 0 and out["nodeOverlaps"] == 0, out["labels"]
    assert out["offEdge"] == [] and out["outside"] == []
    assert out["svgWidth"] <= width - 32 + 0.5 and out["bodyWidth"] <= width


needs_browser = pytest.mark.skipif(not _playwright(), reason="node + playwright not available")


@needs_browser
@pytest.mark.parametrize("width,theme", [(640, "light"), (720, "dark")])
def test_the_plan_card_at_claudes_width(fabric, tmp_path, width, theme):
    _, d = _sc("plan_backend", **SRC)
    out = _show(tmp_path, build.card_html(), d, "plan_backend", theme, width, SRC)
    _no_overlaps(out, width)
    assert out["unlabelled"] == "" and {l["id"] for l in out["labels"]} == {x["id"] for x in d["map"]["relationships"]}
    ship = next(l for l in out["labels"] if l["id"] == SHIP_TO)
    assert ship["text"][0].startswith("R5")
    # 6: the header is just "Plan", Onto says the numbers once, the card's copy of them shows only with the mascots off
    c = d[words.KEY]
    assert out["title"] == "Plan"
    assert out["bubbles"] == {"onto": c["onto"], "thinker": c["thinker"], "builder": c["builder"]}
    assert not out["verdictShown"] and out["text"].count("7 tables, 6 with a key.") == 1
    assert out["afterToggle"]["bubbles"] == {} and out["afterToggle"]["verdictShown"]
    # 3: no argument syntax in what the card shows outside "Show details"
    for said in out["bubbles"].values():
        assert not words.WORDS_WITH_ARGUMENTS.search(said)
    assert "Check against the rows" in out["buttons"] and any(b.startswith("Build a semantic model") for b in out["buttons"])
    # 4: the old summary line is gone from the card
    assert "counting query(ies)" not in out["text"] and "see plan.proposed" not in out["text"]
    # 8: readable in both themes
    assert out["colours"]["bubbleInk"] != out["colours"]["bubble"] and out["colours"]["label"] != out["colours"]["labelBg"]


@needs_browser
def test_the_plan_card_shows_a_link_it_could_not_count_in_grey(fabric, monkeypatch, tmp_path):
    _flaky(fabric, monkeypatch, fails=-1)
    _, d = _sc("plan_backend", **SRC)
    out = _show(tmp_path, build.card_html(), d, "plan_backend", "light", 680, SRC)
    _no_overlaps(out, 680)
    ship = next(l for l in out["labels"] if l["id"] == SHIP_TO)
    assert "st-not_counted" in ship["cls"] and "not counted" in ship["text"][0]
    assert out["bubbles"]["thinker"].startswith("I couldn't count ship_to_id") and "Count again" in out["buttons"]
    assert "not counted" in out["text"]


def _twelve() -> dict:
    """A 12-table plan's map: a star with chains, long names, R1 and R5 links, two keyless tables."""
    names = ["customers", "customer_addresses", "orders", "order_items", "products", "product_categories", "suppliers",
             "warehouses", "shipments", "invoices", "payments", "audit_log"]
    keyless = {"audit_log", "order_items"}
    tables = [{"name": n, "key": [] if n in keyless else [n.rstrip("s") + "_id"], "key_rule": "K3" if n in keyless else "K2", "columns": 6}
              for n in names]
    pairs = [("customer_addresses", "customers", "R1"), ("orders", "customers", "R1"), ("order_items", "orders", "R1"),
             ("order_items", "products", "R1"), ("products", "product_categories", "R1"), ("products", "suppliers", "R1"),
             ("shipments", "orders", "R1"), ("shipments", "warehouses", "R1"), ("invoices", "orders", "R1"),
             ("payments", "invoices", "R1"), ("orders", "customer_addresses", "R5"), ("audit_log", "customers", "R1")]
    rels = []
    for s, t, rule in pairs:
        col = "ship_to_id" if rule == "R5" else t.rstrip("s") + "_id"
        rels.append({"id": f"{s}.{col}>{t}", "source": s, "source_cols": [col], "target": t, "target_cols": [t.rstrip("s") + "_id"], "rule": rule})
    return {"tables": tables, "relationships": rels, "checked": False}


@needs_browser
@pytest.mark.parametrize("width", [640, 720])
def test_a_twelve_table_map_fits_without_overlaps(tmp_path, width):
    m = _twelve()
    sc = {"summary": "12 tables", "relationships": m["relationships"], "map": m,
          words.KEY: {"title": "Plan", "lines": ["12 tables, 10 with a key."], "onto": "12 tables, 10 with a key."}}
    out = _show(tmp_path, build.card_html(), sc, "plan_backend", "light", width)
    _no_overlaps(out, width)
    assert len(out["nodes"]) == 12
    drawn = {l["id"] for l in out["labels"]}
    left = set(out["unlabelled"].split()) if out["unlabelled"] else set()
    assert drawn | left == {r["id"] for r in m["relationships"]} and not drawn & left
    assert len(drawn) >= 9                                                  # most links keep their label in the picture


@needs_browser
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_the_plan_check_card(fabric, tmp_path, theme):
    _, d = _sc("validate_plan", **SRC)
    out = _show(tmp_path, mcp_apps.card_html(), d, "validate_plan", theme, 680, SRC)
    _no_overlaps(out, 680)
    c = d[words.KEY]
    assert out["title"] == "Plan check"
    assert "Next steps (each reads or drafts" not in out["text"]
    builds = [b for b in out["buttons"] if b.startswith(("Build a semantic model", "Create an ontology", "Create an API for GraphQL"))]
    assert len(builds) == 3
    assert not any(b.startswith("Run ") for b in out["buttons"])               # the drafts are under "More", folded
    assert out["more"]["tag"] == "DETAILS" and not out["more"]["open"] and not out["more"]["hidden"]
    assert "Run semantic_model_draft" in out["more"]["text"] or "Run answer_query_draft" in out["more"]["text"]
    assert out["bubbles"]["builder"] == words.BUILDER_PLAN
    assert all(out["bubbles"]["builder"] not in (s.get("text", "") + s.get("why", "")) for s in d["next_steps"])
    assert out["bubbles"]["onto"] == c["onto"] and not out["verdictShown"] and not out["countsShown"]
    assert out["bubbles"]["thinker"] == c["thinker"]
    assert out["afterToggle"]["verdictShown"] and out["afterToggle"]["countsShown"]
    for said in out["bubbles"].values():
        assert not words.WORDS_WITH_ARGUMENTS.search(said)


@needs_browser
def test_the_dry_run_card_has_no_maintainer_notes_and_no_certainty(fabric, tmp_path):
    _, d = _sc("create_semantic_model", **SRC, name="m1")
    assert "Unit-tested" in d["note"] and "certainty" in json.dumps(d)       # still in the tool's own answer
    out = _show(tmp_path, build.card_html(), d, "create_semantic_model", "light", 680, {**SRC, "name": "m1"})
    assert out["errors"] == []
    shown = out["text"]
    for gone in ("Unit-tested", "tested end to end", "certainty", "synthetic data"):
        assert gone not in shown, gone
    assert re.search(r"ship_to_id → addresses \(R5\)", shown)
    assert not words.WORDS_WITH_ARGUMENTS.search(out["bubbles"].get("builder", ""))
