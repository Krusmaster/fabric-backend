"""BL23 (21 Nov 2026): the pilot scan notebook, names and counts only (fabric_backend/pilot_scan.py, docs/PILOT-SCAN.md).

The code cells run against a fake `spark` whose catalog holds the synthetic SAP demo (database `sap`) and the shop
(database `shop`). The tests assert the JSON's shape and counts, that the SAP pack is found by name, that the scope
suggestion follows the links by name, that no row value reaches either file, and that nothing outside the fake is
called: no socket, no SQL other than one COUNT(*) per table, and no file outside the output folder.
"""
from __future__ import annotations

import builtins
import datetime as dt
import json
import re
import socket
from types import SimpleNamespace

import pytest

from fabric_backend import notebook, pilot_scan, sap_demo, seed

_COUNT = re.compile(r"^SELECT COUNT\(\*\) AS n FROM `([^`]+)`\.`([^`]+)`$")


def _estate() -> dict:
    """database -> table -> (columns [(name, type)], rows)."""
    out: dict = {"sap": {}, "shop": {}}
    for name, (cols, types, rows) in sap_demo.tables().items():
        out["sap"][sap_demo.PREFIX + name.lower()] = (list(zip(cols, types)), rows)
    for name, ddl in seed.SCHEMAS.items():
        cols = [tuple(part.strip().split(" ", 1)) for part in ddl.split(",")]
        out["shop"][name] = ([(c, t.lower()) for c, t in cols], seed.rows()[name])
    return out


class FakeCatalog:
    def __init__(self, estate):
        self.estate = estate

    def listDatabases(self):                             # noqa: N802 (pyspark's names)
        return [SimpleNamespace(name=d) for d in self.estate]

    def listTables(self, db):                            # noqa: N802
        return [SimpleNamespace(name=t, tableType="MANAGED", isTemporary=False, database=db) for t in self.estate[db]]

    def listColumns(self, table, db):                    # noqa: N802
        return [SimpleNamespace(name=c, dataType=t) for c, t in self.estate[db][table][0]]


class FakeSpark:
    """Only `SELECT COUNT(*) AS n FROM `db`.`t`` is answered; any other SQL fails the test."""

    def __init__(self, estate):
        self.estate = estate
        self.catalog = FakeCatalog(estate)
        self.queries: list[str] = []

    def sql(self, text):
        self.queries.append(text)
        m = _COUNT.match(text)
        assert m, f"unexpected SQL: {text}"
        n = len(self.estate[m.group(1)][m.group(2)][1])
        return SimpleNamespace(collect=lambda: [(n,)])


def _run(tmp_path, monkeypatch, estate=None, spark_cls=None, **params):
    estate = estate or _estate()
    spark = (spark_cls or FakeSpark)(estate)

    def no_network(*a, **k):
        raise AssertionError("the pilot scan opened a socket")
    monkeypatch.setattr(socket, "socket", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
    real_open = builtins.open
    out = tmp_path / "pilot-scan"

    def guarded_open(path, mode="r", *a, **k):
        if any(m in mode for m in "wax+"):
            assert str(path).startswith(str(out)), f"write outside the output folder: {path}"
        return real_open(path, mode, *a, **k)

    ns = {"spark": spark, "__builtins__": {**vars(builtins), "open": guarded_open}}
    for kind, text in pilot_scan.cells():
        if kind == "markdown":
            continue
        exec(compile(text, "<pilot-scan>", "exec"), ns)       # noqa: S102 (the generated cells, on fakes)
        if kind == "parameters":
            ns["OUTPUT_FOLDER"] = str(out)
            ns.update(params)
    files = sorted(out.iterdir())
    result = json.loads(next(f for f in files if f.suffix == ".json").read_text(encoding="utf-8"))
    md = next(f for f in files if f.suffix == ".md").read_text(encoding="utf-8")
    return result, md, spark, files


def test_json_shape_and_counts(tmp_path, monkeypatch):
    result, md, spark, files = _run(tmp_path, monkeypatch)
    estate = _estate()
    assert [f.suffix for f in files] == [".json", ".md"]
    assert set(result) == {"krusgraph_pilot_scan", "run_at", "reads", "totals", "databases", "tables", "packs", "links",
                           "scope", "skipped"}
    assert result["krusgraph_pilot_scan"] == pilot_scan.FORMAT
    assert dt.datetime.strptime(result["run_at"], "%Y-%m-%dT%H:%M:%SZ")
    assert result["databases"] == [{"name": "sap", "mirrored": False, "tables": len(estate["sap"])},
                                   {"name": "shop", "mirrored": False, "tables": len(estate["shop"])}]
    n_tables = sum(len(v) for v in estate.values())
    assert result["totals"] == {"databases": 2, "tables": n_tables,
                                "columns": sum(len(c) for v in estate.values() for c, _ in v.values()),
                                "rows": sum(len(r) for v in estate.values() for _, r in v.values())}
    for t in result["tables"]:
        cols, rows = estate[t["database"]][t["table"]]
        assert t["row_count"] == len(rows)
        assert t["column_count"] == len(cols)
        assert [(c["name"], c["type"]) for c in t["columns"]] == cols
        assert set(t) == {"database", "table", "type", "column_count", "row_count", "columns"}
    assert len(spark.queries) == n_tables                  # one COUNT(*) per table, nothing else
    assert result["skipped"] == []
    assert "Names, types and row counts only" in md


def test_sap_pack_found_by_name_and_not_the_shop(tmp_path, monkeypatch):
    result, md, _, _ = _run(tmp_path, monkeypatch)
    packs = {p["pack"]: p["tables"] for p in result["packs"]}
    assert set(packs) == {"sap"}
    sap = {t["table"]: t["pack_table"] for t in packs["sap"]}
    assert sap["sap.sap_vbak"] == "VBAK" and sap["sap.sap_vbap"] == "VBAP"
    assert all(k.startswith("sap.") for k in sap)
    assert len(sap) >= 10
    assert "sap.sap_vbak (VBAK)" in md


def test_links_and_scope_suggestion(tmp_path, monkeypatch):
    result, md, _, _ = _run(tmp_path, monkeypatch)
    links = {(l["from"], l["column"], l["to"]) for l in result["links"]}
    assert ("shop.orders", "customer_id", "shop.customers") in links
    assert ("shop.products", "category_id", "shop.categories") in links
    assert any(l["rule"] == "pack sap" and l["from"] == "sap.sap_vbap" and l["to"] == "sap.sap_vbak"
               for l in result["links"])
    scope = result["scope"]
    assert scope["size"] == 20 and len(scope["tables"]) <= 20
    counts = [s["links"] for s in scope["tables"]]
    assert counts == sorted(counts, reverse=True) and min(counts) > 0
    degree: dict = {}
    for l in result["links"]:
        degree[l["from"]] = degree.get(l["from"], 0) + 1
        degree[l["to"]] = degree.get(l["to"], 0) + 1
    assert all(degree[s["table"]] == s["links"] for s in scope["tables"])
    assert "## Scope suggestion" in md


def test_scope_size_parameter(tmp_path, monkeypatch):
    result, _, _, _ = _run(tmp_path, monkeypatch, SCOPE_SIZE=3)
    assert len(result["scope"]["tables"]) == 3


def test_no_row_values_in_either_file(tmp_path, monkeypatch):
    result, md, _, _ = _run(tmp_path, monkeypatch)
    text = json.dumps(result) + md
    estate = _estate()
    names = {c for v in estate.values() for cols, _ in v.values() for c, _ in cols} | {t for v in estate.values() for t in v}
    values = {str(v) for v in estate.values() for _, rows in v.values() for r in rows for v in r
              if isinstance(v, str) and len(v) >= 4 and v not in names and not v.isdigit()}
    assert values, "the fixture should hold text values"
    leaked = sorted(v for v in values if re.search(r"(?<![A-Za-z0-9_])" + re.escape(v) + r"(?![A-Za-z0-9_])", text))
    assert leaked == []


def test_counts_off_mirrored_and_named_databases(tmp_path, monkeypatch):
    result, _, spark, _ = _run(tmp_path, monkeypatch, COUNT_ROWS=False, DATABASES=["sap"], MIRRORED=["sap"])
    assert spark.queries == []
    assert result["databases"] == [{"name": "sap", "mirrored": True, "tables": len(_estate()["sap"])}]
    assert all(t["row_count"] is None for t in result["tables"])


def test_a_failing_count_is_skipped_with_its_kind_only(tmp_path, monkeypatch):
    estate = _estate()

    class Boom(FakeSpark):
        def sql(self, text):
            if "`orders`" in text:
                raise RuntimeError("secret value 4711 in message")
            return super().sql(text)
    result, md, _, _ = _run(tmp_path, monkeypatch, estate=estate, spark_cls=Boom)
    assert {"table": "shop.orders", "why": "not counted (RuntimeError)"} in result["skipped"]
    assert "4711" not in json.dumps(result) + md


def test_max_tables(tmp_path, monkeypatch):
    result, _, _, _ = _run(tmp_path, monkeypatch, MAX_TABLES=5)
    assert len(result["tables"]) == 5
    assert all(s["why"] == "over MAX_TABLES" for s in result["skipped"]) and result["skipped"]


def test_the_cells_hold_no_install_network_or_write():
    code = "\n".join(text for kind, text in pilot_scan.cells() if kind != "markdown")
    for word in ("%pip", "pip install", "requests", "urllib", "http", "socket", "saveAsTable", "insertInto", "INSERT",
                 "DROP", "CREATE", "notebookutils", "mssparkutils", "anthropic", "openai"):
        assert word not in code, word
    assert re.findall(r"spark\.sql\(", code) == ["spark.sql("]


def test_notebook_formats_round_trip():
    src = pilot_scan.source("ws", "lh", "pilot")
    assert src.startswith(notebook.HEADER)
    assert [k for k, _ in notebook.parse(src)] == [k for k, _ in pilot_scan.cells()]
    nb = pilot_scan.ipynb()
    assert nb["nbformat"] == 4 and nb["metadata"]["krusgraph"]["kind"] == "pilot-scan"
    assert [c["cell_type"] for c in nb["cells"]] == ["markdown", "code", "code", "code", "code", "code"]
    assert nb["cells"][1]["metadata"]["tags"] == ["parameters"]


def test_main_prints_the_notebook(capsys):
    assert pilot_scan.main([]) == 0
    assert json.loads(capsys.readouterr().out)["metadata"]["krusgraph"]["kind"] == "pilot-scan"
    assert pilot_scan.main(["--format", "fabric"]) == 0
    assert capsys.readouterr().out.startswith(notebook.HEADER)


@pytest.mark.parametrize("pack", ["sap", "dynamics365", "salesforce", "younium_salesforce"])
def test_pack_names_carry_names_only(pack):
    spec = pilot_scan.pack_names()[pack]
    assert set(spec) == {"names", "tables", "links"}
    assert all(set(t) == {"key", "common"} for t in spec["tables"].values())
    assert all(a in spec["tables"] and b in spec["tables"] for a, b in spec["links"])
