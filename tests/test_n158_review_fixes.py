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
