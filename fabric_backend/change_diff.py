"""What a change to a data product would change, in three layers (round LFD5, 25 November 2026; docs/CHANGES.md).

`diff(before, after, info)` compares two sides of one data product. A side is the plan and the change list applied to it
(changes.apply's ok answer): `before` the list as it is, `after` the list with the new change. The answer has three
layers:

1. plan: keys and links added or removed (drift.plan_snapshot and drift.snapshot_diff, the drift monitor's own
   comparison), and the filters, copied columns and measures the change list adds or takes out;
2. items: per Fabric item the drafts give (the silver notebook, the check notebook, the gold views, the pipeline, the
   semantic model) the old and the new definition, built by the same functions the drafts and the dry runs use. An item
   whose definition differs is marked "update in place", with a short summary ("1 filter step on customers and its 4
   dependents") and the unified diff; one whose definition is the same is "unchanged";
3. numbers: what a caller-supplied `numbers` callable counts (round LFD4's module, wired by whichever pull request
   merges last). Without one the layer says "not counted yet".

`propose(change, plan, info, ...)` is what the read-only tool propose_change answers: the new change validated against
the plan with the list before it (changes.apply), passed through when it is a question or a denial, and otherwise the
diff and a confirm token for a later apply_change. Nothing here reads a row, calls Fabric or writes anything; no model:
the same request against the same plan gives the same answer and the same token.
"""
from __future__ import annotations

import difflib
import hashlib
import json
from collections.abc import Callable
from typing import Protocol, TypedDict

from . import changes as _changes
from .infer import Plan

ITEMS = ("silver_notebook", "check_notebook", "gold_views", "pipeline", "semantic_model")
LABEL = {"silver_notebook": "silver notebook", "check_notebook": "check notebook", "gold_views": "gold views notebook",
         "pipeline": "pipeline", "semantic_model": "semantic model"}
UPDATE, UNCHANGED, NOT_DRAFTED = "update in place", "unchanged", "not drafted"
NOT_COUNTED = "not counted yet"
MAX_DIFF_LINES = 80                    # per item; the rest is counted, not shown (the answer stays within a tool answer)


class Side(TypedDict):
    """One side of the diff: the plan and the change list applied to it (changes.apply's ok answer)."""
    plan: Plan
    applied: dict


class NumbersLayer(Protocol):
    """The third layer's interface. Round LFD4 (fabric_backend/change_numbers.py) supplies it; this module never imports
    it. Called once per diff with both sides as keywords; returns a JSON-able dict, which the layer carries as it is
    under `counted`. It reads rows only; it never writes. An exception is reported, not raised."""

    def __call__(self, *, before: Side, after: Side) -> dict: ...


# ------------------------------------------------------------------ the drafts of one side -----------------------------

def drafts(plan: Plan, info: dict, applied: dict | None) -> dict:
    """Every item's definition for one side, as text, with the specs the summaries read. The same builders as the
    drafts and create_pipeline's dry run (silver.spec, gold.spec, pipeline.check_spec, pipeline.pipeline_content,
    semantic_model.draft), with `changes=applied`; an empty list gives the drafts without changes, byte for byte. LFD9b:
    info["model_reads"] == "silver" (the source has a Krusgraph pipeline) drafts the model on the silver tables. An
    item the source cannot have (gold views need a lakehouse with schemas) is None in `text`, with the reason in
    `not_drafted`."""
    from . import gold, pipeline, semantic_model, silver
    from .infer import PlanInputError
    schema = info.get("schema") or plan.schema.schema
    kw = {"changes": applied} if applied is not None else {}
    label = f"{info['item_name']}.{schema}"
    names = {"silver_notebook": f"silver_{schema}", "gold_views": f"gold_{schema}", "check_notebook": f"pipeline_{schema}_check",
             "pipeline": f"pipeline_{schema}", "semantic_model": f"{schema}_model"}
    text: dict = dict.fromkeys(ITEMS)
    missing: dict[str, str] = {}
    out = {"text": text, "names": names, "not_drafted": missing, "silver": {}, "gold": {}, "model": {"summary": {}}}

    def build(items, make):
        try:
            return make()
        except PlanInputError as e:
            for i in items:
                missing[i] = str(e)
            return None
    s = build(("silver_notebook", "check_notebook"), lambda: silver.spec(plan, info, **kw))
    g = build(("gold_views", "check_notebook"), lambda: gold.spec(plan, info, **kw))
    model = build(("semantic_model",), lambda: semantic_model.draft(plan, info, names["semantic_model"],
                                                                    on_silver=info.get("model_reads") == "silver", **kw))
    if s is not None:
        out["silver"], text["silver_notebook"] = s, silver.notebook_source(s)
    if g is not None:
        out["gold"], text["gold_views"] = g, gold.notebook_source(g)
    if s is not None and g is not None:
        check = pipeline.check_spec(plan, s, g, pipeline.plan_mark_of(plan))
        text["check_notebook"] = pipeline.check_source(check, label, info.get("workspace_id", ""), info.get("item_id", ""),
                                                       info.get("item_name", ""))
    text["pipeline"] = json.dumps(pipeline.pipeline_content(names["silver_notebook"], names["gold_views"], names["check_notebook"],
                                                            label), indent=2, sort_keys=True)
    if model is not None:
        out["model"], text["semantic_model"] = model, "".join(f"--- {path}\n{body}\n" for path, body in sorted(model["parts"].items()))
    return out


# ------------------------------------------------------------------ layer 1: the plan ----------------------------------

def _entries(side: Side) -> dict[str, dict]:
    """The list's entries by their content without `base`: a change re-checked against a plan made again (with a new
    confirmed link) gets a new id, and is still the same change."""
    return {_content(x): x for x in (side["applied"] or {}).get("changes", [])}


def _content(x: dict) -> str:
    return json.dumps({k: v for k, v in x["change"].items() if k != "base"}, sort_keys=True)


def _matched(before: Side, after: Side) -> tuple[set[str], set[str]]:
    """The ids of the before list that are still in the after list, and the ids of the after list that were there
    before (by content, see _entries)."""
    old, new = _entries(before), _entries(after)
    return {x["id"] for k, x in old.items() if k in new}, {x["id"] for k, x in new.items() if k in old}


def _change_word(x: dict) -> dict:
    c = x["change"]
    if x["type"] == "filter_rows":
        return {"id": x["id"], "table": c["table"], "drop_where": _changes.said(c["drop_where"]), "cascade": list(c.get("cascade", []))}
    if x["type"] == "add_column":
        return {"id": x["id"], "table": c["table"], "from": c["from"], "columns": list(c["columns"]),
                "path": list(x["resolved"].get("path", []))}
    if x["type"] == "add_measure":
        return {"id": x["id"], "name": c["name"], "form": c["measure"].get("form", "ratio")}
    return {"id": x["id"], "from": c["from"], "to": c["to"]}


def plan_layer(before: Side, after: Side) -> dict:
    """Keys and links from the two plans (drift.snapshot_diff), filters, columns and measures from the two lists."""
    from .drift import plan_snapshot, snapshot_diff
    snap = snapshot_diff(plan_snapshot(before["plan"]), plan_snapshot(after["plan"]))
    old, new = _entries(before), _entries(after)
    out = {"keys_changed": snap["keys_changed"], "links_added": snap["relationships_added"],
           "links_removed": snap["relationships_removed"]}
    for kind, word in (("filter_rows", "filters"), ("add_column", "columns"), ("add_measure", "measures")):
        out[f"{word}_added"] = [_change_word(x) for i, x in new.items() if i not in old and x["type"] == kind]
        out[f"{word}_removed"] = [_change_word(x) for i, x in old.items() if i not in new and x["type"] == kind]
    said = []
    for k, v in out.items():
        if v:
            noun, verb = k.rsplit("_", 1)
            said.append(f"{_n(len(v), noun.rstrip('s'))} {verb}")
    out["changed"] = bool(said)
    out["summary"] = "; ".join(said) if said else "the plan is the same"
    return out


# ------------------------------------------------------------------ layer 2: the items ---------------------------------

def _n(k: int, word: str) -> str:
    return f"{k} {word}{'' if k == 1 else 's'}"


def _silver_said(b: dict, a: dict, kept: set[str], was: set[str]) -> list[str]:
    old, new = was, kept
    out = [f"1 filter step on {c['table']} and its {_n(len(c['cascade']), 'dependent')}" if c["cascade"]
           else f"1 filter step on {c['table']}" for c in a["silver"].get("changes", []) if c["id"] not in old]
    out += [f"the filter step on {c['table']} taken out" for c in b["silver"].get("changes", []) if c["id"] not in new]
    return out


def _gold_said(b: dict, a: dict, kept: set[str], was: set[str]) -> list[str]:
    from . import gold
    old = was
    joins: dict[tuple[str, str], int] = {}
    for v in gold.all_views(a["gold"]):
        for j in v["joins"]:
            if j.get("change"):
                joins[(j["change"], v["name"])] = joins.get((j["change"], v["name"]), 0) + 1
    out = []
    for c in a["gold"].get("changes", []):
        if c["id"] in old:
            continue
        if c.get("not_applied"):
            out.append(f"{', '.join(c['columns'])} not added: {c['not_applied']}")
        for v in c["views"]:
            k = joins.get((c["id"], v["view"]), 0)
            if v["added"]:
                out.append(f"{_n(k, 'join')} and {_n(len(v['added']), 'column')} in {v['view']}" if k
                           else f"{_n(len(v['added']), 'column')} in {v['view']}")
            if v.get("already_in_view"):
                out.append(f"{', '.join(v['already_in_view'])} already in {v['view']}, marked with the change")
    new = kept
    out += [f"the column(s) {', '.join(c['columns'])} of {c['table']} taken out" for c in b["gold"].get("changes", []) if c["id"] not in new]
    return out


def _model_said(b: dict, a: dict, kept: set[str], was: set[str]) -> list[str]:
    old, new = was, kept
    out = []
    for c in a["model"]["summary"].get("changes", []):
        if c["id"] in old:
            continue
        if c["type"] == "add_measure":
            out.append(f"1 measure: {c['name']}" if not c.get("not_added") else f"the measure {c['name']} is not added: {c['not_added']}")
        else:
            out.append(f"README: the {c['type']} change is {c['said'].split(';')[0]}")
    out += [f"{c.get('name') or c['type']} taken out" for c in b["model"]["summary"].get("changes", []) if c["id"] not in new]
    return out


_SAID = {"silver_notebook": _silver_said, "gold_views": _gold_said, "semantic_model": _model_said}


def _unified(old: str, new: str, name: str) -> tuple[str, int, int, int]:
    lines = list(difflib.unified_diff(old.splitlines(), new.splitlines(), f"{name} (now)", f"{name} (after the change)", lineterm="", n=2))
    plus = sum(1 for x in lines if x.startswith("+") and not x.startswith("+++"))
    minus = sum(1 for x in lines if x.startswith("-") and not x.startswith("---"))
    shown = lines[:MAX_DIFF_LINES]
    if len(lines) > MAX_DIFF_LINES:
        shown.append(f"… {len(lines) - MAX_DIFF_LINES} more line(s) of this diff are not shown")
    return "\n".join(shown), plus, minus, len(lines)


def items_layer(b: dict, a: dict, kept: set[str] = frozenset(), was: set[str] = frozenset()) -> list[dict]:
    """Per item (ITEMS, in the pipeline's order and then the model): update in place or unchanged, with the summary and
    the unified diff of its definition. `kept`: the before list's ids still in the after list; `was`: the after list's
    ids that were in the before list (_matched)."""
    out = []
    for item in ITEMS:
        old, new = b["text"][item], a["text"][item]
        entry = {"item": item, "label": LABEL[item], "name": a["names"][item]}
        if old is None or new is None:
            out.append({**entry, "status": NOT_DRAFTED, "reason": a["not_drafted"].get(item) or b["not_drafted"].get(item, "")})
            continue
        if old == new:
            out.append({**entry, "status": UNCHANGED})
            continue
        text, plus, minus, total = _unified(old, new, a["names"][item])
        said = _SAID.get(item, lambda *_: [])(b, a, kept, was)
        if not said:
            said = [f"{_n(plus, 'line')} added and {minus} removed: the item follows the plan"]
        out.append({**entry, "status": UPDATE, "summary": "; ".join(said), "lines_added": plus, "lines_removed": minus,
                    "diff": text, **({"diff_cut": True} if total > MAX_DIFF_LINES else {})})
    return out


# ------------------------------------------------------------------ layer 3: the numbers -------------------------------

def numbers_layer(before: Side, after: Side, numbers: NumbersLayer | Callable | None, reverts: dict | None = None) -> dict:
    """The counter's answer for the two sides. LFD7: for a revert the counter is called with the sides the other way
    round (`before` the list without the reverted change, `after` the list with it), so it counts the reverted change as
    it counts any change; the layer says so in `reverts` and `read`: the revert takes the numbers from that `after` back
    to that `before`."""
    if reverts is not None and numbers is not None:
        got = numbers_layer(after, before, numbers)
        if got["status"] == "counted":
            got.update(reverts=reverts, read="These are the numbers of the reverted change, counted as when it was applied. The "
                                             "revert takes them back: what the change had as after it, the data product has "
                                             "as before the revert, and the revert's after is the change's before.")
        return got
    if numbers is None:
        return {"status": NOT_COUNTED, "note": "The numbers before and after the change are not counted yet; the plan and the "
                                               "items above are worked out from the plan alone."}
    try:
        counted = numbers(before=before, after=after)
    except Exception as e:                                   # noqa: BLE001 - reported in the answer, never raised
        return {"status": NOT_COUNTED, "note": f"Counting failed ({type(e).__name__}); the plan and the items above stand."}
    return {"status": "counted", "counted": counted}


# ------------------------------------------------------------------ the diff and the proposal -------------------------

def diff(before: Side, after: Side, info: dict, numbers: NumbersLayer | Callable | None = None, *,
         reverts: dict | None = None) -> dict:
    """The three layers: {"plan", "items", "numbers", "summary"}, and `definitions`, a digest of every item's whole new
    definition (the unified diffs are cut at MAX_DIFF_LINES; the digest is not). `reverts` (LFD7): the change a revert
    takes out ({"id", "type"}); the plan layer then names it, and the numbers layer counts it the other way round."""
    b = drafts(before["plan"], info, before["applied"])
    a = drafts(after["plan"], info, after["applied"])
    plan = plan_layer(before, after)
    kept, was = _matched(before, after)
    items = items_layer(b, a, kept, was)
    updated = [x["label"] for x in items if x["status"] == UPDATE]
    digest = hashlib.sha256(json.dumps(a["text"], sort_keys=True).encode("utf-8")).hexdigest()[:16]
    if reverts is not None:
        plan["reverted"] = reverts
    return {"plan": plan, "items": items, "numbers": numbers_layer(before, after, numbers, reverts), "definitions": f"sha256:{digest}",
            "summary": f"{plan['summary']}; " + (f"{_n(len(updated), 'item')} updated in place ({', '.join(updated)})"
                                                 if updated else "no item changes")}


def confirm_token(after: Side, d: dict) -> str:
    """The confirm a later apply_change sends back: the change list's ids in order, the plan they stand on and every
    item's new definition, as the Update dry runs make theirs (workload_api.confirm_token, prefix upd-). Another list,
    another plan or another definition gives another token."""
    from .workload_api import confirm_token as _token
    mark = (after["applied"] or {}).get("plan") or _changes.plan_mark(after["plan"])
    ids = [f"{i:03d}:{x['id']}" for i, x in enumerate((after["applied"] or {}).get("changes", []))]
    return _token("change", {"plan_id": mark.get("plan_id"), "schema": mark.get("schema_fingerprint"),
                             "links": (after["applied"] or {}).get("confirmed")}, [*ids, f"items:{d['definitions']}"])


def propose(change, plan: Plan, info: dict, applied: list | None = None, *, confirmed: list | None = None,
            replan: Callable[[list], Plan] | None = None, numbers: NumbersLayer | Callable | None = None) -> dict:
    """The answer of propose_change. `applied`: the changes applied so far, in order (each a change or an ok answer);
    `confirmed`: the confirmed links the plan was made with; `replan(confirmed)`: the plan made again with these
    confirmed links (an add_link the plan does not hold yet). Answers

    {"result": "question" | "denied", "at", ...}: validate's answer, passed through; `at` is the entry of the list
        (len(applied) for the new change). Nothing else is worked out.
    {"result": "ok", "id", "change", "notes", "diff", "confirm", "confirmed"}: the diff of the list before and with the
        change, and the token for apply_change. `confirmed` is what plan_backend and later calls take (the links the
        plan now stands on, a new link included)."""
    applied = list(applied or [])
    if not isinstance(change, dict):
        return {"result": "denied", "at": len(applied), "kind": "bad_request", "reason": "The change must be one JSON object."}
    before = _changes.apply(applied, plan)
    if before["result"] == "replan":
        return {**before, "at": None, "reason": "The changes applied so far need links the plan does not hold: "
                                                + before["reason"]}
    if before["result"] != "ok":
        return before
    links = list(confirmed or [])
    after_plan = plan
    after = _changes.apply([*applied, change], plan)
    reverts = None
    if after["result"] == "ok" and change.get("type") == "revert":
        gone = next((x for x in before["changes"] if x["id"] not in {y["id"] for y in after["changes"]}), None)
        reverts = {"id": gone["id"], "type": gone["type"]} if gone else None
        conf = gone["resolved"]["in_plan"] if gone and gone["type"] == "add_link" else None
        if conf and conf.get("rule") == "confirmed" and replan is not None:   # LFD7: the plan made again without the link
            entry = {k: v for k, v in conf.items() if k != "rule"}
            links = [x for x in links if not _same_link(x, entry)]
            after_plan = replan(links)
            after = _changes.apply([*applied, change], after_plan)
    if after["result"] == "replan":
        if replan is None:
            return {**after, "at": len(applied)}
        links = links + [c for c in after["confirmed"] if c not in links]
        after_plan = replan(links)
        after = _changes.apply([*applied, change], after_plan)
    if after["result"] != "ok":
        return after
    new = next((x for x in after["changes"] if x["position"] == len(applied)), None)
    if new is None:                                              # a repeat, or a revert: the list's ids say which
        head = _changes.validate(change, plan, applied=before["changes"], reverted=before.get("reverted"))
        new = {"id": head.get("id"), "change": head.get("change"), "notes": head.get("notes", [])}
    sides = ({"plan": plan, "applied": before}, {"plan": after_plan, "applied": after})
    d = diff(*sides, info, numbers, reverts=reverts)
    return {"result": "ok", "id": new["id"], "change": new["change"], "notes": new.get("notes", []),
            "changes": [x["id"] for x in after["changes"]], "confirmed": links, "diff": d,
            **({"reverts": reverts} if reverts else {}), "confirm": confirm_token(sides[1], d)}


def _same_link(a: dict, b: dict) -> bool:
    def key(x):
        return (x["source"].lower(), tuple(c.lower() for c in x["source_cols"]), x["target"].lower(), tuple(c.lower() for c in x["target_cols"]))
    return key(a) == key(b)


WRITES = ("Nothing was written: propose_change reads the plan and drafts the items, and never writes to Fabric. A later "
          "apply_change takes the confirm value back.")


def answer(out: dict, limit: int) -> str:
    """The tool's JSON within `limit` characters: an ok answer says what it wrote (nothing), and the largest unified
    diffs leave the answer first, each marked diff_omitted, until it fits."""
    import copy
    out = copy.deepcopy(out)
    if out.get("result") == "ok":
        out["writes"] = WRITES
    text = json.dumps(out, indent=2)
    items = (out.get("diff") or {}).get("items") or []
    while len(text) > limit and any(x.get("diff") for x in items):
        biggest = max((x for x in items if x.get("diff")), key=lambda x: len(x["diff"]))
        biggest.pop("diff")
        biggest["diff_omitted"] = "the unified diff did not fit in this answer; the summary and the line counts stand"
        text = json.dumps(out, indent=2)
    return text
