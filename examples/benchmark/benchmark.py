"""Round n61: an honest comparison on the repository's synthetic data (examples/benchmark/README.md).

Three ways to get relationships and their traps, on the same four synthetic datasets, scored against facit.json:

  krusgraph  plan() + evidence.validate (validate_plan) + graphs.suggest (suggest_relationships), the library calls
             behind the MCP tools, over in-memory SQLite.
  autodetect an approximation of documented autodetect rules (Power BI Desktop's "Autodetect during load" as described
             on Microsoft Learn, see the README): a relationship where two tables share a column name and data type and
             one side is unique in the rows; many-to-one toward the unique side, one-to-one when both are; single
             column only. Not Power BI itself, whose heuristics are not all documented.
  dbt        dbt-style tests on relationships a person declared: unique + not_null on each declared target key and the
             built-in `relationships` test (single column) for orphans. The person declares the facit, so its
             precision and recall are 1 by construction; what is measured is what the tests then catch.

Run:  python examples/benchmark/benchmark.py            (prints the Markdown table, writes results.json beside it)
Deterministic: fixed synthetic rows, no clock, no network.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

from fabric_backend import browser_check as bc, evidence, graphs                    # noqa: E402
from fabric_backend.dialects import of as dialect_of                                 # noqa: E402
from fabric_backend.infer import plan as make_plan                                   # noqa: E402
from fabric_backend.platforms.local import sample_source                             # noqa: E402

DATASETS = ("shop", "sap", "crm", "traps")


def traps_tables() -> dict[str, tuple[list[str], list[tuple]]]:
    """A fourth synthetic set built for known traps: `code` in two unrelated tables, `name` everywhere, two roles to
    users with names that do not say users, a header total that both lines and payments repeat, and two orphans."""
    t: dict[str, tuple[list[str], list[tuple]]] = {}
    t["users"] = (["user_id", "name"], [(i, f"User {i}") for i in range(1, 6)])
    t["countries"] = (["code", "name"], [("SE", "Country SE"), ("NO", "Country NO"), ("FI", "Country FI")])
    t["currencies"] = (["code", "name"], [("SEK", "Currency SEK"), ("NOK", "Currency NOK"), ("EUR", "Currency EUR")])
    t["customers"] = (["customer_id", "name", "country_code"], [(i, f"Customer {i}", ["SE", "NO", "FI"][i % 3]) for i in range(1, 9)])
    t["products"] = (["product_id", "name"], [(i, f"Product {i}") for i in range(1, 7)])
    inv, lines, pays = [], [], []
    for i in range(1, 13):
        n = 1 + i % 3
        amounts = [100 * (k + 1) for k in range(n)]
        inv.append((1000 + i, 77 if i == 12 else 1 + i % 8, 1 + i % 5, 1 + (i + 2) % 5, ["SEK", "NOK", "EUR"][i % 3], sum(amounts)))
        lines += [(1000 + i, k + 1, 99 if (i, k) == (5, 0) else 1 + (i + k) % 6, a) for k, a in enumerate(amounts)]
        pays += [(len(pays) + 1, 1000 + i, sum(amounts) / 2) for _ in range(2 if i % 2 else 1)]
    t["invoices"] = (["invoice_id", "customer_id", "created_by", "approved_by", "currency_code", "invoice_total"], inv)
    t["invoice_lines"] = (["invoice_id", "line_no", "product_id", "line_amount"], lines)
    t["payments"] = (["payment_id", "invoice_id", "paid_amount"], pays)
    return t


def source(name: str):
    if name == "shop":
        return sample_source()
    if name == "traps":
        return bc._sqlite_source("folder", "Synthetic invoices with known traps", "traps", traps_tables(), "synthetic")
    return bc._source({"sap": "sap", "crm": "crm"}[name], None, "")[0]


def _rel(source_t: str, cols, target_t: str, tcols=None) -> tuple:
    return (source_t.lower(), tuple(sorted(c.lower() for c in cols)), target_t.lower())


def _family(data_type: str) -> str:
    t = (data_type or "").lower()
    return "number" if any(w in t for w in ("int", "decimal", "double", "float", "numeric", "real")) else \
           "date" if "date" in t or "time" in t else "text"


# ---------------------------------------------------------------- (a) Krusgraph -----------------------------------------------

def krusgraph(src) -> dict:
    p = make_plan(src.schema)
    predicted = [(_rel(r.source, r.source_cols, r.target), r.rule) for r in p.relationships]
    predicted += [(_rel(r.source, r.source_cols, r.target), r.rule) for r in getattr(p, "extended", [])]
    checked = evidence.validate(p, src.execute, max_items=200)
    sugg = graphs.suggest(p, src.execute, check=15)["candidates"]
    orphans = {_rel(r["source"], r["columns"], r["target"]) for r in checked["relationships"] if r.get("orphans")}
    doubled = {(f["header"].lower(), c.lower(), f["line"].lower()) for f in checked["amount_levels"]["findings"]
               if isinstance(f["rows_per_header"], dict) and f["rows_per_header"]["max_lines"] > 1 for c in f["amount_columns"]}
    return {"predicted": [r for r, _ in predicted], "suggested": [_rel(c["source"], c["source_cols"], c["target"]) for c in sugg],
            "orphans": orphans, "doubled": doubled, "keys_not_unique": sum(1 for k in checked["keys"] if not k["verdict"].startswith("unique"))}


# ---------------------------------------------------------------- (b) approximation of documented autodetect rules -------

def _unique(src, table: str, col: str) -> bool:
    row = src.execute(evidence.key_sql(src.schema.schema, table, [col], dialect_of(src.execute)))[0]
    n, nulls, d = (int(row.get(k) or 0) for k in ("n", "nulls", "distinct_keys"))
    return n > 0 and nulls == 0 and d == n


def autodetect(src) -> dict:
    tables = list(src.schema)
    predicted, one_to_one = [], set()
    for i, a in enumerate(tables):
        for b in tables[i + 1:]:
            bcols = {c.name.lower(): c for c in b.columns}
            for ca in a.columns:
                cb = bcols.get(ca.name.lower())
                if cb is None or _family(ca.data_type) != _family(cb.data_type):
                    continue
                ua, ub = _unique(src, a.name, ca.name), _unique(src, b.name, cb.name)
                if ub:
                    predicted.append(_rel(a.name, [ca.name], b.name))            # many (or one) a -> one b
                    if ua:
                        one_to_one.add(predicted[-1])
                elif ua:
                    predicted.append(_rel(b.name, [cb.name], a.name))
    return {"predicted": predicted, "suggested": [], "orphans": set(), "doubled": set(), "one_to_one": one_to_one}


# ---------------------------------------------------------------- (c) dbt-style tests on declared relationships -----------

def dbt(src, facit: dict) -> dict:
    schema, dialect = src.schema.schema, dialect_of(src.execute)
    names = {t.name.lower(): t for t in src.schema}
    orphans, untestable = set(), 0
    for r in facit["relationships"]:
        if len(r["source_cols"]) != 1:
            untestable += 1                                   # the built-in relationships test takes one column
            continue
        s, t = names[r["source"].lower()], names[r["target"].lower()]
        row = src.execute(evidence.relationship_sql(schema, s.name, r["source_cols"], t.name, r["target_cols"], dialect))[0]
        if int(row.get("orphans") or 0):
            orphans.add(_rel(r["source"], r["source_cols"], r["target"]))
    return {"predicted": [_rel(r["source"], r["source_cols"], r["target"]) for r in facit["relationships"]], "suggested": [],
            "orphans": orphans, "doubled": set(), "untestable": untestable}


# ---------------------------------------------------------------- scoring ----------------------------------------------------

def score(out: dict, facit: dict, method: str) -> dict:
    truth = {_rel(r["source"], r["source_cols"], r["target"]) for r in facit["relationships"]}
    # a one-to-one relationship has no direction: count it either way round
    pred = {(p[2], p[1], p[0]) if p in out.get("one_to_one", ()) and (p[2], p[1], p[0]) in truth else p for p in out["predicted"]}
    tp = pred & truth
    sugg = set(out["suggested"]) - pred
    traps = facit["traps"]
    o_truth = {_rel(x["source"], x["source_cols"], x["target"]) for x in traps["orphans"]}
    d_truth = {(x["header"].lower(), x["column"].lower(), x["line"].lower()) for x in traps["doubled"]}
    amb = traps["ambiguous"]
    fell = sum(1 for a in amb if any(p not in truth and a["column"].lower() in p[1] for p in pred))
    if method == "dbt":
        decide = f"{len(truth)} relationships declared by hand"
        if out.get("untestable"):
            decide += f"; {out['untestable']} composite need a package or custom test"
    elif method == "krusgraph":
        decide = f"{len(sugg)} suggestion(s) to accept or reject"
    else:
        decide = "every created relationship to review (no rule or evidence given)"
    return {"predicted": len(pred), "true_positives": len(tp), "facit": len(truth),
            "precision": round(len(tp) / len(pred), 2) if pred else None,
            "recall": round(len(tp) / len(truth), 2) if truth else None,
            "recall_with_suggestions": round(len((pred | sugg) & truth) / len(truth), 2) if truth else None,
            "false_positives": sorted(" ".join([p[0], "+".join(p[1]), "->", p[2]]) for p in pred - truth),
            "orphans_found": f"{len(out['orphans'] & o_truth)}/{len(o_truth)}",
            "doubled_found": f"{len(out['doubled'] & d_truth)}/{len(d_truth)}",
            "ambiguous_fallen_for": f"{fell}/{len(amb)}",
            "left_to_human": decide}


def run() -> dict:
    facit = json.loads((HERE / "facit.json").read_text())
    results = {}
    for name in DATASETS:
        src = source(name)
        try:
            results[name] = {"krusgraph": score(krusgraph(src), facit[name], "krusgraph"),
                             "autodetect": score(autodetect(src), facit[name], "autodetect"),
                             "dbt": score(dbt(src, facit[name]), facit[name], "dbt")}
        finally:
            src.close()
    return results


LABELS = {"krusgraph": "Krusgraph (plan + validate_plan + suggest_relationships)",
          "autodetect": "Approximation of documented autodetect rules",
          "dbt": "dbt-style tests, relationships declared by a person"}


def markdown(results: dict) -> str:
    rows = ["| Dataset | Method | Precision | Recall | Recall incl. suggestions | Orphans found | Doubled totals found | "
            "Ambiguous columns fallen for | Left to the person |", "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for ds, by in results.items():
        for m, r in by.items():
            rows.append(f"| {ds} | {LABELS[m]} | {r['precision']} ({r['true_positives']}/{r['predicted']}) | {r['recall']} "
                        f"({r['true_positives']}/{r['facit']}) | {r['recall_with_suggestions']} | {r['orphans_found']} | "
                        f"{r['doubled_found']} | {r['ambiguous_fallen_for']} | {r['left_to_human']} |")
    return "\n".join(rows)


if __name__ == "__main__":
    res = run()
    (HERE / "results.json").write_text(json.dumps(res, indent=2, sort_keys=True) + "\n")
    print(markdown(res))
