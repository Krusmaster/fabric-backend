"""answer_query_draft: a question in Swedish or English plus the tables it is about -> a T-SQL query over the safest
join path, and a GraphQL query against an existing API for GraphQL item when one is named. Nothing is run here.

What is read from the question, and nothing more (anything else is listed under `assumptions`):
  aggregate   count ("how many", "number of", "hur många", "antal"), sum ("total", "sum", "summa", "totalt"),
              average ("average", "mean", "genomsnitt", "snitt")
  grouping    the table or column after "per", "by", "for each", "för varje", "efter", "fördelat på"
  counted     the table after "how many" / "antal" ("how many orders per customer" counts orders)
  top N       "top 5", "topp 5", "the 5 largest", "de 10 första", "5 största"
  latest      "latest", "newest", "most recent", "senaste", "nyaste": order by the first date column, newest first
  measure     for sum and average: a numeric column named in the question, else the first numeric column that is
              neither a key nor a reference
Words are matched to tables through the same names and synonym table the inference uses (kund -> customers).

The join path: from the table the question counts (or the one every other table is reached from by many-to-one
steps) to each other table, the safest path of graphs.safest_path (cost 1/certainty per rule), merged into one join
tree. Every step carries the rule that produced its relationship. GraphQL: Fabric's API for GraphQL groups only by a
table's own columns (groupBy, fabric-docs api-graphql-aggregations.md), so an aggregate over a join is offered as
T-SQL only, and the GraphQL answer says why; lists walk the relationship fields (ManyToOne as an object, OneToMany
as a connection with items), the way app_starter writes them.
"""
from __future__ import annotations

import contextvars
import re

from .evidence import qi
from .graphql import graphql_name
from .infer import SYNONYMS, Plan, PlanInputError, _TRANSLIT, _bases, _canon_bases, _norm, _singulars

# Markers are whole words (\b is Unicode-aware, so "beräkna" does not contain "räkna"); \w* lets an inflected form match
# ("totalt", "summan", "genomsnittlig", "antalet").
COUNT = ("how many", "number of", "count", "counts", "hur många", "hur manga", "antal", "antalet", "räkna", "rakna", "räknar")
SUM = ("total\\w*", "sum", "sums", "summa\\w*", "sammanlag\\w*")
AVG = ("average\\w*", "mean", "genomsnitt\\w*", "snitt\\w*", "medel\\w*")
MOST = ("most", "flest", "fewest", "minst")
LATEST = ("latest", "newest", "most recent", "senaste", "nyaste")
# n87: a value is asked for ("order value", "revenue", "ordervärde", "omsättning"): a quantity is not one
VALUE = ("value\\w*", "worth", "revenue\\w*", "amount\\w*", "turnover", "\\w*värde\\w*", "\\w*varde\\w*", "belopp\\w*",
         "omsättning\\w*", "omsattning\\w*", "intäkt\\w*", "intakt\\w*", "försäljning\\w*", "forsaljning\\w*")
GROUP = ("for each", "for every", "per", "by", "för varje", "for varje", "för var", "efter", "fördelat på", "fordelat pa", "grouped by", "grupperat på")
_RANK = (r"top|topp|first|första|forsta|largest|biggest|highest|most|flest|största|storsta|högsta|hogsta|which|what|vilka|vilken|show|visa|"
         r"list|lista|latest|newest|senaste|nyaste")
_TOP = re.compile(rf"\b(?:{_RANK})\s+(\d{{1,4}})\b|\b(\d{{1,4}})\s+(?:{_RANK})\b")
LINE_WORDS = {"line", "lines", "item", "items", "detail", "details", "row", "rows", "rad", "rader", "position", "positions", "positioner"}
_WORD = re.compile(r"[a-z0-9_åäöüß]+")
LABELS = ("name", "title", "label", "description", "namn", "benamning", "beskrivning", "displayname", "fullname")
NUMERIC = ("int", "bigint", "smallint", "tinyint", "decimal", "numeric", "float", "real", "double", "money", "smallmoney", "long", "short")
DATES = ("date", "datetime", "datetime2", "timestamp", "smalldatetime", "datetimeoffset")
# n87: a negation on a relationship or a column ("customers without orders", "kunder som saknar adress"). The table or
# column after the marker (after a few filler words) is the one that must not exist: NOT EXISTS for a table, IS NULL for a
# column. A marker that cannot be tied to either is said under not_understood and no query is given.
NEGATE = ("without", "with no", "no", "missing", "lacking", "lack", "lacks", "never", "not have", "do not have", "does not have",
          "don't have", "doesn't have", "did not", "didn't", "saknar", "saknas", "utan", "inte har", "har inte", "inte lagt",
          "aldrig", "ingen", "inga", "inget")
_FILLER = {"a", "an", "any", "the", "single", "placed", "made", "have", "has", "had", "place", "make", "en", "ett", "någon", "några",
           "nagon", "nagra", "har", "lagt", "gjort", "någon", "ens", "is", "are", "är", "som"}
# Where the T-SQL of a draft can run: no Krusgraph tool runs T-SQL (query_graphql runs GraphQL only).
TSQL_RUNS_WHERE = ("No Krusgraph tool runs T-SQL. Run it in the Fabric portal's SQL query editor on the source's SQL analytics "
                   "endpoint (open the lakehouse or warehouse, then SQL analytics endpoint, New SQL query), or in SSMS, VS Code "
                   "(mssql) or another SQL client connected to that endpoint.")


def _type(t, col: str) -> str:
    return next(((c.data_type or "").lower().split("(")[0].strip() for c in t.columns if c.name == col), "")


def _words(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def _has(q: str, markers: tuple[str, ...]) -> bool:
    return any(re.search(r"\b" + m.replace(" ", r"\s+") + r"\b", q) for m in markers)


def _phrase_table(words: list[str], candidates: list[str]) -> str | None:
    """A table named by the first two words ("order items", "order lines": a line word stands for the table that holds the
    lines, order_items), else by the first word."""
    from .infer import _words as name_words
    if len(words) >= 2:
        hit = _table_for(words[0] + "_" + words[1], candidates)
        if hit:
            return hit
        if words[1] in LINE_WORDS:
            head = {_norm(x) for x in _singulars(words[0])} | ({_norm(SYNONYMS[words[0]])} if words[0] in SYNONYMS else set())
            for t in candidates:
                tw = name_words(t)
                if len(tw) >= 2 and tw[-1] in LINE_WORDS and _norm("".join(tw[:-1])) in head | {_norm(x) for x in _singulars("".join(tw[:-1]))} & head:
                    return t
    return _table_for(words[0], candidates) if words else None


# n87: the names a knowledge pack gives its tables ("Customer master, general data" for SAP's KNA1, "Sales document,
# header" for VBAK), read for the duration of one understand() call so "per customer" finds sap_kna1.
_PACK_NAMES: contextvars.ContextVar[dict] = contextvars.ContextVar("pack_names", default={})
_GENERIC = {"master", "general", "data", "document", "documents", "header", "items", "item", "the", "of", "and"}
_PACK_ALIASES = {"sales": ("order", "sales order"), "purchasing": ("purchase order",), "billing": ("invoice", "bill"),
                 "supplier": ("vendor",)}


def _pack_names(plan: Plan) -> dict[str, set[str]]:
    """table -> the normalised words a pack's own name for it answers to; header tables only for document words."""
    pack = getattr(plan, "pack", None) or {}
    out: dict[str, set[str]] = {}
    if not pack.get("tables"):
        return out
    try:
        from . import sap_pack
    except ImportError:  # pragma: no cover
        return out
    for table, name in pack["tables"].items():
        try:
            en = (sap_pack.table_info(name) or {}).get("en") or ""
        except Exception:  # noqa: BLE001 - a table another pack knows
            continue
        head, _, part = en.lower().partition(",")
        words = [w for w in _words(head) if w not in _GENERIC]
        if not words:
            continue
        line = "item" in part
        forms = set()
        if "document" not in head or not line:                  # "Sales document, items" is not "the order"
            forms |= {_norm(words[0])} | {_norm(x) for x in _singulars(words[0])}
            for alias in _PACK_ALIASES.get(words[0], ()):
                forms.add(_norm(alias.replace(" ", "")))
        out[table] = forms
    return out


def _table_for(word: str, candidates: list[str]) -> str | None:
    w = _norm(word)
    forms = {_norm(x) for x in _singulars(word.lower().translate(_TRANSLIT))} | {w}
    syn = SYNONYMS.get(word.lower().translate(_TRANSLIT))
    if syn:
        forms.add(_norm(syn))
    for t in candidates:
        if w == _norm(t) or forms & (_bases(t) | _canon_bases(t)):
            return t
    named = _PACK_NAMES.get()
    for t in candidates:
        if forms & named.get(t, set()):
            return t
    return None


def _phrase_column(words: list[str], plan: Plan, tables: list[str]) -> tuple[str, str] | None:
    """A column named by the first two words ("order date" -> order_date), else by the first word."""
    if len(words) >= 2:
        hit = _column_for(words[0] + "_" + words[1], plan, tables)
        if hit:
            return hit
    return _column_for(words[0], plan, tables) if words else None


def _column_for(word: str, plan: Plan, tables: list[str]) -> tuple[str, str] | None:
    """A column of one of the tables named by the word, directly or through the synonym table (land -> country)."""
    forms = {_norm(word)} | {_norm(x) for x in _singulars(word.lower().translate(_TRANSLIT))}
    syn = SYNONYMS.get(word.lower().translate(_TRANSLIT))
    if syn:
        forms.add(_norm(syn))
    return next(((t, c) for t in tables for c in plan.schema[t].column_names if _norm(c) in forms), None)


def _after(text: str, markers: tuple[str, ...]) -> list[list[str]]:
    """The words that follow each marker, up to three, for every place a marker occurs."""
    out = []
    low = text.lower()
    for m in markers:
        for hit in re.finditer(r"(?<![a-z0-9_åäö])" + re.escape(m) + r"(?![a-z0-9_åäö])", low):
            out.append(_words(low[hit.end():])[:3])
    return out


def _negations(q: str, plan: Plan, tables: list[str], everything: list[str]) -> tuple[list[str], list[list[str]], list[str]]:
    """The tables and columns a negation marker applies to, and the markers that could not be tied to either."""
    low, neg_tables, neg_cols, unread, spans = q.lower(), [], [], [], []
    for m in sorted(NEGATE, key=len, reverse=True):                 # "with no" before "no", "do not have" before "not have"
        for hit in re.finditer(r"(?<![a-z0-9_åäö'])" + m.replace(" ", r"\s+") + r"(?![a-z0-9_åäö'])", low):
            if any(a <= hit.start() < b for a, b in spans):
                continue
            spans.append((hit.start(), hit.end()))
            after = _words(low[hit.end():])
            i = 0
            while i < len(after) and i < 4 and after[i] in _FILLER:
                i += 1
            rest = after[i:i + 3]
            t = rest and (_phrase_table(rest, tables) or _phrase_table(rest, everything))
            col = None if t else (rest and _phrase_column(rest, plan, tables))
            if not t and not col and m in ("missing", "saknas"):    # "where the address is missing", "adress saknas"
                before = [w for w in _words(low[:hit.start()]) if w not in _FILLER][-2:]
                t = before and (_phrase_table(before[-1:], tables) or _phrase_table(before[-1:], everything))
            if t:
                if t not in neg_tables:
                    neg_tables.append(t)
            elif col:
                if list(col) not in neg_cols:
                    neg_cols.append(list(col))
            else:
                said = " ".join([m] + after[:3]).strip()
                unread.append(f"'{said}': a negation that names no table or column of the plan, so it cannot be applied; "
                              "name the table that must have no rows (tables=) or the column that must be empty")
    return neg_tables, neg_cols, unread


def _first_named(q: str, tables: list[str], exclude: list[str]) -> str | None:
    ws = _words(q)
    for i in range(len(ws)):
        t = _phrase_table(ws[i:i + 2], tables)
        if t and t not in exclude:
            return t
    return None


def understand(question: str, plan: Plan, tables: list[str]) -> dict:
    token = _PACK_NAMES.set(_pack_names(plan))
    try:
        return _understand(question, plan, tables)
    finally:
        _PACK_NAMES.reset(token)


# "per X" and its Swedish forms: a marker whose X must be found, or the question is not answered (never one total instead).
_PER = ("per", "for each", "for every", "för varje", "for varje", "för var", "fördelat på", "fordelat pa", "grouped by", "grupperat på")


def _understand(question: str, plan: Plan, tables: list[str]) -> dict:
    q = " " + question.lower() + " "
    everything = [t.name for t in plan.schema]
    without, without_columns, unread = _negations(q, plan, tables, everything)
    aggregate = "count" if _has(q, COUNT) else "avg" if _has(q, AVG) else "sum" if _has(q, SUM) else None
    if aggregate is None and _has(q, VALUE) and any(_has(q, (m,)) for m in GROUP):
        aggregate = "sum"                                     # "revenue per category": a value per group is a sum, not a count
    if aggregate is None and _has(q, MOST):
        aggregate = "count"                                   # "which customers have the most orders": a count per customer
    top = None
    m = _TOP.search(q)
    if m:
        n = int(m.group(1) or m.group(2))
        top = n if 0 < n <= 1000 else None
    else:                                                      # "5 kunder", "10 orders": a number before a table's name
        ws = _words(q)
        for a, b in zip(ws, ws[1:]):
            if a.isdigit() and 0 < int(a) <= 1000 and _table_for(b, everything):
                top = int(a)
                break
    counted = None
    if aggregate == "count":
        for words in _after(q, COUNT + MOST):
            hit = words and (_phrase_table(words, tables) or _phrase_table(words, everything))
            if hit and hit not in without:
                counted = hit
                break
    group_table = group_column = None
    for words in _after(q, GROUP):
        for i in range(len(words)):
            rest = words[i:]
            col = _phrase_column(rest, plan, tables)          # "per order date" is the column, not the orders table
            if col:
                group_column = col
                break
            hit = _phrase_table(rest, tables) or _phrase_table(rest, everything)
            if hit and hit != counted and hit not in without:                        # "how many orders per order" cannot group orders by themselves
                group_table = hit
                break
        if group_table or group_column:
            break
    if not (group_table or group_column):
        for m in _PER:
            for words in _after(q, (m,)):
                said = [w for w in words if not w.isdigit()][:2]
                if said and not any(w in _FILLER for w in said[:1]):
                    unread.append(f"'{m} {' '.join(said)}': no table or column of the plan is named {' '.join(said)!r}, so the "
                                  "grouping cannot be applied and one total would answer a different question; add the table "
                                  "to tables= or name its column")
                    break
            if unread:
                break
    asked_column = None                                       # "which city ...": the column the answer is about
    for words in _after(q, ("which", "what", "vilken", "vilka", "vilket")):
        col = words and _phrase_column(words[:2], plan, tables)
        if col and not _phrase_table(words[:1], tables):
            asked_column = list(col)
            break
    measure = None
    if aggregate in ("sum", "avg"):
        said = set(_norm(w) for w in _words(q))
        for t in tables:
            for c in plan.schema[t].column_names:
                if _type(plan.schema[t], c) in NUMERIC and (_norm(c) in said or _norm(SYNONYMS.get(c.lower(), c)) in said):
                    measure = (t, c)
                    break
            if measure:
                break
    if aggregate and not (group_table or group_column):
        rest = [t for t in tables if t != counted and t not in without]
        if counted and rest and not without:
            group_table = rest[0]                             # "the most orders" with customers and orders: per customer
    assumed_count = False
    if aggregate is None and (group_table or group_column):
        aggregate, assumed_count = "count", True              # "customers per country": a count per country
    mentioned = []
    ws = _words(q)
    for i in range(len(ws)):
        col = _phrase_column(ws[i:i + 2], plan, tables)
        if col and list(col) not in mentioned:
            mentioned.append(list(col))
    unused = [n for n in re.findall(r"\b\d+(?:[.,]\d+)?\b", q) if not (top is not None and n == str(top))]
    mentioned = [c for c in mentioned if c not in without_columns]
    return {"aggregate": aggregate, "top": top, "latest": _has(q, LATEST), "group_table": group_table,
            "group_column": list(group_column) if group_column else None, "counted": counted, "measure": list(measure) if measure else None,
            "columns_named": mentioned, "not_used": unused, "count_assumed": assumed_count,
            "without": without, "without_columns": without_columns, "with": [],
            "subject": _first_named(q, tables, without) if (without or without_columns) else None, "unread": unread,
            "value_asked": aggregate in ("sum", "avg") and measure is None and _has(q, VALUE), "asked_column": asked_column}


def _label(plan: Plan, t: str) -> str:
    cols = plan.schema[t].column_names
    singular = {_norm(x) for x in _singulars(t)}
    for c in cols:
        n = _norm(c)
        if n in LABELS or any(n == s + "name" for s in singular):
            return c
    key = plan.keys.get(t, ([], ""))[0]
    return key[0] if key else cols[0]


def _grain(plan: Plan, tables: list[str]) -> str:
    """The table every other one is reached from by many-to-one steps only (the finest grain), else the first given."""
    from .graphs import safest_path
    for t in tables:
        if all((p := safest_path(plan, t, o)) is not None and all(s["forward"] for s in p) for o in tables if o != t):
            return t
    return tables[0]


def _join_tree(plan: Plan, root: str, others: list[str]) -> tuple[list[dict], dict[str, str], bool]:
    """The merged safest paths from root: steps in join order, alias per table, and whether a step fans out."""
    from .graphs import safest_path
    aliases, steps, fans_out = {root: "t0"}, [], False
    for other in others:
        if other == root:
            continue
        path = safest_path(plan, root, other)
        if path is None:
            raise PlanInputError(f"tables: no chain of relationships connects {root} and {other}; join_path suggests the missing one")
        for s in path:
            if s["to"] in aliases:
                continue
            aliases[s["to"]] = f"t{len(aliases)}"
            fans_out = fans_out or not s["forward"]
            steps.append(s)
    return steps, aliases, fans_out


def _personal(plan: Plan, show: bool) -> dict[tuple[str, str], dict]:
    """The columns the privacy rules flag (fabric_backend/privacy.py), or none when the caller asked to see them."""
    from . import privacy
    return {} if show else privacy.personal_columns(plan.schema)


def _value_source(plan: Plan, tables: list[str], u: dict) -> dict:
    """Where the value a question asks for comes from: an amount column of the given tables ({"amount": [t, c]}), else
    quantity × a price the plan reaches (amounts.order_amount_measures: {"table", "column", "dimension", "price", ...}),
    else {"not_found": why}. A quantity is never summed as a value."""
    from . import amounts
    pack_amounts = {a["column"].lower() for a in ((getattr(plan, "pack", None) or {}).get("amounts") or []) if isinstance(a, dict) and a.get("column")}
    line_first = sorted(tables, key=lambda t: 0 if t == _grain(plan, tables) else 1)
    for t in line_first:
        for c in plan.schema[t].column_names:
            typ = _type(plan.schema[t], c)
            if typ in NUMERIC and (amounts.looks_like_amount(c, typ) or c.lower() in pack_amounts):
                return {"amount": (t, c)}
    for m in amounts.order_amount_measures(plan)["measures"]:
        if m["table"] in tables:
            said = (f"no value column: none of {', '.join(tables)} has an amount, and summing {m['table']}.{m['column']} would add "
                    f"up items, not value. Offered instead, and labelled as such: {m['column']} × {m['dimension']}.{m['price']} "
                    f"per {m['table']} row (through {m['table']}.{m['via']} → {m['dimension']}, {m['rule']}). {m['price_note']}")
            said = said.replace("a list price, not necessarily the price paid", "a list price, not the price paid")
            return {"table": m["table"], "column": m["column"], "dimension": m["dimension"], "price": m["price"], "via": m["via"],
                    "rule": m["rule"], "name": m["name"], "said": said,
                    "offered": f"{m['column']} × {m['dimension']}.{m['price']} (quantity × price, computed: not a stored value)"}
    return {"not_found": f"no value column: none of {', '.join(tables)} has an amount, and no price is in reach to multiply a "
                         "quantity by; summing a quantity would answer a different question. Name the column to sum"}


def tsql(plan: Plan, question: str, tables: list[str], show_personal_data: bool = False) -> dict:
    names = {t.name.lower(): t.name for t in plan.schema}
    missing = [t for t in tables if t.lower() not in names]
    if missing or not tables:
        raise PlanInputError("tables: name the tables the question is about; not in the schema: " + ", ".join(repr(m) for m in missing)
                             if missing else "tables: name the tables the question is about (list_tables shows them)")
    tables = list(dict.fromkeys(names[t.lower()] for t in tables))
    u = understand(question, plan, tables)
    personal = _personal(plan, show_personal_data)
    left_out: list[dict] = []

    def allowed(t: str, c: str) -> bool:
        f = personal.get((t, c))
        if f and not any(x["table"] == t and x["column"] == c for x in left_out):
            left_out.append({"table": t, "column": c, **f})
        return f is None
    personal_group = None
    if u["group_column"] and not allowed(*u["group_column"]):
        t = u["group_column"][0]
        personal_group = tuple(u["group_column"])
        u["group_column"] = None                              # never grouped by: its values would be the answer
        if plan.keys.get(t):                                  # group by the row the personal column belongs to, by its key
            u["group_table"] = t
    schema = plan.schema.schema
    value = _value_source(plan, tables, u) if u.get("value_asked") else None
    if value and value.get("not_found"):
        u["unread"].append(value["not_found"])
    if u["unread"]:                                           # a negation that names nothing: no query, never another question
        return {"understood": u, "root": None, "tables": tables, "measure": None, "path": [], "sql": None, "assumptions": [],
                "_steps": [], "personal_left_out": left_out, "_personal": personal, "not_understood": list(u["unread"])}
    involved = list(dict.fromkeys(tables + [x for x in (u["group_table"], u["counted"]) if x] + u["without"]
                                  + [c[0] for c in u["without_columns"]]))
    negation = bool(u["without"] or u["without_columns"])
    computed = value if value and value.get("price") else None
    if value and value.get("amount"):
        u["measure"] = list(value["amount"])
    if computed:
        involved = list(dict.fromkeys(involved + [computed["table"], computed["dimension"]]))
    root = (computed["table"] if computed and not u["counted"] else None) or u["counted"] or (u["subject"] if negation else None) \
        or _grain(plan, [t for t in involved if t not in u["without"]] or involved)
    conditions: list[str] = []
    joined = [t for t in involved if t != root and t not in u["without"]]
    if negation:                                              # "customers with orders but no address": orders is a condition too
        from .graphs import safest_path
        for t in list(joined):
            if t == u["group_table"] or t in [c[0] for c in u["without_columns"] + u["columns_named"]]:
                continue
            path = safest_path(plan, root, t)
            if path is not None and not all(s["forward"] for s in path):
                joined.remove(t)
                u["with"].append(t)
    steps, alias, fans_out = _join_tree(plan, root, joined)
    assumptions = []

    def on(s, a, b):
        r = s["rel"]
        left, right = (r.source_cols, r.target_cols) if s["forward"] else (r.target_cols, r.source_cols)
        return " AND ".join(f"{a}.{qi(x)} = {b}.{qi(y)}" for x, y in zip(left, right))
    joins = [f"JOIN {qi(schema)}.{qi(s['to'])} AS {alias[s['to']]} ON {on(s, alias[s['from']], alias[s['to']])}" for s in steps]
    if negation or u["with"]:
        from .graphs import safest_path
        for k, (t, exists) in enumerate([(t, True) for t in u["with"]] + [(t, False) for t in u["without"]], start=1):
            path = safest_path(plan, root, t)
            if path is None:
                raise PlanInputError(f"tables: no chain of relationships connects {root} and {t}; join_path suggests the missing one")
            names = [f"n{k}_{i}" for i in range(len(path))]
            inner = f"SELECT 1 FROM {qi(schema)}.{qi(path[0]['to'])} AS {names[0]}"
            inner += "".join(f" JOIN {qi(schema)}.{qi(s['to'])} AS {names[i]} ON {on(s, names[i - 1], names[i])}"
                             for i, s in enumerate(path) if i)
            inner += f" WHERE {on(path[0], 't0', names[0])}"
            conditions.append(f"{'' if exists else 'NOT '}EXISTS ({inner})")
            via = " -> ".join([root] + [s["to"] for s in path])
            rules = ", ".join(s["rule"] for s in path)
            assumptions.append(f"only {root} rows {'with' if exists else 'without'} a matching {t} row "
                               f"({'EXISTS' if exists else 'NOT EXISTS'} over {via}, {rules})")
        for t, c in u["without_columns"]:
            conditions.append(f"{alias[t]}.{qi(c)} IS NULL")
            assumptions.append(f"only rows where {t}.{c} is empty (IS NULL)")
    where = ("\nWHERE " + "\n  AND ".join(conditions)) if conditions else ""
    select, group, order = [], [], []
    measure = level = None
    root_key = plan.keys.get(root, ([], ""))[0]
    if u["aggregate"]:
        asked = u.get("asked_column")
        if u["group_table"] and asked and asked[0] == u["group_table"] and asked[1] not in plan.keys.get(asked[0], ([], ""))[0]:
            g, c = asked                                      # "which city has the most orders": one group per city
            if allowed(g, c):
                select.append(f"{alias[g]}.{qi(c)}")
                group.append(f"{alias[g]}.{qi(c)}")
            else:
                key_cols = plan.keys.get(g, ([], ""))[0]
                select += [f"{alias[g]}.{qi(k)}" for k in key_cols]
                group += [f"{alias[g]}.{qi(k)}" for k in key_cols]
                f = personal[(g, c)]
                assumptions.append(f"{g}.{c} looks like personal data ({f['rule']}: {f['what']}) and is left out, so the question is not "
                                   f"answered per {c}: grouped by {g}'s key {', '.join(key_cols)} instead (one row per {g} row, not per "
                                   f"{c}); show_personal_data=true groups by {c}")
        elif u["group_table"]:
            g = u["group_table"]                              # the root itself too: one group per root row
            key_cols = plan.keys.get(g, ([], ""))[0]
            cols = list(dict.fromkeys(key_cols + [c for c in [_label(plan, g)] if c in key_cols or allowed(g, c)]))
            select += [f"{alias[g]}.{qi(c)}" for c in cols]
            group += [f"{alias[g]}.{qi(c)}" for c in cols]
        elif u["group_column"]:
            t, c = u["group_column"]
            select.append(f"{alias[t]}.{qi(c)}")
            group.append(f"{alias[t]}.{qi(c)}")
        if u["aggregate"] == "count":
            name = f"{root}_count"
            if fans_out and root_key:
                expr = "COUNT(DISTINCT " + " + '|' + ".join(f"CAST(t0.{qi(c)} AS varchar(400))" for c in root_key) + ")" if len(root_key) > 1 \
                    else f"COUNT(DISTINCT t0.{qi(root_key[0])})"
                assumptions.append(f"the path goes one-to-many, so each {root} row is counted once (DISTINCT on its key)")
            else:
                expr = "COUNT_BIG(*)"
        elif computed:
            line, qty, dim, price = computed["table"], computed["column"], computed["dimension"], computed["price"]
            measure = [line, qty]
            name = "order_amount_from_quantity_x_" + price if computed["name"] == "Order amount" else f"{line}_amount_from_quantity_x_{price}"
            inner = f"{alias[line]}.{qi(qty)} * {alias[dim]}.{qi(price)}"
            expr = f"SUM({inner})" if u["aggregate"] == "sum" else f"AVG(CAST({inner} AS float))"
            assumptions.insert(0, computed["said"])
        else:
            if u["measure"]:
                mt, mc = u["measure"]
            else:
                refs = {c.lower() for r in plan.relationships for c in r.source_cols if r.source == root}
                mt, mc = root, next((c for c in plan.schema[root].column_names if _type(plan.schema[root], c) in NUMERIC
                                     and c not in root_key and c.lower() not in refs), None)
                if mc is None:
                    raise PlanInputError(f"no numeric column in {root} to {'sum' if u['aggregate'] == 'sum' else 'average'}; name the column in the question")
                assumptions.append(f"the question names no column to {'sum' if u['aggregate'] == 'sum' else 'average'}: {root}.{mc} is the first numeric column that is neither key nor reference")
            measure = [mt, mc]
            name = f"{'total' if u['aggregate'] == 'sum' else 'average'}_{mc}"
            expr = f"SUM({alias[mt]}.{qi(mc)})" if u["aggregate"] == "sum" else f"AVG(CAST({alias[mt]}.{qi(mc)} AS float))"
            mkey = plan.keys.get(mt, ([], ""))[0]
            if (mt != root or fans_out) and mkey:
                # the total that doubles (amounts.py): mt's rows repeat once per root row, so take each mt row once
                level = (mt, mkey)
                expr = f"SUM(x.{qi(mc)})" if u["aggregate"] == "sum" else f"AVG(CAST(x.{qi(mc)} AS float))"
                assumptions.append(f"{mt}.{mc} is a value on {mt}, and the joined rows repeat each {mt} row (once per {root} row): it is "
                                   f"{'summed' if u['aggregate'] == 'sum' else 'averaged'} once per {mt} row (DISTINCT on its key "
                                   f"{' + '.join(mkey)}), never over the {root} rows: an amount on {mt} and one on {root} are different levels")
            elif fans_out and u["aggregate"] == "sum":
                assumptions.append("the path goes one-to-many, so a value can be counted more than once in the sum; check the grain")
        select.append(f"{expr} AS {qi(name)}")
        order.append(f"{qi(name)} DESC")
    else:
        select += [f"t0.{qi(c)}" for c in plan.schema[root].column_names if allowed(root, c)]
        for t in joined:
            if t != root:
                cols = [c for tt, c in u["columns_named"] if tt == t] or [_label(plan, t)]
                cols = [c for c in cols if allowed(t, c)] or plan.keys.get(t, ([], ""))[0][:1]
                select += [f"{alias[t]}.{qi(c)} AS {qi(t + '_' + c)}" for c in cols]
        if fans_out:
            back = next(s for s in steps if not s["forward"])
            assumptions.append(f"the path goes one-to-many ({back['from']} -> {back['to']}): a {root} row appears once per {back['to']} row")
        if u["latest"]:
            date_col = next((c for c in plan.schema[root].column_names if _type(plan.schema[root], c) in DATES), None)
            if date_col:
                order.append(f"t0.{qi(date_col)} DESC")
            else:
                assumptions.append(f"'latest' asked for, but {root} has no date column; ordered by its key")
        if not order and root_key:
            order += [f"t0.{qi(c)}" for c in root_key]
    top = u["top"] or (None if u["aggregate"] else 100)
    if u["aggregate"] and not group and u["top"]:
        top = None
    if level:
        mt, mkey = level
        mc = measure[1]
        outer = [g.split(".", 1)[1] for g in group]           # the grouping columns by their own names
        inner = list(dict.fromkeys(group + [f"{alias[mt]}.{qi(c)}" for c in mkey] + [f"{alias[mt]}.{qi(mc)}"]))
        names_in = []
        for i, e in enumerate(inner):
            n = e.split(".", 1)[1]
            names_in.append(f"{e} AS {n}" if n not in [x.split(" AS ")[-1] for x in names_in] else f"{e} AS {qi('c' + str(i))}")
        sql = (("SELECT " + (f"TOP ({top}) " if top else "")) + ", ".join([f"x.{c}" for c in outer] + [select[-1]])
               + "\nFROM (SELECT DISTINCT " + ", ".join(names_in) + f"\n      FROM {qi(schema)}.{qi(root)} AS t0"
               + "".join("\n      " + j for j in joins) + where.replace("\n", "\n      ") + ") AS x"
               + (("\nGROUP BY " + ", ".join(f"x.{c}" for c in outer)) if outer else "")
               + (("\nORDER BY " + ", ".join(order)) if order and group else ""))
    else:
        sql = (("SELECT " + (f"TOP ({top}) " if top else "")) + ", ".join(select) + f"\nFROM {qi(schema)}.{qi(root)} AS t0"
               + "".join("\n" + j for j in joins) + where + (("\nGROUP BY " + ", ".join(group)) if group else "")
               + (("\nORDER BY " + ", ".join(order)) if order and (group or not u["aggregate"]) else ""))
    if not u["aggregate"] and not u["top"]:
        assumptions.append("no number of rows asked for: the first 100")
    if personal_group and not u["group_table"]:
        assumptions.append(f"not grouped by {personal_group[0]}.{personal_group[1]}: it looks like personal data and the table has no key "
                           "to stand in; one total instead (show_personal_data=true groups by it)")
    elif u["aggregate"] and not group:
        assumptions.append("no grouping read from the question: one total")
    if u["count_assumed"]:
        assumptions.append("no count, sum or average named: the rows are counted per group")
    if u["not_used"]:
        assumptions.append(f"not applied: {', '.join(u['not_used'])} — conditions (dates, amounts, filters) are not read from the "
                           "question; add a WHERE to the query")
    not_understood = [f"{n}: a condition (date, amount or filter) in the question that the query does not apply; add a WHERE"
                      for n in u["not_used"]]
    return {"understood": u, "root": root, "tables": involved, "measure": measure,
            "path": [{k: v for k, v in s.items() if k not in ("rel", "cost")} for s in steps], "sql": sql, "assumptions": assumptions,
            "_steps": steps, "personal_left_out": left_out, "_personal": personal, "not_understood": not_understood,
            "value_column": ({"found": False, "said": computed["said"], "offered": computed["offered"]} if computed else
                             {"found": True, "column": ".".join(value["amount"])} if value and value.get("amount") else None)}


def _types_by_table(description: dict) -> dict[str, dict]:
    return {str(t.get("source", "")).split(".")[-1].lower(): t for t in description.get("types", [])}


def graphql(plan: Plan, description: dict, answer: dict) -> dict:
    """The GraphQL query for an answer from tsql(), against the API described by describe_definition()."""
    types = _types_by_table(description)
    u, root = answer["understood"], answer["root"]
    if answer.get("sql") is None:
        return {"not_possible": "the question was not fully understood (see not_understood), so no query is given"}
    if u.get("without") or u.get("with") or u.get("without_columns"):
        cond = ", ".join([f"no {t}" for t in u.get("without", [])] + [f"with {t}" for t in u.get("with", [])]
                         + [f"empty {t}.{c}" for t, c in u.get("without_columns", [])])
        return {"not_possible": f"Fabric's API for GraphQL filters a type by its own fields only; it cannot ask for {root} rows "
                                f"by whether related rows exist ({cond}: an anti-join or semi-join, NOT EXISTS / EXISTS). This "
                                "question has no GraphQL form on this API, and a list without that condition would answer a "
                                "different question; the T-SQL answers it"}
    if (answer.get("value_column") or {}).get("found") is False:
        return {"not_possible": "the value is computed (quantity × a price on another table), and Fabric's GraphQL aggregations "
                                "sum one column of one type; the T-SQL answers it"}
    rt = types.get(root.lower())
    if rt is None:
        return {"not_possible": f"the API has no type for {root}; describe_backend lists what it exposes"}
    if u["aggregate"]:
        group_fields = []
        if u["group_column"] and u["group_column"][0] == root:
            group_fields = [graphql_name(u["group_column"][1].lstrip("_"))]
        elif u["group_table"] and u["group_table"] != root:
            step = next((s for s in answer["_steps"] if s["to"] == u["group_table"] and s["from"] == root and s["forward"]), None)
            if step is None:
                return {"not_possible": f"Fabric's API for GraphQL groups only by a table's own columns, and {u['group_table']} is more than one "
                                        "many-to-one step from {root}; the T-SQL answers it".replace("{root}", root)}
            group_fields = [graphql_name(c.lstrip("_")) for c in step["rel"].source_cols]
        elif u["group_column"] or u["group_table"]:
            return {"not_possible": "Fabric's API for GraphQL groups only by the queried table's own columns; the T-SQL answers it"}
        if u["aggregate"] == "count":
            key = plan.keys.get(root, ([], ""))[0]
            field = graphql_name((key[0] if key else plan.schema[root].column_names[0]).lstrip("_"))
            agg = f"count(field: {field})"
        else:
            mt, mc = answer.get("measure") or [root, None]
            if mt != root or mc is None:
                return {"not_possible": f"the column to aggregate is in {mt}, not in {root}; GraphQL aggregates a table's own columns, the T-SQL answers it"}
            agg = f"{u['aggregate']}(field: {graphql_name(mc.lstrip('_'))})"
        missing = [f for f in group_fields + [agg.split("field: ")[1].rstrip(")")] if f not in rt.get("fields", [])]
        if missing:
            return {"not_possible": f"the API's {rt['type']} has no field {', '.join(missing)}"}
        if not group_fields:
            return {"not_possible": "Fabric documents its GraphQL aggregations with groupBy only; for one total, the T-SQL answers it"}
        query = (f"query {{ {rt['query_field']} {{ groupBy(fields: [{', '.join(group_fields)}]) {{ fields {{ {' '.join(group_fields)} }} "
                 f"aggregations {{ {agg} }} }} }} }}")
        notes = ["groups come back unordered and without a limit: sort and cut them in the client (Fabric's aggregations have no top N)"]
        if u["group_table"] and u["group_table"] != root:
            g = u["group_table"]
            label, key = _label(plan, g), plan.keys.get(g, ([], ""))[0]
            if label in key:
                tail = f"the T-SQL returns {', '.join(key)} too"
            elif (g, label) in answer.get("_personal", {}):
                tail = f"the T-SQL returns {', '.join(key)} only ({g}.{label}: personal data, left out)"
            else:
                tail = f"the T-SQL also returns {g}.{label}"
            notes.append(f"grouped by {', '.join(group_fields)}; {tail}")
        return {"query": query, "notes": notes}
    # a list: walk the relationship fields along the join tree
    children: dict[str, list[dict]] = {}
    for s in answer["_steps"]:
        children.setdefault(s["from"], []).append(s)

    hidden_by_table = {}
    for (t, c) in answer.get("_personal", {}):
        hidden_by_table.setdefault(t.lower(), set()).add(graphql_name(c.lstrip("_")))

    def fields_of(table: str, n: int) -> list[str]:
        t = types[table.lower()]
        return [f for f in t.get("fields", []) if not f.startswith("_") and f not in hidden_by_table.get(table.lower(), set())][:n]

    def block(table: str, depth: int) -> str:
        parts = fields_of(table, 8 if depth == 0 else 4)
        for s in children.get(table, []):
            r, tt = s["rel"], types.get(s["to"].lower())
            if tt is None:
                raise LookupError(s["to"])
            want = (r.field_name if s["forward"] else r.reverse_name) or ""
            card = "ManyToOne" if s["forward"] else "OneToMany"
            rels = [x for x in types[table.lower()].get("relationships", []) if str(x.get("to", "")).split(".")[-1].lower() == s["to"].lower()
                    and x.get("cardinality") == card]
            rel = next((x for x in rels if x.get("field") == want), rels[0] if rels else None)
            if rel is None:
                raise LookupError(f"{table} -> {s['to']}")
            inner = block(s["to"], depth + 1)
            parts.append(f"{rel['field']} {{ {inner} }}" if card == "ManyToOne" else f"{rel['field']} {{ items {{ {inner} }} }}")
        return " ".join(parts)
    try:
        body = block(root, 0)
    except LookupError as e:
        return {"not_possible": f"the API has no relationship field for {e}; plan_drift shows what differs from today's plan"}
    args = [f"first: {u['top'] or 100}"]
    if u["latest"]:
        date_col = next((c for c in plan.schema[root].column_names if _type(plan.schema[root], c) in DATES), None)
        if date_col and graphql_name(date_col.lstrip("_")) in rt.get("fields", []):
            args.append(f"orderBy: {{ {graphql_name(date_col.lstrip('_'))}: DESC }}")
    return {"query": f"query {{ {rt['query_field']}({', '.join(args)}) {{ items {{ {body} }} }} }}", "notes": []}


def draft(plan: Plan, question: str, tables: list[str], description: dict | None = None, api: str | None = None,
          show_personal_data: bool = False) -> dict:
    from . import privacy
    a = tsql(plan, question, tables, show_personal_data)
    understood = {k: v for k, v in a["understood"].items() if v not in (None, False, []) and k not in ("unread", "subject", "value_asked")}   # only what was read
    out = {"question": question}
    if a.get("value_column") and not a["value_column"]["found"]:
        out["value_column"] = a["value_column"]                                    # said first: no value column, what is offered
    out |= {"understood": understood, "tables": a["tables"], "starts_at": a["root"],
           "path": a["path"], "tsql": a["sql"], "assumptions": a["assumptions"]}
    if a["not_understood"]:
        out["not_understood"] = a["not_understood"]
    if description is not None:
        g = graphql(plan, description, a)
        out["graphql"] = dict(g, api=api)
    if a["personal_left_out"]:
        out["personal_data"] = {"left_out": [f"{x['table']}.{x['column']} ({x['rule']}: {x['what']})" for x in a["personal_left_out"]],
                                "notice": f"left out by name (privacy rules); the key stands in where the table has one. {privacy.PARAMETER}=true includes them."}
    if a["sql"] is None:
        out["runs"] = "nothing: no query is given for a question that was not fully understood; rephrase what not_understood names"
        return out
    out["runs"] = ("nothing: the T-SQL runs on the source's SQL analytics endpoint or a warehouse" +
                   ("; query_graphql with question= and tables= runs the GraphQL version" if description is not None else ""))
    return out
