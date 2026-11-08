"""n158: the findings of the independent review of 8 November 2026 (docs/REVIEW-2026-11-08-fable.md), one test per
finding, each failing on the code the review read (b2bcb84).

H1: a table or column name with a line break in it ended a comment line in the generated code and started a statement
of its own (in the silver and gold notebooks, the pipeline's check notebook, the dbt project, the Databricks drafts and
the SodaCL and ODCS drafts). Every generator here is fed names that carry `\\n` and `\\r` followed by a statement, and
the generated code must parse with the statement nowhere outside a comment or a string literal.
"""
import ast
from pathlib import Path
import io
import re
import tokenize

import pytest

from fabric_backend import codegen, dbt, gold, notebook, pipeline, seed, silver
from fabric_backend.infer import plan
from fabric_backend.schema import Column, Schema, Table

INFO = dict(workspace_id="11111111-1111-1111-1111-111111111111", item_id="lh-1", item_name="shop_lh", item_kind="Lakehouse",
            schema="shop", schemas_enabled=True)
PAYLOAD = "import os; os.system('id') #"
BREAKS = ("\n", "\r", "\r\n", " ", "\x0b", "\x85")


def evil_schema(brk: str) -> tuple[Schema, str, str]:
    """The shop seed with the customers table's key and the products table renamed to carry a line break and a statement."""
    src = seed.schema("shop")
    key = f"customer_id{brk}{PAYLOAD}"
    table = f"products{brk}{PAYLOAD}"
    sch = Schema(schema="shop")
    for t in src.tables.values():
        name = table if t.name == "products" else t.name
        cols = [Column(key if (t.name == "customers" and c.name == "customer_id") else c.name, c.data_type) for c in t.columns]
        sch.tables[name] = Table(name, cols, schema="shop")
    return sch, key, table


def evil_plan(brk: str):
    sch, key, table = evil_schema(brk)
    # the key passed as keys= (the review's probe), the products table found by its own name rules
    return plan(sch, {"customers": [key]}), key, table


def _python_cells(source: str) -> list[str]:
    return [text for kind, text in notebook.parse(source) if kind != "markdown"]


def _no_payload_statement(code: str) -> None:
    """The code parses, and no statement calls os.system: the payload stayed inside a comment or a string literal."""
    tree = ast.parse(code)
    for node in ast.walk(tree):
        assert not isinstance(node, (ast.Import, ast.ImportFrom)) or all(a.name != "os" for a in node.names), code
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr != "system", code


def _comments(code: str) -> list[str]:
    return [t.string for t in tokenize.generate_tokens(io.StringIO(code).readline) if t.type == tokenize.COMMENT]


@pytest.mark.parametrize("brk", BREAKS, ids=repr)
def test_h1_silver_notebook_keeps_a_name_with_a_line_break_inside_its_comment(brk):
    p, key, table = evil_plan(brk)
    s = silver.spec(p, INFO)
    assert any(t["key"] == [key] for t in s["tables"])                      # the name reached the notebook
    src = silver.notebook_source(s)
    cells = _python_cells(src)
    for code in cells:
        _no_payload_statement(code)
    joined = "\n".join(cells)
    assert not any(line.startswith("import os") for line in src.splitlines())
    # the name is still readable in the comment, with the break written as its escape
    assert any(codegen.one_line(key) in c for c in _comments(joined))


@pytest.mark.parametrize("brk", BREAKS, ids=repr)
def test_h1_gold_and_pipeline_check_notebooks_keep_the_name_inside_comments(brk):
    p, key, table = evil_plan(brk)
    s_silver = silver.spec(p, INFO)
    s_gold = gold.spec(p, INFO)
    assert s_gold["views"]
    for src in (gold.notebook_source(s_gold), pipeline.check_source(pipeline.check_spec(p, s_silver, s_gold), "shop_lh.shop")):
        for code in _python_cells(src):                                      # the SQL is inside a string literal there
            _no_payload_statement(code)
    # the SQL the gold notebook runs: without its comment lines and its quoted identifiers, no trace of the payload
    for v in s_gold["views"]:
        sql = gold.create_sql(v, s_gold)
        bare = re.sub(r"`(?:[^`]|``)*`", "", "\n".join(x for x in sql.splitlines() if not x.lstrip().startswith("--")))
        bare = re.sub(r'"(?:[^"\\]|\\.)*"', "", bare)
        assert "os.system" not in bare, sql


@pytest.mark.parametrize("brk", ("\n", "\r"), ids=repr)
def test_h1_dbt_databricks_soda_and_odcs_drafts_keep_the_name_on_its_line(brk):
    from fabric_backend import databricks_drafts, domains, quality_suites
    p, key, table = evil_plan(brk)
    texts = [v for k, v in dbt.project(p, "shop", "shop")["files"].items() if not k.endswith(".md")]
    texts.append(dbt.schema_yml(p, "shop", "shop"))
    d = databricks_drafts.pipeline(p, "main")
    texts += [v for k, v in d["files"].items() if isinstance(v, str) and not k.endswith(".md")]
    texts.append(databricks_drafts.constraints(p, "main")["sql"])
    soda = quality_suites.soda_checks(p, "shop")                              # names are bare in SodaCL's check lines
    assert not any(line.lstrip().startswith("import os") for line in soda.splitlines()), soda
    texts += list(domains.draft(p, "shop")["contracts"].values())
    for text in texts:
        assert "os.system" not in _outside_quotes_and_comments(text), text


def _outside_quotes_and_comments(text: str) -> str:
    """What is left of SQL or YAML after its comments (`--` or `#` to the end of the line) and its quoted parts ([...],
    `...`, "...", '...') are taken out: a name that ended a comment early leaves its statement here."""
    out, i, n = [], 0, len(text)
    while i < n:
        ch = text[i]
        if text.startswith("--", i) or ch == "#":
            while i < n and text[i] not in "\r\n":
                i += 1
        elif ch in "[`\"'":
            close = {"[": "]"}.get(ch, ch)
            i += 1
            while i < n:
                if text[i] == "\\" and ch in "\"'":
                    i += 2
                elif text[i] == close and text.startswith(close * 2, i):
                    i += 2
                elif text[i] == close:
                    i += 1
                    break
                else:
                    i += 1
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def test_h1_one_line_leaves_printable_names_alone_and_escapes_every_line_end():
    assert codegen.one_line("Kund nr. (äöå) 😀") == "Kund nr. (äöå) 😀"
    for brk in ("\n", "\r", "\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\x85", " ", " ", "\x00", "\x7f"):
        out = codegen.one_line(f"a{brk}b")
        assert len(out.splitlines()) == 1 and out.isprintable(), repr(out)
    assert codegen.comment("x\ny") == "# x\\ny"


# ------------------------------------------------------------------ group 2: M1 to M5 ----------------------------

from test_browser import CHROMIUM, _playwright_available, site  # noqa: E402,F401  the same local server fixture

KEYLESS = "code,city,amount\nA1,Lund,1\nB2,Lund,1\nC3,Malmo,2\n"           # no key by name; code is unique: a key candidate


def _check_browser(site_url: str) -> dict:
    import json
    import os
    import subprocess
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    out = subprocess.run(["node", str(root / "tests/check_n158_browser.js"), site_url] + ([CHROMIUM] if CHROMIUM else []),
                         capture_output=True, text=True, timeout=300, env=os.environ | {"CHECK_KEYLESS": KEYLESS})
    assert out.returncode == 0, out.stderr[-2000:]
    return json.loads(out.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def check_page(site):
    return _check_browser(site)


@pytest.mark.skipif(not _playwright_available(), reason="node + playwright not available")
def test_m3_the_power_bi_and_app_panels_never_say_null(check_page):
    assert check_page["errors"] == []
    assert "Power BI project" in check_page["model_text"] and "null" not in check_page["model_text"]
    assert "null" not in check_page["app_text"]


def test_m1_views_in_the_source_schema_are_refused():
    from fabric_backend import views
    from fabric_backend.infer import PlanInputError
    p = plan(seed.schema("shop"))
    for target in (p.schema.schema, p.schema.schema.upper()):
        with pytest.raises(PlanInputError, match="source schema"):
            views.statements(p, target)
    assert views.statements(p, "krusgraph")["views"]                        # another schema still works



def _shop_proposal():
    from fabric_backend import evidence, fix_plan
    from silver_cases import seed_rows, sqlite_execute
    p = plan(seed.schema("shop"))
    ex = sqlite_execute(seed_rows())
    return p, fix_plan.propose(p, evidence.validate(p, ex), ex), ex


def test_m2_an_accepted_fix_for_a_table_outside_tables_is_refused_by_the_silver_notebook():
    from fabric_backend import fix_plan
    from fabric_backend.infer import PlanInputError
    p, prop, _ = _shop_proposal()
    ids = {e["id"] for e in prop["fixes"]}
    assert "key:orders" in ids
    with pytest.raises(PlanInputError, match="is for table orders, which is not in tables"):
        fix_plan.accept(silver.spec(p, INFO, tables=["products"]), prop["fixes"], [{"id": "key:orders", "winner": "order_date"}], p)
    s = fix_plan.accept(silver.spec(p, INFO, tables=["orders"]), prop["fixes"], [{"id": "key:orders", "winner": "order_date"}], p)
    assert [f["id"] for f in s["fixes"]] == ["key:orders"]               # inside tables it is applied as before


def test_m2_an_accepted_fix_for_a_table_outside_tables_is_refused_by_the_dbt_project():
    from fabric_backend import evidence, fix_plan
    from fabric_backend.infer import PlanInputError
    p, prop, ex = _shop_proposal()
    resolved = fix_plan.resolve(prop["fixes"], [{"id": "key:orders", "winner": "order_date"}], p)
    v = evidence.validate(p, ex)
    with pytest.raises(PlanInputError, match="is for table orders, which is not in tables"):
        dbt.project(p, "shop", "shop", "lh", v, tables=["products"], fixes=resolved)
    out = dbt.project(p, "shop", "shop", "lh", v, tables=["orders"], fixes=resolved)
    assert [f["id"] for f in out["fixes"]] == ["key:orders"]


def test_m4_long_integer_ids_keep_their_exact_values(tmp_path):
    from fabric_backend.platforms import local
    (tmp_path / "accounts.csv").write_text("account_id,name\n9007199254740993,a\n9007199254740992,b\n", encoding="utf-8")
    (tmp_path / "events.csv").write_text("event_id,account_id\n1234567890123456789,9007199254740993\n"
                                         "1234567890123456788,9007199254740992\n", encoding="utf-8")
    src = local.folder_source(tmp_path)
    try:
        acc = [r["account_id"] for r in src.execute("SELECT account_id FROM [data].[accounts] ORDER BY name")]
        assert acc == [9007199254740993, 9007199254740992]                 # not one value twice
        ev = [r["event_id"] for r in src.execute("SELECT event_id FROM [data].[events] ORDER BY event_id")]
        assert ev == ["1234567890123456788", "1234567890123456789"]          # 19 digits: text, every digit kept
        types = {c.name: c.data_type for c in src.schema["events"].columns}
        assert types["event_id"] not in ("real", "float")
    finally:
        src.close()
    assert local._guess_type(["1234567890123456789"]) == "text" and local._guess_type(["123456789012345678"]) == "int"
    assert local._coerce("9007199254740993", "int") == 9007199254740993 and local._coerce(12.0, "int") == 12


def test_m5_readme_states_the_live_facts_of_tool_status():
    from pathlib import Path
    from fabric_backend import tool_status
    readme = " ".join((Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8").split())
    assert "not yet created in Fabric" not in readme and "shop_report_visuals" in tool_status.LIVE["create_report"][1]
    assert "created live on 7 November 2026 (`shop_report_visuals`" in readme
    assert "not yet tried with a real client" not in readme
    assert "do not pass them yet" not in readme and "every hosted tool pass since round n87" in readme


# ------------------------------------------------------------------ group 3: the low findings ---------------------

def _drift_mocks(monkeypatch, schedules_status=200):
    import requests
    from test_drift_monitor import Resp
    calls = []

    def get(url, **k):
        if url.endswith("/jobs/execute/schedules"):
            return Resp(schedules_status, {"value": []} if schedules_status == 200 else {"errorCode": "Forbidden"})
        return Resp(200, {"value": []})

    def post(url, **k):
        calls.append(url)
        if url.endswith("/notebooks"):
            return Resp(201, {"id": "nb-1"})
        if url.endswith("/dataPipelines"):
            return Resp(201, {"id": "pl-1"})
        return Resp(201, {"id": "sch-1"})
    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr(requests, "post", post)
    return calls


def test_l1_create_drift_monitor_does_not_schedule_by_default(lakehouse, monkeypatch):  # noqa: F811
    import inspect
    import json
    from fabric_backend import server
    assert inspect.signature(server.create_drift_monitor).parameters["schedule"].default is False
    calls = _drift_mocks(monkeypatch)
    out = json.loads(server.create_drift_monitor("Sales", "shop_lh", name="m", schema="shop", dry_run=False))
    assert out["result"]["status"] == "Succeeded" and out["result"]["schedule"]["status"] == "Skipped"
    assert "DataPipeline.Execute.All" in out["result"]["schedule"]["why"]
    assert not any(u.endswith("/schedules") for u in calls)
    out = json.loads(server.create_drift_monitor("Sales", "shop_lh", name="m", schema="shop", dry_run=False, schedule=True))
    assert out["result"]["schedule"]["mode"] == "created"                    # those who pass schedule=true keep it


def test_l2_a_failed_schedule_listing_adds_no_schedule(lakehouse, monkeypatch):  # noqa: F811
    import json
    from fabric_backend import server
    calls = _drift_mocks(monkeypatch, schedules_status=403)
    out = json.loads(server.create_drift_monitor("Sales", "shop_lh", name="m", schema="shop", dry_run=False, schedule=True))
    assert "error" in out and out["result"]["schedule"]["status"] == "Failed"
    assert not any(u.endswith("/schedules") for u in calls)                  # no POST: a duplicate could follow


from test_drift_monitor import lakehouse  # noqa: E402,F401


def test_l3_the_package_declares_the_python_it_needs():
    import tomllib
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    assert tomllib.loads((root / "pyproject.toml").read_text())["project"]["requires-python"] == ">=3.12"
    assert "| Python | 3.12+" in (root / "README.md").read_text(encoding="utf-8")
    assert "| Python | 3.12 or later" in (root / "docs/LOCAL.md").read_text(encoding="utf-8")


from test_creating_tools import shop  # noqa: E402,F401  (the mocked hosted source)


def test_l4_no_row_values_also_covers_read_from_rows(shop, monkeypatch):  # noqa: F811
    import json
    from fabric_backend import server, switches

    def execute(sql):
        if "first_date" in sql:
            return [{"first_date": "2024-01-03", "last_date": "2025-11-30"}]
        return [{"fractions": 0}] if "fractions" in sql else []
    monkeypatch.setattr(server, "_execute_factory", lambda item, tok: execute)
    monkeypatch.setenv(switches.NO_ROW_VALUES, "1")
    raw = server.create_semantic_model(*shop, name="shop_model", schema="shop")
    said = json.loads(switches.answer(raw))["read_from_rows"]
    assert said[0].startswith("Dates: the first and last value of orders.order_date were read")
    assert not any("2024-01-03" in x or "2025-11-30" in x for x in said)
    monkeypatch.delenv(switches.NO_ROW_VALUES)
    said = json.loads(server.create_semantic_model(*shop, name="shop_model", schema="shop"))["read_from_rows"]
    assert said[0].startswith("Dates: 2024-01-03 to 2025-11-30 in orders.order_date")    # unchanged without the switch


def test_l5_the_applying_tools_count_as_far_as_validate_plan_can(shop, monkeypatch):  # noqa: F811
    import json
    from fabric_backend import server
    seen = []

    class Stop(Exception):
        pass

    def validate(p, execute, max_items=60):
        seen.append(max_items)
        raise Stop("counted")
    monkeypatch.setattr(server._evidence, "validate", validate)
    for call in (lambda: server.silver_notebook_draft(*shop, schema="shop", fixes=["key:orders"]),
                 lambda: server.dbt_schema(*shop, schema="shop", project=True, fixes=["key:orders"])):
        out = call()
        assert "error" in json.loads(out)
    assert seen == [200, 200]


def test_l6_the_dbt_sources_path_stays_in_models_sources():
    p = plan(seed.schema("shop"))
    files = dbt.project(p, "../../etc/evil", "shop")["files"]
    paths = [k for k in files if k.startswith("models/sources/")]
    assert paths == ["models/sources/etc_evil.yml"] and not any(".." in k for k in files)
    assert "models/sources/shop.yml" in dbt.project(p, "shop", "shop")["files"]


def test_l7_a_relationship_view_keeps_a_column_name_with_a_closing_bracket():
    from fabric_backend import views
    sch = seed.schema("shop")
    addresses = sch.tables["addresses"]
    sch.tables["addresses"] = Table("addresses", [Column("city]x" if c.name == "city" else c.name, c.data_type) for c in addresses.columns],
                                    schema=sch.schema)
    p = plan(sch, None, [{"source": "orders", "source_cols": ["ship_to_id"], "target": "addresses", "target_cols": ["address_id"]}])
    r = next(r for r in p.relationships if r.source == "orders" and r.target == "addresses")
    sql = views.relationship_view_sql(p, r, "krusgraph")
    assert "t.[city]]x] AS [addresses_city]]x]" in sql and "city]]]]x" not in sql


def test_l8_the_m_expression_keeps_a_lakehouse_name_with_a_quote_in_one_string():
    from fabric_backend import semantic_model
    p = plan(seed.schema("shop"))
    info = dict(INFO, sql_endpoint="x.datawarehouse.fabric.microsoft.com", sql_db='shop "lh" #(tab)')
    expr = semantic_model.draft(p, info, "m")["parts"]["definition/expressions.tmdl"]
    assert 'Sql.Database("x.datawarehouse.fabric.microsoft.com", "shop ""lh"" #(#)(tab)")' in expr


@pytest.mark.parametrize("name", ["ord😀", "kund nr", "a\x85b", "tab\tcol", 'q"uote\\'])
def test_l9_python_literals_read_back_exactly(name):
    for value in (name, [name, "x"], {"t": [name]}):
        lit = codegen.py_literal(value)
        assert ast.literal_eval(lit) == value and len(lit.splitlines()) == 1
    assert ast.literal_eval(codegen.py_literal({"t": [name]}, indent=2)) == {"t": [name]}


def test_l9_a_column_with_an_emoji_reaches_the_silver_and_gold_notebooks_as_itself():
    sch = seed.schema("shop")
    customers = sch.tables["customers"]
    sch.tables["customers"] = Table("customers", [Column("land😀" if c.name == "country" else c.name, c.data_type) for c in customers.columns],
                                    schema=sch.schema)
    p = plan(sch, {"customers": ["land😀"]})                                # the key: written into the cell's calls
    src = silver.notebook_source(silver.spec(p, INFO))
    assert "\\ud83d" not in src and '["land😀"]' in src
    for code in _python_cells(src):
        ast.parse(code)
    assert "\\ud83d" not in pipeline._py({"c": "land😀"})


@pytest.mark.skipif(not _playwright_available(), reason="node + playwright not available")
def test_l10_every_accept_on_check_has_its_button(check_page):
    said = [f for f in check_page["keyless"] if "Accept" in f["text"]]
    assert all(f["buttons"] for f in said), said
    assert any("`keys`" in f["text"] or "keys" in f["text"] for f in check_page["keyless"])


def test_l10_the_engine_says_keys_where_the_page_has_no_accept():
    from fabric_backend import browser_check
    r = browser_check.analyze("files", [("events.csv", KEYLESS.encode())])
    items = r["findings"] + r["suggestions"]
    assert any(f["check"] in ("key_candidate", "keyless", "composite_key") for f in items)
    for f in items:
        assert "Accept" not in f["next"] or f["confirmed"], f
        assert "accept it" not in (f.get("checked") or "")
    assert any("`keys`" in f["next"] for f in items)


def test_l11_decide_says_which_accepted_relationship_the_model_leaves_out():
    from fabric_backend import browser_check
    files = [("customers.csv", b"customer_id,name\n1,a\n1,b\n2,c\n"), ("orders.csv", b"order_id,buyer\n10,1\n11,2\n")]
    acc = [{"source": "orders", "source_cols": ["buyer"], "target": "customers", "target_cols": ["customer_id"]}]
    r = browser_check.decide("files", files, accepted=acc)
    assert r["not_in_model"] == ["orders.buyer -> customers"]
    files[0] = ("customers.csv", b"customer_id,name\n1,a\n2,c\n")
    assert browser_check.decide("files", files, accepted=acc)["not_in_model"] == []
    js = (Path(__file__).resolve().parents[1] / "fabric_backend/static/check.js").read_text(encoding="utf-8")
    assert "counted in the rows and in the Power BI model" not in js and "d.notInModel" in js


@pytest.mark.skipif(not _playwright_available(), reason="node + playwright not available")
def test_l12_the_file_chooser_offers_only_what_the_engine_reads(check_page):
    assert check_page["accept"] == ".csv,.xlsx,text/csv"


def test_l13_no_page_view_record_is_declared_for_explore():
    from fabric_backend import usage
    root = Path(__file__).resolve().parents[1]
    assert "/explore" not in usage.PAGE_VIEW_PATHS
    privacy = (root / "fabric_backend/page_templates/PRIVACY.md").read_text(encoding="utf-8")
    assert "`/check`, `/explore`" not in privacy
    for doc in ("docs/USAGE.md", "docs/OPERATIONS.md"):
        assert "/check, /explore" not in (root / doc).read_text(encoding="utf-8").replace("`", "")


def test_l14_privacy_says_the_reuse_margin_is_not_a_deletion_time():
    from fabric_backend import entra
    root = Path(__file__).resolve().parents[1]
    privacy = (root / "fabric_backend/page_templates/PRIVACY.md").read_text(encoding="utf-8")
    assert "until 120 seconds before they expire;" not in privacy
    assert "reused until 120 seconds before the expiry" in privacy and "trimmed or the server restarts" in privacy
    assert entra.MAX_CACHED_TOKENS == 5000


def test_l15_offline_access_is_named_beside_the_permissions_table():
    from fabric_backend import access
    root = Path(__file__).resolve().parents[1]
    asked = [f for f in ("fabric_backend/entra.py", "fabric_backend/registration_flow.py")
             if "offline_access" in (root / f).read_text(encoding="utf-8")]
    assert asked                                                            # the code asks for it ...
    assert "`offline_access`" in access.table_md() and "<code>offline_access</code>" in access.table_html()   # ... the table says so


def test_l16_llms_txt_names_other_clients_records_only_when_registration_is_on(monkeypatch):
    from fabric_backend import discovery
    clause = "sign-ins from other MCP clients keep a few encrypted records"
    monkeypatch.delenv("KRUSGRAPH_CLIENT_REGISTRATION", raising=False)
    assert clause not in discovery.llms_txt()
    monkeypatch.setenv("KRUSGRAPH_CLIENT_REGISTRATION", "1")
    assert clause in discovery.llms_txt()


from test_client_registration import env, keys  # noqa: E402,F401  (Entra faked, a memory store)


def test_l17_the_site_offers_mcp_connect_only_when_the_layer_started(env, monkeypatch):  # noqa: F811
    from test_client_registration import client
    monkeypatch.delenv("KRUSGRAPH_REGISTRATION_KEY")                      # switched on, but not configured
    c = client(env=env)
    assert c.get("/mcp/connect").status_code == 404
    assert "One address for every client" not in c.get("/start").text      # n169: the sentence that names /mcp/connect
    monkeypatch.setenv("KRUSGRAPH_REGISTRATION_KEY", __import__("test_client_registration").KEY)
    c = client(env=env)                                                     # configured: the layer starts, the site says so
    assert c.get("/mcp/connect").status_code != 404 and "One address for every client" in c.get("/start").text


def test_l18_the_cursor_register_step_says_it_needs_dynamic_registration():
    docs = (Path(__file__).resolve().parents[1] / "fabric_backend/page_templates/DOCS.md").read_text(encoding="utf-8")
    at = docs.index("/register -H")
    assert "KRUSGRAPH_CLIENT_REGISTRATION_DCR=1" in docs[at - 400:at]


def test_l19_repo_docs_follow_the_permissions_and_the_code():
    root = Path(__file__).resolve().parents[1]
    read = lambda p: " ".join((root / p).read_text(encoding="utf-8").split())
    assert "The app does not ask for them today" not in read("docs/NOTEBOOKS.md")
    assert "`OPERATOR` in `tool_status.py`) are the customer's" not in read("docs/SEGMENTATION.md")
    assert "`create_semantic_model`, `create_ontology`, `create_data_agent` (creating) and" not in read("docs/DEPLOY-NEXT.md")
    assert "Every parameter of the 36 hosted tools" not in read("docs/INFERENCE.md")
    site = read("docs/SITE.md")
    assert "`domains`, `fix`, `dbt`" not in site and "Write dbt tests" not in site
    chat = read("fabric_backend/static/chat-demo.js")
    assert "var STEPS = ['scan', 'yes', 'no', 'model', 'ontology', 'domains', 'fixes', 'dbt'];" in chat and "Draft a dbt project" in chat
    assert "| offers `create_ontology` |" not in read("docs/DEPLOY-NEXT.md")
    assert not any("KRUSGRAPH_ONTOLOGY_WRITE" in (root / "fabric_backend" / f).read_text(encoding="utf-8")
                   for f in ("server.py", "switches.py", "tool_status.py"))


def test_l20_the_chat_launch_button_carries_the_n149_labels():
    from fabric_backend import pages
    b = pages.chat_launch_html()
    assert f'data-label-check="{pages.CHECK_LABEL}"' in b and f'data-label-connect="{pages.CONNECT_LABEL}"' in b
    js = (Path(__file__).resolve().parents[1] / "fabric_backend/static/chat-demo.js").read_text(encoding="utf-8")
    assert "Try your own files" not in js and "Connect to your agent" not in js
