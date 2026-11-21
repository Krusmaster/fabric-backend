"""The pilot scan notebook (21 Nov 2026, round BL23; backlog S-04, I-35): what a pilot's estate looks like, names and
counts only.

Before the first session a pilot imports this notebook into their own Fabric workspace, attaches the lakehouse(s) they
want looked at and runs it with their own permissions. It reads the Spark catalog: the databases (lakehouses, or the
schemas of a lakehouse with schemas), their tables, each table's column names and types, and one `COUNT(*)` per table.
It writes one JSON file and one markdown summary to `Files/krusgraph/pilot-scan/` of the notebook's default lakehouse.
The customer reads them and decides whether to share them; nothing is sent anywhere.

What it never does: read a row value (the only query is `SELECT COUNT(*)`), install anything (no `%pip`), call the
network, write a table, or call an AI model. Every rule in it is a name rule written out in the cell.

Pack matching (decided in round BL23): a Fabric notebook does not have the `fabric_backend` package installed and the
scan must not install it, so `cells()` copies the names the knowledge packs know (each pack table's name, its aliases
and its key columns, and which pack tables the packs link) into the setup cell as data, and the cell matches a table
when its name, without case, separators and a leading landing word (`sap_`, `bronze_`, ...), is a pack table's name or
alias and the table has the pack's key columns (the client column may be missing). That is `sap_pack.match`'s name rule
without its later refinements (BL8's prefixes and suffixes such as `P01_VBAK`, key-column suggestions, mirror metadata):
the scan names candidates, `plan_backend` decides.

The scope suggestion is the `SCOPE_SIZE` (20) tables with the most links by name, as docs/GETTING-STARTED.md "How to
scope to 20 tables" describes: a column `<table>_id`/`<table>id`/`<table>_key`/`<table>_no` points at that table
(singular or plural), and a pack relationship links two matched tables. Ties go by name.

    cells()           -> the notebook as (kind, text) cells (notebook.py's format)
    source()          -> Fabric's notebook-content.py text
    ipynb()           -> nbformat 4 JSON, for the import dialog
    python -m fabric_backend.pilot_scan > krusgraph-pilot-scan.ipynb
"""
from __future__ import annotations

import json

from . import notebook, sap_pack

FILENAME = "krusgraph-pilot-scan.ipynb"
FOLDER = "Files/krusgraph/pilot-scan"
FORMAT = 1
CLIENT_COLUMNS = ("MANDT", "RCLNT", "CLIENT", "COMPANY")

INTRO = """# Krusgraph pilot scan: names and counts only

Run this notebook in your own workspace, with your own permissions, before the first session. Attach the lakehouse(s)
you want looked at (the first one as the default lakehouse). It reads:

- the databases the Spark catalog lists (your lakehouses, or the schemas of a lakehouse with schemas),
- each table's name, type, column names and column types,
- one `SELECT COUNT(*)` per table (set `COUNT_ROWS = False` to skip it).

It writes one JSON file and one markdown summary to `{folder}/` of the default lakehouse. You read them and decide
whether to share them. The notebook reads no row values, installs nothing, writes no table and sends nothing anywhere.

It also says which tables a Krusgraph knowledge pack (SAP, Dynamics 365, Salesforce, Younium) knows by name, and
suggests {scope} tables to start with: those with the most links by name. Both are name rules, not checks; the first
session checks them against the rows.
"""

PARAMETERS = '''DATABASES = []          # [] reads every database the catalog lists; or name them, e.g. ["sales_lakehouse"]
MIRRORED = []           # names of databases that are mirrored databases (or shortcuts to one), so the summary says so
COUNT_ROWS = True       # one SELECT COUNT(*) per table; False reads names and types only
SCOPE_SIZE = {scope}         # how many tables the scope suggestion names
MAX_TABLES = 2000       # stop reading after this many tables (the summary says so)
OUTPUT_FOLDER = "/lakehouse/default/{folder}"   # where the default lakehouse is mounted'''

SETUP = '''# Krusgraph pilot scan: setup. Name rules only; no row values, no network, nothing installed.
import json
import os
import re
from datetime import datetime, timezone

RUN_AT = datetime.now(timezone.utc).replace(microsecond=0)
LEADING = {leading}
CLIENT_COLUMNS = {clients}
# The knowledge packs' table names, aliases and key columns, and the pack tables they link (copied from Krusgraph's
# packs when this notebook was generated; names only).
PACKS = json.loads(r"""{packs}""")


def norm(name):
    return re.sub(r"[^A-Z0-9]", "", str(name).upper())


def base_name(table):
    words = [w for w in re.split(r"[^A-Za-z0-9]+", table.split(".")[-1]) if w]
    while len(words) > 1 and words[0].lower() in LEADING:
        words = words[1:]
    return norm("".join(words))


def stems(table):
    b = base_name(table)
    out = {{b}}
    if b.endswith("IES") and len(b) > 4:
        out.add(b[:-3] + "Y")
    if b.endswith("ES") and len(b) > 3:
        out.add(b[:-2])
    if b.endswith("S") and len(b) > 2:
        out.add(b[:-1])
    return out


def pack_matches(tables):
    """{{pack: {{"db.table": pack table}}}} for each pack that knows at least two tables, one of them by a name of its own."""
    found = {{}}
    for pack, spec in sorted(PACKS.items()):
        hits, own = {{}}, False
        for t in tables:
            name = spec["names"].get(base_name(t["table"]))
            if not name:
                continue
            have = {{norm(c["name"]) for c in t["columns"]}}
            key = [k for k in spec["tables"][name]["key"] if k not in CLIENT_COLUMNS]
            if key and all(k in have for k in key):
                hits[t["id"]] = name
                own = own or not spec["tables"][name]["common"]
        if len(hits) >= 2 and own:
            found[pack] = dict(sorted(hits.items()))
    return found


def name_links(tables, packs):
    """Links by name: a column <table>_id / _key / _no / _code points at that table; a pack relationship links two
    matched tables. Each link once, as from-table, column, to-table, rule."""
    by_stem = {{}}
    for t in tables:
        for s in stems(t["table"]):
            by_stem.setdefault(s, []).append(t["id"])
    links = set()
    for t in tables:
        for c in t["columns"]:
            n = norm(c["name"])
            for suffix in ("ID", "KEY", "NO", "CODE"):
                if n.endswith(suffix) and len(n) > len(suffix):
                    for target in by_stem.get(n[: -len(suffix)], []):
                        if target != t["id"]:
                            links.add((t["id"], c["name"], target, "name"))
    for pack, hits in packs.items():
        by_pack = {{}}
        for tid, name in hits.items():
            by_pack.setdefault(name, []).append(tid)
        for src, tgt in PACKS[pack]["links"]:
            for a in by_pack.get(src, []):
                for b in by_pack.get(tgt, []):
                    if a != b:
                        links.add((a, "", b, "pack " + pack))
    return [{{"from": a, "column": c, "to": b, "rule": r}} for a, c, b, r in sorted(links)]


def quote(*parts):
    return ".".join("`" + p.replace("`", "``") + "`" for p in parts)'''

READ = '''# Read the catalog: names, types and one COUNT(*) per table.
tables, skipped, databases = [], [], []
wanted = DATABASES or [d.name for d in spark.catalog.listDatabases()]
for db in sorted(wanted):
    found = [t for t in spark.catalog.listTables(db) if not t.isTemporary]
    databases.append({"name": db, "mirrored": db in MIRRORED, "tables": len(found)})
    for t in sorted(found, key=lambda t: t.name.lower()):
        if len(tables) >= MAX_TABLES:
            skipped.append({"table": db + "." + t.name, "why": "over MAX_TABLES"})
            continue
        try:
            columns = [{"name": c.name, "type": c.dataType} for c in spark.catalog.listColumns(t.name, db)]
        except Exception as e:                       # the error's kind only, never its message
            skipped.append({"table": db + "." + t.name, "why": "columns not readable (" + type(e).__name__ + ")"})
            continue
        rows = None
        if COUNT_ROWS:
            try:
                rows = int(spark.sql("SELECT COUNT(*) AS n FROM " + quote(db, t.name)).collect()[0][0])
            except Exception as e:
                skipped.append({"table": db + "." + t.name, "why": "not counted (" + type(e).__name__ + ")"})
        tables.append({"id": db + "." + t.name, "database": db, "table": t.name, "type": t.tableType,
                       "column_count": len(columns), "row_count": rows, "columns": columns})
print(len(tables), "tables in", len(databases), "databases read")'''

SCOPE = '''# Which tables a pack knows, links by name, and the scope suggestion.
packs = pack_matches(tables)
links = name_links(tables, packs)
degree = {t["id"]: 0 for t in tables}
for l in links:
    degree[l["from"]] += 1
    degree[l["to"]] += 1
ranked = sorted((t for t in degree if degree[t] > 0), key=lambda t: (-degree[t], t.lower()))
scope = [{"table": t, "links": degree[t]} for t in ranked[:SCOPE_SIZE]]
for pack, hits in packs.items():
    print(pack + ":", len(hits), "tables known by name")
print("scope suggestion:", ", ".join(s["table"] for s in scope) or "no links found by name")'''

WRITE = '''# Write the JSON and the markdown summary to the default lakehouse. Nothing is sent anywhere.
RESULT = {
    "krusgraph_pilot_scan": FORMAT,
    "run_at": RUN_AT.strftime("%Y-%m-%dT%H:%M:%SZ"),
    "reads": "names, types and row counts only; no row values",
    "totals": {"databases": len(databases), "tables": len(tables),
               "columns": sum(t["column_count"] for t in tables),
               "rows": sum(t["row_count"] or 0 for t in tables)},
    "databases": databases,
    "tables": [{k: t[k] for k in ("database", "table", "type", "column_count", "row_count", "columns")} for t in tables],
    "packs": [{"pack": p, "tables": [{"table": k, "pack_table": v} for k, v in hits.items()]} for p, hits in packs.items()],
    "links": links,
    "scope": {"size": SCOPE_SIZE, "rule": "most links by name, then by name", "tables": scope},
    "skipped": skipped,
}

md = ["# Krusgraph pilot scan", "",
      "Run at " + RESULT["run_at"] + ". Names, types and row counts only; no row values were read and nothing was sent.", "",
      "{databases} databases, {tables} tables, {columns} columns, {rows} rows.".format(**RESULT["totals"]), "",
      "| Database | Mirrored | Tables |", "| --- | --- | --- |"]
md += ["| {} | {} | {} |".format(d["name"], "yes" if d["mirrored"] else "", d["tables"]) for d in databases]
md += ["", "| Table | Type | Columns | Rows | Links by name |", "| --- | --- | --- | --- | --- |"]
md += ["| {} | {} | {} | {} | {} |".format(t["id"], t["type"], t["column_count"],
                                         "" if t["row_count"] is None else t["row_count"], degree[t["id"]]) for t in tables]
md += ["", "## Known to a Krusgraph pack (by name)", ""]
md += ["- " + p + ": " + ", ".join(k + " (" + v + ")" for k, v in hits.items()) for p, hits in packs.items()] or ["- none"]
md += ["", "## Scope suggestion: up to " + str(SCOPE_SIZE) + " tables with the most links by name", ""]
md += ["- " + s["table"] + " (" + str(s["links"]) + ")" for s in scope] or ["- no links found by name"]
if skipped:
    md += ["", "## Not read", ""] + ["- " + s["table"] + ": " + s["why"] for s in skipped]

os.makedirs(OUTPUT_FOLDER, exist_ok=True)
stamp = RUN_AT.strftime("%Y%m%dT%H%M%SZ")
with open(os.path.join(OUTPUT_FOLDER, "pilot-scan-" + stamp + ".json"), "w", encoding="utf-8") as f:
    json.dump(RESULT, f, indent=2, ensure_ascii=False)
with open(os.path.join(OUTPUT_FOLDER, "pilot-scan-" + stamp + ".md"), "w", encoding="utf-8") as f:
    f.write("\\n".join(md) + "\\n")
print("written to", OUTPUT_FOLDER, "as pilot-scan-" + stamp + ".json and .md")'''


def pack_names() -> dict:
    """What the setup cell carries of each pack: names (normalised name or alias -> pack table), each table's key
    columns (normalised) and whether its name is a common word, and the pack table pairs a relationship links."""
    out = {}
    for name in sap_pack.available():
        pack = sap_pack.load(name)
        names: dict[str, str] = {}
        for t in pack["tables"]:
            names[sap_pack._norm(t)] = t
        for t, spec in pack["tables"].items():
            for a in spec.get("aliases", []):
                names.setdefault(sap_pack._norm(a), t)
        tables = {t: {"key": [sap_pack._norm(k) for k in spec["key"]], "common": bool(spec.get("common_name"))}
                  for t, spec in pack["tables"].items()}
        links = sorted({(r["source"], r["target"]) for r in pack["relationships"]})
        out[name] = {"names": dict(sorted(names.items())), "tables": dict(sorted(tables.items())),
                     "links": [list(pair) for pair in links]}
    return out


def cells(scope_size: int = 20) -> list[tuple[str, str]]:
    """The notebook as (kind, text) cells: an introduction, the parameters, the setup, the read, the scope, the write."""
    packs = json.dumps(pack_names(), sort_keys=True, separators=(",", ":"))
    setup = SETUP.format(leading=repr(tuple(sap_pack._LEADING)), clients=repr(CLIENT_COLUMNS), packs=packs)
    return [("markdown", INTRO.format(folder=FOLDER, scope=scope_size)),
            ("parameters", PARAMETERS.format(scope=scope_size, folder=FOLDER)),
            ("code", setup),
            ("code", READ),
            ("code", SCOPE),
            ("code", WRITE.replace("FORMAT", str(FORMAT), 1))]


def source(workspace_id: str = "", lakehouse_id: str = "", lakehouse_name: str = "") -> str:
    """The notebook as Fabric's notebook-content.py, with the lakehouse as its default when one is given."""
    return notebook.fabric_source(cells(), notebook.notebook_metadata(workspace_id, lakehouse_id, lakehouse_name))


def ipynb() -> dict:
    """The notebook as nbformat 4 JSON, for Fabric's import dialog. Nothing is uploaded or written here."""
    nb_cells = []
    for i, (kind, text) in enumerate(cells(), 1):
        cell = {"cell_type": "markdown" if kind == "markdown" else "code", "id": f"krusgraph-scan-{i:03d}",
                "metadata": {"tags": ["parameters"]} if kind == "parameters" else {},
                "source": text.splitlines(keepends=True)}
        if cell["cell_type"] == "code":
            cell.update({"execution_count": None, "outputs": []})
        nb_cells.append(cell)
    return {"nbformat": 4, "nbformat_minor": 5, "cells": nb_cells,
            "metadata": {"kernel_info": {"name": "synapse_pyspark"},
                         "kernelspec": {"name": "synapse_pyspark", "display_name": "Synapse PySpark", "language": "Python"},
                         "language_info": {"name": "python"},
                         "krusgraph": {"kind": "pilot-scan", "format": FORMAT}}}


def main(argv: list[str] | None = None) -> int:
    """`python -m fabric_backend.pilot_scan > krusgraph-pilot-scan.ipynb`: the notebook on stdout."""
    import argparse

    ap = argparse.ArgumentParser(prog="python -m fabric_backend.pilot_scan")
    ap.add_argument("--format", choices=["ipynb", "fabric"], default="ipynb",
                    help="ipynb for the import dialog (default), fabric for notebook-content.py")
    a = ap.parse_args(argv)
    print(json.dumps(ipynb(), indent=1) if a.format == "ipynb" else source(), end="" if a.format == "fabric" else "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
