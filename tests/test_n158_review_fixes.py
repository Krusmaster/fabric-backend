"""n158: the findings of the independent review of 8 November 2026 (docs/REVIEW-2026-11-08-fable.md), one test per
finding, each failing on the code the review read (b2bcb84).

H1: a table or column name with a line break in it ended a comment line in the generated code and started a statement
of its own (in the silver and gold notebooks, the pipeline's check notebook, the dbt project, the Databricks drafts and
the SodaCL and ODCS drafts). Every generator here is fed names that carry `\\n` and `\\r` followed by a statement, and
the generated code must parse with the statement nowhere outside a comment or a string literal.
"""
import ast
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

KEYLESS = "event,city,amount\nopen,Lund,1\nopen,Lund,1\nclose,Malmo,2\nclose,Lund,3\n"


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
