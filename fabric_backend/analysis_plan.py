"""Which analyses a schema's SAP order-to-cash data supports, and why: deterministic rules, no AI (round AP2).

    recommend(plan, execute=None, weights=None, document_types=None, max_items=20) -> {
        "rule_version", "recommendations": [{analysis, name, readiness, score, value, readiness_value, quality, reasons,
        caveats, missing, uses: {tables, columns}, next_step, rule, fabric}], "land_next", "signals", "thresholds", ...}

What it reads. The plan Krusgraph already makes (plan_backend): which table is which SAP table (the SAP pack's names,
`sap_pack.pack_table`, CDS view names included), the keys and the relationships (item -> header, document -> customer
and material master). With a connection (`execute`) it counts, read-only, per sales dataset (billing documents, sales
orders): rows, calendar months with rows and the gaps between them, customers and how many bought more than once,
materials and in how many months each sold, currencies, return or credit documents, and the orphans of the joins the
analyses use. Counts only: no value leaves the database (the rule of profile.py, round n132); a month is compared
inside the query and only the number of months comes back. Personal-data columns are never read.

What it does with them. Each of the ten analyses in analysis/o2c.json has one rule (R1-R10, AP1's design): hard inputs
that must be there (or the analysis is "missing" and the answer says what to land), soft inputs scored linearly between a
floor and a target, a data-quality factor (0.8 when a join it needs has orphans) and a value (1 to 5, Krusgraph's own
judgement, replaceable by `weights`). score = value x mean(soft parts) x quality. readiness: "ready" (>= 0.8, no soft
part below 0.5), "partial" (>= 0.4, or capped by one weak part), "missing" (a hard input missing or < 0.4). Ties are
broken by the catalogue's order. Every recommendation says why ("Recommended because ...") and what is missing.

What it does not do. It runs no analysis and no model, calls no AI service and writes nothing. The analyses run later, in
the notebook analysis_notebook_draft writes, on Fabric Data Science (MLflow experiments, AutoML, Data Wrangler, semantic
link), started by the analyst. The thresholds are starting points to be validated by a data scientist.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .dialects import TSQL, of as dialect_of
from .infer import PlanInputError

HERE = Path(__file__).parent / "analysis"
NOTEBOOK_P1 = ("A7", "A8", "A3")
STATUSES = ("ready", "partial", "missing")


@lru_cache(maxsize=None)
def _catalogue_text(area: str) -> str:
    path = HERE / f"{area}.json"
    if not path.is_file():
        raise PlanInputError(f"area {area!r}: only 'o2c' (SAP order to cash) is built; p2p, inventory and finance are planned")
    return path.read_text(encoding="utf-8")


def catalogue(area: str = "o2c") -> dict:
    return json.loads(_catalogue_text(area))


def _norm(name: str) -> str:
    return "".join(ch for ch in str(name).upper() if ch.isalnum())


# ------------------------------------------------------------------ metadata: which table and column is which ----------

def _pack_names(plan) -> dict[str, str]:
    """{schema table: SAP pack table} for the tables the pack knows (VBRK, I_BILLING_DOCUMENT, ...)."""
    from . import sap_pack
    out = {}
    for t in plan.schema:
        found = sap_pack.pack_table(t.name)
        if found:
            out[t.name] = found
    return out


def _find_table(names: dict[str, str], candidates: list[str]) -> str | None:
    want = [_norm(c) for c in candidates]
    for c in want:                                      # the catalogue's order decides (VBRK before I_BillingDocument)
        for table in sorted(names):
            if _norm(names[table]) == c:
                return table
    return None


def _column(plan, table: str | None, candidates: list[str]) -> str | None:
    if not table:
        return None
    have = {_norm(c.name): c.name for c in plan.schema[table].columns}
    for c in candidates:
        if _norm(c) in have:
            return have[_norm(c)]
    return None


def _link(plan, source: str | None, target: str | None, column: str | None = None):
    """The plan's relationship source -> target (through `column` when given), or None."""
    if not source or not target:
        return None
    for r in plan.relationships:
        if r.source == source and r.target == target and (column is None or column.lower() in [c.lower() for c in r.source_cols]):
            return r
    return None


def resolve(plan, cat: dict) -> dict:
    """Which schema tables and columns play each role, from the pack's names and the plan's relationships."""
    names = _pack_names(plan)
    masters = {k: _find_table(names, v) for k, v in cat["masters"].items()}
    tables = {k: [t for t in sorted(names) if _norm(names[t]) in [_norm(c) for c in v]] for k, v in cat["tables"].items()}
    datasets = {}
    for key, d in cat["datasets"].items():
        header, item = _find_table(names, d["header"]), _find_table(names, d["item"])
        side = {"header": header, "item": item}
        fields = {}
        for f, cands in d["fields"].items():
            got = None
            for where, col in cands:
                c = _column(plan, side[where], [col])
                if c:
                    got = {"table": side[where], "column": c, "where": where}
                    break
            fields[f] = got
        join = _link(plan, item, header)
        cust, mat = fields.get("customer"), fields.get("material")
        datasets[key] = {
            "what": d["what"], "header": header, "item": item, "fields": fields,
            "join": ({"source_cols": list(join.source_cols), "target_cols": list(join.target_cols), "rule": join.rule} if join else None),
            "customer_link": _link(plan, cust["table"], masters["customer"], cust["column"]) if cust else None,
            "material_link": _link(plan, mat["table"], masters["material"], mat["column"]) if mat else None,
            "return_types": d["return_types"], "pack": {t: names.get(t) for t in (header, item) if t}}
    return {"names": names, "masters": masters, "tables": tables, "datasets": datasets}


def _usable(ds: dict) -> bool:
    """A dataset the sales rules can read: a date and an amount or quantity, on one table or joined item -> header."""
    f = ds["fields"]
    if not f.get("date") or not (f.get("amount") or f.get("quantity")):
        return False
    sides = {x["where"] for x in f.values() if x}
    return sides == {"header"} or sides == {"item"} or bool(ds["join"])


# ------------------------------------------------------------------ counts (read-only, never a value) ----------------

def _month_key(expr: str) -> str:
    """'YYYYMM' of a date, a datetime or SAP's 'YYYYMMDD' text; the same text in T-SQL, Spark SQL and SQLite."""
    return f"SUBSTRING(REPLACE(CAST({expr} AS VARCHAR(30)), '-', ''), 1, 6)"


def _month_index(key: str) -> str:
    return f"(CAST(SUBSTRING({key}, 1, 4) AS INT) * 12 + CAST(SUBSTRING({key}, 5, 2) AS INT))"


def base_sql(plan, ds: dict, dialect=TSQL, returns: list[str] | None = None) -> str:
    """The rows one sales dataset's rules count, as a derived table x: mk (month key), mi (month index), doc, cust, mat,
    cur, ret (1 for a return or credit document type). Item joined to its header (inner join: an orphan item is left out
    and counted on its own as quality)."""
    q = dialect.quote
    f, schema = ds["fields"], plan.schema.schema
    alias = {"header": "h", "item": "i"}
    use_item = any(x and x["where"] == "item" for x in f.values()) and ds["item"]
    use_header = any(x and x["where"] == "header" for x in f.values()) and ds["header"]
    if use_item and use_header:
        on = " AND ".join(f"i.{q(a)} = h.{q(b)}" for a, b in zip(ds["join"]["source_cols"], ds["join"]["target_cols"]))
        src = f"{dialect.table(schema, ds['item'])} AS i INNER JOIN {dialect.table(schema, ds['header'])} AS h ON {on}"
    elif use_item:
        src = f"{dialect.table(schema, ds['item'])} AS i"
    else:
        src = f"{dialect.table(schema, ds['header'])} AS h"

    def col(name):
        x = f.get(name)
        return f"{alias[x['where']]}.{q(x['column'])}" if x else "NULL"
    doc_side = "h" if use_header else "i"
    doc_cols = (ds["join"]["target_cols"] if use_header and ds["join"] else
                [c.name for c in plan.schema[ds["header"] if use_header else ds["item"]].columns
                 if c.name.upper() in ("VBELN", "BILLINGDOCUMENT", "BILLING_DOCUMENT", "SALESDOCUMENT", "SALES_DOCUMENT")])
    client = ("MANDT", "RCLNT", "CLIENT")             # one client per question; a document is its number (VBELN)
    doc_cols = [c for c in doc_cols if c.upper() not in client] or doc_cols
    doc = f"{doc_side}.{q(doc_cols[-1])}" if doc_cols else "NULL"
    rtypes = ", ".join("'" + str(t).replace("'", "''") + "'" for t in (returns or []))
    ret = f"CASE WHEN {col('doc_type')} IN ({rtypes}) THEN 1 ELSE 0 END" if rtypes and f.get("doc_type") else "0"
    mk = _month_key(col("date"))
    return (f"SELECT {mk} AS mk, {_month_index(mk)} AS mi, {doc} AS doc, {col('customer')} AS cust, {col('material')} AS mat, "
            f"{col('currency')} AS cur, {ret} AS ret FROM {src} WHERE {col('date')} IS NOT NULL")


def count_sql(plan, ds: dict, dialect=TSQL, returns: list[str] | None = None) -> dict[str, str]:
    """The three counting statements of one dataset: totals, per customer, per material. Each returns one row of counts."""
    c = dialect.count
    x = f"({base_sql(plan, ds, dialect, returns)}) AS x"
    filled = "x.{0} IS NOT NULL AND LTRIM(RTRIM(CAST(x.{0} AS VARCHAR(60)))) <> ''"
    totals = (f"SELECT {c}(*) AS row_count, {c}(DISTINCT x.mk) AS months, MAX(x.mi) - MIN(x.mi) + 1 AS span, "
              f"{c}(DISTINCT x.doc) AS documents, {c}(DISTINCT x.cust) AS customers, {c}(DISTINCT x.mat) AS materials, "
              f"{c}(DISTINCT x.cur) AS currencies, {c}(DISTINCT CASE WHEN x.ret = 1 THEN x.doc END) AS return_documents FROM {x}")
    per_customer = (f"SELECT {c}(*) AS customers, SUM(CASE WHEN g.n >= 2 THEN 1 ELSE 0 END) AS repeat_customers, "
                    f"SUM(CASE WHEN g.n >= 3 AND g.lm <= t.last_mi - 6 THEN 1 ELSE 0 END) AS churned, "
                    f"{c}(DISTINCT g.fm) AS first_months FROM (SELECT x.cust, {c}(DISTINCT x.doc) AS n, MIN(x.mi) AS fm, "
                    f"MAX(x.mi) AS lm FROM {x} WHERE {filled.format('cust')} GROUP BY x.cust) AS g CROSS JOIN "
                    f"(SELECT MAX(y.mi) AS last_mi FROM ({base_sql(plan, ds, dialect, returns)}) AS y) AS t")
    per_material = (f"SELECT {c}(*) AS materials, SUM(CASE WHEN g.m >= 6 THEN 1 ELSE 0 END) AS six_months, "
                    f"SUM(CASE WHEN g.m >= 18 THEN 1 ELSE 0 END) AS eighteen_months, "
                    f"SUM(CASE WHEN g.k >= 2 THEN 1 ELSE 0 END) AS several_customers FROM (SELECT x.mat, "
                    f"{c}(DISTINCT x.mk) AS m, {c}(DISTINCT x.cust) AS k FROM {x} WHERE {filled.format('mat')} GROUP BY x.mat) AS g")
    out = {"totals": totals}
    if ds["fields"].get("customer"):
        out["per_customer"] = per_customer
    if ds["fields"].get("material"):
        out["per_material"] = per_material
    return out


def _int(v) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def _orphans(plan, execute, r, dialect) -> dict:
    from . import evidence, sap_pack
    initial = sap_pack.initial_columns(r.source, r.source_cols, r.target) if r.rule == "SAP pack" else []
    sql = evidence.relationship_sql(plan.schema.schema, r.source, list(r.source_cols), r.target, list(r.target_cols), dialect,
                                    blank_is_none=r.rule == "SAP pack", initial=initial or None)
    row = (list(execute(sql)) or [{}])[0]
    return {"source": r.source, "columns": list(r.source_cols), "target": r.target,
            "rows_with_value": _int(row.get("with_value")), "orphans": _int(row.get("orphans"))}


def count(plan, roles: dict, execute, document_types: dict, max_items: int = 20) -> dict:
    """{dataset: {"totals", "per_customer", "per_material", "joins": [orphans], "not_counted": [...]}}: counts only."""
    dialect = dialect_of(execute)
    budget = max(1, int(max_items))
    out = {}
    for key, ds in roles["datasets"].items():
        if not _usable(ds):
            continue
        returns = document_types.get(ds["return_types"], [])
        got = {"joins": [], "not_counted": [], "statements": 0}
        for name, sql in count_sql(plan, ds, dialect, returns).items():
            if got["statements"] >= budget:
                got["not_counted"].append(f"{name}: max_items reached")
                continue
            try:
                row = (list(execute(sql)) or [{}])[0]
                got[name] = {k: _int(v) for k, v in row.items()}
            except Exception as e:                                       # noqa: BLE001 - the class only: a message can quote a value
                got["not_counted"].append(f"{name}: the count could not run ({type(e).__name__})")
            got["statements"] += 1
        budget -= got["statements"]
        for link in (_link(plan, ds["item"], ds["header"]), ds["customer_link"], ds["material_link"]):
            if link is None:
                continue
            if budget <= 0:
                got["not_counted"].append(f"orphans {link.source} -> {link.target}: max_items reached")
                continue
            try:
                got["joins"].append(_orphans(plan, execute, link, dialect))
            except Exception as e:                                       # noqa: BLE001
                got["not_counted"].append(f"orphans {link.source} -> {link.target}: could not run ({type(e).__name__})")
            budget -= 1
        out[key] = got
    return out


# ------------------------------------------------------------------ the rules ----------------------------------------

def part(v: float, floor: float, target: float) -> float:
    """Linear between floor (0) and target (1)."""
    if target <= floor:
        return 1.0 if v >= target else 0.0
    return round(max(0.0, min(1.0, (v - floor) / (target - floor))), 3)


def _ref(x: dict | None) -> str:
    return f"{x['table']}.{x['column']}" if x else "?"


class _Rule:
    """One analysis: hard inputs, soft parts, reasons, caveats, missing, the tables and columns it uses."""

    def __init__(self, a: dict, value: float):
        self.a, self.value = a, value
        self.hard_missing: list[str] = []
        self.parts: list[tuple[str, float]] = []
        self.reasons: list[str] = []
        self.caveats: list[str] = []
        self.missing: list[str] = []
        self.unlock: list[str] = []
        self.tables: list[str] = []
        self.columns: list[str] = []
        self.quality = 1.0
        self.counted = True
        self.not_counted_why: str | None = None
        self.not_applicable = False

    def need(self, ok, missing: str, unlock: str | None = None):
        if not ok:
            self.hard_missing.append(missing)
            if unlock and unlock not in self.unlock:
                self.unlock.append(unlock)
        return bool(ok)

    def use(self, *xs):
        for x in xs:
            if not x:
                continue
            if x["table"] not in self.tables:
                self.tables.append(x["table"])
            ref = _ref(x)
            if ref not in self.columns:
                self.columns.append(ref)

    def use_table(self, *ts):
        for t in ts:
            if t and t not in self.tables:
                self.tables.append(t)


def _dataset(roles: dict) -> tuple[str | None, dict | None]:
    for key in ("billing", "orders"):                    # billing first: what was invoiced, AP1's choice
        ds = roles["datasets"].get(key)
        if ds and _usable(ds):
            return key, ds
    return None, None


def _quality(rule: _Rule, counts: dict, th: dict, links: list[tuple[str, str]]):
    for j in counts.get("joins", []):
        if (j["source"], j["target"]) in links and j["orphans"]:
            rule.quality = th["quality_factor"]
            rule.caveats.append(f"{j['orphans']} of {j['rows_with_value']} {j['source']} rows point at no {j['target']} row "
                                f"({', '.join(j['columns'])}): quality factor {th['quality_factor']} (validate_plan's count)")


def _months_text(n: int, ds: dict) -> str:
    return f"{n} calendar month{'s' if n != 1 else ''} of {ds['what']} with rows"


def _rules(roles: dict, counts: dict | None, th: dict, values: dict, doc_types: dict) -> list[_Rule]:
    key, ds = _dataset(roles)
    c = (counts or {}).get(key, {}) if key else {}
    tot, cus, mat = c.get("totals", {}), c.get("per_customer", {}), c.get("per_material", {})
    cus_ok, mat_ok = "per_customer" in c, "per_material" in c   # AP3: a count that did not run is not a zero
    counted = counts is not None
    cat = {a["id"]: a for a in catalogue()["analyses"]}
    f = ds["fields"] if ds else {}
    months, span = tot.get("months", 0), tot.get("span", 0)
    gaps = max(0, span - months) if months else 0
    join_links = [(ds["item"], ds["header"])] if ds and ds["join"] else []
    sales = "billing documents (VBRK + VBRP) or sales orders (VBAK + VBAP) with a date, an amount and the item-to-header link"
    out = []

    def new(aid: str) -> _Rule:
        r = _Rule(cat[aid], values[aid])
        r.counted = counted
        out.append(r)
        return r

    def months_reason(r: _Rule):
        r.reasons.append(f"{_ref(f.get('date'))} is the date ({_months_text(months, ds)}, "
                         f"{'no gap' if not gaps else f'{gaps} month(s) without rows'} between the first and the last; profile)")

    # R1 forecasting -> A7
    r = new("A7")
    if r.need(ds, f"no sales data the rules can read: {sales}", "sales"):
        r.use(f.get("date"), f.get("amount") or f.get("quantity"))
        r.reasons.append(f"{_ref(f.get('amount') or f.get('quantity'))} is the {'amount' if f.get('amount') else 'quantity'} to forecast "
                         f"(SAP pack: {ds['pack'].get(ds['item']) or ds['pack'].get(ds['header'])})")
        if counted:
            months_reason(r)
            r.parts += [("months", part(months, *th["months"])), ("gaps", 1.0 if gaps == 0 else 0.5 if gaps == 1 else 0.0),
                        ("currency", 1.0 if tot.get("currencies", 0) <= 1 else 0.5)]
            if months < th["months"][0]:
                r.missing.append(f"Only {months} month(s) of {ds['what']} history; forecasting needs at least {th['months'][0]} and "
                                 f"about {th['months'][1]} (two yearly cycles). Land more history or start with a descriptive trend.")
                r.unlock.append("history")
            elif months < th["months"][1]:
                r.caveats.append(f"{months} months: one yearly cycle is visible, two ({th['months'][1]}) make the season reliable")
            if tot.get("currencies", 0) > 1:
                r.caveats.append(f"{tot['currencies']} currencies in {_ref(f.get('currency'))}: convert to one before forecasting")
            n = mat.get("materials", 0)
            if n and mat.get("eighteen_months", 0) * 2 < n:
                r.caveats.append(f"per material: {mat.get('eighteen_months', 0)} of {n} materials sold in {th['per_item_regular_months']} "
                                 "or more months: forecast the total or product groups, or use a method for intermittent demand")
        _quality(r, c, th, join_links)

    # R2 RFM -> A8
    r = new("A8")
    if r.need(ds, f"no sales data: {sales}", "sales"):
        cust = f.get("customer")
        if r.need(cust and ds["customer_link"], "a customer column on the documents linked to the customer master "
                  "(e.g. VBRK.KUNRG -> KNA1)", "customers"):
            r.use(cust, f.get("date"), f.get("amount"))
            r.use_table(roles["masters"]["customer"])
            r.need(f.get("amount"), "an amount on the items (e.g. VBRP.NETWR) for M, the monetary score", "sales")
            r.reasons.append(f"{_ref(cust)} -> {roles['masters']['customer']} is the customer (plan, rule {ds['customer_link'].rule}), "
                             f"{_ref(f.get('date'))} the date and {_ref(f.get('amount'))} the amount: R, F and M can be derived")
            if counted and not cus_ok:
                n = tot.get("customers", 0)
                if n < th["customers"][0]:
                    r.parts.append(("customers", part(n, *th["customers"])))
                    r.missing.append(f"Only {n} customers with documents; RFM needs at least {th['customers'][0]}.")
                else:
                    r.counted, r.not_counted_why = False, "the per-customer count did not run (repeat share not known)"
            elif counted:
                n, rep = cus.get("customers", 0), cus.get("repeat_customers", 0)
                share = round(rep / n, 3) if n else 0.0
                r.reasons.append(f"{n} customers with documents, {round(100 * share, 1)} % of them with 2 or more (profile)")
                r.parts += [("customers", part(n, *th["customers"])), ("repeat_share", part(share, *th["repeat_share"])),
                            ("months", part(months, *th["rfm_months"]))]
                if n < th["customers"][1]:
                    r.caveats.append(f"{n} customers (target {th['customers'][1]}): quintiles will be thin; consider fixed thresholds")
                if n < th["customers"][0]:
                    r.missing.append(f"Only {n} customers with documents; RFM needs at least {th['customers'][0]}.")
                if n >= th["cluster_customers"]:
                    r.reasons.append(f"{n} customers: k-means clustering on R, F, M is offered beside the scores")
                else:
                    r.caveats.append(f"clustering not offered: fewer than {th['cluster_customers']} customers")
        _quality(r, c, th, join_links + ([(ds["customer_link"].source, ds["customer_link"].target)] if ds["customer_link"] else []))

    # R4 ABC/XYZ -> A3
    r = new("A3")
    if r.need(ds, f"no sales data: {sales}", "sales"):
        m = f.get("material")
        if r.need(m and ds["material_link"], "a material column on the items linked to the material master (e.g. VBRP.MATNR -> MARA)",
                  "materials"):
            r.use(m, f.get("amount"), f.get("quantity"), f.get("date"))
            r.use_table(roles["masters"]["material"])
            r.reasons.append(f"{_ref(m)} -> {roles['masters']['material']} is the material (plan, rule {ds['material_link'].rule}); "
                             f"{_ref(f.get('amount') or f.get('quantity'))} gives the value for ABC"
                             + (f" and {_ref(f.get('quantity'))} the demand for XYZ" if f.get("quantity") else ""))
            if counted and not mat_ok:
                r.counted, r.not_counted_why = False, "the per-material count did not run"
            elif counted:
                n = mat.get("materials", 0)
                r.reasons.append(f"{n} materials sold (profile)")
                r.parts.append(("materials", part(n, *th["materials"])))
                if n < th["materials"][0]:
                    r.missing.append(f"Only {n} materials sold; below {th['materials'][0]} an ABC split is a list.")
                six = mat.get("six_months", 0)
                if months >= th["months"][0] and n and six * 2 >= n and f.get("quantity"):
                    r.reasons.append(f"XYZ: {six} of {n} materials sold in {th['xyz_months_per_item']} or more months over {months} months")
                else:
                    r.caveats.append(f"XYZ part not ready: {six} of {n} materials sold in {th['xyz_months_per_item']} or more months, "
                                     f"{months} months of history (XYZ needs a monthly series per material); ABC only")
        _quality(r, c, th, join_links + ([(ds["material_link"].source, ds["material_link"].target)] if ds["material_link"] else []))

    # R3 cohorts and churn -> A4
    r = new("A4")
    if r.need(ds, f"no sales data: {sales}", "sales"):
        cust = f.get("customer")
        if r.need(cust and ds["customer_link"], "a customer column linked to the customer master", "customers"):
            r.use(cust, f.get("date"))
            if counted:
                ok = r.need(months >= th["cohort_months"][0], f"at least {th['cohort_months'][0]} months of history "
                            f"({months} now)", "history")
                if ok and not cus_ok:
                    r.counted, r.not_counted_why = False, "the per-customer count did not run (first months and churn not known)"
                elif ok:
                    fm = cus.get("first_months", 0)
                    r.reasons.append(f"first-document month derivable for {cus.get('customers', 0)} customers, in {fm} different months")
                    r.parts += [("months", part(months, *th["cohort_months"])), ("first_months", part(fm, *th["cohort_first_months"]))]
                    churned = cus.get("churned", 0)
                    if churned >= th["churned_for_model"]:
                        r.reasons.append(f"{churned} customers count as churned by the example definition (3 or more documents, "
                                         "none in the last 6 months): a churn model can be trained once the definition is agreed")
                    else:
                        r.caveats.append(f"a churn model is not offered: {churned} customers count as churned by the example definition "
                                         f"(3 or more documents, none in the last 6 months), below {th['churned_for_model']}; cohort tables only")
        _quality(r, c, th, join_links)

    # R8 margin -> A1
    r = new("A1")
    if r.need(ds, f"no sales data: {sales}", "sales"):
        cost = f.get("cost") if key == "billing" else None
        has_cost = bool(cost) or bool(roles["tables"]["conditions"]) or any(roles["names"].get(t) in ("ACDOCA",) for t in roles["tables"]["receivables"])
        if r.need(has_cost, "a cost: VBRP.WAVWR, a cost condition in KONV/PRCD_ELEMENTS, or ACDOCA cost-of-goods lines", "cost"):
            r.use(f.get("amount"), cost)
            r.reasons.append("revenue and a cost are both present" + (f" ({_ref(cost)})" if cost else ""))
            r.parts.append(("cost", 1.0))
        else:
            r.caveats.append("offered instead: revenue concentration by customer and material (no cost needed)")

    # R5 OTIF -> A5
    r = new("A5")
    orders = roles["datasets"].get("orders") or {}
    req = (orders.get("fields") or {}).get("requested_date")
    sched = roles["tables"]["schedule_line"]
    from_sched = None
    if sched and roles.get("plan") is not None:
        from_sched = _column(roles["plan"], sched[0], ["EDATU", "REQUESTED_DELIVERY_DATE"])
    actual = None
    if roles["tables"]["delivery"] and roles.get("plan") is not None:
        actual = _column(roles["plan"], roles["tables"]["delivery"][0], ["WADAT_IST", "ACTUAL_GOODS_MOVEMENT_DATE"])
    link = roles["tables"]["delivery_item"] and orders.get("item") and _link(roles["plan"], roles["tables"]["delivery_item"][0], orders["item"])
    r.need(link, "delivery items linked to order items (LIPS.VGBEL/VGPOS -> VBAP)", "otif_dates")
    r.need(req or from_sched, "a requested delivery date (VBEP.EDATU or VBAK.VDATU)", "otif_dates")
    r.need(actual, "the actual goods issue date (LIKP.WADAT_IST)", "otif_dates")
    if link:
        r.use_table(roles["tables"]["delivery_item"][0], orders.get("item"))
        if r.hard_missing:
            r.caveats.append("offered instead: in-full only (delivered against ordered quantity) and lead time from creation "
                             "dates, which is not OTIF")
    if not r.hard_missing:
        r.reasons.append("order items, delivery items, a requested date and the goods issue date are present")
        r.parts.append(("dates", 1.0))

    # R6 DSO and aging -> A2
    r = new("A2")
    rec = roles["tables"]["receivables"]
    if r.need(rec, "customer open and cleared items: BSID/BSAD (ECC) or ACDOCA customer lines (S/4HANA)", "receivables"):
        r.use_table(*rec)
        r.reasons.append(f"receivables table(s) {', '.join(rec)} present (SAP pack)")
        r.caveats.append("the due date and clearing date roles are read by name; the SAP pack does not name them yet (P2)")
        r.parts.append(("receivables", 1.0))

    # R7 price realisation -> A6
    r = new("A6")
    cond = roles["tables"]["conditions"]
    if r.need(cond, "document conditions: KONV (ECC) or PRCD_ELEMENTS (S/4HANA)", "conditions"):
        r.use_table(*cond)
        r.reasons.append(f"conditions table {cond[0]} present (SAP pack, module pricing)")
        r.parts.append(("conditions", 1.0))
    elif ds and f.get("material") and counted and mat.get("materials"):
        r.caveats.append(f"offered instead: unit price dispersion (amount / quantity per material), a proxy, not a price waterfall; "
                         f"{mat.get('several_customers', 0)} of {mat.get('materials', 0)} materials are sold to 2 or more customers")

    # R9 credit risk -> A9
    r = new("A9")
    r.need(rec, "A2's payment history: BSID/BSAD or ACDOCA customer lines", "receivables")
    r.need(roles["masters"]["customer"], "the customer master (KNA1 or I_Customer)", "customers")
    if not r.hard_missing:
        r.use_table(*rec, roles["masters"]["customer"])
        r.reasons.append("payment history and the customer master are present")
        r.parts.append(("history", 1.0))
    r.caveats.append("a warning list from payment behaviour, not a credit rating")

    # R10 returns -> A10
    r = new("A10")
    if r.need(ds and f.get("doc_type"), f"a document type column ({'FKART' if key == 'billing' else 'AUART'})", "sales"):
        r.use(f.get("doc_type"))
        types = doc_types.get(ds["return_types"], [])
        if counted:
            n = tot.get("return_documents", 0)
            if r.need(n > 0, f"no documents of the return or credit types {', '.join(types)} in {_ref(f.get('doc_type'))}: not "
                      "applicable to this data (confirm the types with document_types)"):
                r.reasons.append(f"{n} return or credit documents of the types {', '.join(types)} in {_ref(f.get('doc_type'))} (profile)")
                r.parts.append(("returns", part(n, *th["returns"])))
            else:
                r.not_applicable = True
    return out


def _score(r: _Rule, th: dict) -> dict:
    a = r.a
    if r.hard_missing:
        status, readiness = "missing", 0.0
    elif not r.counted:
        status, readiness = "partial", th["not_counted_readiness"]
        if r.not_counted_why:
            r.caveats.append(f"{r.not_counted_why}: readiness taken as {readiness} to rank; see signals.counts not_counted")
        else:
            r.caveats.append(f"rows not counted (profile=false or no connection): readiness taken as {readiness} to rank; run with "
                             "profile=true for the counts")
    else:
        readiness = round(sum(v for _, v in r.parts) / len(r.parts), 3) if r.parts else 1.0
        weak = [n for n, v in r.parts if v < th["weak_part"]]
        if r.missing:                                    # a soft input below its floor: not ready, and the answer says why
            status = "missing"
        elif readiness * r.quality >= th["ready"] and not weak:
            status = "ready"
        elif readiness * r.quality >= th["partial"] or (weak and readiness * r.quality >= th["partial"]):
            status = "partial"
        else:
            status = "missing"
        if weak and status != "missing":
            r.caveats.append(f"capped at partial: {', '.join(weak)} below {th['weak_part']}")
    score = round(r.value * readiness * r.quality, 2) if status != "missing" else 0.0
    missing = list(r.hard_missing) + [m for m in r.missing if m not in r.hard_missing]
    if status == "missing" and not missing:
        missing.append("readiness below the partial line: " + ", ".join(f"{n} {v}" for n, v in r.parts))
    if status == "missing":
        lead = "Not recommended yet because: " + "; ".join(missing)
    else:
        lead = "Recommended because: " + "; ".join(r.reasons)
    if a["notebook"] == "P1" and status != "missing":
        nxt = f"analysis_notebook_draft(analysis=\"{a['id']}\"): a notebook wired to these tables (dry run; nothing is created or run)"
    elif status == "missing":
        nxt = "land: " + "; ".join(catalogue()["land"][u]["text"] for u in r.unlock) if r.unlock else "nothing to do on this data"
    else:
        nxt = "notebook planned for phase 2; the rule already says the data is there"
    return {"analysis": a["id"], "name": a["name"], "readiness": status, "score": score, "value": r.value,
            "readiness_value": round(readiness, 3), "quality": r.quality, "because": lead,
            "reasons": r.reasons if status != "missing" else [],
            "caveats": r.caveats, "missing": missing, "uses": {"tables": r.tables, "columns": r.columns},
            "next_step": nxt, "rule": a["rule"], "parts": {n: v for n, v in r.parts}, "fabric": a["fabric"],
            **({"not_applicable": True} if r.not_applicable else {}), "_unlock": r.unlock}


def recommend(plan, execute=None, weights: dict | None = None, document_types: dict | None = None, max_items: int = 20,
              area: str = "o2c", profile: bool = True) -> dict:
    """The ranked analyses for a plan (see the module text). `execute` with profile=True counts; without, names only."""
    cat = catalogue(area)
    th = cat["thresholds"]
    values = {a["id"]: a["value"] for a in cat["analyses"]}
    if weights:
        bad = [k for k, v in weights.items() if k not in values or not isinstance(v, (int, float)) or isinstance(v, bool) or not 0 <= v <= 5]
        if bad:
            raise PlanInputError(f"weights: analysis ids A1-A10 with a value from 0 to 5; not {', '.join(map(str, bad))}")
        values.update({k: float(v) if v % 1 else int(v) for k, v in weights.items()})
    doc_types = {k: list(v) for k, v in cat["document_types"].items() if k != "note"}
    if document_types:
        bad = [k for k in document_types if k not in doc_types]
        if bad:
            raise PlanInputError(f"document_types: keys {', '.join(doc_types)}; not {', '.join(bad)}")
        doc_types.update({k: [str(x) for x in v] for k, v in document_types.items()})
    roles = resolve(plan, cat)
    roles["plan"] = plan
    counts = count(plan, roles, execute, doc_types, max_items) if (execute is not None and profile) else None
    rules = _rules(roles, counts, th, values, doc_types)
    order = [a["id"] for a in cat["analyses"]]
    scored = [_score(r, th) for r in rules]
    rank = {"ready": 0, "partial": 1, "missing": 2}
    scored.sort(key=lambda e: (-e["score"], rank[e["readiness"]], order.index(e["analysis"])))
    unlock: dict[str, list[str]] = {}
    for e in scored:
        if e["readiness"] == "missing" and not e.get("not_applicable"):
            for u in e["_unlock"]:
                unlock.setdefault(u, []).append(e["analysis"])
    for e in scored:
        e.pop("_unlock")
    land = sorted(({"land": cat["land"][u]["text"], "unlocks": sorted(ids, key=order.index), "value": sum(values[i] for i in ids)}
                   for u, ids in unlock.items()), key=lambda x: (-x["value"], x["land"]))
    key, ds = _dataset(roles)
    signals = {"pack_tables": {t: roles["names"][t] for t in sorted(roles["names"])},
               "dataset": ({"name": key, "header": ds["header"], "item": ds["item"],
                            "fields": {k: _ref(v) for k, v in ds["fields"].items() if v},
                            "field_columns": {k: {"table": v["table"], "column": v["column"]} for k, v in ds["fields"].items() if v},
                            "join": ds["join"], "customer_link": bool(ds["customer_link"]), "material_link": bool(ds["material_link"])}
                           if ds else None),
               "counts": ({k: {x: v for x, v in c.items() if x != "statements"} for k, c in counts.items()} if counts is not None else
                          "not counted (profile=false or no connection)")}
    ready = [e["analysis"] for e in scored if e["readiness"] == "ready"]
    summary = (f"{len(ready)} of {len(scored)} analyses ready ({', '.join(ready) or 'none'}), "
               f"{sum(e['readiness'] == 'partial' for e in scored)} partial, {sum(e['readiness'] == 'missing' for e in scored)} missing; "
               f"top: {scored[0]['analysis']} {scored[0]['name']} ({scored[0]['readiness']}, score {scored[0]['score']})")
    return {"summary": summary, "rule_version": cat["rule_version"], "area": area, "recommendations": scored, "land_next": land,
            "signals": signals, "thresholds": th, "values": values, "document_types": doc_types,
            "notes": [cat["rule"], cat["value_note"],
                      "Counts only: no row value left the database; the analyses themselves run later, in a notebook on Fabric "
                      "Data Science that the analyst starts. Krusgraph complements Fabric Data Science; it does not run models.",
                      "The thresholds are starting points to be validated by a data scientist."]}
