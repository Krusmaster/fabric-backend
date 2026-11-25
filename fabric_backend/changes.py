"""The change contract: one small JSON request per change to a data product, checked by fixed rules against the plan.

A person who has built a data product writes a sentence in their own MCP client ("remove test customers"). The client's
model turns the sentence into one of the requests below; Krusgraph runs no model. This module is the contract between
the two (docs/CHANGES.md): the JSON schema, a canonical form, an id derived from the content, and `validate`, which
answers `ok` (the normalised change), `question` (what is ambiguous, with candidates) or `denied` (with the reason).

    filter_rows   {"type", "table", "drop_where": predicate, "cascade": [tables]}
    add_column    {"type", "table", "from", "columns": [...], "via": [links]}
    add_link      {"type", "from": {"table", "columns"}, "to": {"table", "columns"}}
    add_measure   {"type", "name", "measure": count | distinct_count | sum | ratio}
    revert        {"type", "change": "chg-..."}

A predicate is {"column", "op": "equals" | "is_true" | "is_not_empty", "value"} or {"any": [...]} / {"all": [...]} of
predicates. Nothing in a request is SQL, DAX or any other expression text: a field that would carry one is denied.

Pure functions, no I/O and no clock: the same request against the same plan gives the same answer and the same id.
Row counts in a question's candidates are the caller's (`counts`); nothing here reads a row. The rules that decide are
the engine's own: privacy.py for personal data, amounts.py for the total that doubles, the plan's relationships and
their direction (paths.py) for a join that fans out, review.py's plan id for a stale `base`.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata

from . import amounts, privacy
from .infer import Plan, _family, _stem, _words
from .paths import _edges, shortest_paths

CONTRACT = "krusgraph.change/1"
TYPES = ("filter_rows", "add_column", "add_link", "add_measure", "revert")
OPS = ("equals", "is_true", "is_not_empty")
FORMS = ("count", "distinct_count", "sum", "ratio")
RESULTS = ("ok", "question", "denied")
QUESTIONS = {
    "filter_column": "filter_rows names no column: which column says that a row goes",
    "cascade": "other tables point at the filtered one: whether their rows go too",
    "path": "add_column has several equally short join paths that repeat no row: which one",
    "link": "add_column has no join path that repeats no row: which link to add first",
    "link_direction": "add_link points from a key at a column that is not a key: whether it was meant the other way",
    "revert_dependent": "a later change in the list stands on the change a revert takes out: whether to revert that one first",
}
DENIALS = {
    "bad_request": "the request is not shaped as the contract says",
    "unknown_contract": "the request names a contract version this server does not read",
    "unknown_type": "the change type is not one of the five",
    "unknown_field": "the request has a field the contract does not have",
    "free_text": "the request carries SQL or another expression as text",
    "instruction_like": "a name reads like an instruction to a model",
    "too_complex": "the predicate is deeper or longer than the contract allows",
    "stale_base": "the change was written against another plan than the current one",
    "unknown_table": "a table is not in the plan",
    "unknown_column": "a column is not in its table",
    "personal_data": "a column looks like personal data (privacy.py, by name)",
    "wrong_type": "an operation does not fit the column's type",
    "not_dependent": "a cascade table does not point at the filtered table",
    "cascade_gap": "a cascade table reaches the filtered table only through a table that is not in the cascade",
    "no_change": "the change would change nothing",
    "already_exists": "what the change adds is already there",
    "unknown_link": "a link in via is not a relationship of the plan",
    "bad_via": "the links in via do not lead from the table to the table the columns come from",
    "fan_out": "the join path repeats rows (one-to-many)",
    "repeated_amount": "an amount would be repeated on every row it is joined to",
    "no_path": "no relationship connects the two tables",
    "type_mismatch": "the two sides of a link have different types",
    "not_a_key": "a link must point at the key of its target table",
    "not_additive": "a sum over a column that is not a number, or is a key or a reference",
    "unknown_measure": "a ratio names a measure that does not exist",
    "unknown_change": "revert names a change that was not applied",
    "already_reverted": "revert names a change that an earlier revert already took out",
}

MAX_NAME = 128
MAX_VALUE = 200
MAX_DEPTH = 4
MAX_LEAVES = 20
MAX_HOPS = 5
MAX_CANDIDATES = 8

_ID = re.compile(r"^chg-[0-9a-f]{16}$")
_PLAN_ID = re.compile(r"^plan-[0-9a-f]{12}$")
_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{16}$")
_TYPE_WORD = re.compile(r"^[a-z_]{1,40}$")
_MEASURE_NAME = re.compile(r"^[^\W_][\w %/().,:+&-]{0,79}$")
# Field names that say "here comes an expression": denied as free text whatever they hold.
_TEXT_FIELDS = {"sql", "where", "expression", "expr", "dax", "query", "raw", "formula", "condition", "filter", "predicate",
                "code", "script", "having", "select", "tsql", "m", "python"}
_VALUE_MARKS = (";", "--", "/*", "*/", "`")

# A name that reads like an instruction (judged by the name only, like privacy.py). A column name comes from the data
# owner's source and travels back to the client's model in an answer, so such a name is never accepted and never echoed.
INSTRUCTION_RULES = {
    "N1": "the name is shaped like text, not like a name: a control character, a line break, markup or more than eight words",
    "N2": "the name pairs an order (ignore, disregard, forget, bypass, override, reveal ...) with what a model is told "
          "(instructions, prompt, previous, system ...)",
    "N3": "the name addresses the reader (you are, you must, system prompt, as an AI ...)",
}
_ORDER = {"ignore", "disregard", "forget", "bypass", "jailbreak", "exfiltrate", "pretend", "reveal", "override", "obey"}
_TOLD = {"instruction", "instructions", "prompt", "prompts", "previous", "prior", "above", "guardrail", "guardrails", "system",
         "safety"}
_ADDRESS = (("you", "are"), ("you", "must"), ("you", "should"), ("you", "will"), ("you", "shall"), ("as", "an", "ai"),
            ("system", "prompt"), ("developer", "message"), ("new", "instructions"), ("do", "not", "tell"),
            ("assistant", "must"), ("assistant", "should"), ("call", "the", "tool"))
_MARKUP = set("<>{}`")

# A flag column by name or type: what "remove the test rows" most often means. Listed, never chosen.
_FLAG_FIRST = {"is", "has"}
_FLAG_WORDS = {"flag", "test", "demo", "dummy", "fake", "internal", "deleted", "inactive", "archived", "obsolete", "sample"}
_BOOL = ("bool", "bit")


class ChangeError(ValueError):
    """A request the contract does not accept: `kind` is a key of DENIALS, `reason` says it in plain words."""

    def __init__(self, kind: str, reason: str):
        super().__init__(reason)
        self.kind, self.reason = kind, reason


class _Ask(Exception):
    def __init__(self, kind: str, question: str, candidates: list, answer_with: str):
        super().__init__(question)
        self.kind, self.question, self.candidates, self.answer_with = kind, question, candidates, answer_with


# ------------------------------------------------------------------ names ---------------------------------------------

def reads_like_instruction(name: str) -> str | None:
    """The rule (N1-N3) by which a name reads like an instruction to a model, or None."""
    if len(name) > MAX_NAME or any(ch in _MARKUP or unicodedata.category(ch).startswith("C") for ch in name):
        return "N1"
    words = _words(name)
    if len(words) > 8:
        return "N1"
    if set(words) & _ORDER and set(words) & _TOLD:
        return "N2"
    for seq in _ADDRESS:
        if any(tuple(words[i:i + len(seq)]) == seq for i in range(len(words) - len(seq) + 1)):
            return "N3"
    return None


def _text(v) -> str:
    return unicodedata.normalize("NFC", v).strip()


def _name(v, what: str) -> str:
    if not isinstance(v, str) or not _text(v):
        raise ChangeError("bad_request", f"{what} must be a name (a non-empty string).")
    name = _text(v)
    rule = reads_like_instruction(name)
    if rule:
        raise ChangeError("instruction_like", f"{what} reads like an instruction, not like a name (rule {rule}: "
                                              f"{INSTRUCTION_RULES[rule]}). It is not repeated here and nothing was looked up.")
    return name


def _names(v, what: str) -> list[str]:
    if isinstance(v, str):
        v = [v]
    if not isinstance(v, list) or not v:
        raise ChangeError("bad_request", f"{what} must be a list of at least one name.")
    return [_name(x, f"a name in {what}") for x in v]


def _fields(d: dict, allowed: set[str], where: str, required: tuple[str, ...] = ()) -> None:
    for k in d:
        if not isinstance(k, str):
            raise ChangeError("bad_request", f"{where}: a field name is not a string.")
        if k in allowed:
            continue
        if k.lower() in _TEXT_FIELDS:
            raise ChangeError("free_text", f"{where} has a field for an expression as text. The contract takes no SQL, DAX or other "
                                           "expression: a filter is a predicate over named columns, a measure is one of the forms "
                                           f"{', '.join(FORMS)}.")
        shown = repr(k) if _TYPE_WORD.match(k) else "one that is not named here"
        raise ChangeError("unknown_field", f"{where} has a field the contract does not have ({shown}); it takes {', '.join(sorted(allowed))}.")
    missing = [k for k in required if k not in d]
    if missing:
        raise ChangeError("bad_request", f"{where} lacks {', '.join(missing)}.")


def _structure(v, where: str) -> dict:
    if isinstance(v, str):
        raise ChangeError("free_text", f"{where} is text. The contract takes no SQL, DAX or other expression as text; {where} is a "
                                       "JSON object (docs/CHANGES.md).")
    if not isinstance(v, dict):
        raise ChangeError("bad_request", f"{where} must be a JSON object.")
    return v


# ------------------------------------------------------------------ the canonical form --------------------------------

def _dump(v) -> str:
    return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _value(v):
    if isinstance(v, bool) or isinstance(v, int):
        return v
    if isinstance(v, float):
        if not math.isfinite(v):
            raise ChangeError("bad_request", "A value to compare with must be a finite number.")
        return int(v) if v == int(v) else v
    if isinstance(v, str):
        s = unicodedata.normalize("NFC", v)
        if len(s) > MAX_VALUE or any(unicodedata.category(ch).startswith("C") for ch in s) or any(m in s for m in _VALUE_MARKS):
            raise ChangeError("free_text", "A value to compare with is one plain value: at most "
                                           f"{MAX_VALUE} characters, no line break and none of {' '.join(_VALUE_MARKS)}. It is compared "
                                           "as a value, never run.")
        return s
    raise ChangeError("bad_request", "A value to compare with must be a string, a number or true/false.")


def _predicate(v, depth: int = 1) -> dict:
    v = _structure(v, "drop_where")
    if depth > MAX_DEPTH:
        raise ChangeError("too_complex", f"drop_where is nested deeper than {MAX_DEPTH} levels.")
    group = [k for k in ("any", "all") if k in v]
    if group:
        _fields(v, {"any", "all"}, "A group in drop_where")
        if len(group) != 1:
            raise ChangeError("bad_request", "A group in drop_where is either any or all, not both.")
        op = group[0]
        if not isinstance(v[op], list) or not v[op]:
            raise ChangeError("bad_request", f"{op} in drop_where must be a list of at least one predicate.")
        parts: dict[str, dict] = {}
        for child in v[op]:
            c = _predicate(child, depth + 1)
            for x in (c[op] if op in c else [c]):                  # any inside any is one any
                parts[_dump(x)] = x
        ordered = [parts[k] for k in sorted(parts)]
        return ordered[0] if len(ordered) == 1 else {op: ordered}
    _fields(v, {"column", "op", "value"}, "A predicate in drop_where", required=("column", "op"))
    if v["op"] not in OPS:
        if isinstance(v["op"], str) and not _TYPE_WORD.match(v["op"]):
            raise ChangeError("free_text", f"op in drop_where is one of {', '.join(OPS)}, not an expression.")
        raise ChangeError("bad_request", f"op in drop_where must be one of {', '.join(OPS)}.")
    out = {"column": _name(v["column"], "column in drop_where"), "op": v["op"]}
    if v["op"] == "equals":
        if "value" not in v:
            raise ChangeError("bad_request", "equals in drop_where needs a value.")
        out["value"] = _value(v["value"])
    elif "value" in v:
        raise ChangeError("bad_request", f"{v['op']} in drop_where takes no value.")
    return out


def _leaves(p: dict) -> list[dict]:
    for op in ("any", "all"):
        if op in p:
            return [leaf for c in p[op] for leaf in _leaves(c)]
    return [p]


def _side(v, where: str) -> dict:
    v = _structure(v, where)
    _fields(v, {"table", "columns"}, where, required=("table", "columns"))
    return {"table": _name(v["table"], f"table in {where}"), "columns": _names(v["columns"], f"columns in {where}")}


def _link(v, where: str) -> dict:
    v = _structure(v, where)
    _fields(v, {"from", "to"}, where, required=("from", "to"))
    a, b = _side(v["from"], f"from in {where}"), _side(v["to"], f"to in {where}")
    if len(a["columns"]) != len(b["columns"]):
        raise ChangeError("bad_request", f"{where}: from and to must name the same number of columns, pair by pair.")
    pairs = sorted(set(zip(a["columns"], b["columns"])))            # a link is a set of column pairs
    return {"from": {"table": a["table"], "columns": [p[0] for p in pairs]},
            "to": {"table": b["table"], "columns": [p[1] for p in pairs]}}


def _operand(v, where: str, ratio: bool) -> dict:
    v = _structure(v, where)
    if "measure" in v and "form" not in v:
        if not ratio:
            raise ChangeError("bad_request", f"{where}: a measure by name is only a part of a ratio.")
        _fields(v, {"measure"}, where)
        return {"measure": _measure_name(v["measure"], f"measure in {where}")}
    if v.get("form") not in FORMS:
        if isinstance(v.get("form"), str) and not _TYPE_WORD.match(v["form"]):
            raise ChangeError("free_text", f"form in {where} is one of {', '.join(FORMS)}, not an expression.")
        raise ChangeError("bad_request", f"{where} needs a form: one of {', '.join(FORMS)}.")
    form = v["form"]
    if form == "ratio":
        if ratio:
            raise ChangeError("bad_request", f"{where}: a ratio's parts are count, distinct_count, sum or an existing measure, not a ratio.")
        _fields(v, {"form", "numerator", "denominator"}, where, required=("numerator", "denominator"))
        return {"form": form, "numerator": _operand(v["numerator"], "numerator", True),
                "denominator": _operand(v["denominator"], "denominator", True)}
    if form == "count":
        _fields(v, {"form", "table"}, where, required=("table",))
        return {"form": form, "table": _name(v["table"], f"table in {where}")}
    _fields(v, {"form", "table", "column"}, where, required=("table", "column"))
    return {"form": form, "table": _name(v["table"], f"table in {where}"), "column": _name(v["column"], f"column in {where}")}


def _measure_name(v, where: str) -> str:
    name = " ".join(_name(v, where).split())
    if not _MEASURE_NAME.match(name):
        raise ChangeError("bad_request", f"{where} must be a short name: at most 80 characters, starting with a letter or a digit, "
                                         "of letters, digits, spaces and % / ( ) . , : + & -.")
    return name


def _base(v) -> dict:
    v = _structure(v, "base")
    _fields(v, {"plan_id", "schema_fingerprint"}, "base")
    if not v:
        raise ChangeError("bad_request", "base names the plan the change was written against: plan_id, schema_fingerprint or both.")
    for k, shape in (("plan_id", _PLAN_ID), ("schema_fingerprint", _FINGERPRINT)):
        if k in v and not (isinstance(v[k], str) and shape.match(v[k])):
            raise ChangeError("bad_request", f"base.{k} is not shaped like one ({shape.pattern}).")
    return dict(v)


def canonical(change) -> dict:
    """The change in its canonical form, checked against the contract's shape only (no plan): every name trimmed and in
    Unicode NFC, lists that are sets sorted and without repeats (the columns of add_column, the tables of cascade, the
    predicates of an any/all, the column pairs of a link), a group of one predicate as that predicate, a whole number as
    an integer, and `contract` always present. Idempotent: canonical(canonical(x)) == canonical(x). Raises ChangeError."""
    change = _structure(change, "The change")
    kind = change.get("type")
    if not isinstance(kind, str) or kind not in TYPES:
        shown = f" ({kind!r})" if isinstance(kind, str) and _TYPE_WORD.match(kind) else ""
        raise ChangeError("unknown_type", f"The change type{shown} is not one of {', '.join(TYPES)}.")
    if change.get("contract", CONTRACT) != CONTRACT:
        raise ChangeError("unknown_contract", f"This server reads {CONTRACT}.")
    common = {"type", "contract", "base"}
    out: dict = {"contract": CONTRACT, "type": kind}
    if "base" in change:
        out["base"] = _base(change["base"])
    if kind == "filter_rows":
        _fields(change, common | {"table", "drop_where", "cascade"}, "filter_rows", required=("table",))
        out["table"] = _name(change["table"], "table")
        if "drop_where" in change:
            out["drop_where"] = _predicate(change["drop_where"])
            if len(_leaves(out["drop_where"])) > MAX_LEAVES:
                raise ChangeError("too_complex", f"drop_where has more than {MAX_LEAVES} predicates.")
        if "cascade" in change:
            if not isinstance(change["cascade"], list):
                raise ChangeError("bad_request", "cascade is a list of table names; an empty list means that no other table's rows go.")
            out["cascade"] = sorted({_name(t, "a table in cascade") for t in change["cascade"]})
    elif kind == "add_column":
        _fields(change, common | {"table", "from", "columns", "via"}, "add_column", required=("table", "from", "columns"))
        if isinstance(change["from"], dict):
            raise ChangeError("bad_request", "from in add_column is the name of the table the columns come from.")
        out.update(table=_name(change["table"], "table"), columns=sorted(set(_names(change["columns"], "columns"))))
        out["from"] = _name(change["from"], "from")
        if "via" in change:
            via = change["via"] if isinstance(change["via"], list) else [change["via"]]
            if not via:
                raise ChangeError("bad_request", "via is a link or a list of links; leave it out to let the plan give the path.")
            out["via"] = [_link(x, "a link in via") for x in via]
    elif kind == "add_link":
        _fields(change, common | {"from", "to"}, "add_link", required=("from", "to"))
        out.update(_link({"from": change["from"], "to": change["to"]}, "add_link"))
    elif kind == "add_measure":
        _fields(change, common | {"name", "measure"}, "add_measure", required=("name", "measure"))
        out.update(name=_measure_name(change["name"], "name"), measure=_operand(change["measure"], "measure", False))
    else:
        _fields(change, common | {"change"}, "revert", required=("change",))
        if not isinstance(change["change"], str) or not _ID.match(change["change"]):
            raise ChangeError("bad_request", "change in revert is the id of an applied change (chg- and sixteen hexadecimal digits).")
        out["change"] = change["change"]
    return out


def canonical_json(change) -> str:
    """The canonical form as text: keys sorted, no spaces, UTF-8 as it is. This is what the id is the hash of."""
    return _dump(canonical(change))


def change_id(change) -> str:
    """`chg-` and the first sixteen hexadecimal digits of the SHA-256 of the canonical JSON. No clock and no counter:
    the same change gives the same id, anywhere."""
    return "chg-" + hashlib.sha256(canonical_json(change).encode("utf-8")).hexdigest()[:16]


# ------------------------------------------------------------------ the plan's side -----------------------------------

def plan_mark(plan: Plan) -> dict:
    """The current plan's id and schema fingerprint, as the review file and the pipeline compute them."""
    from . import review
    from .drift import plan_snapshot
    snap = plan_snapshot(plan)
    return {"plan_id": review.plan_id(snap), "schema_fingerprint": review.schema_fingerprint(snap)}


def link_id(source: str, source_cols, target: str, target_cols) -> str:
    """How a link is named in `counts["links"]`: orders.ship_to_id->addresses.address_id (columns joined with +)."""
    return f"{source}.{'+'.join(source_cols)}->{target}.{'+'.join(target_cols)}"


def _as_link(r) -> dict:
    return {"from": {"table": r.source, "columns": list(r.source_cols)}, "to": {"table": r.target, "columns": list(r.target_cols)}}


def _safe_name(name: str) -> bool:
    return reads_like_instruction(name) is None


class _Checker:
    def __init__(self, plan: Plan, counts: dict | None, applied, measures, reverted=None):
        self.plan, self.counts = plan, counts or {}
        # applied: ids, or the entries of apply's answer ({"id", "type", "change", "resolved", "given"}), in the list's order
        self.entries = [x for x in applied or [] if isinstance(x, dict) and isinstance(x.get("id"), str)]
        self.applied = None if applied is None else {i for x in applied for i in (
            (x.get("id"), x.get("given")) if isinstance(x, dict) else (x,)) if isinstance(i, str)}
        self.reverted = {x for x in reverted or [] if isinstance(x, str)}
        self.personal = privacy.personal_columns(plan.schema)
        own = [m["name"] for m in amounts.order_amount_measures(plan)["measures"]]
        self.measures = {m.casefold(): m for m in [*own, *(measures or [])] if isinstance(m, str)}
        self.notes: list[str] = []

    # names -------------------------------------------------------------------------------------------------------
    def table(self, name: str) -> str:
        if name in self.plan.schema:
            return name
        hits = [t.name for t in self.plan.schema if t.name.casefold() == name.casefold()]
        if len(hits) == 1:
            return hits[0]
        known = sorted(t.name for t in self.plan.schema if _safe_name(t.name))
        raise ChangeError("unknown_table", f"There is no table {name!r} in the plan"
                          + (" (several differ only by case: write it exactly)" if hits else "")
                          + f". Its tables: {', '.join(known[:40])}" + (f" and {len(known) - 40} more." if len(known) > 40 else "."))

    def column(self, table: str, name: str, personal: bool = True) -> str:
        t = self.plan.schema[table]
        if name in t.column_names:
            col = name
        elif t.has(name):
            col = t.col(name)
        else:
            raise ChangeError("unknown_column", f"There is no column {name!r} in {table}.")
        found = self.personal.get((table, col))
        if personal and found:
            raise ChangeError("personal_data", f"{table}.{col} looks like personal data ({found['what']}, rule {found['rule']}: "
                                               f"{found['why']}). A change neither filters on such a column, copies it nor measures it.")
        return col

    def type_of(self, table: str, column: str) -> str:
        return next((c.data_type or "" for c in self.plan.schema[table].columns if c.name == column), "").lower()

    def key(self, table: str) -> list[str]:
        return list(self.plan.keys.get(table, ([], ""))[0])

    def count(self, *path):
        v = self.counts
        for p in path:
            v = v.get(p) if isinstance(v, dict) else None
        return v if isinstance(v, int) and not isinstance(v, bool) else None

    def link_counts(self, link: dict) -> dict | None:
        c = (self.counts.get("links") or {}).get(link_id(link["from"]["table"], link["from"]["columns"],
                                                         link["to"]["table"], link["to"]["columns"]))
        return {k: v for k, v in c.items() if isinstance(v, int) and not isinstance(v, bool)} if isinstance(c, dict) else None

    def link(self, link: dict) -> dict:
        """A link with its tables and columns in the plan's own spelling."""
        a, b = self.table(link["from"]["table"]), self.table(link["to"]["table"])
        return {"from": {"table": a, "columns": [self.column(a, c) for c in link["from"]["columns"]]},
                "to": {"table": b, "columns": [self.column(b, c) for c in link["to"]["columns"]]}}

    def relationship(self, link: dict):
        """The plan's relationship a link names, written in either direction; None when the plan has none."""
        def same(r, x, y) -> bool:
            return (r.source == x["table"] and r.target == y["table"]
                    and sorted(zip((c.lower() for c in r.source_cols), (c.lower() for c in r.target_cols)))
                    == sorted(zip((c.lower() for c in x["columns"]), (c.lower() for c in y["columns"]))))
        for r in self.plan.relationships:
            if same(r, link["from"], link["to"]) or same(r, link["to"], link["from"]):
                return r
        return None

    # filter_rows -------------------------------------------------------------------------------------------------
    def flags(self, table: str) -> list[dict]:
        out = []
        for c in self.plan.schema[table].columns:
            if c.name not in self.plan.schema[table].column_names or (table, c.name) in self.personal or not _safe_name(c.name):
                continue
            words, typed = _words(c.name), any(b in (c.data_type or "").lower() for b in _BOOL)
            named = bool(words) and (words[0] in _FLAG_FIRST or bool(set(words) & _FLAG_WORDS))
            if not (typed or named):
                continue
            entry = {"column": c.name, "type": (c.data_type or "").lower(),
                     "why": " and ".join(w for w in ("its type is true/false" if typed else "", "its name reads like a flag" if named else "") if w),
                     "drop_where": {"column": c.name, "op": "is_true"}}
            for k, path in (("rows_true", ("true", table, c.name)), ("rows", ("rows", table))):
                if self.count(*path) is not None:
                    entry[k] = self.count(*path)
            out.append(entry)
        return sorted(out, key=lambda e: e["column"].lower())[:MAX_CANDIDATES]

    def dependents(self, table: str) -> dict[str, int]:
        """Every table whose rows point, directly or through other tables, at rows of `table`: {table: hops}."""
        seen, frontier, hop = {table: 0}, [table], 0
        while frontier:
            hop += 1
            nxt = []
            for r in self.plan.relationships:
                if r.target in frontier and r.source not in seen:
                    seen[r.source] = hop
                    nxt.append(r.source)
            frontier = nxt
        del seen[table]
        return seen

    def predicate(self, table: str, p: dict) -> dict:
        for op in ("any", "all"):
            if op in p:
                return {op: [self.predicate(table, c) for c in p[op]]}
        col = self.column(table, p["column"])
        kind, typ = _family(self.type_of(table, col)), self.type_of(table, col)
        boolean = any(b in typ for b in _BOOL)
        if p["op"] == "is_true" and not (boolean or (kind == "number" and "int" in typ)):
            raise ChangeError("wrong_type", f"is_true needs a true/false column or a whole-number flag; {table}.{col} is {typ or 'untyped'}. "
                                            "Use equals with the value that marks the rows.")
        if p["op"] == "equals":
            v = p["value"]
            fits = (isinstance(v, bool) and (boolean or "int" in typ)) or \
                   (not isinstance(v, bool) and isinstance(v, (int, float)) and kind == "number") or \
                   (isinstance(v, str) and kind != "number" and not boolean)
            if not fits:
                raise ChangeError("wrong_type", f"The value compared with {table}.{col} ({typ or 'untyped'}) is "
                                                f"{'true/false' if isinstance(v, bool) else 'a number' if not isinstance(v, str) else 'text'}; "
                                                "the two must be of the same kind.")
        return {**p, "column": col}

    def filter_rows(self, c: dict) -> tuple[dict, dict]:
        table = self.table(c["table"])
        out = {"table": table}
        if "drop_where" not in c:
            cands = self.flags(table)
            raise _Ask("filter_column",
                       f"Which rows of {table} go? The change names no column. "
                       + (f"{len(cands)} column(s) of {table} read like a flag, by name or type." if cands else
                          f"No column of {table} reads like a flag by name or type: name the column and the value that marks the rows."),
                       cands, "drop_where")
        merged = canonical({"type": "filter_rows", "table": table, "drop_where": self.predicate(table, c["drop_where"])})
        out["drop_where"] = merged["drop_where"]                   # canonical again: two spellings of one column are one predicate
        deps = self.dependents(table)
        chosen = [self.table(t) for t in c["cascade"]] if "cascade" in c else None
        if chosen is None and deps:
            cands = []
            for t in sorted(deps, key=lambda x: (deps[x], x.lower())):
                if not _safe_name(t):
                    continue
                entry = {"table": t, "points_at": "directly" if deps[t] == 1 else f"through {deps[t] - 1} table(s)",
                         "through": [_as_link(r) for r in self.plan.relationships if r.source == t and r.target != t
                                     and (r.target == table or r.target in deps)]}
                for k, path in (("rows", ("rows", t)), ("rows_affected", ("cascade", t))):
                    if self.count(*path) is not None:
                        entry[k] = self.count(*path)
                cands.append(entry)
            direct = sum(1 for t in deps if deps[t] == 1)
            raise _Ask("cascade",
                       f"{direct} table(s) point at {table}" + (f", and {len(deps) - direct} more through them" if len(deps) > direct else "")
                       + f". Without a cascade their rows stay and point at {table} rows that are gone. Should those rows go too? "
                         "Answer with cascade: the tables whose rows go with them, or an empty list to keep them all.",
                       cands, "cascade")
        chosen = sorted(set(chosen or []), key=str.lower)
        for t in chosen:
            if t not in deps:
                raise ChangeError("not_dependent", f"{t} does not point at {table}, directly or through other tables, by the plan's "
                                                   "relationships: there is nothing to cascade to.")
        reached, left = {table}, list(chosen)
        while left:
            step = [t for t in left if any(r.source == t and r.target in reached for r in self.plan.relationships)]
            if not step:
                raise ChangeError("cascade_gap", f"{', '.join(left)} reach(es) {table} only through a table that is not in the cascade. "
                                                 "Add the table in between, or leave this one out.")
            reached.update(step)
            left = [t for t in left if t not in step]
        out["cascade"] = chosen
        kept = sorted((t for t in deps if t not in chosen and _safe_name(t)), key=str.lower)
        if kept:
            self.notes.append(f"Rows of {', '.join(kept)} that point at removed rows stay and will point at nothing.")
        resolved = {"cascade": [{"table": t, "through": [_as_link(r) for r in self.plan.relationships
                                                         if r.source == t and r.target != t and r.target in reached]} for t in chosen]}
        return out, resolved

    # add_column --------------------------------------------------------------------------------------------------
    def repeats(self, r, forward: bool) -> bool:
        """Whether a step repeats rows of where it starts: against the relationship's direction (one-to-many), unless
        the reference is the source's own key (one-to-one, amounts.py's exception)."""
        return not forward and not amounts._one_to_one(self.plan, r)

    def safe_paths(self, start: str, end: str) -> list[list[tuple]]:
        """Every path from start to end, of at most MAX_HOPS steps, on which no step repeats a row; shortest first."""
        adj, out = _edges(self.plan), []

        def walk(node: str, steps: list, seen: set) -> None:
            if len(out) >= MAX_CANDIDATES * 4 or len(steps) > MAX_HOPS:
                return
            if node == end:
                out.append(list(steps))
                return
            for nxt, r, fwd in sorted(adj.get(node, []), key=lambda e: (e[0].lower(), e[1].source_cols, e[2])):
                if nxt in seen or self.repeats(r, fwd):
                    continue
                walk(nxt, steps + [(r, fwd)], seen | {nxt})
        walk(start, [], {start})
        return sorted(out, key=len)

    def fan_out(self, start: str, steps: list[tuple]) -> str:
        node, said = start, ""
        for r, fwd in steps:
            nxt = r.target if fwd else r.source
            if self.repeats(r, fwd) and not said:
                said = (f"{node} to {nxt} is one-to-many ({nxt}.{'+'.join(r.source_cols)} points at {node}): one row of {node} "
                        f"meets several rows of {nxt}")
            node = nxt
        tables = [start] + [(r.target if fwd else r.source) for r, fwd in steps]
        return (f"The join path {' → '.join(tables)} fans out: {said}, so every row of {start} would be repeated and its numbers "
                f"counted more than once. {amounts.RULE}")

    def link_candidates(self, table: str, source: str) -> list[dict]:
        """Links that would connect `table` to `source` many-to-one and are not in the plan: what the plan proposed and
        did not apply, and reference-like columns of `table` with the type of `source`'s single key."""
        out: dict[str, dict] = {}
        for p in self.plan.proposed:
            if p.get("source") == table and p.get("target") == source and p.get("source_cols") and p.get("target_cols"):
                link = {"from": {"table": table, "columns": list(p["source_cols"])}, "to": {"table": source, "columns": list(p["target_cols"])}}
                out[_dump(link)] = {"link": link, "why": f"the plan proposed it ({p.get('rule', 'R5')}) and did not apply it", "score": 3}
        key = self.key(source)
        linked = {c.lower() for r in self.plan.relationships if r.source == table for c in r.source_cols}
        if len(key) == 1:
            for col in self.plan.schema[table].column_names:
                stem, suffix = _stem(col)
                if not suffix or col.lower() in linked or col in self.key(table) or (table, col) in self.personal:
                    continue
                if _family(self.type_of(table, col)) != _family(self.type_of(source, key[0])):
                    continue
                shared = bool(set(stem) & set(_words(source)))
                link = {"from": {"table": table, "columns": [col]}, "to": {"table": source, "columns": [key[0]]}}
                out.setdefault(_dump(link), {
                    "link": link, "score": 2 if shared else 1,
                    "why": f"{table}.{col} ends in {suffix!r} like a reference, is in no relationship and has the type of {source}.{key[0]}"
                           + ("; the names share a word" if shared else "; nothing in the name says it points at " + source)})
        cands = []
        for c in sorted(out.values(), key=lambda c: (-c["score"], _dump(c["link"]))):
            names = [c["link"]["from"]["table"], c["link"]["to"]["table"], *c["link"]["from"]["columns"], *c["link"]["to"]["columns"]]
            if not all(_safe_name(n) for n in names):
                continue
            entry = {"change": {"type": "add_link", **c["link"]}, "why": c["why"]}
            if self.link_counts(c["link"]) is not None:
                entry["counts"] = self.link_counts(c["link"])
            cands.append(entry)
        return cands[:MAX_CANDIDATES]

    def add_column(self, c: dict) -> tuple[dict, dict]:
        table, source = self.table(c["table"]), self.table(c["from"])
        if table == source:
            raise ChangeError("no_change", f"The columns already are in {table}: table and from are the same table.")
        cols = sorted({self.column(source, x) for x in c["columns"]}, key=str.lower)
        clash = [x for x in cols if self.plan.schema[table].has(x)]
        if clash:
            raise ChangeError("already_exists", f"{table} already has a column named {', '.join(clash)}.")
        if "via" in c:
            steps, node = [], table
            for raw in c["via"]:
                link = self.link(raw)
                r = self.relationship(link)
                if r is None:
                    raise ChangeError("unknown_link", f"{link_id(link['from']['table'], link['from']['columns'], link['to']['table'], link['to']['columns'])} "
                                                      "is not a relationship of the plan. Add it with add_link first, plan again, and "
                                                      "send this change against the new plan.")
                if r.source == node:
                    steps.append((r, True))
                    node = r.target
                elif r.target == node:
                    steps.append((r, False))
                    node = r.source
                else:
                    raise ChangeError("bad_via", f"The links in via do not form a path: one starts at neither end of {node}. "
                                                 f"They lead from {table} to {source}, in that order.")
            if node != source:
                raise ChangeError("bad_via", f"The links in via lead from {table} to {node}, not to {source}.")
            if any(self.repeats(r, fwd) for r, fwd in steps):
                raise ChangeError("fan_out", self.fan_out(table, steps))
        else:
            safe = self.safe_paths(table, source)
            if len(safe) > 1 and len(safe[1]) > len(safe[0]):           # one shortest path: join_path's choice, and said
                longer = [" → ".join([table] + [(r.target if f else r.source) for r, f in p]) for p in safe[1:]]
                longer = [x for x in longer if _safe_name(x)]
                self.notes.append(f"The columns come over the shortest path. {len(safe) - 1} longer path(s) also repeat no row"
                                  + (f" ({'; '.join(longer[:3])})" if longer else "") + " and may mean something else: send via to choose one.")
            elif len(safe) > 1:
                cands = []
                for p in safe[:MAX_CANDIDATES]:
                    entry = {"via": [_as_link(r) for r, _ in p], "tables": [table] + [(r.target if f else r.source) for r, f in p],
                             "hops": len(p)}
                    counted = {link_id(r.source, r.source_cols, r.target, r.target_cols): self.link_counts(_as_link(r)) for r, _ in p}
                    if any(v is not None for v in counted.values()):
                        entry["counts"] = {k: v for k, v in counted.items() if v is not None}
                    if all(_safe_name(n) for n in entry["tables"]):
                        cands.append(entry)
                raise _Ask("path", f"{len(safe)} join paths lead from {table} to {source} without repeating a row, and none is "
                                   "shorter than the others. Which one do the columns come over?", cands, "via")
            if not safe:
                any_path = shortest_paths(self.plan, table, source, 1)
                cands = self.link_candidates(table, source)
                if cands:
                    raise _Ask("link",
                               (f"The only join path from {table} to {source} repeats rows ({' → '.join([table] + [(r.target if f else r.source) for r, f in any_path[0]])}). "
                                if any_path else f"No relationship connects {table} and {source}. ")
                               + f"{len(cands)} column(s) of {table} could be a link to {source}; none is in the plan, and none is "
                                 "counted until validate_plan counts it. Which one, if any? Send it as add_link, plan again, then "
                                 "send this change with via.", cands, "add_link")
                if any_path:
                    raise ChangeError("fan_out", self.fan_out(table, any_path[0]))
                raise ChangeError("no_path", f"No relationship connects {table} and {source}, and no column of {table} looks like a "
                                             f"reference to {source}. A link has to be added with add_link first.")
            steps = safe[0]
        if any(fwd and not amounts._one_to_one(self.plan, r) for r, fwd in steps):
            header = amounts.columns(self.plan)
            repeated = [x for x in cols if (source, x) in header or amounts.looks_like_amount(x, self.type_of(source, x))
                        or amounts.is_hours(x, self.type_of(source, x))]
            if repeated:
                raise ChangeError("repeated_amount",
                                  f"{source}.{', '.join(repeated)} is an amount with one value per row of {source}; copied to {table} "
                                  f"it stands on every {table} row that points at it, and a sum over {table} counts it once per row. "
                                  f"{amounts.RULE} Add it as a measure (add_measure) instead.")
        resolved = {"path": [table] + [(r.target if f else r.source) for r, f in steps],
                    "columns": [{"column": x, "type": self.type_of(source, x)} for x in cols]}
        return {"table": table, "from": source, "columns": cols, "via": [_as_link(r) for r, _ in steps]}, resolved

    # add_link ----------------------------------------------------------------------------------------------------
    def add_link(self, c: dict) -> tuple[dict, dict]:
        link = self.link(c)
        a, b = link["from"], link["to"]
        if self.relationship(link) is not None:
            r = self.relationship(link)
            raise ChangeError("already_exists", f"The plan already has {link_id(r.source, r.source_cols, r.target, r.target_cols)} (rule {self.plan.label(r.rule)}).")
        if a["table"] == b["table"] and [x.lower() for x in a["columns"]] == [x.lower() for x in b["columns"]]:
            raise ChangeError("no_change", "A link from a column to itself says nothing.")
        for x, y in zip(a["columns"], b["columns"]):
            fx, fy = _family(self.type_of(a["table"], x)), _family(self.type_of(b["table"], y))
            if fx != fy:
                raise ChangeError("type_mismatch", f"{a['table']}.{x} is {fx} and {b['table']}.{y} is {fy}: a link compares the two for "
                                                   "equality, so they must be of the same kind.")
        key = self.key(b["table"])
        if {x.lower() for x in key} != {x.lower() for x in b["columns"]}:
            own = self.key(a["table"])
            if own and {x.lower() for x in own} == {x.lower() for x in a["columns"]}:
                flipped = {"type": "add_link", "from": b, "to": a}
                raise _Ask("link_direction",
                           f"{a['table']}.{'+'.join(a['columns'])} is the key of {a['table']}, and {b['table']}.{'+'.join(b['columns'])} is "
                           f"not the key of {b['table']}. A link points from the many rows to the one row they belong to. Was it "
                           f"meant the other way, from {b['table']} to {a['table']}?",
                           [{"change": flipped, "why": f"each {b['table']} row then points at one {a['table']} row"}], "add_link")
            raise ChangeError("not_a_key", f"{b['table']}.{'+'.join(b['columns'])} is not the key of {b['table']} ("
                              + (f"its key is {'+'.join(key)}" if key else "the plan has no key for it")
                              + "). A confirmed relationship points at a key: one row on that side for every row that points.")
        confirmed = {"source": a["table"], "source_cols": a["columns"], "target": b["table"], "target_cols": b["columns"]}
        self.notes.append("The link becomes a confirmed relationship: stated by a person, not counted. validate_plan counts it "
                          "against the rows.")
        return link, {"confirmed": confirmed}

    # add_measure -------------------------------------------------------------------------------------------------
    def operand(self, m: dict) -> dict:
        if "measure" in m:
            known = self.measures.get(m["measure"].casefold())
            if known is None:
                names = sorted(n for n in self.measures.values() if _safe_name(n))
                raise ChangeError("unknown_measure", f"There is no measure {m['measure']!r}. "
                                  + (f"The measures that exist: {', '.join(names)}." if names else "The data product has no measures yet.")
                                  + " A ratio is built from existing measures or from count, distinct_count and sum.")
            return {"measure": known}
        if m["form"] == "ratio":
            return {"form": "ratio", "numerator": self.operand(m["numerator"]), "denominator": self.operand(m["denominator"])}
        table = self.table(m["table"])
        if m["form"] == "count":
            return {"form": "count", "table": table}
        col = self.column(table, m["column"])
        if m["form"] == "sum":
            typ = self.type_of(table, col)
            refs = {x.lower() for r in self.plan.relationships if r.source == table for x in r.source_cols}
            if not amounts.is_numeric(typ) or col.lower() in refs | {k.lower() for k in self.key(table)}:
                raise ChangeError("not_additive", f"{table}.{col} "
                                  + ("is a key or a reference to another table" if amounts.is_numeric(typ) else f"is {typ or 'untyped'}, not a number")
                                  + ": a sum of it means nothing. Count its rows or its distinct values instead.")
        return {"form": m["form"], "table": table, "column": col}

    def add_measure(self, c: dict) -> tuple[dict, dict]:
        if c["name"].casefold() in self.measures:
            raise ChangeError("already_exists", f"There already is a measure named {self.measures[c['name'].casefold()]!r}.")
        measure = self.operand(c["measure"])
        if measure.get("form") == "ratio" and measure["numerator"] == measure["denominator"]:
            raise ChangeError("no_change", "The ratio divides a number by itself: it is always 1.")
        return {"name": c["name"], "measure": measure}, {}

    def revert(self, c: dict) -> tuple[dict, dict]:
        target = c["change"]
        if self.applied is not None and target not in self.applied:
            if target in self.reverted:
                raise ChangeError("already_reverted", f"{target} was already taken out by an earlier revert; the list holds it no more. "
                                                      "To have it again, send the change itself.")
            raise ChangeError("unknown_change", f"{target} is not among the changes applied to this data product"
                                                + (" (a revert is undone by sending the change it took out again)." if self.applied else "."))
        if self.applied is None:
            self.notes.append("No list of applied changes was given: the id is well-formed, whether it was applied is not checked.")
            return {"change": target}, {}
        at = next((i for i, x in enumerate(self.entries) if target in (x["id"], x.get("given"))), None)
        if at is None:
            self.notes.append("The applied changes were given as ids only: whether a later change stands on this one is not checked.")
            return {"change": target}, {}
        dependents = [d for d in (_depends(self.entries[at], x) for x in self.entries[at + 1:]) if d]
        if dependents:
            said = "; ".join(f"{d['change']} ({d['type']}): {d['why']}" for d in dependents[:MAX_CANDIDATES])
            raise _Ask("revert_dependent", f"A later change stands on {target}: {said}. Revert "
                       + ("it" if len(dependents) == 1 else "them, the last first,") + " before this one; nothing is taken out for you.",
                       dependents[:MAX_CANDIDATES], "revert")
        return {"change": target}, {"reverts": {"id": self.entries[at]["id"], "type": self.entries[at]["type"]}}


def _link_key(link: dict) -> tuple:
    """A link in either direction, its column pairs in either case, as one value."""
    a = (link["from"]["table"].lower(), tuple(c.lower() for c in link["from"]["columns"]))
    b = (link["to"]["table"].lower(), tuple(c.lower() for c in link["to"]["columns"]))
    return tuple(sorted((a, b)))


def _measures_named(m: dict) -> set[str]:
    if "measure" in m:
        return {m["measure"].casefold()}
    if m.get("form") == "ratio":
        return _measures_named(m["numerator"]) | _measures_named(m["denominator"])
    return set()


def _depends(target: dict, later: dict) -> dict | None:
    """Whether `later` (an entry after `target` in the list) stands on `target`, by the change types' own fields: an
    add_column or a cascade that joins over the link an add_link confirmed, a ratio that names the measure an add_measure
    added. A filter and a copied column stand on nothing a later change needs."""
    t, c = target["change"], later["change"]
    why = None
    if target["type"] == "add_link":
        link = _link_key(t)
        if later["type"] == "add_column" and any(_link_key(x) == link for x in c.get("via", [])):
            why = "its join path follows the link"
        elif later["type"] == "filter_rows" and any(_link_key(x) == link for cc in (later.get("resolved") or {}).get("cascade", [])
                                                   for x in cc.get("through", [])):
            why = "its cascade follows the link"
    elif target["type"] == "add_measure" and later["type"] == "add_measure":
        if t["name"].casefold() in _measures_named(c["measure"]):
            why = f"its ratio reads the measure {t['name']}"
    if why is None:
        return None
    return {"change": later["id"], "type": later["type"], "why": why, "revert": {"type": "revert", "change": later["id"]}}


def validate(change, plan: Plan, *, counts: dict | None = None, applied=None, measures: list[str] | None = None,
             reverted: list[str] | None = None) -> dict:
    """One change against the current plan. The answer is one of:

    {"result": "ok", "id", "change", "resolved", "notes"}: `change` is the normalised change: canonical, names in the
        plan's own spelling, `base` naming the current plan, the path of an add_column and the cascade of a
        filter_rows filled in. `id` is its id; validating `change` again gives the same answer. `resolved` holds what
        the rules worked out and the next round needs (the links of a cascade, the column types, the `confirmed` entry).
    {"result": "question", "kind", "question", "candidates", "answer_with"}: kind is a key of QUESTIONS; `answer_with`
        names the field (or the change type) the answer goes into. Nothing is chosen for the person.
    {"result": "denied", "kind", "reason"}: kind is a key of DENIALS.

    counts (optional, the caller's; nothing is read here): {"rows": {table: n}, "true": {table: {column: n}},
    "cascade": {table: n}, "links": {link_id: {name: n}}}. applied: the changes applied so far, for revert: their ids, or
    the entries of apply's ok answer (then a revert whose change a later entry stands on is a question, revert_dependent).
    reverted: the ids earlier reverts took out (a second revert of one is denied as already_reverted). measures: the
    names of the measures the data product has beyond those the plan itself gives (amounts.py)."""
    try:
        c = canonical(change)
        mark = plan_mark(plan)
        stale = [k for k, v in c.get("base", {}).items() if mark[k] != v]
        if stale:
            raise ChangeError("stale_base", f"The change was written against another plan ({', '.join(stale)} differ(s)); the current "
                                            f"plan is {mark['plan_id']}. Read the plan again and send the change against it.")
        checker = _Checker(plan, counts, applied, measures, reverted)
        body, resolved = getattr(checker, c["type"])(c)
        normalised = canonical({"type": c["type"], "base": mark, **body})
        return {"result": "ok", "id": change_id(normalised), "change": normalised, "resolved": resolved, "notes": checker.notes}
    except ChangeError as e:
        return {"result": "denied", "kind": e.kind, "reason": e.reason}
    except _Ask as q:
        return {"result": "question", "kind": q.kind, "question": q.question, "candidates": q.candidates, "answer_with": q.answer_with}


# ------------------------------------------------------------------ applying a list (LFD3) ----------------------------

def holds(predicate: dict, row: dict) -> bool:
    """Whether a canonical drop_where holds for a row in memory, as the silver notebook's condition does: a NULL never
    matches (the row stays), is_true is true for true and a non-zero number, is_not_empty for a value that is not blank."""
    for op, every in (("any", any), ("all", all)):
        if op in predicate:
            return every(holds(p, row) for p in predicate[op])
    v = row.get(predicate["column"])
    if v is None:
        return False
    if predicate["op"] == "equals":
        want = predicate["value"]
        return v == want and (isinstance(v, str) == isinstance(want, str))
    if predicate["op"] == "is_true":
        return v.strip().lower() in ("true", "t", "yes", "y", "1") if isinstance(v, str) else bool(v)
    return str(v).strip() != ""


def said(predicate: dict) -> str:
    """A drop_where in words, for a comment or a quarantine reason: is_test is true, country equals 'XX'."""
    for op, word in (("any", " or "), ("all", " and ")):
        if op in predicate:
            return "(" + word.join(said(p) for p in predicate[op]) + ")"
    if predicate["op"] == "equals":
        return f"{predicate['column']} equals {predicate['value']!r}"
    return f"{predicate['column']} {'is true' if predicate['op'] == 'is_true' else 'is not empty'}"


def _steps(plan: Plan, change: dict) -> list[dict]:
    """The join steps of a normalised add_column, from its table to `from`, each with the plan's rule: `columns` on the
    side already joined, `to_columns` on the table joined next (a step may follow a one-to-one link backwards)."""
    node, out = change["table"], []
    for link in change["via"]:
        r = _Checker(plan, None, None, None).relationship(link)
        forward = link["from"]["table"] == node
        here, there = (link["from"], link["to"]) if forward else (link["to"], link["from"])
        out.append({"from": node, "to": there["table"], "columns": list(here["columns"]), "to_columns": list(there["columns"]),
                    "rule": r.rule if r is not None else "confirmed", "forward": forward})
        node = there["table"]
    return out


def _rebased(change, mark: dict):
    """A change written against an earlier plan of the same tables (another plan_id, the same schema fingerprint: the
    plan was made again, with a confirmed link, say) is checked again against the current plan, by every rule; a change
    written against other tables keeps its base and is denied as stale."""
    if not isinstance(change, dict) or not isinstance(change.get("base"), dict):
        return change
    base = change["base"]
    if base.get("schema_fingerprint") == mark["schema_fingerprint"]:
        return {**change, "base": mark}
    return change


def apply(changes: list, plan: Plan, *, measures: list[str] | None = None) -> dict:
    """The change list as input to the drafts (round LFD3): every change validated, in order, against the current plan.

    A list entry is a change (as a client sends it, or the normalised `change` of an ok answer) or an ok answer of
    `validate`. A revert takes out the change it names (by the id it was given or its id against this plan). An add_link
    that the plan does not hold yet is not applied here: the answer is `replan`, with the `confirmed` entries for
    plan_backend, and the same list is applied again to the new plan, where the link is a relationship and the changes that
    need it are accepted. A change whose base is an earlier plan of the same tables (same schema fingerprint) is checked
    again against this one; one written against other tables is denied as stale.

    {"result": "ok", "plan", "changes": [{"id", "type", "change", "resolved", "notes", "position"}], "reverted", "confirmed"}
        `changes` keeps the list's order, without reverted changes, repeats and reverts; `confirmed` is the plan's
        confirmed entries the list's add_link changes stand on. This is what silver.apply_changes, gold.apply_changes and
        semantic_model.draft(changes=...) take; an empty list gives drafts identical to those without changes.
    {"result": "replan", "confirmed", "reason"}
    {"result": "denied" | "question", "at", ...}: the answer of validate for the entry at index `at`; nothing applies."""
    if not isinstance(changes, list):
        return {"result": "denied", "at": None, "kind": "bad_request", "reason": "The change list must be a list."}
    mark = plan_mark(plan)
    entries = [c["change"] if isinstance(c, dict) and c.get("result") == "ok" and "change" in c else c for c in changes]
    replan = []
    undone = _undone(entries, plan)
    for i, c in enumerate(entries):                                    # links first: a new link means a new plan
        if not (isinstance(c, dict) and c.get("type") == "add_link") or i in undone:
            continue                                                   # LFD7: a link a later revert takes out needs no plan
        try:
            link = _Checker(plan, None, None, None).link(_link({"from": c.get("from"), "to": c.get("to")}, "add_link"))
        except ChangeError:
            continue                                                   # validated, and denied, below
        if _Checker(plan, None, None, None).relationship(link) is None:
            got = validate(_rebased(c, mark), plan)
            if got["result"] != "ok":
                return {**got, "at": entries.index(c)}
            if got["resolved"]["confirmed"] not in replan:
                replan.append(got["resolved"]["confirmed"])
    if replan:
        return {"result": "replan", "confirmed": replan,
                "reason": f"{len(replan)} link(s) are not in the plan yet. Plan again with them in confirmed (plan_backend), then apply "
                          "the same list to the new plan: the changes that need a link are checked against the plan that has it."}
    kept: list[dict] = []
    reverted: list[str] = []
    gone_ids: set[str] = set()
    extra = list(measures or [])
    for i, raw in enumerate(entries):
        c = _rebased(raw, mark)
        if isinstance(c, dict) and c.get("type") == "add_link":
            try:
                canonical(c)
                link = _Checker(plan, None, None, None).link(_link({"from": c.get("from"), "to": c.get("to")}, "add_link"))
            except ChangeError:
                return {**validate(c, plan), "at": i}
            if c.get("base", mark) != mark:
                return {**validate(c, plan), "at": i}                     # written against other tables: stale
            r = _Checker(plan, None, None, None).relationship(link)
            normalised = canonical({"type": "add_link", "base": mark, **link})
            if r is None:                                              # LFD7: in `undone`, taken out by a later revert
                in_plan = {"source": link["from"]["table"], "source_cols": list(link["from"]["columns"]),
                           "target": link["to"]["table"], "target_cols": list(link["to"]["columns"]), "rule": "confirmed"}
                said = "The plan does not hold the link; a later revert in the list takes it out."
            else:
                in_plan = {"source": r.source, "source_cols": list(r.source_cols), "target": r.target,
                           "target_cols": list(r.target_cols), "rule": r.rule}
                said = f"The link is a relationship of the plan (rule {r.rule}); the drafts follow it as the plan does."
            entry = {"id": change_id(normalised), "type": "add_link", "change": normalised, "position": i,
                     "resolved": {"in_plan": in_plan}, "notes": [said]}
            given = _given_id(raw)
        else:
            got = validate(c, plan, applied=kept, measures=extra, reverted=sorted(gone_ids))
            if got["result"] != "ok" and i in undone and c.get("type") != "revert":
                # LFD7: a change a later revert takes out, which this plan no longer accepts (a column over a link the
                # plan was made again without): kept as it was sent until its revert, and never drafted
                kept.append({"id": _given_id(raw), "type": c["type"], "change": canonical(c), "resolved": {}, "position": i,
                             "notes": [f"Not checked against this plan ({got.get('kind')}); a later revert in the list takes it out."]})
                continue
            if got["result"] != "ok":
                return {**got, "at": i}
            if got["change"]["type"] == "revert":
                target = got["change"]["change"]
                gone = next(x for x in kept if target in (x["id"], x.get("given")))
                kept = [x for x in kept if x is not gone]
                reverted.append(target)
                gone_ids |= {i for i in (target, gone["id"], gone.get("given")) if i}
                continue
            entry = {"id": got["id"], "type": got["change"]["type"], "change": got["change"], "resolved": got["resolved"],
                     "notes": got["notes"], "position": i}
            given = _given_id(raw)
            if entry["type"] == "add_column":
                entry["resolved"] = {**entry["resolved"], "steps": _steps(plan, got["change"])}
            if entry["type"] == "add_measure":
                extra.append(got["change"]["name"])
        if any(x["id"] == entry["id"] for x in kept):
            continue                                                   # the same change twice is one change
        if given and given != entry["id"]:
            entry["given"] = given
        kept.append(entry)
    confirmed = [x["resolved"]["in_plan"] for x in kept if x["type"] == "add_link" and x["resolved"]["in_plan"]["rule"] == "confirmed"]
    return {"result": "ok", "plan": mark, "changes": [{k: v for k, v in x.items() if k != "given"} for x in kept],
            "reverted": reverted, "confirmed": [{k: v for k, v in c.items() if k != "rule"} for c in confirmed]}


def _undone(entries: list, plan: Plan) -> set[int]:
    """LFD7: the positions of the entries a later revert in the list takes out (by the id they were sent with, and for a
    link also its id against this plan), and that are not sent again after that revert. The list does not stand on them:
    a link among them asks for no new plan, and a change among them that this plan no longer accepts is not denied."""
    mark = plan_mark(plan)
    ids: dict[int, set[str]] = {}
    for i, c in enumerate(entries):
        if not isinstance(c, dict) or c.get("type") == "revert":
            continue
        try:
            ids[i] = {change_id(c)}
            if c.get("type") == "add_link":
                link = _Checker(plan, None, None, None).link(_link({"from": c.get("from"), "to": c.get("to")}, "add_link"))
                ids[i].add(change_id({"type": "add_link", "base": mark, **link}))
        except ChangeError:
            continue
    reverts = [(i, c.get("change")) for i, c in enumerate(entries) if isinstance(c, dict) and c.get("type") == "revert"]
    out = set()
    for i, mine in ids.items():
        last_sent = max(j for j, other in ids.items() if other & mine)
        if i == last_sent and any(j > i and target in mine for j, target in reverts):
            out |= {j for j, other in ids.items() if other & mine}
    return out


def _given_id(raw) -> str | None:
    try:
        return change_id(raw)
    except ChangeError:
        return None


def of_type(applied: dict | None, kind: str) -> list[dict]:
    """The entries of an applied list (apply's ok answer) of one type, in the list's order; [] without a list."""
    if not applied:
        return []
    if applied.get("result") != "ok":
        raise ChangeError("bad_request", "The drafts take apply's ok answer; this list was not applied "
                                         f"({applied.get('result')}): {applied.get('reason') or applied.get('question') or ''}".rstrip(": "))
    return [x for x in applied["changes"] if x["type"] == kind]


# ------------------------------------------------------------------ versions (LFD7) -----------------------------------

_VERSION = re.compile(r"^v(0|[1-9][0-9]{0,5})$")


def _entry_change(c):
    return c["change"] if isinstance(c, dict) and c.get("result") == "ok" and "change" in c else c


def version_id(changes: list) -> str:
    """The id of a version: `ver-` and sixteen hexadecimal digits of the SHA-256 of the list's change ids in order (each
    the id of its canonical form, so the id is the list's content). v0, the empty list, has the id of []."""
    ids = [change_id(_entry_change(c)) for c in changes]
    return "ver-" + hashlib.sha256(_dump(ids).encode("utf-8")).hexdigest()[:16]


def versions(changes: list) -> list[dict]:
    """The change list as versions: v0 (no changes), v1 (the first change), v2 (the first two) and so on. A version is the
    list up to and including its change, reverts included, so a revert is a version of its own and never rewrites an
    earlier one. Each: {"version": "vN", "id": version_id of the first N, "change": the Nth change's id or None, "type",
    "reverts": the id a revert names}. Raises ChangeError for an entry the contract does not read."""
    out = [{"version": "v0", "id": version_id([]), "change": None, "type": None}]
    ids: list[str] = []
    for c in changes:
        c = canonical(_entry_change(c))
        ids.append(change_id(c))
        entry = {"version": f"v{len(ids)}", "id": "ver-" + hashlib.sha256(_dump(ids).encode("utf-8")).hexdigest()[:16],
                 "change": ids[-1], "type": c["type"]}
        if c["type"] == "revert":
            entry["reverts"] = c["change"]
        out.append(entry)
    return out


def version(changes: list, name: str) -> list:
    """The list of a version by its name (v0, v1, ...): the first N entries. Raises ChangeError for another name."""
    m = _VERSION.match(name) if isinstance(name, str) else None
    if not m or int(m.group(1)) > len(changes):
        raise ChangeError("bad_request", f"There is no version {name!r}: the list has v0 to v{len(changes)}.")
    return list(changes[:int(m.group(1))])


def since(previous: list, current: list) -> dict:
    """What changed from one version of the list to another, by the changes' ids: {"previous", "previous_id", "current",
    "current_id", "added": [{"id", "type", ("reverts")}], "reverted": [ids], "dropped": [ids], "later": bool}. `later` is
    true when `current` continues `previous` (the usual case: a version and the one after it); otherwise the two lists
    went apart and `dropped` holds the ids of `previous` that `current` does not have."""
    old, new = versions(previous), versions(current)
    n = 0
    while n < min(len(old), len(new)) - 1 and old[n + 1]["change"] == new[n + 1]["change"]:
        n += 1
    later = n == len(old) - 1
    have = {x["change"] for x in new[1:]}
    added = [{"id": x["change"], "type": x["type"], **({"reverts": x["reverts"]} if x.get("reverts") else {})} for x in new[n + 1:]]
    return {"previous": old[-1]["version"], "previous_id": old[-1]["id"], "current": new[-1]["version"], "current_id": new[-1]["id"],
            "later": later, "added": added, "reverted": [x["reverts"] for x in added if x.get("reverts")],
            "dropped": [] if later else [x["change"] for x in old[n + 1:] if x["change"] not in have]}


# ------------------------------------------------------------------ the list a notebook carries (LFD7) ----------------

NOTEBOOK_LIST = "CHANGE_LIST = "


def notebook_list_params(entries: list[dict], reader: str) -> str:
    """The lines a notebook's parameters cell gets for the changes it applies: a comment and CHANGE_LIST, the entries
    ([{"id", "change"}]) as one JSON string. The run does not use it; `reader` names the function that reads it back."""
    from .codegen import py_literal
    text = json.dumps(entries, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return ("# The changes this notebook applies (docs/CHANGES.md), as JSON: each change's id and its normalised form, in the\n"
            f"# list's order. Krusgraph reads them back ({reader}) to know what is built; the run does not use them.\n"
            f"{NOTEBOOK_LIST}{py_literal(text)}")


def read_notebook_list(definition) -> list[dict]:
    """The CHANGE_LIST of a notebook's parameters cell, read back from the notebook-content.py text or the item definition
    ({"definition": {"parts": [...]}} or {"parts": [...]}, as Get Notebook Definition and notebook.envelope give it, the
    payload in base64). [{"id", "change"}] in order; [] without one. Each entry's change is checked against the contract
    and its id against the change, so a list edited by hand is not read as one Krusgraph wrote. Raises ChangeError."""
    import ast
    import base64
    from . import notebook as _nb
    text = definition
    if isinstance(definition, dict):
        parts = (definition.get("definition") or definition).get("parts") or []
        part = next((x for x in parts if isinstance(x, dict) and str(x.get("path", "")).endswith(".py")), None)
        if part is None:
            raise ChangeError("bad_request", "The notebook definition has no notebook-content.py part.")
        text = base64.b64decode(part.get("payload") or "").decode("utf-8")
    if not isinstance(text, str):
        raise ChangeError("bad_request", "A notebook definition is its notebook-content.py text or the item definition.")
    lines = [x for kind, body in _nb.parse(text) if kind == "parameters" for x in body.splitlines() if x.startswith(NOTEBOOK_LIST)]
    if not lines:
        return []
    try:
        listed = json.loads(ast.literal_eval(lines[0][len(NOTEBOOK_LIST):]))
    except (ValueError, SyntaxError, TypeError) as e:
        raise ChangeError("bad_request", f"CHANGE_LIST in the parameters cell cannot be read ({type(e).__name__}).") from None
    if not isinstance(listed, list):
        raise ChangeError("bad_request", "CHANGE_LIST in the parameters cell is not a list.")
    out = []
    for x in listed:
        if not isinstance(x, dict) or set(x) != {"id", "change"}:
            raise ChangeError("bad_request", "An entry of CHANGE_LIST is not {id, change}.")
        if change_id(x["change"]) != x["id"]:
            raise ChangeError("bad_request", f"The entry {str(x['id'])[:40]!r} of CHANGE_LIST does not match its change: "
                                             "the list was edited after Krusgraph wrote it.")
        out.append({"id": x["id"], "change": canonical(x["change"])})
    return out
