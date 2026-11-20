"""Business requirements, as a pasted list, matched to checked SAP tables, joins and measures by rules (round RQ1).

Written 19 November 2026 by round RQ1. The flow it serves (docs/REQUIREMENTS-TO-FABRIC.md): the business collects
requirements in a Copilot Workspace, Copilot summarises them as a list, someone pastes that list here, and Krusgraph
says for each line what the checked data can answer. Nothing is read from the Workspace: Microsoft Learn documents no
API for a Workspace's content (read 19 November 2026), so the list is pasted text.

    parse(text)                                   -> [{id, text}]  (R1, R2 ... in the order given)
    draft(plan, text, validation=None, schema="") -> {"rule_version", "requirements": [{id, text, state, ...}],
                                                      "counts", "feeds", "questions", "never"}

No AI and no language model: fixed word lists (SYNONYMS, in English and Swedish), the SAP pack's table names
(sap_pack.pack_table) and the plan's columns decide, so the same list and the same plan give the same answer, byte for
byte. A requirement gets one of four states:

- "answerable": every table, column and join it needs is in the plan, and the joins were counted and held
  (validate_plan's evidence: orphans 0), or no join is needed;
- "trap": answerable, but only by following a rule the answer states: a header amount that repeats on every line
  (VBAK.NETWR over VBAP rows), a join with rows that point at nothing, quantities in several units;
- "missing": a table or field it needs is not in the plan; the answer names it (LIKP.WADAT_IST, BSID ...);
- "unclear": the words do not decide (no measure, "sales" as invoiced or as ordered, "best" without a measure); the
  answer asks one question.

What it reads: the plan (names, keys, relationships) and, when given, validate_plan's counts. What it writes: nothing.
The T-SQL in the answer names columns only; no row value is read here or returned (the leak test is in
tests/test_rq1_requirements_draft.py). Personal-data columns (privacy rules) are never used: a customer is its number.

What the answer feeds (`feeds`), each item with its requirement ids: the tables for gold_views_draft and
semantic_model_draft (their `tables=`), one example query per answerable requirement for create_data_agent (its
`requirements=` adds them to the agent's example queries, each query starting with "-- R1: ..."), and the measures a
semantic model would need, as a list to review (semantic_model_draft does not take them as input yet).
"""
from __future__ import annotations

import re

from .evidence import qi
from .infer import Plan

RULE_VERSION = "RQ1-1 (19 November 2026)"
STATES = ("answerable", "trap", "missing", "unclear")
MAX_REQUIREMENTS = 20
MAX_LINE_CHARS = 240
MAX_INPUT_CHARS = 8000
APPROVAL = ("A person approves: read each requirement's state and evidence, answer the questions, then run the next "
            "steps as dry runs. Nothing here writes to Fabric.")

# ------------------------------------------------------------------ the word lists (English and Swedish) ---------------
# Each entry is a regular-expression fragment matched at a word start in the lower-cased requirement. Order matters:
# the first measure that matches is the requirement's measure; open items and late deliveries come before revenue,
# because "unpaid invoices" names an invoice and "late deliveries per customer" is not revenue.
SYNONYMS: dict[str, tuple[str, ...]] = {
    # measures
    "open_items": ("unpaid", "not paid", "open invoice", "open item", "outstanding", "overdue", "receivable", "dso",
                   "days sales outstanding", "obetal", "förfall", "kundfordring", "utestående", "öppna fakturor",
                   "öppna poster", "ej betal"),
    "late_delivery": ("late deliver", "late shipment", "delayed", "delivered late", "on time", "on-time", "otif",
                      "delivery performance", "försen", "sena leveranser", "sen leverans", "leveransprecision",
                      "levererats för sent", "för sent"),
    "margin": ("margin", "profit", "contribution", "cost of", "costs", "marginal", "täckningsbidrag", "kostnad", "vinst"),
    "order_count": ("number of orders", "order count", "how many orders", "count of orders", "antal order",
                    "antalet order", "orderantal"),
    "order_value": ("order value", "order intake", "orders received", "booked", "bookings", "ordervärde",
                    "orderingång", "orderstock", "beställt värde"),
    "revenue": ("revenue", "turnover", "invoiced", "billed", "billing", "net sales", "intäkt", "omsättning",
                "fakturer", "nettoomsättning"),
    "quantity": ("quantity", "quantities", "volume", "units sold", "pieces", "kvantitet", "volym", "styck", "antal sålda"),
    "sales_word": ("sales", "sold", "försäljning", "sålt", "sålda"),
    "vague": ("best", "top", "worst", "performance", "kpi", "insight", "how are we doing", "overview", "bäst", "topp",
              "sämst", "översikt", "hur går det"),
    # dimensions
    "customer": ("customer", "client", "account", "sold-to", "sold to", "kund", "beställare"),
    "payer": ("payer", "betalare", "bill-to", "bill to", "fakturamottagare"),
    "ship_to": ("ship-to", "ship to", "varumottagare", "leveransadress"),
    "material": ("material", "product", "article", "sku", "artikel", "produkt", "vara", "varor"),
    "country": ("country", "countries", "land", "länder", "region", "market", "marknad"),
    "sales_org": ("sales org", "sales organisation", "sales organization", "säljorganisation", "vkorg"),
    "month": ("month", "monthly", "månad", "per månad", "månatlig"),
    "quarter": ("quarter", "kvartal"),
    "year": ("year", "yearly", "annual", "per år", "årlig", "årsvis"),
    "week": ("week", "weekly", "vecka", "veckovis"),
    "day": ("daily", "per day", "dag", "dagligen", "per dag"),
}
MEASURES = ("open_items", "late_delivery", "margin", "order_count", "order_value", "revenue", "quantity")
GRAINS = ("day", "week", "month", "quarter", "year")

# A small glossary of the SAP fields the rules use (the SAP pack names the tables; this names the fields).
FIELDS = {
    ("VBRK", "NETWR"): "net value of the billing document (header)", ("VBRP", "NETWR"): "net value of the billing item",
    ("VBRK", "FKDAT"): "billing date", ("VBRK", "KUNAG"): "sold-to party", ("VBRK", "KUNRG"): "payer",
    ("VBRK", "WAERK"): "document currency", ("VBRP", "MATNR"): "material", ("VBRP", "FKIMG"): "billed quantity",
    ("VBAK", "NETWR"): "net value of the sales order (header)", ("VBAP", "NETWR"): "net value of the order item",
    ("VBAK", "ERDAT"): "order creation date", ("VBAK", "KUNNR"): "sold-to party", ("VBAK", "WAERK"): "document currency",
    ("VBAK", "VBELN"): "sales document number", ("VBAP", "MATNR"): "material", ("VBAP", "KWMENG"): "order quantity",
    ("VBAP", "VRKME"): "sales unit", ("VBAK", "VKORG"): "sales organisation", ("VBRK", "VKORG"): "sales organisation",
    ("KNA1", "LAND1"): "customer's country", ("VBEP", "EDATU"): "requested delivery date of the schedule line",
    ("LIKP", "WADAT_IST"): "actual goods issue date", ("LIKP", "LFDAT"): "planned delivery date",
    ("LIKP", "ERDAT"): "date the delivery was created (not when it left)", ("VBAP", "WAVWR"): "cost of the item",
    ("BSID", "ZFBDT"): "baseline date for payment of an open customer item", ("BSAD", "AUGDT"): "clearing date",
}


def _norm_words(text: str) -> str:
    return " " + re.sub(r"[^0-9a-zåäöéü\-]+", " ", str(text).lower()).strip() + " "


def _has(text: str, key: str) -> bool:
    return any(re.search(r"(?<![0-9a-zåäöéü])" + re.escape(w), text) for w in SYNONYMS[key])


# ------------------------------------------------------------------ the input ----------------------------------------

_BULLET = re.compile(r"^\s*(?:[-*•–·>]+|\d{1,3}[.)]|[a-zA-Z][.)]|\[[ xX]\])\s*")
_OWN_ID = re.compile(r"^\s*(?:R|K|REQ|KRAV)[- ]?(\d{1,3})\s*[:.)-]\s*", re.IGNORECASE)


def parse(text) -> list[dict]:
    """[{id, text}] from pasted text (one requirement per line; bullets, numbers and checkboxes are dropped; headings,
    blank lines and lines ending in ':' are skipped) or a list of strings. Ids are R1, R2 ... in the order given; an
    own id like "R7:" or "Krav 7:" is kept as the text's start but the id stays the position, so it is stable."""
    if isinstance(text, (list, tuple)):
        lines = [str(x) for x in text if x is not None]
    else:
        lines = str(text or "")[:MAX_INPUT_CHARS].splitlines()
    out = []
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or line.endswith(":") or set(line) <= set("-=*_ "):
            continue
        while _BULLET.match(line) and _BULLET.sub("", line, count=1) != line:     # "- [x] 2. ..." as well
            line = _BULLET.sub("", line, count=1)
        line = line.strip().strip("*_").strip()
        line = _OWN_ID.sub("", line).strip()
        if len(line) < 3:
            continue
        out.append(line[:MAX_LINE_CHARS])
        if len(out) >= MAX_REQUIREMENTS:
            break
    return [{"id": f"R{i}", "text": t} for i, t in enumerate(out, 1)]


def understand(text: str) -> dict:
    """{measure, measures, dims, grain, role, vague}: what the words say, by SYNONYMS alone."""
    t = _norm_words(text)
    measures = [m for m in MEASURES if _has(t, m)]
    if "revenue" in measures and "open_items" in measures:            # "unpaid invoices": the invoice is the open item
        measures.remove("revenue")
    if "revenue" in measures and "late_delivery" in measures:
        measures.remove("revenue")
    if "order_value" in measures and "order_count" in measures:
        measures.remove("order_value")
    dims = [d for d in ("customer", "material", "country", "sales_org") if _has(t, d)]
    role = "payer" if _has(t, "payer") else "ship_to" if _has(t, "ship_to") else "sold_to"
    if role != "sold_to" and "customer" not in dims:
        dims.insert(0, "customer")
    grain = next((g for g in GRAINS if _has(t, g)), None)
    return {"measure": measures[0] if measures else None, "measures": measures, "dims": dims, "grain": grain,
            "role": role, "sales_word": _has(t, "sales_word"), "vague": _has(t, "vague")}


# ------------------------------------------------------------------ the plan -----------------------------------------

class _Plan:
    """The plan's SAP tables by pack name, its columns and the counted evidence, for the rules below."""

    def __init__(self, plan: Plan, validation: dict | None):
        from . import privacy, sap_pack
        self.plan = plan
        self.by_pack: dict[str, str] = {}
        for t in plan.schema:
            found = sap_pack.pack_table(t.name)
            if found and found not in self.by_pack:
                self.by_pack[found] = t.name
        self.cols = {t.name: {c.upper(): c for c in t.column_names} for t in plan.schema}
        self.personal = {(t.lower(), c.lower()) for t, c in privacy.personal_columns(plan.schema)}
        self.validation = validation
        self.links = {}
        for r in (validation or {}).get("relationships") or []:
            self.links[(r["source"].lower(), tuple(c.upper() for c in r["columns"]), r["target"].lower())] = r
        self.keys = {k["table"].lower(): k for k in (validation or {}).get("keys") or []}
        self.levels = {(f["header"].lower(), f["line"].lower()): f
                       for f in ((validation or {}).get("amount_levels") or {}).get("findings") or []}

    def table(self, pack: str) -> str | None:
        return self.by_pack.get(pack)

    def col(self, pack: str, column: str) -> str | None:
        t = self.table(pack)
        if not t:
            return None
        c = self.cols[t].get(column.upper())
        if c and (t.lower(), c.lower()) in self.personal:
            return None
        return c

    def relationship(self, src_pack: str, tgt_pack: str, first: str | None = None):
        s, t = self.table(src_pack), self.table(tgt_pack)
        if not s or not t:
            return None
        found = [r for r in self.plan.relationships if r.source == s and r.target == t]
        if first:
            found = [r for r in found if any(c.upper() == first.upper() for c in r.source_cols)] or found
        return found[0] if found else None

    def link_evidence(self, r) -> dict:
        """{state: checked | failed | not_checked, rows, orphans, verdict} for one relationship: counts only."""
        v = self.links.get((r.source.lower(), tuple(c.upper() for c in r.source_cols), r.target.lower()))
        on = " AND ".join(f"{r.source}.{a} = {r.target}.{b}" for a, b in zip(r.source_cols, r.target_cols))
        base = {"join": f"{r.source} → {r.target}", "on": on, "rule": r.rule}
        if self.validation is None:
            return {**base, "state": "not_checked", "verdict": "not counted: validate=false"}
        if v is None or v.get("orphans") is None:
            return {**base, "state": "not_checked", "verdict": (v or {}).get("verdict") or "not counted in this call"}
        n = int(v.get("orphans") or 0)
        return {**base, "state": "failed" if n else "checked", "rows": v.get("rows_with_value"), "orphans": n,
                "verdict": v.get("verdict")}

    def key_evidence(self, table: str) -> dict:
        k = self.keys.get(table.lower())
        cols = list((self.plan.keys.get(table) or ([], ""))[0])
        if self.validation is None or k is None:
            return {"table": table, "key": cols, "state": "not_checked"}
        ok = int(k.get("nulls") or 0) == 0 and k.get("distinct") == k.get("rows")
        return {"table": table, "key": cols, "state": "checked" if ok else "failed", "verdict": k.get("verdict")}


# ------------------------------------------------------------------ the rules ----------------------------------------
# One dataset per measure: the SAP header and item tables, the amount, the date and the customer's field per role.
DATASETS = {
    "revenue": {"header": "VBRK", "item": "VBRP", "amount": "NETWR", "currency": "WAERK", "date": "FKDAT",
                "customer": {"sold_to": "KUNAG", "payer": "KUNRG"}, "what": "invoiced net value (billing documents)",
                "rule": "RQ-M1"},
    "order_value": {"header": "VBAK", "item": "VBAP", "amount": "NETWR", "currency": "WAERK", "date": "ERDAT",
                    "customer": {"sold_to": "KUNNR"}, "what": "net value of the sales orders", "rule": "RQ-M2"},
    "order_count": {"header": "VBAK", "item": "VBAP", "count": "VBELN", "date": "ERDAT",
                    "customer": {"sold_to": "KUNNR"}, "what": "number of sales orders", "rule": "RQ-M3"},
    "quantity": {"header": "VBAK", "item": "VBAP", "quantity": "KWMENG", "unit": "VRKME", "date": "ERDAT",
                 "customer": {"sold_to": "KUNNR"}, "what": "ordered quantity (sales order items)", "rule": "RQ-M4"},
}
GRAIN_SQL = {"month": 6, "year": 4, "day": 8}


def _period(expr: str, grain: str | None) -> str | None:
    """The period of a date, a datetime or SAP's 'YYYYMMDD' text as text: the same in T-SQL, Spark SQL and SQLite."""
    n = GRAIN_SQL.get(grain or "")
    if n:
        return f"SUBSTRING(REPLACE(CAST({expr} AS VARCHAR(30)), '-', ''), 1, {n})"
    return None


def _missing(what: str, pack: str, column: str | None = None, alt: str = "") -> dict:
    from . import sap_pack
    en = (sap_pack.load("sap")["tables"].get(pack) or {}).get("en", "")
    field = f"{pack}.{column}" if column else pack
    meaning = FIELDS.get((pack, column or ""), en)
    return {"field": field, "what": meaning or what, "why": what, **({"or": alt} if alt else {})}


def _question(req: dict, u: dict, ask: str, rule: str) -> dict:
    return {**req, "state": "unclear", "question": ask, "understood": _said(u), "rule": rule}


def _said(u: dict) -> str:
    parts = [u["measure"] or "no measure"]
    if u["dims"]:
        parts.append("by " + ", ".join(u["dims"]))
    if u["grain"]:
        parts.append("per " + u["grain"])
    return " ".join(parts)


def _one(req: dict, P: _Plan, schema: str) -> dict:
    u = understand(req["text"])
    m = u["measure"]
    if len(u["measures"]) > 1:
        return _question(req, u, f"This line asks for {' and '.join(u['measures'])}. Which one first? Write one measure "
                                 "per line and paste the list again.", "RQ-U1")
    if m is None and u["sales_word"]:
        return _question(req, u, "Sales as invoiced revenue (billing documents, VBRK) or as order value (sales orders, "
                                 "VBAK)? Write 'revenue' or 'order value' and paste the list again.", "RQ-U2")
    if m is None and u["vague"]:
        return _question(req, u, "Best or top by which measure: revenue, order value, number of orders or quantity? "
                                 "And over which period?", "RQ-U3")
    if m is None:
        return _question(req, u, "Which number should this show (revenue, order value, number of orders, quantity, "
                                 "late deliveries or unpaid invoices), and per what?", "RQ-U4")
    if m == "open_items":
        return _open_items(req, u, P)
    if m == "late_delivery":
        return _late(req, u, P, schema)
    if m == "margin":
        return {**req, "state": "missing", "understood": _said(u), "rule": "RQ-X3",
                "missing": [_missing("a margin needs a cost per item", "VBAP", "WAVWR",
                                     "the pricing conditions (PRCD_ELEMENTS or KONV) with their cost condition")],
                "say": "A margin needs the cost of what was sold; the SAP demo has net values only."}
    return _amounts(req, u, P, schema, m)


def _open_items(req: dict, u: dict, P: _Plan) -> dict:
    has = [t for t in ("BSID", "BSAD", "BSEG", "ACDOCA") if P.table(t)]
    if not has:
        return {**req, "state": "missing", "understood": _said(u), "rule": "RQ-X1",
                "missing": [_missing("open customer items say which invoices are unpaid", "BSID",
                                     alt="BSAD (cleared items) with BSEG.AUGDT, or ACDOCA with its clearing date; in "
                                         "S/4HANA the open items are in ACDOCA")],
                "say": "Billing documents say what was invoiced, not what was paid: the payments are in accounting."}
    return {**req, "state": "unclear", "understood": _said(u), "rule": "RQ-X1b", "tables": has,
            "question": "Unpaid on which date: today, or at the end of each month? And overdue from the baseline date "
                        "(ZFBDT) plus the payment terms, or from the invoice date?"}


def _late(req: dict, u: dict, P: _Plan, schema: str) -> dict:
    need = []
    if not P.table("LIKP"):
        need.append(_missing("deliveries", "LIKP"))
    if not P.table("VBEP"):
        need.append(_missing("the requested date is on the schedule line", "VBEP"))
    elif not P.col("VBEP", "EDATU"):
        need.append(_missing("the requested date", "VBEP", "EDATU"))
    if P.table("LIKP") and not P.col("LIKP", "WADAT_IST"):
        need.append(_missing("when the goods actually left; LIKP.ERDAT is when the delivery was created", "LIKP",
                             "WADAT_IST", "LIKP.LFDAT (planned delivery date) says when it was due, not when it left"))
    if need:
        return {**req, "state": "missing", "understood": _said(u), "rule": "RQ-X2", "missing": need,
                "say": "A late delivery compares the date the customer asked for with the date the goods left."}
    joins = [P.relationship("LIPS", "LIKP", "VBELN"), P.relationship("LIPS", "VBAP", "VGBEL"), P.relationship("VBEP", "VBAP")]
    if not all(joins):
        return {**req, "state": "missing", "understood": _said(u), "rule": "RQ-X2",
                "missing": [_missing("the delivery items' link to the order items", "LIPS", "VGBEL")]}
    ev = [P.link_evidence(r) for r in joins]
    lk, li, ep = (lambda c: P.col("LIKP", c)), (lambda c: P.col("LIPS", c)), (lambda c: P.col("VBEP", c))
    shipped, requested = f"REPLACE(CAST(d.{qi(lk('WADAT_IST'))} AS VARCHAR(30)), '-', '')", "REPLACE(CAST(e.requested AS VARCHAR(30)), '-', '')"
    select, group = [f"d.{qi(lk('MANDT'))} AS client"], [f"d.{qi(lk('MANDT'))}"]
    if "customer" in u["dims"] and lk("KUNAG"):
        select.append(f"d.{qi(lk('KUNAG'))} AS customer")
        group.append(f"d.{qi(lk('KUNAG'))}")
    if u["grain"] in GRAIN_SQL:
        per = _period(f"d.{qi(lk('WADAT_IST'))}", u["grain"])
        select.append(f"{per} AS {u['grain']}")
        group.append(per)
    r_li, r_ep = joins[1], joins[2]
    on_d = " AND ".join(f"l.{qi(x)} = d.{qi(y)}" for x, y in zip(joins[0].source_cols, joins[0].target_cols))
    on_e = " AND ".join(f"l.{qi(x)} = e.{qi(y)}" for x, y in zip(r_li.source_cols, r_li.target_cols))
    ecols = ", ".join(qi(c) for c in r_ep.source_cols)
    sql = (f"-- {req['id']}: {req['text']}\n-- delivery items that left after the first requested date; rules RQ-M5 "
           f"({RULE_VERSION}); no row value here\n"
           f"SELECT {', '.join(select)}, COUNT(*) AS late_items, COUNT(DISTINCT d.{qi(lk('VBELN'))}) AS deliveries_with_late_items\n"
           f"FROM {_t(schema, P.table('LIPS'))} AS l\nJOIN {_t(schema, P.table('LIKP'))} AS d ON {on_d}\n"
           f"JOIN (SELECT {ecols}, MIN({qi(ep('EDATU'))}) AS requested FROM {_t(schema, P.table('VBEP'))} GROUP BY {ecols}) AS e ON {on_e}\n"
           f"WHERE {shipped} > {requested}\nGROUP BY {', '.join(group)}")
    traps = ["An order item can have several schedule lines (VBEP): the query compares with the first requested date "
             "(MIN(EDATU)) per item, so no line is counted twice."]
    failed = [e for e in ev if e["state"] == "failed"]
    traps_shown = [f"{e['orphans']} row(s) of {e['join']} point at nothing: the join leaves them out." for e in failed]
    return {**req, "state": "trap" if failed else "answerable", "understood": _said(u), "rule": "RQ-M5",
            "measure": "late delivery items", "joins": ev, "traps": traps_shown, "notes": traps,
            "key": P.key_evidence(P.table("LIPS")), "checked": all(e["state"] != "not_checked" for e in ev),
            "columns": ["LIKP.WADAT_IST (actual goods issue date)", "VBEP.EDATU (requested delivery date)"],
            "tables": sorted(P.table(t) for t in ("LIKP", "LIPS", "VBAP", "VBEP")), "query": sql}


def _amounts(req: dict, u: dict, P: _Plan, schema: str, m: str) -> dict:
    ds = DATASETS[m]
    h, i = P.table(ds["header"]), P.table(ds["item"])
    line_level = "material" in u["dims"] or m == "quantity"
    need = []
    if not h:
        need.append(_missing(ds["what"], ds["header"]))
    if line_level and not i:
        need.append(_missing("per material needs the items", ds["item"]))
    if need:
        return {**req, "state": "missing", "understood": _said(u), "rule": ds["rule"], "missing": need}
    if u["role"] == "ship_to":
        return _question(req, u, "The ship-to party is on the delivery (LIKP.KUNNR) and in the partner rows (VBPA, "
                                 "PARVW WE), not on this document's header. Use the sold-to party instead, or the "
                                 "deliveries?", "RQ-U5")
    cust_col = ds["customer"].get(u["role"])
    if "customer" in u["dims"] and not cust_col:
        return _question(req, u, f"The {u['role'].replace('_', '-')} of a sales order is a partner row (VBPA, PARVW "
                                 "RG), not a header field. Use the sold-to party (VBAK.KUNNR) instead?", "RQ-U6")
    out = {**req, "understood": _said(u), "rule": ds["rule"], "measure": ds["what"]}
    a, b = "h", "i"
    fact, fact_pack = (i, ds["item"]) if line_level else (h, ds["header"])
    alias = b if line_level else a
    select, group, cols_used, missing, traps, joins = [], [], [], [], [], []
    hc = lambda c: P.col(ds["header"], c)                          # noqa: E731
    ic = lambda c: P.col(ds["item"], c)                            # noqa: E731
    client = hc("MANDT")
    if client:
        select.append(f"{a}.{qi(client)} AS client")
        group.append(f"{a}.{qi(client)}")
    if "customer" in u["dims"]:
        c = hc(cust_col)
        if not c:
            missing.append(_missing("the customer", ds["header"], cust_col))
        else:
            select.append(f"{a}.{qi(c)} AS customer")
            group.append(f"{a}.{qi(c)}")
            cols_used.append(f"{ds['header']}.{cust_col} ({FIELDS.get((ds['header'], cust_col), 'customer')})")
            if u["role"] == "sold_to" and m == "revenue" and hc("KUNRG"):
                traps.append("Customer here is the sold-to party (VBRK.KUNAG); the payer (VBRK.KUNRG) can be another "
                             "customer. Write 'payer' in the requirement to use the payer.")
    if "country" in u["dims"]:
        r = P.relationship(ds["header"], "KNA1", cust_col or "KUNNR")
        land = P.col("KNA1", "LAND1")
        if not r or not land:
            missing.append(_missing("the customer's country", "KNA1", "LAND1"))
        else:
            joins.append(P.link_evidence(r))
            select.append(f"k.{qi(land)} AS country")
            group.append(f"k.{qi(land)}")
            cols_used.append("KNA1.LAND1 (customer's country)")
    if "sales_org" in u["dims"]:
        c = hc("VKORG")
        if not c:
            missing.append(_missing("the sales organisation", ds["header"], "VKORG"))
        else:
            select.append(f"{a}.{qi(c)} AS sales_org")
            group.append(f"{a}.{qi(c)}")
    if "material" in u["dims"]:
        c = ic("MATNR")
        if not c:
            missing.append(_missing("the material", ds["item"], "MATNR"))
        else:
            select.append(f"{b}.{qi(c)} AS material")
            group.append(f"{b}.{qi(c)}")
            cols_used.append(f"{ds['item']}.MATNR (material)")
    if u["grain"]:
        d = hc(ds["date"])
        per = _period(f"{a}.{qi(d)}", u["grain"]) if d else None
        if not d:
            missing.append(_missing("the date", ds["header"], ds["date"]))
        elif per is None:
            return _question(req, u, f"Per {u['grain']}: Krusgraph's rules group by day, month or year. Which one?",
                             "RQ-U7")
        else:
            select.append(f"{per} AS {u['grain']}")
            group.append(per)
            cols_used.append(f"{ds['header']}.{ds['date']} ({FIELDS.get((ds['header'], ds['date']), 'date')})")
    if m in ("revenue", "order_value"):
        amt = (ic if line_level else hc)(ds["amount"])
        cur = hc(ds["currency"])
        if not amt:
            missing.append(_missing(ds["what"], fact_pack, ds["amount"]))
        else:
            select.insert(0, f"SUM({alias}.{qi(amt)}) AS net_value")
            cols_used.insert(0, f"{fact_pack}.{ds['amount']} ({FIELDS.get((fact_pack, ds['amount']), 'amount')})")
            if cur:
                select.append(f"{a}.{qi(cur)} AS currency")
                group.append(f"{a}.{qi(cur)}")
        if line_level:
            lv = P.levels.get((h.lower(), i.lower()))
            how = ""
            if lv and lv.get("rows_per_header"):
                rp = lv["rows_per_header"]
                how = (f" In the data, {ds['item']} has {rp.get('avg_lines')} rows per {ds['header']} row on average "
                       f"and up to {rp.get('max_lines')}.")
            traps.insert(0, f"{ds['header']}.{ds['amount']} is the whole document's value and repeats on every "
                            f"{ds['item']} row: summing it per material counts each document once per line. Sum "
                            f"{ds['item']}.{ds['amount']} instead (done in the query below).{how}")
    elif m == "order_count":
        c = hc(ds["count"])
        select.insert(0, f"COUNT(DISTINCT {a}.{qi(c)}) AS orders")
        cols_used.insert(0, f"{ds['header']}.VBELN (sales document number)")
    elif m == "quantity":
        q, unit = ic(ds["quantity"]), ic(ds["unit"])
        if not q:
            missing.append(_missing("the quantity", ds["item"], ds["quantity"]))
        else:
            select.insert(0, f"SUM({b}.{qi(q)}) AS quantity")
            cols_used.insert(0, f"{ds['item']}.{ds['quantity']} (order quantity)")
            if unit:
                select.append(f"{b}.{qi(unit)} AS unit")
                group.append(f"{b}.{qi(unit)}")
                traps.append("Quantities are in different units (VRKME): the query sums per unit; never add pieces "
                             "and kilograms.")
    if missing:
        return {**out, "state": "missing", "missing": missing}
    frm = f"FROM {qi(schema)}.{qi(fact)} AS {alias}" if schema else f"FROM {qi(fact)} AS {alias}"
    if line_level:
        r = P.relationship(ds["item"], ds["header"], "VBELN")
        if not r:
            return {**out, "state": "missing", "missing": [_missing("the items' link to their header", ds["item"])]}
        e = P.link_evidence(r)
        joins.insert(0, e)
        on = " AND ".join(f"{b}.{qi(x)} = {a}.{qi(y)}" for x, y in zip(r.source_cols, r.target_cols))
        frm += f"\nJOIN {_t(schema, h)} AS {a} ON {on}"
        if e["state"] == "failed":
            traps.append(f"{e['orphans']} {ds['item']} row(s) point at no {ds['header']} row ({e['verdict']}): the "
                         "join leaves them out. In silver they go to quarantine with the reason; decide in the "
                         "review whether that is right.")
    if any(x.startswith("k.") for x in group):
        r = P.relationship(ds["header"], "KNA1", cust_col or "KUNNR")
        on = " AND ".join(f"{a}.{qi(x)} = k.{qi(y)}" for x, y in zip(r.source_cols, r.target_cols))
        frm += f"\nJOIN {_t(schema, P.table('KNA1'))} AS k ON {on}"
        if joins and joins[-1]["state"] == "failed":
            traps.append(f"{joins[-1]['orphans']} {ds['header']} row(s) name a customer that is not in KNA1: the join "
                         "leaves them out.")
    sql = (f"-- {req['id']}: {req['text']}\n-- {ds['what']}; rules {ds['rule']} ({RULE_VERSION}); no row value here\n"
           f"SELECT {', '.join(select)}\n{frm}\nGROUP BY {', '.join(group)}")
    out["key"] = P.key_evidence(fact)
    out["joins"] = joins
    out["columns"] = cols_used
    out["traps"] = traps if any("repeats" in t or "point at no" in t or "units" in t or "name a customer" in t
                                for t in traps) else []
    out["notes"] = [t for t in traps if t not in out["traps"]]
    out["state"] = "trap" if out["traps"] else "answerable"
    out["tables"] = sorted({fact, h} | ({P.table("KNA1")} if "country" in u["dims"] else set()))
    out["query"] = sql
    unchecked = [j for j in joins if j["state"] == "not_checked"] + ([out["key"]] if out["key"]["state"] == "not_checked" else [])
    if unchecked:
        out["checked"] = False
        out["notes"].append("Not counted yet: run validate_plan (or this tool with validate=true) before trusting it.")
    else:
        out["checked"] = True
    return out


def _t(schema: str, table: str) -> str:
    return f"{qi(schema)}.{qi(table)}" if schema else qi(table)


# ------------------------------------------------------------------ the answer ---------------------------------------

def draft(plan: Plan, text, validation: dict | None = None, schema: str = "") -> dict:
    """The answer for a pasted list: each requirement's state with its evidence, the questions, and what it feeds."""
    reqs = parse(text)
    P = _Plan(plan, validation)
    schema = schema or getattr(plan.schema, "schema", "") or ""
    sap = bool(P.by_pack)
    if not reqs:
        return {"rule_version": RULE_VERSION, "requirements": [], "counts": {s: 0 for s in STATES},
                "ask": "Paste the requirements as a list, one per line (for example from a Copilot Workspace summary)."}
    out = []
    for r in reqs:
        if not sap:
            u = understand(r["text"])
            out.append({**r, "state": "missing", "understood": _said(u), "rule": "RQ-X0",
                        "missing": [{"field": "SAP order-to-cash tables (VBRK, VBAK, LIKP ...)",
                                     "what": "requirements_draft's rules know the SAP pack's order to cash only",
                                     "why": "no table of this schema is one the SAP pack recognises"}]})
            continue
        out.append(_one(r, P, schema))
    counts = {s: sum(1 for x in out if x["state"] == s) for s in STATES}
    ok = [x for x in out if x["state"] in ("answerable", "trap") and x.get("query")]
    tables = sorted({t for x in ok for t in x.get("tables") or [] if t})
    feeds = {
        "gold_views_draft": {"tables": tables, "requirements": [x["id"] for x in ok]},
        "semantic_model_draft": {"tables": tables, "measures": [
            {"requirement": x["id"], "measure": x.get("measure") or x["understood"],
             "rule": "sum the item amount" if any("repeats" in t for t in x.get("traps") or []) else "sum once per document"}
            for x in ok if x.get("measure")]},
        "create_data_agent": {"example_queries": [{"requirement": x["id"], "question": x["text"], "query": x["query"]}
                                                  for x in ok]},
    }
    questions = [{"requirement": x["id"], "question": x["question"]} for x in out if x["state"] == "unclear"]
    checked = validation is not None
    return {"rule_version": RULE_VERSION, "checked": checked, "requirements": out, "counts": counts,
            "questions": questions, "feeds": feeds, "approval": APPROVAL,
            "never": "No row value is read or returned: the evidence is counts from validate_plan; the queries name "
                     "columns only. No AI: fixed word lists and the SAP pack's names decide."}


def example_queries(answer: dict) -> list[dict]:
    """create_data_agent's extra example queries from a draft: {question, query}, the query starting with its id."""
    return [{"question": x["question"], "query": x["query"]}
            for x in (answer.get("feeds") or {}).get("create_data_agent", {}).get("example_queries") or []]


def card(answer: dict) -> dict:
    """The card's words (mcp_apps_words.card reads a tool's own kg_card): one result line, up to five lines, the
    requirements behind Show as notes. Plain words, the counts and the ids only."""
    c = answer.get("counts") or {}
    reqs = answer.get("requirements") or []
    if not reqs:
        return {"title": "Requirements", "result": answer.get("ask") or "No requirement was found in the text."}
    n = len(reqs)
    parts = [f"{c.get('answerable', 0)} answerable now", f"{c.get('trap', 0)} with a trap",
             f"{c.get('missing', 0)} missing data", f"{c.get('unclear', 0)} unclear"]
    result = f"{n} {'requirement' if n == 1 else 'requirements'}: " + ", ".join(parts) + "."
    label = {"answerable": "Answerable now", "trap": "Answerable, with a trap", "missing": "Missing data",
             "unclear": "Unclear"}
    lines = []
    for x in reqs[:5]:
        why = ""
        if x["state"] == "missing":
            why = "needs " + ", ".join(m["field"] for m in x.get("missing") or [])
        elif x["state"] == "unclear":
            why = x.get("question", "")
        elif x["state"] == "trap":
            why = (x.get("traps") or [""])[0].split(": ")[0]
        else:
            why = "key and joins counted" if x.get("checked") else "not counted yet"
        lines.append(f"{x['id']} {label[x['state']]}: {x['text']}" + (f". {why}" if why else ""))
    notes = [{"line": f"{x['id']}: {x['text']}",
              "items": ([f"State: {label[x['state']]}"] + [f"Column: {k}" for k in x.get("columns") or []]
                        + [f"Join {j['join']}: {j['state'].replace('_', ' ')}" for j in x.get("joins") or []]
                        + [f"Trap: {t}" for t in x.get("traps") or []]
                        + [f"Missing: {m['field']} ({m['what']})" for m in x.get("missing") or []]
                        + ([f"Question: {x['question']}"] if x.get("question") else []))}
             for x in reqs]
    return {"title": "Requirements", "result": result, "lines": lines, "notes": notes}


# ------------------------------------------------------------------ the next steps (the card's buttons) ----------------

def next_steps(call: dict, answer: dict) -> list[dict]:
    """At most four steps, the first primary, each naming the requirement ids it serves. Drafts and dry runs only: a
    card's buttons run the read and draft tools (gold_views_draft, semantic_model_draft); the data agent's dry run is a
    sentence for the chat, which Claude runs as a dry run. On the sample the one step is to run it on your own data."""
    from .next_rules import _as_sentence, _step
    from .start_flow import build_names
    if not isinstance(answer, dict) or answer.get("error") or not answer.get("requirements"):
        return []
    call = {k: v for k, v in (call or {}).items() if k != "ctx"}
    ok = [x["id"] for x in answer["requirements"] if x["state"] in ("answerable", "trap") and x.get("query")]
    asks = answer.get("questions") or []
    ids = ", ".join(ok)
    if call.get("sample") or not call.get("workspace") or not call.get("source"):
        return [{"label": "Run it on my lakehouse", "primary": True,
                 "why": "The same list against your own SAP tables: names and counts only, nothing is created.",
                 "say": "Run requirements_draft on my lakehouse with the same requirements list.",
                 "ask": "Run requirements_draft on my lakehouse with the same requirements list."}]
    base = {k: call[k] for k in ("workspace", "source", "schema") if call.get(k)}
    tables = (answer.get("feeds") or {}).get("gold_views_draft", {}).get("tables") or []
    out = []
    if answer.get("checked") is False:
        out.append(_step("Check against the rows", "validate_plan", base,
                         "Counts each key and link the requirements use first: nothing is built on a guess."))
    if ok:
        out.append(_step(f"Draft the gold views for {ids}", "gold_views_draft", {**base, "tables": tables},
                         f"A draft over the tables {ids} use: SQL to read, nothing is created."))
        out.append(_step(f"Draft the semantic model for {ids}", "semantic_model_draft", {**base, "tables": tables},
                         "A draft in TMDL over the same tables: nothing is created."))
        name = build_names(base.get("source"), base.get("schema"))["create_data_agent"]
        agent = _step(f"Data agent with {ids} as examples (dry run)", "create_data_agent",
                      {**base, "name": name, "requirements": "\n".join(x["text"] for x in answer["requirements"]),
                       "validate": True, "dry_run": True},
                      "A dry run: each answerable requirement becomes an example query that starts with its id.")
        out.append(_as_sentence(agent))
    if asks:
        q = asks[0]
        out.append({"label": f"Answer the question for {q['requirement']}", "why": q["question"],
                    "say": f"For {q['requirement']}: {q['question']}", "ask": f"For {q['requirement']}: {q['question']}"})
    out = out[:4]
    if out:
        out[0] = {**out[0], "primary": True}
    return out
