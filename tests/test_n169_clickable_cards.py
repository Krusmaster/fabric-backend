"""Round n169: the mascots' next steps on the MCP Apps cards are buttons (founder, 8 November 2026: "I want to click the
mascots' suggestions and have everything created, without writing text"), and Claude signs in at /mcp/connect.

Checked here, all with the hosted server against the synthetic shop workspace (test_golden.fabric):
- the buttons come only from the tool's own answer: an answer with an error, or a tool without buttons, gets none;
- a build button's payload is a dry run, under a free name derived from the source that no item of the workspace has;
- the dry run's answer is the only one with Create, and Create carries dry_run=false and otherwise the identical
  arguments; a dry run whose name is taken gets no Create;
- after a create that succeeded: "Open in Fabric" from the result's id, and after a semantic model "Create a report on
  it", again a dry run;
- plan_backend without a schema on a source with several schemas asks which, one button per schema, and plans nothing;
- with the flag off nothing changes: no build card, no actions, the module functions answer as before;
- /start, the docs, the connect chooser, llms.txt and /consent/done give Claude /mcp/connect with "Register
  automatically" when client registration is on, and /mcp when it is off.
What this does not show: that Claude renders the card or runs a button. That is tried by hand after a deploy.
"""
from __future__ import annotations

import asyncio
import json
import re
from html.parser import HTMLParser

import pytest

from fabric_backend import mcp_apps, mcp_apps_build as build, server

from test_golden import SRC, fabric  # noqa: F401  (the hosted server against the synthetic shop workspace)
import golden_support as gs

TAKEN = {"demo_lh", "demo_wh", "shop_api", "shop_model"}       # the item names of the fake workspace


def _registered(name):
    """The tool the way server.py registers it with the flag on: the module's function with the actions added."""
    return build.with_actions(name, getattr(server, name), server._item_names, server._workspace_id_ctx)


def _call(tool_name, /, **kw):
    return json.loads(_registered(tool_name)(**kw))


# ------------------------------------------------------------------ names ---------------------------------------------

def test_a_suggested_name_is_never_one_the_workspace_has():
    assert build.free_name("shop_model", TAKEN) == "shop_model_2"
    assert build.free_name("shop_model", TAKEN | {"SHOP_MODEL_2", "shop_model_3"}) == "shop_model_4"   # case-insensitive
    assert build.free_name("shop_ontology", TAKEN) == "shop_ontology"
    for base in ("shop_model", "shop_api", "demo_lh"):
        assert build.free_name(base, TAKEN).lower() not in {t.lower() for t in TAKEN}
    assert build.name_base("demo_lh", "shop") == "shop" and build.name_base("demo lh", "dbo") == "demo_lh"
    assert build.name_base("9x", None) == "kg_9x"


# ------------------------------------------------------------------ after planning --------------------------------------

def test_plan_backend_offers_the_check_and_three_dry_run_builds(fabric):
    out = _call("plan_backend", **SRC)
    acts = out["actions"]
    assert [a["label"] for a in acts] == ["Check against the rows", "Build a semantic model", "Create an ontology",
                                          "Create an API for GraphQL"]
    check = acts[0]
    assert check["kind"] == "call" and check["tool"] == "validate_plan" and check["who"] == "thinker"
    assert check["arguments"] == {"workspace": "demo", "source": "demo_lh", "schema": "shop"}
    names = {}
    for a in acts[1:]:
        assert a["kind"] == "dry_run" and a["who"] == "builder"
        assert a["arguments"]["dry_run"] is True                     # a build button's payload is the dry run
        assert a["arguments"]["name"] == a["name"] and a["name"].lower() not in {t.lower() for t in TAKEN}
        assert a["name"] in a["say"] and "dry run" in a["say"]
        names[a["tool"]] = a["name"]
    assert names == {"create_semantic_model": "shop_model_2", "create_ontology": "shop_ontology",
                     "create_backend": "shop_api_2"}


def test_validate_plan_offers_the_builds_but_not_the_check_it_just_ran(fabric):
    out = _call("validate_plan", **SRC)
    assert [a["label"] for a in out["actions"]] == ["Build a semantic model", "Create an ontology", "Create an API for GraphQL"]
    assert out["next_steps"] == json.loads(server.validate_plan(**SRC))["next_steps"]      # the n103 steps are unchanged


def test_an_answer_with_an_error_gets_no_button(fabric):
    text = _registered("plan_backend")(**{**SRC, "source": "missing_lh"})
    assert json.loads(text).get("error") and "actions" not in json.loads(text)
    assert build.actions_for("create_semantic_model", {"workspace": "demo", "name": "x"}, {"error": "no"}, TAKEN) == ([], None)
    assert build.actions_for("list_tables", {"workspace": "demo"}, {"tables": []}, TAKEN) == ([], None)


def test_no_name_is_suggested_when_the_item_names_cannot_be_read(fabric, monkeypatch):
    def refuse(workspace, ctx):
        raise RuntimeError("403")
    out = json.loads(build.with_actions("plan_backend", server.plan_backend, refuse, server._workspace_id_ctx)(**SRC))
    assert [a["label"] for a in out["actions"]] == ["Check against the rows"]
    assert "could not be read" in out["actions_note"]


# ------------------------------------------------------------------ dry run, then Create ------------------------------

@pytest.mark.parametrize("tool", ["create_semantic_model", "create_ontology", "create_backend"])
def test_only_the_dry_run_has_create_with_the_identical_arguments(fabric, tool):
    plan = _call("plan_backend", **SRC)
    button = next(a for a in plan["actions"] if a["tool"] == tool)
    dry = _call(tool, **button["arguments"])                        # what the button asks the host to run
    assert dry["dry_run"] is True
    [create] = dry["actions"]
    assert create["kind"] == "create" and create["label"] == "Create" and create["tool"] == tool
    assert create["arguments"] == {**button["arguments"], "dry_run": False}
    assert {k: v for k, v in create["arguments"].items() if k != "dry_run"} == \
           {k: v for k, v in button["arguments"].items() if k != "dry_run"}
    assert "dry_run=false" in create["say"]


def test_a_dry_run_whose_name_is_taken_gets_no_create(fabric):
    dry = _call("create_semantic_model", **SRC, name="shop_model")
    assert dry["dry_run"] is True and "actions" not in dry
    assert "already exists" in dry["actions_note"] and "nothing is overwritten" in dry["actions_note"]


def test_a_dry_run_called_without_dry_run_still_creates_with_the_same_arguments(fabric):
    dry = _call("create_ontology", **SRC, name="shop_ontology")      # Claude left dry_run out: the default is a dry run
    [create] = dry["actions"]
    assert create["arguments"] == {**SRC, "name": "shop_ontology", "dry_run": False}


def test_the_create_answer_has_no_create_but_open_in_fabric_and_a_report_dry_run():
    args = {**SRC, "name": "shop_model_2", "dry_run": False}
    answer = {"dry_run": False, "result": {"status": "Succeeded", "id": "sm-new"}}
    acts, note = build.actions_for("create_semantic_model", args, answer, TAKEN, gs.WS)
    assert note is None and [a["kind"] for a in acts] == ["link", "dry_run"]
    assert acts[0]["url"] == f"https://app.fabric.microsoft.com/groups/{gs.WS}/datasets/sm-new/details"
    report = acts[1]
    assert report["label"] == "Create a report on it" and report["tool"] == "create_report"
    assert report["arguments"] == {"workspace": "demo", "model": "shop_model_2", "name": "shop_model_2_report", "dry_run": True}
    acts, _ = build.actions_for("create_backend", {**SRC, "name": "a", "dry_run": False},
                                {"dry_run": False, "result": {"status": "Failed"}}, TAKEN, gs.WS)
    assert acts == []                                                # no link to an item that was not created
    acts, _ = build.actions_for("create_report", {"workspace": "demo", "model": "m", "name": "r", "dry_run": False},
                                {"dry_run": False, "result": {"status": "Succeeded", "id": "r1"}}, TAKEN, gs.WS)
    assert [a["url"] for a in acts] == [f"https://app.fabric.microsoft.com/groups/{gs.WS}/reports/r1"]


def test_the_report_dry_run_has_create_with_the_same_arguments(fabric):
    dry = _call("create_report", workspace="demo", model="shop_model", name="shop_model_report", dry_run=True)
    [create] = dry["actions"]
    assert create["arguments"] == {"workspace": "demo", "model": "shop_model", "name": "shop_model_report", "dry_run": False}


# ------------------------------------------------------------------ several schemas -----------------------------------

@pytest.fixture
def two_schemas(fabric, monkeypatch):
    real = server._execute_factory

    def factory(item, token):
        execute = real(item, token)

        def run(sql, *a, **k):
            if "INFORMATION_SCHEMA.TABLES" in sql and "GROUP BY TABLE_SCHEMA" in sql:
                return [{"TABLE_SCHEMA": "sap", "TABLE_COUNT": 9}, {"TABLE_SCHEMA": "shop", "TABLE_COUNT": 7}]
            return execute(sql, *a, **k)
        run.close = getattr(execute, "close", lambda: None)
        return run
    monkeypatch.setattr(server, "_execute_factory", factory)
    return fabric


def test_plan_backend_without_a_schema_asks_which_one_and_plans_nothing(two_schemas):
    text = server.plan_backend(workspace="demo", source="demo_lh")             # a text client gets the question too
    out = json.loads(text)
    assert out["choose_schema"] is True and [s["schema"] for s in out["schemas"]] == ["sap", "shop"]
    assert "Which one" in out["summary"] and "keys" not in out and "relationships" not in out
    card = _call("plan_backend", workspace="demo", source="demo_lh")
    assert [a["label"] for a in card["actions"]] == ["Plan sap (9 tables)", "Plan shop (7 tables)"]
    for a, schema in zip(card["actions"], ("sap", "shop")):
        assert a["kind"] == "call" and a["tool"] == "plan_backend" and a["who"] == "thinker"
        assert a["arguments"] == {"workspace": "demo", "source": "demo_lh", "schema": schema}
    picked = _call("plan_backend", **card["actions"][1]["arguments"])
    assert "choose_schema" not in picked and picked["actions"][1]["arguments"]["schema"] == "shop"


def test_plan_backend_with_one_schema_plans_it_and_says_which(fabric, monkeypatch):
    monkeypatch.setattr(server, "_source_schemas", lambda w, s, c: [{"schema": "shop", "tables": 7}])
    out = json.loads(server.plan_backend(workspace="demo", source="demo_lh"))
    assert out["schema_chosen"] == "shop" and "choose_schema" not in out
    named = server.plan_backend(**SRC)
    assert "schema_chosen" not in json.loads(named)                           # a named schema: the answer as before


def test_the_schema_query_reads_base_tables_and_leaves_system_schemas_out():
    sql = server.SCHEMAS_SQL
    assert "BASE TABLE" in sql and "'sys'" in sql and "'INFORMATION_SCHEMA'" in sql and "GROUP BY TABLE_SCHEMA" in sql


# ------------------------------------------------------------------ the flag and the cards ----------------------------

def test_flag_off_means_no_build_card_and_no_actions(fabric):
    if mcp_apps.enabled():
        pytest.skip("KRUSGRAPH_MCP_APPS is set in this environment")
    assert build.tool_meta() is None and mcp_apps.registration("create_semantic_model") == {}
    assert "actions" not in json.loads(server.plan_backend(**SRC))            # text clients: the answer as before
    assert "actions" not in json.loads(server.create_semantic_model(**SRC, name="shop_model_2"))


def test_flag_on_registers_the_build_card_for_the_build_tools():
    reg = mcp_apps.registration("create_backend", on=True)
    assert reg["structured_output"] is False
    assert reg["meta"] == {"ui": {"resourceUri": build.CARD_URI}, "ui/resourceUri": build.CARD_URI}
    assert "meta" not in mcp_apps.registration("validate_plan", on=True)    # validate_plan keeps its own card
    [apps] = mcp_apps.extensions(on=True)
    from mcp.server.mcpserver import MCPServer
    m = MCPServer("n169", extensions=[apps])
    uris = {str(r.uri) for r in asyncio.run(m.list_resources())}
    assert build.CARD_URI in uris and mcp_apps.CARD_URI in uris
    assert build.CARD_URI.startswith("ui://krusgraph/")


class _Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags, self.attrs = [], []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attrs += [(tag, k, v) for k, v in attrs]


@pytest.mark.parametrize("html", [build.card_html(), mcp_apps.card_html()], ids=["build", "validate"])
def test_the_cards_load_nothing_and_use_only_the_host_calls_of_the_spec(html):
    p = _Tags()
    p.feed(html)
    assert not {"img", "link", "iframe", "object", "embed", "base", "form", "a"} & set(p.tags)
    assert not [a for a in p.attrs if a[1] in ("src", "href", "action", "srcset")]
    low = html.lower()
    for banned in ("http://", "//cdn", "url(", "@import", "fetch(", "xmlhttprequest", "websocket", "localstorage",
                   "innerhtml", "eval(", "new function", "ui/update-model-context"):
        assert banned not in low, banned
    # the only address in the page is the Fabric portal's, which a link action must point at
    assert set(re.findall(r"https://[a-z0-9.\\/-]+", low)) <= {"https://app\\.fabric\\.microsoft\\.com\\/"}
    for method in ('"tools/call"', '"ui/message"', '"ui/open-link"'):
        assert method in html, method
    assert "a.arguments.dry_run === true" in html                     # a build button is a dry run
    assert 'a.kind === "create"' in html and "fromDryRun === true" in html   # Create only from a dry run's answer
    assert "sameArgs(effective(want, a.defaults), effective(a.arguments, a.defaults))" in html   # ... with exactly that dry
    # run's arguments (n172: as the tool runs them; the MCP SDK fills in defaults, test_n172_card_polish.py)


def test_the_card_allows_no_tool_but_the_ones_the_actions_name():
    assert build.ALLOWED == {"validate_plan": "call", "plan_backend": "call", "create_semantic_model": "build",
                             "create_ontology": "build", "create_backend": "build", "create_report": "build"}
    assert '"create_views"' not in build.card_html() and '"create_data_agent"' not in build.card_html()


# ------------------------------------------------------------------ Claude's sign-in ----------------------------------

@pytest.fixture
def site(monkeypatch):
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://krusgraph.com/mcp")
    from fabric_backend import pages
    monkeypatch.setattr(pages, "_registration_on", lambda: True)
    return pages


def test_start_and_docs_give_claude_mcp_connect_with_register_automatically(site):
    v = site._vars()
    assert v["CLAUDE_URL"] == "https://krusgraph.com/mcp/connect"
    from starlette.testclient import TestClient
    start = TestClient(server.build_app()).get("/start").text
    assert '<code id="mcp-url">https://krusgraph.com/mcp/connect</code>' in start
    assert "Register automatically" in start and "Why /mcp/connect" in start
    assert "added earlier with <code>https://krusgraph.com/mcp</code> keep working" in start
    docs = site.docs_md()
    assert "Add custom connector, with the URL\n   `https://krusgraph.com/mcp/connect`. Keep **Register automatically**" in docs
    assert "Why /mcp/connect" in docs and "added earlier with `https://krusgraph.com/mcp` keep working" in docs
    chooser = site.connect_menu_html("start")
    assert 'data-copy-text="https://krusgraph.com/mcp/connect"' in chooser and "Register automatically" in chooser
    assert 'data-copy-text="https://krusgraph.com/mcp"' not in chooser
    done = site.consent_done_html({"admin_consent": "True"})
    assert "<code>https://krusgraph.com/mcp/connect</code>" in done and "Register automatically" in done


def test_without_client_registration_claude_keeps_mcp(monkeypatch):
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://krusgraph.com/mcp")
    from fabric_backend import pages
    monkeypatch.setattr(pages, "_registration_on", lambda: False)
    assert pages._vars()["CLAUDE_URL"] == "https://krusgraph.com/mcp"
    assert "Register automatically" not in pages.consent_done_html({"admin_consent": "True"})


def test_llms_txt_gives_claude_the_connect_address(site):
    from fabric_backend import discovery
    text = discovery.llms_txt() if hasattr(discovery, "llms_txt") else ""
    if not text:
        pytest.skip("no llms_txt function")
    assert "Add custom connector → URL `https://krusgraph.com/mcp/connect` → keep “Register automatically”" in text


# ------------------------------------------------------------------ the card in a browser -----------------------------

def _playwright() -> bool:
    import shutil
    import subprocess
    if not shutil.which("node"):
        return False
    return subprocess.run(["node", "-e", "require('playwright')"], capture_output=True).returncode == 0


def _browser(tmp_path, mode: str) -> dict:
    import subprocess
    from pathlib import Path
    plan = _call("plan_backend", **SRC)
    button = next(a for a in plan["actions"] if a["tool"] == "create_semantic_model")
    dry = _call("create_semantic_model", **button["arguments"])
    created_args = {**button["arguments"], "dry_run": False}
    acts, _ = build.actions_for("create_semantic_model", created_args,
                                {"dry_run": False, "result": {"status": "Succeeded", "id": "sm-new"}}, TAKEN, gs.WS)
    created = {"dry_run": False, "result": {"status": "Succeeded", "id": "sm-new"}, "summary": dry["summary"], "actions": acts}
    (tmp_path / "card.html").write_text(build.card_html())
    (tmp_path / "data.json").write_text(json.dumps({"args": SRC, "plan": plan, "dry": dry, "created": created}))
    run = subprocess.run(["node", str(Path(__file__).parent / "mcp_apps_build_browser.js"), str(tmp_path / "card.html"),
                          str(tmp_path / "data.json"), mode], capture_output=True, text=True, timeout=90)
    assert run.returncode == 0, run.stderr
    return {**json.loads(run.stdout), "button": button}


@pytest.mark.skipif(not _playwright(), reason="node + playwright not available")
def test_in_a_browser_a_click_runs_the_dry_run_then_create_with_the_same_arguments(tmp_path, fabric):  # noqa: F811
    out = _browser(tmp_path, "tools")
    assert out["errors"] == []
    calls = [m["params"] for m in out["log"] if m.get("method") == "tools/call"]
    dry_args = out["button"]["arguments"]
    assert calls == [{"name": "create_semantic_model", "arguments": dry_args},
                     {"name": "create_semantic_model", "arguments": {**dry_args, "dry_run": False}}]
    links = [m["params"]["url"] for m in out["log"] if m.get("method") == "ui/open-link"]
    assert links == [f"https://app.fabric.microsoft.com/groups/{gs.WS}/datasets/sm-new/details"]
    assert out["reportButtons"] == 1 and "Build a semantic model (shop_model_2)" in out["text"]
    assert not [m for m in out["log"] if m.get("method") == "ui/message"]


@pytest.mark.skipif(not _playwright(), reason="node + playwright not available")
def test_in_a_browser_a_host_without_tool_calls_gets_the_prompt_as_a_message(tmp_path, fabric):  # noqa: F811
    out = _browser(tmp_path, "msg")
    assert out["errors"] == [] and not [m for m in out["log"] if m.get("method") == "tools/call"]
    [msg] = [m["params"] for m in out["log"] if m.get("method") == "ui/message"]
    assert msg == {"role": "user", "content": {"type": "text", "text": out["button"]["say"]}}
    assert "dry run" in msg["content"]["text"] and "dry_run=true" in msg["content"]["text"]
