"""Round AP3b, problem 3: verify_build compares a notebook as Fabric gives it back (the founder's live run of 25 November
2026: demo_lh_silver "differed" on 285 of 464 lines, the first being Fabric's '# CELL ********************' against the
dry run's 'RUN_ID = ""').

Fabric returns notebook-content.py in its own layout: the "# Fabric notebook source" header, a "# METADATA" block with
its own keys, each cell after its marker ("# MARKDOWN", "# PARAMETERS CELL", "# CELL") and a "# METADATA" block after
each code cell, markdown re-flowed (LT1). verify_build now takes both sides to their code cells (the markers, the
metadata blocks and the markdown left out) and compares the cells' sources. The Fabric-format notebook below is built
from the dry run itself (the synthetic shop sample, seed.py), so "the same code" is known; then one line is changed, and
then the notebook an earlier Krusgraph wrote (no RUN_ID and alert parameters, an older description) is made."""
from __future__ import annotations

import json

from fabric_backend import notebook, seed, server, verify_build as vb
from fabric_backend.infer import plan

INFO = {"workspace_id": "11111111-1111-1111-1111-111111111111", "item_id": "33333333-3333-3333-3333-333333333333",
        "item_name": "demo_lh", "item_kind": "Lakehouse", "schema": "shop", "sql_endpoint": "h", "sql_db": "demo_lh",
        "schemas_enabled": True, "onelake_tables_path": ""}


def dry_runs() -> dict[str, str]:
    b = server._pipeline_build(plan(seed.schema("shop")), INFO, "shop", "silver", "gold", None, False, "pipeline_shop", "", "")
    return {n["name"]: n["content"] for n in b["notebooks"]}


def _meta(obj: dict) -> list[str]:
    return ["# META " + ln if ln else "# META" for ln in json.dumps(obj, indent=4).splitlines()]


def as_fabric_gives_it(text: str, split_first_code_cell: bool = True) -> str:
    """The notebook as Fabric's getDefinition returns it: its own metadata (more keys, another indent), markdown without
    its blank '#' lines, a metadata block after every code cell with Fabric's keys, a long cell split in two by the
    portal's editor, trailing spaces and Windows line ends."""
    out = ["# Fabric notebook source", "", "# METADATA ********************", "",
           *_meta({"kernel_info": {"name": "synapse_pyspark"}, "dependencies": {"lakehouse": {
               "default_lakehouse": INFO["item_id"], "default_lakehouse_name": "demo_lh",
               "default_lakehouse_workspace_id": INFO["workspace_id"], "known_lakehouses": [{"id": INFO["item_id"]}]}}}), ""]
    split = split_first_code_cell
    for kind, src in notebook.parse(text):
        if kind == "markdown":
            out += ["# MARKDOWN ********************", ""]
            out += [("# " + ln).rstrip() for ln in src.splitlines() if ln.strip()]
            out.append("")
            continue
        lines = src.splitlines()
        chunks = [lines]
        if kind == "code" and split and len(lines) > 6:
            chunks, split = [lines[:3], lines[3:]], False
        for chunk in chunks:
            out += ["# PARAMETERS CELL ********************" if kind == "parameters" else "# CELL ********************", ""]
            out += [ln + "  " if ln.strip() else ln for ln in chunk]
            out += ["", "# METADATA ********************", "",
                    *_meta({"language": "python", "language_group": "synapse_pyspark", "frozen": False, "editable": True}), ""]
    return "\r\n".join(out) + "\r\n"


def test_the_same_code_in_fabrics_layout_is_as_the_dry_run():
    for name, text in dry_runs().items():
        fabric = as_fabric_gives_it(text)
        assert fabric != text and "# CELL ********************" in fabric
        got = vb.compare_notebook(text, fabric)
        assert got["differences"] == [], (name, got["differences"])
        assert got["checked"]["lines"] > 100


def test_the_cells_are_read_from_either_layout():
    text = dry_runs()["silver_shop"]
    mine, theirs = vb.notebook_cells(text), vb.notebook_cells(as_fabric_gives_it(text, split_first_code_cell=False))
    assert [c["kind"] for c in mine] == [c["kind"] for c in theirs]
    assert [c["lines"] for c in mine if c["kind"] != "markdown"] == [c["lines"] for c in theirs if c["kind"] != "markdown"]
    assert not any(ln.startswith(("# META", "# CELL", "# PARAMETERS", "# MARKDOWN", "# Fabric")) for c in mine for ln in c["lines"])


def test_one_changed_line_still_differs():
    text = dry_runs()["silver_shop"]
    fabric = as_fabric_gives_it(text).replace('TABLE_FORMAT = "delta"', 'TABLE_FORMAT = "parquet"', 1)
    d = vb.compare_notebook(text, fabric)["differences"]
    assert len(d) == 1
    assert d[0]["said"].startswith("The notebook's code differs from the dry run on 1 line(s); the first is code line 2: "
                                   "'TABLE_FORMAT = \"parquet\"")
    assert not d[0].get("earlier_version")
    line = vb.line("notebook", "demo_lh_silver", vb.compare_notebook(text, fabric))
    assert line["state"] == "differs"


def test_a_notebook_an_earlier_krusgraph_wrote_is_said_to_be_one():
    """The live run's case: the parameters cell of a pipeline built on 9 November ends before RUN_ID (added on 11
    November, n200), and its description is that version's."""
    text = dry_runs()["silver_shop"]
    old = "\n".join(ln for ln in text.splitlines()
                    if not ln.startswith(("RUN_ID =", "ALERT_KEY_VAULT =", "ALERT_SECRET_NAME =", "ALERT_ON =")))
    old = old.replace("Generated by Krusgraph from the plan: clean copies", "Generated by Krusgraph: clean copies")
    d = vb.compare_notebook(text, as_fabric_gives_it(old))["differences"]
    assert d[0]["earlier_version"] is True
    assert d[0]["said"].startswith("The notebook was built by an earlier version of Krusgraph; Update the build in place "
                                   "brings it to the current dry run (its parameters cell lacks RUN_ID, ALERT_KEY_VAULT, "
                                   "ALERT_SECRET_NAME, ALERT_ON, which later versions add; its description is the one an "
                                   "earlier version wrote).")


def test_a_hand_edit_is_not_called_an_earlier_version():
    text = dry_runs()["gold_shop"]
    edited = as_fabric_gives_it(text).replace('SOURCE_SCHEMA = "shop"', 'SOURCE_SCHEMA = "shop2"', 1)
    d = vb.compare_notebook(text, edited)["differences"]
    assert d and not d[0].get("earlier_version") and "earlier version" not in d[0]["said"]
