"""The receipt as a notebook the customer runs (21 November 2026, round BL19; backlog C-36 next step, P-27;
docs/RECEIPTS.md "Run it as a notebook").

A receipt (receipt.py) lists every number Krusgraph stated with the statement that counted it. This module turns it
into a notebook the buyer imports into their own Fabric (or Databricks) workspace, attaches to the same lakehouse and
runs, without Krusgraph and without sending a row anywhere:

    cells(plan, validation)  -> [(kind, text)]: a title cell, one small helper, then per number a markdown cell with
                                the sentence and a code cell that runs its SQL with spark.sql and prints
                                "stated N, now M, same" or "changed"; a summary cell at the end
    ipynb(plan, validation)  -> the notebook as nbformat 4 JSON (a dict), for download; nothing is uploaded

The cells use the same (kind, text) form as notebook.py, so notebook.fabric_source() can also write them as a Fabric
notebook-content.py. The statements are receipt.build(..., dialect=dialects.DATABRICKS): backtick quoting and COUNT,
which Spark SQL reads. Plain Python only: no %pip, no import, no network, no write; every statement is a SELECT that
counts. The notebook holds table names, column names and counts, never a row value. Nothing here runs a query.
"""
from __future__ import annotations

import json

from . import receipt
from .dialects import DATABRICKS

FILENAME = "krusgraph-receipt.ipynb"

_HELPER = '''# Krusgraph receipt check (read-only). Each cell below runs one counting SELECT with spark.sql and compares its
# answer with the count Krusgraph stated. Nothing is installed, written or sent.
krusgraph_results = {}


def krusgraph_check(n, sql, stated):
    row = spark.sql(sql).collect()[0].asDict()
    parts, same = [], True
    for name, value in stated.items():
        now = row.get(name)
        if isinstance(value, float) or isinstance(now, float):
            ok = round(float(now or 0), 2) == round(float(value), 2)  # avg_lines is rounded to two decimals
        else:
            ok = int(now or 0) == int(value)
        same = same and ok
        parts.append(f"{name}: stated {value}, now {now}, {'same' if ok else 'changed'}")
    krusgraph_results[n] = same
    print(f"{n}. {'same' if same else 'changed'}: " + "; ".join(parts))
    return same'''

_SUMMARY = '''changed = sorted(n for n, same in krusgraph_results.items() if not same)
print(f"{len(krusgraph_results) - len(changed)} of {len(krusgraph_results)} numbers are the same as stated.")
if changed:
    print("Changed: " + ", ".join(str(n) for n in changed) + ". The rows changed since the receipt, or the statement "
          "ran on other tables (check the schema name).")'''


def _literal(sql: str) -> str:
    """The statement as a Python string literal a person can read: triple quotes where that is safe, repr otherwise."""
    if '"""' in sql or "\\" in sql or sql.endswith('"'):
        return repr(sql)
    return '"""' + sql + '"""'


def _counts(counts: dict) -> str:
    return "{" + ", ".join(f"{json.dumps(str(k))}: {v!r}" for k, v in counts.items()) + "}"


def _md(text: str) -> str:
    return text.replace("\n", " ")


def from_rows(rows: list[dict], source: str = "") -> list[tuple[str, str]]:
    """The cells for receipt rows already built (in a Spark-readable dialect)."""
    counted = [r for r in rows if r["sql"]]
    at = rows[0]["generated_at"] if rows else ""
    intro = ["# Krusgraph receipt notebook", "",
             f"Generated {at} (UTC)" + (f" from {_md(source)}" if source else "") + f". {len(counted)} number(s) to re-run"
             + (f", {len(rows) - len(counted)} not counted" if len(rows) > len(counted) else "") + ".", "",
             "Attach this notebook to the lakehouse the numbers were counted on and run all cells. Each code cell runs one "
             "read-only SELECT that only counts and prints the count Krusgraph stated, the count now, and `same` or "
             "`changed`. Nothing is installed, written or sent, and no row value is in this notebook.", "",
             "The counts are over the whole tables at the time above; new rows change them. Each statement names its "
             "tables as `schema`.`table`; if your lakehouse uses another schema or database name, change it in the cell."]
    out: list[tuple[str, str]] = [("markdown", "\n".join(intro)), ("code", _HELPER)]
    for r in rows:
        title = f"## {r['n']}. {r['kind'].capitalize()}: `{r['item']}`"
        if not r["sql"]:
            out.append(("markdown", f"{title}\n\n{_md(r['sentence'])}\n\nNot counted, so there is no number and no "
                                    "statement to re-run."))
            continue
        out.append(("markdown", f"{title}\n\n{_md(r['sentence'])}"))
        out.append(("code", f"krusgraph_check({r['n']}, {_literal(r['sql'])}, {_counts(r['counts'])})"))
    out.append(("markdown", "## Summary"))
    out.append(("code", _SUMMARY))
    return out


def cells(plan, validation: dict, generated_at=None, source: str = "") -> list[tuple[str, str]]:
    """The notebook's cells: receipt.build in Spark SQL (dialects.DATABRICKS), one markdown and one code cell per
    number, a markdown cell only for an item that was not counted."""
    return from_rows(receipt.build(plan, validation, generated_at, dialect=DATABRICKS), source)


def to_ipynb(cell_list: list[tuple[str, str]]) -> dict:
    nb_cells = []
    for i, (kind, text) in enumerate(cell_list, 1):
        lines = text.splitlines(keepends=True)
        cell = {"cell_type": "markdown" if kind == "markdown" else "code", "id": f"krusgraph-{i:03d}",
                "metadata": {}, "source": lines}
        if cell["cell_type"] == "code":
            cell.update({"execution_count": None, "outputs": []})
        nb_cells.append(cell)
    return {"nbformat": 4, "nbformat_minor": 5, "cells": nb_cells,
            "metadata": {"kernel_info": {"name": "synapse_pyspark"},
                         "kernelspec": {"name": "synapse_pyspark", "display_name": "Synapse PySpark", "language": "Python"},
                         "language_info": {"name": "python"},
                         "krusgraph": {"kind": "receipt", "format": receipt.FORMAT, "dialect": DATABRICKS.name}}}


def ipynb(plan, validation: dict, generated_at=None, source: str = "") -> dict:
    """The receipt notebook as nbformat 4 JSON, for download. Nothing is uploaded or written here."""
    return to_ipynb(cells(plan, validation, generated_at, source))


def main(argv: list[str] | None = None) -> int:
    """`python -m fabric_backend.receipt_notebook --sample sap > krusgraph-receipt.ipynb`: the notebook for a synthetic
    sample, printed to stdout (the shell writes the file)."""
    import argparse

    from . import evidence, sap_demo
    from .infer import plan as infer_plan
    from .platforms import local
    ap = argparse.ArgumentParser(prog="python -m fabric_backend.receipt_notebook")
    ap.add_argument("--sample", choices=["shop", "sap"], required=True)
    a = ap.parse_args(argv)
    if a.sample == "sap":
        schema, execute = sap_demo.sqlite()
    else:
        src = local.sample_source()
        schema, execute = src.schema, src.execute
    p = infer_plan(schema)
    print(json.dumps(ipynb(p, evidence.validate(p, execute, 200), source=f"sample {a.sample}"), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
