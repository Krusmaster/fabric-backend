"""Evidence state and coverage (n226, SCOPE-REVIEW section 6, mechanism 1).

One shared field on every answer made from a plan: for each key and link, what stands behind it, and one headline that
says how much of the schema that covers. The template is plan_backend's own answer, which already names the rule of
every key and link and what R5 counted; this module says it in the same words everywhere.

States (STATES, in this order):
  key                                    link
  "counted unique"                       "counted and holds"
  "counted, not unique"                  "counted, holds; target key not unique"   (a join can repeat rows)
                                         "counted, does not hold"                  (orphans)
                                         "counted in a sample, holds"              (R5: the first N distinct values)
  "declared, not counted"                (K0 / R0: the source declares it; the rows were not counted in this call)
  "given, not counted"                   (K1 keys= / confirmed=: the caller said so)
  "from a pack, not counted"             (a knowledge pack's documented key or link)
  "by name only"                         (K2–K5 / R1–R4: a name rule, nothing counted)
  "not counted: <reason>"                (an empty table, no value to compare, a query that failed)
  "not checked (time)"                   (budget.NOT_CHECKED: the call's time ran out first)

The answer's field is `evidence`: {state: [item ids]}, ids as review.py writes them (key:orders,
rel:orders.customer_id>customers), so a long list is cut like any other list (compact.bounded) and the editor can look
an item up by the id it already uses. `coverage` is the headline and its numbers:

  "412 tables: 96 with a counted key, 210 with a key by name only, 106 without a key; 300 links proposed, 58 counted,
   51 hold; 240 columns that look like references are unlinked."

"Counted" in the headline means counted over the whole table in this call (validate) or by R5 for its key; a link R5
counted in a sample is said apart, never as counted. Nothing here queries: it reads the plan and, when given, the
check's answer (evidence.validate).
"""
from __future__ import annotations

import contextvars
import json

from .infer import PACK_RULE, Plan, _strip_prefix, _table_prefix, _words

COUNTED_UNIQUE = "counted unique"
COUNTED_NOT_UNIQUE = "counted, not unique"
HOLDS = "counted and holds"
HOLDS_WARNING = "counted, holds; target key not unique"
FAILS = "counted, does not hold"
SAMPLE_HOLDS = "counted in a sample, holds"
DECLARED = "declared, not counted"
GIVEN = "given, not counted"
PACK = "from a pack, not counted"
BY_NAME = "by name only"
NOT_CHECKED = "not checked (time)"            # = budget.NOT_CHECKED
NOT_COUNTED = "not counted"                   # the prefix of "not counted: <reason>"

STATES = (COUNTED_UNIQUE, COUNTED_NOT_UNIQUE, HOLDS, HOLDS_WARNING, FAILS, SAMPLE_HOLDS, DECLARED, GIVEN, PACK, BY_NAME,
          NOT_COUNTED, NOT_CHECKED)


def _key_id(table: str) -> str:
    return f"key:{table}"


def _rel_id(source: str, cols, target: str) -> str:
    return f"rel:{source}.{'+'.join(cols)}>{target}"


def key_rule_state(rule: str) -> str:
    """A key's state from its rule alone, before anything is counted in this call."""
    if rule == "K0":
        return DECLARED
    if rule == "K1":
        return GIVEN
    if rule == PACK_RULE:
        return PACK
    if rule == "R5":                         # R5 gave the key after counting it unique and never NULL over the whole table
        return COUNTED_UNIQUE
    return BY_NAME


def rel_rule_state(r) -> str:
    rule = r.rule
    if rule == "R0":
        return DECLARED
    if rule == "confirmed":
        return GIVEN
    if rule == PACK_RULE:
        return PACK
    if rule == "R5":
        return SAMPLE_HOLDS if "a sample" in (getattr(r, "note", "") or "") else HOLDS
    return BY_NAME


def key_check_state(k: dict) -> str:
    """A key entry of evidence.validate's answer."""
    v = str(k.get("verdict", ""))
    if v.startswith("unique"):
        return COUNTED_UNIQUE
    if v.startswith("empty table"):
        return "not counted: the table is empty"
    return COUNTED_NOT_UNIQUE


def rel_check_state(r: dict) -> str:
    v = str(r.get("verdict", ""))
    if v.startswith("holds"):
        return HOLDS_WARNING if "; but" in v else HOLDS
    if v.startswith("no rows with a value"):
        return "not counted: no rows with a value"
    return FAILS


def states(plan: Plan, checks: dict | None = None) -> dict[str, str]:
    """{item id: state} for every key, relationship and extended relationship of the plan; a check's answer, when
    given, overrides the rule's state for what it counted or could not count."""
    out: dict[str, str] = {}
    for t, (_cols, rule) in plan.keys.items():
        out[_key_id(t)] = key_rule_state(rule)
    for r in list(plan.relationships) + list(getattr(plan, "extended", [])):
        out[_rel_id(r.source, r.source_cols, r.target)] = rel_rule_state(r)
    if checks:
        for k in checks.get("keys", []) or []:
            out[_key_id(k["table"])] = key_check_state(k)
        for r in checks.get("relationships", []) or []:
            out[_rel_id(r["source"], r["columns"], r["target"])] = rel_check_state(r)
        for x in checks.get("not_counted", []) or []:
            if x.get("id"):
                out[x["id"]] = x.get("evidence") or NOT_COUNTED
    return out


def _bucket(state: str) -> str:
    return NOT_COUNTED if state.startswith(NOT_COUNTED + ":") else state


def grouped(st: dict[str, str], first: int | None = None, keep: set[str] | None = None) -> dict[str, list[str]]:
    """{state: [ids]} in STATES order; "not counted: <reason>" keeps its reason as its own group. `first` lists at most
    so many ids per state (coverage's states carry the counts); `keep` (table names) lists only the items of those
    tables (a key of one of them, a link with an end among them)."""
    groups: dict[str, list[str]] = {}
    for i, s in st.items():
        if keep is not None and not _touches(i, keep):
            continue
        groups.setdefault(s, []).append(i)
    order = {s: n for n, s in enumerate(STATES)}
    return {s: (groups[s][:first] if first else groups[s]) for s in sorted(groups, key=lambda s: (order.get(_bucket(s), len(STATES)), s))}


def _touches(item: str, keep: set[str]) -> bool:
    if item.startswith("key:"):
        return item[4:] in keep
    body = item[4:]
    source, _, target = body.rpartition(">")
    return target in keep or source.split(".", 1)[0] in keep


_REF_WORDS = {"id", "key", "code", "nr", "no", "num", "sk", "bk"}


def looks_like_reference(column: str, prefix: str = "") -> bool:
    """A column whose name ends like a reference: customer_id, CustomerID, o_custkey, KUNNR, sku_code, order_no.
    A bare `id`, `key`, `code` or `no` is a table's own identifier, not a reference; `paid` or `valid` are not ids."""
    words = _words(_strip_prefix(column, prefix)) if prefix else _words(column)
    if len(words) < 2 and not (words and len(words[-1]) >= 5 and words[-1].endswith(("key", "nr"))):
        return False
    last = words[-1]
    return last in _REF_WORDS or (len(last) >= 5 and last.endswith(("key", "nr")))


def unlinked_references(plan: Plan) -> list[str]:
    """table.column for every column that looks like a reference and is neither part of its table's key nor the source
    of a relationship (relationships, extended ones, and the ambiguous columns counted apart by the caller)."""
    linked = {(r.source, c.lower()) for r in list(plan.relationships) + list(getattr(plan, "extended", [])) for c in r.source_cols}
    out = []
    for t in plan.schema:
        own = {c.lower() for c in plan.keys.get(t.name, ([], ""))[0]}
        prefix = _table_prefix(t)
        for c in t.column_names:
            if c.lower() in own or (t.name, c.lower()) in linked:
                continue
            if looks_like_reference(c, prefix):
                out.append(f"{t.name}.{c}")
    return out


def _n(n: int, one: str, many: str | None = None) -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


def coverage(plan: Plan, checks: dict | None = None, st: dict[str, str] | None = None, first: int = 20) -> dict:
    """The headline and its numbers."""
    st = st if st is not None else states(plan, checks)
    n_tables = len(plan.schema)
    key_states = [st[_key_id(t)] for t in plan.keys]
    kc = {s: key_states.count(s) for s in set(key_states)}
    by_bucket: dict[str, int] = {}
    for s in key_states:
        by_bucket[_bucket(s)] = by_bucket.get(_bucket(s), 0) + 1
    keyless = n_tables - len(plan.keys)
    links = list(plan.relationships) + list(getattr(plan, "extended", []))
    link_states = [st[_rel_id(r.source, r.source_cols, r.target)] for r in links]
    counted = sum(1 for s in link_states if s in (HOLDS, HOLDS_WARNING, FAILS))
    hold = sum(1 for s in link_states if s == HOLDS)
    sample = link_states.count(SAMPLE_HOLDS)
    timed = link_states.count(NOT_CHECKED) + key_states.count(NOT_CHECKED)
    failed = sum(1 for s in link_states + key_states if s.startswith(NOT_COUNTED + ":"))
    unlinked = unlinked_references(plan)
    ambiguous = len(plan.ambiguous)

    parts = [f"{by_bucket.get(COUNTED_UNIQUE, 0)} with a counted key"]
    if by_bucket.get(COUNTED_NOT_UNIQUE):
        parts.append(f"{by_bucket[COUNTED_NOT_UNIQUE]} with a key the rows show is not unique")
    if by_bucket.get(DECLARED):
        parts.append(f"{by_bucket[DECLARED]} with a declared key not counted")
    if by_bucket.get(GIVEN):
        parts.append(f"{by_bucket[GIVEN]} with a key you gave, not counted")
    if by_bucket.get(PACK):
        parts.append(f"{by_bucket[PACK]} with a key from a pack, not counted")
    parts.append(f"{by_bucket.get(BY_NAME, 0)} with a key by name only")
    other = by_bucket.get(NOT_COUNTED, 0) + by_bucket.get(NOT_CHECKED, 0)
    if other:
        parts.append(f"{other} with a key not counted")
    parts.append(f"{keyless} without a key")
    head = f"{_n(n_tables, 'table')}: " + ", ".join(parts)
    lp = f"{_n(len(links), 'link')} proposed, {counted} counted, {hold} hold"
    if sample:
        lp += f", {sample} counted in a sample of their values"
    if timed:
        lp += f", {timed} not checked (time)"
    if failed:
        lp += f", {failed} not counted (see evidence)"
    tail = (f"1 column that looks like a reference is unlinked" if len(unlinked) == 1
            else f"{len(unlinked)} columns that look like references are unlinked")
    if ambiguous:
        tail += f" ({ambiguous} of them could point at more than one table)"
    out = {
        "headline": f"{head}; {lp}; {tail}.",
        "tables": n_tables,
        "keys": {"with_key": len(plan.keys), "without_key": keyless, "states": {s: kc[s] for s in sorted(kc)}},
        "links": {"proposed": len(links), "counted": counted, "hold": hold, "counted_in_a_sample": sample,
                  "states": {s: link_states.count(s) for s in sorted(set(link_states))}},
        "unlinked_reference_columns": len(unlinked),
        "counted_means": "counted over the whole table in this call; a key or link by name only is a candidate until counted",
    }
    if unlinked:
        out["unlinked_first"] = unlinked[:first]
    if not checks:
        out["next"] = "validate_plan counts the keys and links (by importance, within the call's time budget)"
    return out


EVIDENCE_FIRST = 50                  # ids per state in a summary-form answer


def attach(answer: dict, plan: Plan, checks: dict | None = None, per_item: bool = True, first: int | None = None,
           keep: set[str] | None = None) -> dict:
    """The answer with `coverage` and, with per_item, `evidence` ({state: [ids]}). Keys already there are kept.
    `first` and `keep` as in grouped(); coverage is always the whole plan's."""
    st = states(plan, checks)
    out = dict(answer)
    out.setdefault("coverage", coverage(plan, checks, st))
    if per_item:
        out.setdefault("evidence", grouped(st, first, keep))
        if first and any(len(v) >= first for v in out["evidence"].values()):
            out["coverage"]["evidence_lists"] = (f"evidence lists at most {first} ids per state here; coverage's states "
                                                 "give the counts, detail=\"full\" every id")
    return out


def entry_states(plan: Plan, checks: dict | None = None) -> tuple[dict[str, str], dict[tuple, str]]:
    """For an answer that lists keys and relationships as objects: ({table: state}, {(source, cols, target): state})."""
    st = states(plan, checks)
    keys = {t: st[_key_id(t)] for t in plan.keys}
    rels = {(r.source, tuple(r.source_cols), r.target): st[_rel_id(r.source, r.source_cols, r.target)]
            for r in list(plan.relationships) + list(getattr(plan, "extended", []))}
    return keys, rels


# ------------------------------------------------------------------ per call ---------------------------------------
# The plan (and the check) a tool call made, so errors.safe can put `coverage` on the answer of every tool that made a
# plan, in one place. Noted by the hosted and local plan readers and by evidence.validate; nothing outlives the call.

_NOTED: contextvars.ContextVar[dict | None] = contextvars.ContextVar("krusgraph_coverage", default=None)


def begin():
    return _NOTED.set({"plan": None, "checks": None})


def end(token) -> None:
    _NOTED.reset(token)


def note(plan: Plan, checks: dict | None = None) -> None:
    """The first plan of the call is the one its answer is about; a check of a plan replaces a plan noted without one."""
    slot = _NOTED.get()
    if slot is None or plan is None:
        return
    if slot["plan"] is None or (checks is not None and (slot["plan"] is plan or slot["checks"] is None)):
        slot["plan"] = plan
        if checks is not None:
            slot["checks"] = checks


# The tools whose answer is made from a plan of keys and links and is a JSON object of its own fields (not a map of
# table names, as list_tables's): `coverage` goes on these. plan_backend and validate_plan also carry `evidence`.
PLAN_TOOLS = frozenset({
    "plan_backend", "validate_plan", "review_plan", "create_backend", "rayfin_connector", "ontology_draft", "create_ontology",
    "semantic_model_draft", "create_semantic_model", "compare_semantic_model", "join_path", "analyze_schema",
    "suggest_relationships", "data_dictionary", "dbt_schema", "domain_draft", "sap_pack_draft", "plan_drift", "create_views",
    "create_data_agent", "silver_notebook_draft", "create_silver_notebook", "gold_views_draft", "create_gold_views",
    "drift_monitor_draft", "create_drift_monitor", "create_pipeline", "export_item_definitions", "answer_query_draft",
    "lineage", "databricks_constraints_draft", "create_databricks_constraints", "databricks_pipeline_draft",
    "create_databricks_pipeline", "databricks_metric_view_draft", "export_databricks_bundle",
})


def with_coverage(text, tool: str = ""):
    """The tool's JSON answer with `coverage` when the call made a plan; anything else unchanged (another tool, an
    error, a refusal, text that is not a JSON object, an answer that already has it)."""
    slot = _NOTED.get()
    if tool not in PLAN_TOOLS or not slot or slot["plan"] is None or not isinstance(text, str) or not text.lstrip().startswith("{"):
        return text
    try:
        data = json.loads(text)
    except ValueError:
        return text
    if not isinstance(data, dict) or "coverage" in data or "error" in data or data.get("choose_schema"):
        return text
    try:
        cov = coverage(slot["plan"], slot["checks"], first=10)
    except Exception:                                                   # noqa: BLE001 - a headline never breaks an answer
        return text
    data["coverage"] = cov
    out = json.dumps(data, indent=2, default=str)
    if len(out) > LIMIT >= len(text):                                   # an answer cut to fit stays within the limit
        data["coverage"] = {"headline": cov["headline"]}
        out = json.dumps(data, indent=2, default=str)
    return out if len(out) <= max(LIMIT, len(text)) else text


LIMIT = 60000                                                           # server.MAX_RESULT_CHARS
