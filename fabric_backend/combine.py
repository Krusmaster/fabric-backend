"""SM7 (docs/SMOOTH/COMBINE-SOURCES.md): several sources in one data product, matched by rules with counts.

A plan over several schemas of one item (SM5, `schema="crm+sap"`) keeps each source apart: no link is guessed across
schemas. This module proposes how the sources' customers are the same customers, counts it on the rows, and, once the
person has accepted a match, drafts the conformed gold and the model over it. No AI, no fuzzy matching, no row value in
any answer: names, rules and counts.

**Which tables.** The party tables are the ones the knowledge packs map to DP1's catalog products `customer` (SAP's
KNA1, business key `tenant_id` + `customer_number`) and `crm_account` (Salesforce's Account, key `account_id`), as
master (fabric_backend/data_products/mapping.yaml). One per schema; a schema without one takes no part.

**The rules** (COMBINE-SOURCES.md section 2), each a pair (column on one side -> the other side's customer number):

- M0 declared: a column of one party table whose name names the other source (its schema or pack name, as a word) and
  an identifier word (no, nr, number, id, key), or holds the other side's key column name: `crm.Account.SAP_Customer_No__c`
  -> `sap.KNA1.KUNNR`. Certainty 1.0 once the count holds.
- M1 same identifier: a column on each side named as the same official identifier (VAT id, organisation number, DUNS,
  GLN). Values compared after fixed steps: trimmed, upper case, spaces, dashes, dots and slashes removed, a leading
  two-letter country prefix removed. Certainty 0.9 once the count holds.
- M2 counted overlap: a key-shaped column of one party table (its name has an identifier word, it is no link of its
  own plan and no code-list column) against the other side's customer number. 0.9 with at least 95 % of the filled
  values found and at least 50 distinct values, else 0.6.
- M4 name only (Name vs NAME1) is never used: names are not identifiers.

M0 and M2 compare values cast to text, trimmed, case folded and with leading zeros stripped (the S1 steps of
propose.normal_forms). When the side pointed at has a tenant column (SAP's client, MANDT) and the other side has none,
the match runs within the tenant with the most rows; the other tenants' rows stay, counted as "only in" that source.

**The counts.** Two statements per candidate on the one connection (both schemas are in it): the rows of the
referencing side, how many hold a value, how many find the other side as written and after normalising; and the rows
of the side pointed at, how many are found, and how many are found by more than one row. At most MAX_CANDIDATES
candidates are counted. A candidate holds when at least HOLDS of its filled values are found.

**The decision** is the person's, one tap: the item `match:<from table>.<column>><to table>.<column>`, accepted or
rejected, kept in the flow state (flow_state.py) like a link. Nothing is joined on a match that is not accepted.

**What an accepted match drafts** (`gold`): `gold.xref_customer` (one row per source row: `customer_key`, each side's
key columns, `match_rule`, `matched_on`, `only_in`), `gold.dim_customer` (one row per conformed customer, the side
pointed at as master: each of its rows is one customer, and the other side's rows that match it join that customer, so
no source row ever has two keys and no total doubles), and one view per transaction table that points at a party table
(`gold.fact_<source>_<product>`), re-keyed to `customer_key`, at its own grain. The model (`model_schema`) holds
dim_customer and the facts, each fact related to dim_customer only, never to another fact.

Not in SM7 (issue in the PR): creating the schema shortcuts (G5), the conformed code-list dimensions (M3), the pipeline
step that runs the gold SQL, the ontology and agent over it, and the person's choice of master and properties.

**ON1 (SAP and Dynamics 365, issue #152).** The same rules match two concepts, each on its own (`concept`):
`customer` (the party tables above: SAP's KNA1, Dataverse's `account`, Business Central's `Customer`) and `product`
(DP1's `product` masters: SAP's MARA, Dataverse's `product`, Business Central's `Item`). Two additions, both by name:

- Dataverse names its columns in lower case without separators (`accountnumber`, `productnumber`,
  `new_sapcustomerno`). In a column name with no capital letter, a word that ends in number, no, nr or num is read as
  its head and that identifier word (`accountnumber` -> account + number), and a head that starts with the other
  source's name is that name (`sapcustomerno` names sap: M0). GUID lookups end in `id` and are never split.
- The columns Link to Fabric adds (`Id`, `IsDelete`, `SinkCreatedOn`, `SinkModifiedOn`, `versionnumber`;
  dataverse_meta.SYSTEM_COLUMNS) are never a candidate: `Id` is the lake's row id, not a customer number.

**Ambiguous rows** are counted, never resolved: `ambiguous` is the number of referencing rows whose normalised value
is also held by another referencing row, or finds more than one row on the other side. `matched` is `found` less
`ambiguous`. Accepting the match stays the person's tap, with the ambiguous count in its evidence.
"""
from __future__ import annotations

import functools
import re

from .dialects import DATABRICKS, TSQL, Dialect
from .schema import Column, Schema, Table

PARTY = ("customer", "crm_account")             # DP1 catalog products that are a party who buys
CONCEPTS = {"customer": PARTY, "product": ("product",)}   # ON1: what is matched across sources, by DP1 product (master)
FACT_KIND, FACT_ROLE = "transaction", "header"
ID_WORDS = {"no", "nr", "number", "num", "id", "key"}
TAIL_WORDS = ("number", "num", "nr", "no")      # ON1: the tails read off a lower-case compound name; never "id"
CODE_WORDS = {"currency", "country", "iso", "language", "lang", "unit"}   # code lists are M3, never a customer match
IDENTIFIERS = {                                   # M1: official identifiers, by the column's name (words joined)
    "vat id": ("vat", "vatid", "vatno", "vatnumber", "stceg", "ustid", "vatregistrationnumber", "taxid"),
    "organisation number": ("orgnr", "orgno", "orgnumber", "organisationnumber", "organizationnumber", "regno",
                            "registrationnumber", "companynumber", "corporateid"),
    "DUNS number": ("duns", "dunsno", "dunsnumber"),
    "GLN": ("gln", "globallocationnumber"),
}
CERTAINTY = {"M0": 1.0, "M1": 0.9, "M2": 0.6}
ORDER = ("M0", "M1", "M2")
HOLDS = 0.95
M2_DISTINCT = 50
MAX_CANDIDATES = 4
PREFIX = "match:"


def _words(name: str) -> list[str]:
    """'SAP_Customer_No__c' -> ['sap', 'customer', 'no', 'c']; 'AccountNumber' -> ['account', 'number']."""
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(name))
    return [w for w in re.split(r"[^0-9a-z]+", spaced.lower()) if w]


def _rule_words(name: str, system: set[str] = frozenset()) -> set[str]:
    """The words the rules read in a column name. ON1: a name with no capital letter (Dataverse's logical names) also
    gives each compound word's head and identifier tail (`accountnumber` -> account, number), and a head that starts
    with a source's name gives that name (`sapcustomerno` -> sap)."""
    words = _words(name)
    out = set(words)
    if str(name) != str(name).lower():
        return out
    for w in words:
        tail = next((t for t in TAIL_WORDS if w.endswith(t) and len(w) > len(t) + 1), None)
        if tail is None:
            continue
        head = w[:-len(tail)]
        out |= {head, tail}
        out |= {x for x in system if head.startswith(x) and len(head) > len(x)}
    return out


def _system_column(name: str) -> bool:
    """The columns Link to Fabric adds to every Dataverse table (dataverse_meta.SYSTEM_COLUMNS): never a match key."""
    from .dataverse_meta import SYSTEM_COLUMNS
    return str(name).lower() in {c.lower() for c in SYSTEM_COLUMNS}


def _joined(name: str) -> str:
    w = _words(name)
    if len(w) > 1 and w[-1] == "c":                                  # Salesforce's custom field suffix (__c)
        w = w[:-1]
    return "".join(w)


def identifier_of(column: str) -> str | None:
    """M1: which official identifier a column is named as, or None."""
    j = _joined(column)
    for kind, names in IDENTIFIERS.items():
        if j in names or any(j.endswith(n) and len(n) >= 4 for n in names):
            return kind
    return None


# ------------------------------------------------------------------------------------------------ the party tables
@functools.lru_cache(maxsize=1)
def _dp_mapping() -> dict:
    """DP1's mapping.yaml, read once per process (read-only here)."""
    from . import data_product_catalog as dpc
    return dpc.load_mapping()


@functools.lru_cache(maxsize=1)
def _dp_products() -> dict:
    """DP1's catalog products by id, read once per process (read-only here)."""
    from . import data_product_catalog as dpc
    return dpc.products()


def _dp_tables(pack: str) -> dict:
    from . import data_product_catalog as dpc
    return dpc.tables(pack, _dp_mapping())


def _schema_of(key: str) -> str:
    return key.split(".", 1)[0] if "." in key else ""


def _col(t: Table, name: str) -> str | None:
    return next((c.name for c in t.columns if c.name.lower() == str(name).lower()), None)


def _entries(plan) -> dict[str, list[dict]]:
    """{table key: DP1 mapping entries} for a plan over several schemas: each schema's pack (plan.pack.by_schema)."""
    pk = plan.pack or {}
    by_schema = pk.get("by_schema") or {}
    names = pk.get("tables") or {}
    mapped: dict[str, dict] = {}
    out: dict[str, list[dict]] = {}
    for key, pack_name in names.items():
        pack = by_schema.get(_schema_of(key)) or pk.get("pack")
        if not pack:
            continue
        if pack not in mapped:
            try:
                mapped[pack] = {k.upper(): v for k, v in _dp_tables(pack).items()}
            except KeyError:
                mapped[pack] = {}
        hit = mapped[pack].get(str(pack_name).upper())
        if hit:
            out[key] = hit
    return out


def parties(plan, concept: str = "customer") -> dict[str, dict]:
    """{schema: {table, product, number, tenant, key}} per schema with a master table of the concept (DP1's key
    mapping): the party tables for `customer` (SM7), the product masters for `product` (ON1)."""
    wanted = CONCEPTS[concept]
    out: dict[str, dict] = {}
    for key, entries in _entries(plan).items():
        for e in entries:
            if e.get("product") not in wanted or e.get("role") != "master":
                continue
            s = _schema_of(key)
            t = plan.schema[key]
            gen = e.get("key") or {}
            number_gen = next((g for g in gen if g != "tenant_id"), None)
            number = _col(t, gen.get(number_gen, "")) if number_gen else None
            tenant = _col(t, gen.get("tenant_id", "")) if gen.get("tenant_id") else None
            if s and number and s not in out:
                out[s] = {"table": key, "product": e["product"], "number": number, "tenant": tenant,
                          "key": [c for c in (tenant, number) if c],
                          "title": _dp_products().get(e["product"], {}).get("title", e["product"])}
    return out


def facts(plan, party: dict[str, dict]) -> list[dict]:
    """The transaction tables (DP1 kind transaction, role header) that point at a party table, one link each (the
    plan's first): [{table, schema, product, name, cols, party_cols}]."""
    kinds = {p: v.get("kind") for p, v in _dp_products().items()}
    entries = _entries(plan)
    out, taken = [], set()
    targets = {v["table"]: s for s, v in party.items()}
    for r in plan.relationships:
        if r.target not in targets or r.source in {f["table"] for f in out}:
            continue
        e = next((x for x in entries.get(r.source, []) if kinds.get(x.get("product")) == FACT_KIND
                  and x.get("role") == FACT_ROLE), None)
        if e is None:
            continue
        s = targets[r.target]
        name = f"fact_{s}_{e['product']}"
        if name in taken:
            name = f"{name}_{r.source.split('.', 1)[-1].lower()}"
        taken.add(name)
        out.append({"table": r.source, "schema": s, "product": e["product"], "name": name,
                    "cols": list(r.source_cols), "party_cols": list(r.target_cols)})
    return out


# ------------------------------------------------------------------------------------------------ the rules
def _system_words(schema: str, plan) -> set[str]:
    pack = ((plan.pack or {}).get("by_schema") or {}).get(schema)
    return {w for w in (_words(schema) + (_words(pack) if pack else [])) if len(w) >= 2}


def _fk_cols(plan, table: str) -> set[str]:
    """The columns of `table` that are a link of their own plan, or one the pack lists with a condition (a hierarchy,
    an owner): never a customer number of another source."""
    out = {c.lower() for r in plan.relationships if r.source == table for c in r.source_cols}
    for x in (plan.pack or {}).get("not_applied") or []:
        if isinstance(x, dict) and x.get("source") == table:
            out |= {str(c).lower() for c in x.get("source_cols") or []}
    return out


def _personal(plan, table: str) -> set[str]:
    """The columns privacy.py flags as personal data: left out of dim_customer, as the gold views leave them out."""
    from . import privacy
    part, bare = _schema_of(table), table.split(".", 1)[-1]
    sub = Schema(schema=part or plan.schema.schema)                  # the source's own tables, by their own names
    for t in plan.schema:
        if not part or _schema_of(t.name) == part:
            n = t.name.split(".", 1)[-1] if part else t.name
            sub.tables[n] = Table(n, list(t.columns), list(t.keys), [], schema=sub.schema, tags=dict(t.tags))
    try:
        return {c.lower() for (t, c) in privacy.personal_columns(sub, [bare]) if t == bare}
    except Exception:                                                # noqa: BLE001 - then none is flagged
        return set()


def candidates(plan, concept: str = "customer") -> list[dict]:
    """Every candidate key pair between two schemas' master tables of the concept (the party tables by default), by M0,
    M1 and M2 (names only; nothing counted)."""
    party = parties(plan, concept)
    out: list[dict] = []
    schemas = list(party)
    for a in schemas:
        for b in schemas:
            if a == b:
                continue
            pa, pb = party[a], party[b]
            ta, tb = plan.schema[pa["table"]], plan.schema[pb["table"]]
            own = {c.lower() for c in pa["key"]} | _fk_cols(plan, pa["table"])
            system = _system_words(b, plan)
            for c in ta.columns:
                if c.name.lower() in own or _system_column(c.name):
                    continue
                w = _rule_words(c.name, system)
                if (w & system and w & ID_WORDS) or pb["number"].lower() in c.name.lower():
                    out.append(_cand("M0", a, pa, c.name, b, pb, pb["number"], f"{c.name} names {b} and an identifier"))
                elif a < b and (kind := identifier_of(c.name)):              # M1 is symmetric: once per pair
                    other = next((x.name for x in tb.columns if identifier_of(x.name) == kind), None)
                    if other:
                        out.append(_cand("M1", a, pa, c.name, b, pb, other, f"both are a {kind}", kind=kind))
                elif w & ID_WORDS and not w & CODE_WORDS and _compatible(c, tb, pb["number"]):
                    out.append(_cand("M2", a, pa, c.name, b, pb, pb["number"], f"{c.name} is key-shaped"))
    seen, uniq = set(), []
    for x in sorted(out, key=lambda x: (ORDER.index(x["rule"]), x["id"])):
        if x["id"] not in seen:
            seen.add(x["id"])
            uniq.append({**x, "concept": concept})
    return uniq


def _compatible(c: Column, tb: Table, number: str) -> bool:
    other = next((x for x in tb.columns if x.name == number), None)
    text = lambda t: any(k in str(t).lower() for k in ("char", "string", "text"))
    return other is not None and (text(c.data_type) or text(other.data_type) or str(c.data_type) == str(other.data_type))


def _cand(rule: str, a: str, pa: dict, col: str, b: str, pb: dict, to_col: str, why: str, kind: str = "") -> dict:
    src, tgt = pa["table"], pb["table"]
    return {"id": f"{PREFIX}{src}.{col}>{tgt}.{to_col}", "rule": rule, "certainty": CERTAINTY[rule], "why": why,
            "from": {"schema": a, "table": src, "column": col, "key": list(pa["key"])},
            "to": {"schema": b, "table": tgt, "column": to_col, "key": list(pb["key"]),
                   "tenant": pb["tenant"] if rule != "M1" and not pa["tenant"] else None},
            **({"identifier": kind} if kind else {})}


# ------------------------------------------------------------------------------------------------ the counts
def _text(expr: str, d: Dialect) -> str:
    return f"CAST({expr} AS STRING)" if d.name == "databricks" else f"CAST({expr} AS NVARCHAR(4000))"


def normal(expr: str, rule: str, d: Dialect = TSQL) -> str:
    """The value as compared: M0/M2 the S1 steps (trim, case fold, leading zeros off); M1 the identifier steps."""
    from .propose import normal_forms
    if rule != "M1":
        return normal_forms(expr, d)["zeros_stripped"]
    x = f"UPPER(LTRIM(RTRIM({_text(expr, d)})))"
    for ch in (" ", "-", ".", "/"):
        x = f"REPLACE({x}, '{ch}', '')"
    letter = lambda i: f"UPPER(SUBSTRING({x}, {i}, 1)) <> LOWER(SUBSTRING({x}, {i}, 1))"
    return f"CASE WHEN {letter(1)} AND {letter(2)} THEN SUBSTRING({x}, 3, 4000) ELSE {x} END"


def _tenant_pick(to: dict, d: Dialect, alias: str = "x") -> str:
    """The tenant with the most rows (ties: the lowest), as a scalar subquery; no value is written into the SQL."""
    q = d.quote
    ten, tbl = q(to["tenant"]), d.table("+", to["table"])
    body = f"{alias}.{ten} FROM {tbl} AS {alias} GROUP BY {alias}.{ten} ORDER BY {d.count}(*) DESC, {alias}.{ten}"
    return f"(SELECT TOP (1) {body})" if d.limit_style == "top" else f"(SELECT {body} LIMIT 1)"


def count_sql(c: dict, d: Dialect = TSQL) -> tuple[str, str]:
    """The two statements of one candidate: (referencing side, side pointed at)."""
    q, n = d.quote, d.count
    fr, to, rule = c["from"], c["to"], c["rule"]
    a, b = d.table("+", fr["table"]), d.table("+", to["table"])
    col, num = q(fr["column"]), q(to["column"])
    scope = f" WHERE t.{q(to['tenant'])} = {_tenant_pick(to, d)}" if to.get("tenant") else ""
    has = f"s.{col} IS NOT NULL AND LTRIM(RTRIM({_text('s.' + col, d)})) <> ''"
    one = (f"SELECT {n}(*) AS a_rows, SUM(CASE WHEN {has} THEN 1 ELSE 0 END) AS filled, {n}(r.k) AS found_raw, "
           f"{n}(m.k) AS found, SUM(CASE WHEN m.k IS NOT NULL AND (m.n > 1 OR g.n > 1) THEN 1 ELSE 0 END) AS ambiguous"
           f" FROM {a} AS s"
           f" LEFT JOIN (SELECT DISTINCT {_text('t.' + num, d)} AS k FROM {b} AS t{scope}) AS r ON {_text('s.' + col, d)} = r.k"
           f" LEFT JOIN (SELECT {normal('t.' + num, rule, d)} AS k, {n}(*) AS n FROM {b} AS t{scope}"
           f" GROUP BY {normal('t.' + num, rule, d)}) AS m ON {normal('s.' + col, rule, d)} = m.k"
           f" LEFT JOIN (SELECT {normal('s.' + col, rule, d)} AS k, {n}(*) AS n FROM {a} AS s WHERE {has}"
           f" GROUP BY {normal('s.' + col, rule, d)}) AS g ON {normal('s.' + col, rule, d)} = g.k")
    on_scope = f" AND t.{q(to['tenant'])} = {_tenant_pick(to, d)}" if to.get("tenant") else ""
    two = (f"SELECT {n}(*) AS b_rows, {n}(m.k) AS b_found, SUM(CASE WHEN m.n > 1 THEN 1 ELSE 0 END) AS b_shared, "
           f"{n}(DISTINCT m.k) AS distinct_found FROM {b} AS t"
           f" LEFT JOIN (SELECT {normal('s.' + col, rule, d)} AS k, {n}(*) AS n FROM {a} AS s WHERE {has}"
           f" GROUP BY {normal('s.' + col, rule, d)}) AS m ON {normal('t.' + num, rule, d)} = m.k{on_scope}")
    return one, two


def _int(v) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def count(plan, execute, dialect: Dialect = TSQL, concept: str = "customer") -> dict:
    """{candidates: [candidate + counts], proposed: id or None, party, facts, queries, concept}. Never raises: a
    statement that fails leaves its candidate `not_counted` with the reason. `facts` (the transaction tables re-keyed
    to the conformed key) are drafted for the customer only."""
    party = parties(plan, concept)
    cands = candidates(plan, concept)
    out: list[dict] = []
    queries = 0
    for c in cands[:MAX_CANDIDATES]:
        one, two = count_sql(c, dialect)
        try:
            r1 = list(execute(one))[0]
            r2 = list(execute(two))[0]
            queries += 2
        except Exception as e:                                       # noqa: BLE001 - said, never raised
            out.append({**c, "not_counted": (str(e) or type(e).__name__).splitlines()[0][:160]})
            continue
        k = {"a_rows": _int(r1.get("a_rows")), "filled": _int(r1.get("filled")), "found_raw": _int(r1.get("found_raw")),
             "found": _int(r1.get("found")), "b_rows": _int(r2.get("b_rows")), "b_found": _int(r2.get("b_found")),
             "b_shared": _int(r2.get("b_shared")), "distinct": _int(r2.get("distinct_found")),
             "ambiguous": _int(r1.get("ambiguous"))}
        k["matched"] = k["found"] - k["ambiguous"]
        k["only_a"] = k["a_rows"] - k["found"]
        k["only_b"] = k["b_rows"] - k["b_found"]
        share = k["found"] / k["filled"] if k["filled"] else 0.0
        holds = bool(k["found"]) and share >= HOLDS
        certainty = c["certainty"]
        if c["rule"] == "M2" and holds and k["distinct"] >= M2_DISTINCT:
            certainty = 0.9
        out.append({**c, "counts": k, "share": round(share, 4), "holds": holds,
                    "certainty": certainty if holds else 0.0})
    for c in cands[MAX_CANDIDATES:]:
        out.append({**c, "not_counted": f"more than {MAX_CANDIDATES} candidates: not counted"})
    held = [c for c in out if c.get("holds")]
    best = max(held, key=lambda c: (c["certainty"], -ORDER.index(c["rule"]), c["counts"]["found"]), default=None)
    return {"candidates": out, "proposed": best["id"] if best else None, "party": party,
            "facts": facts(plan, party) if concept == "customer" else [], "queries": queries, "concept": concept}


# ------------------------------------------------------------------------------------------------ the words
def _source_word(schema: str) -> str:
    return schema.upper() if len(schema) <= 4 else schema


def card_line(c: dict) -> str:
    """The match in at most 25 words: 'SAP has 4 customers, the CRM 5 accounts. 4 accounts match on
    SAP_Customer_No__c after normalising. 1 only in SAP, 1 only in the CRM.'"""
    k = c["counts"]
    fr, to = c["from"], c["to"]
    nb, na = _noun(to["table"]), _noun(fr["table"])
    how = " after normalising" if k["found"] != k["found_raw"] and c["rule"] != "M1" else ""
    on = c.get("identifier") or fr["column"]
    return (f"{_source_word(to['schema'])} has {k['b_rows']} {_plural(nb, k['b_rows'])}, the {_source_word(fr['schema'])} "
            f"{k['a_rows']} {_plural(na, k['a_rows'])}. {k['found']} {_plural(na, k['found'])} match on {on}{how}. "
            f"{k['only_b']} only in {_source_word(to['schema'])}, {k['only_a']} only in the {_source_word(fr['schema'])}.")


def _noun(table: str) -> str:
    t = table.split(".", 1)[-1].lower()
    return {"kna1": "customer", "account": "account", "customer": "customer", "mara": "material", "product": "product",
            "product2": "product", "item": "item"}.get(t, "row")


def match_line(c: dict) -> str:
    """ON1: card_line with the ambiguous rows apart, in at most 25 words: 'SAP has 6 customers, D365 6 accounts. 3
    accounts match on accountnumber after normalising, 2 ambiguous. 2 only in SAP, 1 only in D365.'"""
    k = c["counts"]
    fr, to = c["from"], c["to"]
    nb, na = _noun(to["table"]), _noun(fr["table"])
    how = " after normalising" if k["found"] != k["found_raw"] and c["rule"] != "M1" else ""
    on = c.get("identifier") or fr["column"]
    amb = f", {k['ambiguous']} ambiguous" if k.get("ambiguous") else ""
    return (f"{_source_word(to['schema'])} has {k['b_rows']} {_plural(nb, k['b_rows'])}, {_source_word(fr['schema'])} "
            f"{k['a_rows']} {_plural(na, k['a_rows'])}. {k['matched']} {_plural(na, k['matched'])} match on {on}{how}{amb}. "
            f"{k['only_b']} only in {_source_word(to['schema'])}, {k['only_a']} only in {_source_word(fr['schema'])}.")


def _plural(noun: str, n: int) -> str:
    return noun if n == 1 else noun + "s"


def evidence(c: dict) -> list[str]:
    """The counted evidence under the decision: what was compared, the rule, and what is shared or out of scope."""
    k = c["counts"]
    fr, to = c["from"], c["to"]
    out = [f"{c['rule']}: {c['why']}. {fr['table']}.{fr['column']} {chr(8594)} {to['table']}.{to['column']}.",
           f"{k['filled']} of {k['a_rows']} {fr['table']} rows hold a value; {k['found_raw']} match as written, "
           f"{k['found']} after normalising."]
    if k.get("ambiguous"):
        out.append(f"{k['ambiguous']} {fr['table']} {'row is' if k['ambiguous'] == 1 else 'rows are'} ambiguous: the value "
                   f"is held by another {fr['table']} row too, or finds more than one {to['table']} row. The rules do not "
                   f"pick one: you decide.")
    if k["b_shared"]:
        out.append(f"{k['b_shared']} {to['table']} {'row is' if k['b_shared'] == 1 else 'rows are'} matched by more than "
                   f"one {fr['table']} row: they become one {_noun(to['table']) if c.get('concept') == 'product' else 'customer'}.")
    if to.get("tenant"):
        out.append(f"Matched within the {to['tenant']} value with the most rows; the other {to['tenant']} values stay, "
                   f"counted as only in {_source_word(to['schema'])}.")
    out.append("Nothing is joined until you accept.")
    return out


def customers(c: dict) -> int:
    """How many rows dim_customer gets: every row of the side pointed at, plus the other side's rows found nowhere."""
    return c["counts"]["b_rows"] + c["counts"]["only_a"]


def accepted(result: dict, decisions) -> dict | None:
    """The candidate the person accepted (the last decision on a match item wins), or None."""
    taken = {}
    for d in decisions or []:
        if isinstance(d, dict) and str(d.get("item", "")).startswith(PREFIX):
            taken[d["item"]] = d.get("review")
    for c in result.get("candidates") or []:
        if taken.get(c["id"]) == "accepted" and c.get("counts"):
            return c
    return None


# ------------------------------------------------------------------------------------------------ the conformed gold
def _xcol(schema: str, col: str) -> str:
    return f"{schema}_{col}"


def gold_sql(c: dict, plan, fact_list: list[dict], gold: str = "gold", d: Dialect = DATABRICKS,
             concept: str = "customer") -> dict[str, str]:
    """{table: Spark SQL} of the conformed gold for an accepted match, read in the product lakehouse (its schemas are
    the sources). Master: the side pointed at. ON1: `concept` names the tables and the key (`xref_product`,
    `dim_product`, `product_key`); the customer's are as SM7 wrote them."""
    q = d.quote
    xref, dim, ck = f"xref_{concept}", f"dim_{concept}", f"{concept}_key"
    fr, to, rule = c["from"], c["to"], c["rule"]
    m_s, o_s = to["schema"], fr["schema"]
    mk, ok = to["key"], fr["key"]
    mt, ot = d.table("+", to["table"]), d.table("+", fr["table"])
    g = lambda name: f"{q(gold)}.{q(name)}"
    mcols = ", ".join(f"t.{q(k)} AS {q(_xcol(m_s, k))}" for k in mk)
    ocols = ", ".join(f"s.{q(k)} AS {q(_xcol(o_s, k))}" for k in ok)
    in_scope = (f"t.{q(to['tenant'])} = {_tenant_pick(to, d, 'x')}" if to.get("tenant") else "TRUE")
    mx = [q(_xcol(m_s, k)) for k in mk]
    ox = [q(_xcol(o_s, k)) for k in ok]
    on_m = " AND ".join(f"b.{x} = m.{x}" for x in mx)
    on_o = " AND ".join(f"a.{x} = m.{x}" for x in ox)
    null = lambda cols: ", ".join(f"NULL AS {x}" for x in cols)
    order = ", ".join([f"u.{x}" for x in mx] + [f"CASE WHEN u.{mx[-1]} IS NULL THEN u.{x} END" for x in ox])
    xref_sql = (
        f"CREATE OR REPLACE TABLE {g(xref)} AS\n"
        f"WITH b AS (SELECT {mcols}, {normal('t.' + q(to['column']), rule, d)} AS k, {in_scope} AS in_scope FROM {mt} AS t),\n"
        f"a AS (SELECT {ocols}, {normal('s.' + q(fr['column']), rule, d)} AS k FROM {ot} AS s),\n"
        f"m AS (SELECT {', '.join('b.' + x for x in mx)}, {', '.join('a.' + x for x in ox)} FROM a JOIN b ON a.k = b.k AND b.in_scope),\n"
        f"u AS (SELECT {', '.join('b.' + x for x in mx)}, {', '.join('m.' + x for x in ox)}, "
        f"CASE WHEN m.{ox[0]} IS NULL THEN '{m_s}' END AS only_in FROM b LEFT JOIN m ON {on_m}\n"
        f"      UNION ALL SELECT {null(mx)}, {', '.join('a.' + x for x in ox)}, '{o_s}' AS only_in FROM a\n"
        f"      LEFT ANTI JOIN m ON {on_o})\n"
        f"SELECT DENSE_RANK() OVER (ORDER BY u.{mx[-1]} IS NULL, {order}) AS {ck},\n"
        f"       u.*, CASE WHEN u.only_in IS NULL THEN '{rule}' END AS match_rule,\n"
        f"       CASE WHEN u.only_in IS NULL THEN '{fr['table']}.{fr['column']} = {to['table']}.{to['column']}' END AS matched_on\n"
        f"FROM u")
    # one row per customer: the master's row, and the first matched row of the other side (the lowest key)
    m_props, o_props = properties(plan, to), properties(plan, fr)
    agg = (", ".join(f"MIN({x}) AS {x}" for x in mx + ox) + f", {d.count}({ox[-1]}) AS {q(o_s + '_rows')}, "
           "MIN(only_in) AS only_in")
    dim_sql = (f"CREATE OR REPLACE TABLE {g(dim)} AS\n"
               f"WITH x AS (SELECT {ck}, {agg} FROM {g(xref)} GROUP BY {ck})\n"
               f"SELECT x.*" + "".join(f", t.{q(p)} AS {q(_xcol(m_s, p))}" for p in m_props)
               + "".join(f", s.{q(p)} AS {q(_xcol(o_s, p))}" for p in o_props) + "\n"
               f"FROM x LEFT JOIN {mt} AS t ON " + " AND ".join(f"t.{q(k)} = x.{q(_xcol(m_s, k))}" for k in mk)
               + f"\nLEFT JOIN {ot} AS s ON " + " AND ".join(f"s.{q(k)} = x.{q(_xcol(o_s, k))}" for k in ok))
    out = {xref: xref_sql, dim: dim_sql}
    for f in fact_list:
        s = f["schema"]
        xs = [q(_xcol(s, k)) for k in f["party_cols"]]
        on = " AND ".join(f"f.{q(src)} = x.{q(_xcol(s, k))}" for src, k in zip(f["cols"], f["party_cols"]))
        out[f["name"]] = (f"CREATE OR REPLACE VIEW {g(f['name'])} AS\n"
                          f"SELECT x.{ck}, f.* FROM {d.table('+', f['table'])} AS f\n"
                          f"LEFT JOIN (SELECT DISTINCT {ck}, {', '.join(xs)} FROM {g(xref)} "
                          f"WHERE {xs[-1]} IS NOT NULL) AS x ON {on}")
    return out


def model_schema(c: dict, plan, fact_list: list[dict], gold: str = "gold", concept: str = "customer") -> Schema:
    """The conformed gold as a Schema for the model: dim_customer keyed on customer_key, each fact with customer_key
    pointing at it (a declared foreign key), and no link between facts. ON1: `concept` names the dimension and key."""
    dim, ck = f"dim_{concept}", f"{concept}_key"
    fr, to = c["from"], c["to"]
    s = Schema(schema=gold)
    mt, ot = plan.schema[to["table"]], plan.schema[fr["table"]]
    cols = [Column(ck, "bigint", False)]
    cols += [Column(_xcol(to["schema"], k), _type(mt, k)) for k in to["key"]]
    cols += [Column(_xcol(fr["schema"], k), _type(ot, k)) for k in fr["key"]]
    cols += [Column(f"{fr['schema']}_rows", "bigint"), Column("only_in", "nvarchar")]
    cols += [Column(_xcol(to["schema"], p), _type(mt, p)) for p in properties(plan, to)]
    cols += [Column(_xcol(fr["schema"], p), _type(ot, p)) for p in properties(plan, fr)]
    s.tables[dim] = Table(dim, cols, [ck], [], schema=gold)
    for f in fact_list:
        src = plan.schema[f["table"]]
        keys = list((plan.keys.get(f["table"]) or ([], ""))[0])
        fcols = [Column(ck, "bigint")] + [Column(x.name, x.data_type) for x in src.columns if x.name.lower() != ck]
        s.tables[f["name"]] = Table(f["name"], fcols, keys, [([ck], dim, [ck])], schema=gold)
    return s


def properties(plan, side: dict) -> list[str]:
    """A party table's columns that dim_customer carries: not its key, not personal data (privacy.py)."""
    gone = _personal(plan, side["table"])
    return [x.name for x in plan.schema[side["table"]].columns if x.name not in side["key"] and x.name.lower() not in gone]


def personal_left_out(plan, c: dict) -> list[str]:
    """'sap.KNA1.TELF1', ...: the party columns left out of dim_customer as personal data."""
    out = []
    for side in (c["to"], c["from"]):
        gone = _personal(plan, side["table"])
        out += [f"{side['table']}.{x.name}" for x in plan.schema[side["table"]].columns if x.name.lower() in gone]
    return out


def _type(t: Table, col: str) -> str:
    return next((x.data_type for x in t.columns if x.name == col), "nvarchar")


def model_line(c: dict, fact_list: list[dict]) -> str:
    """'SAP + CRM → 1 dim_customer (5 customers), 3 SAP facts and 7 CRM facts share it; no link between facts.'"""
    by: dict[str, int] = {}
    for f in fact_list:
        by[f["schema"]] = by.get(f["schema"], 0) + 1
    srcs = [c["to"]["schema"], c["from"]["schema"]]
    facts_said = " and ".join(f"{by.get(s, 0)} {_source_word(s)} {_plural('fact', by.get(s, 0))}" for s in srcs)
    return (f"{' + '.join(_source_word(s) for s in srcs)} {chr(8594)} 1 dim_customer ({customers(c)} customers); "
            f"{facts_said} share it, no link between facts.")
