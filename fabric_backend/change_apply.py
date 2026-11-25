"""Applying a change through Update (round LFD6, 25 November 2026; docs/CHANGES.md, "Applying a change").

propose_change shows a change's diff and a confirm token; apply_change takes the token back. This module holds the
rules apply_change follows; the server (server._apply_change) reads and writes Fabric through them. No model: every
decision below is a comparison a person can repeat.

- What is written: only the items the diff marks "update in place", in ORDER (the silver, check and gold notebooks, the
  pipeline's definition), then one pipeline run when the change needs rows (run_needed: the silver or the gold
  notebook changes), then the semantic model, then one refresh. Never a delete.
- Whose items: only an item Krusgraph made (ours: its description carries the plan marker, workload_api.MARK, or says
  Krusgraph, as workload_api._krusgraph_made reads it), and only when its definition in Fabric is the diff's "now"
  (same: verify_build's own comparisons). An item already as the change makes it is left as it is.
- The plan marker gets the change list: its count and a digest of its ids in order (digest, workload_api.mark_text).
  A marker written before LFD6 has no change part and reads as zero changes (changes_of).
- Afterwards: the definitions read back and compared with what was written ("definition verified"), and, after a run
  that succeeded, the silver tables' rows counted and compared with the numbers layer's "after" ("numbers verified
  after a run"). The two are separate states (verify_build's VERIFIED, DIFFERS, NOT_CHECKED).

The numbers layer of propose_change is LFD4's counter (numbers), and an answer is kept under the tool's limit by
summarising the receipt, then leaving out the SQL of each number, then the largest unified diffs (answer, fit).
"""
from __future__ import annotations

import copy
import hashlib
import json
import time

from . import change_diff as _diff

ORDER = ("silver_notebook", "check_notebook", "gold_views", "pipeline", "semantic_model")   # change_diff.ITEMS' order
NOTEBOOKS = ("silver_notebook", "check_notebook", "gold_views")
RUN_ITEMS = ("silver_notebook", "gold_views")          # the notebooks that write rows: a change to them needs a run
TYPE = {"silver_notebook": "Notebook", "check_notebook": "Notebook", "gold_views": "Notebook", "pipeline": "DataPipeline",
        "semantic_model": "SemanticModel"}
ROUTE = {"Notebook": "notebooks", "DataPipeline": "dataPipelines", "SemanticModel": "semanticModels"}
RUN_WAIT_SECONDS = 30                                   # the run is read this long; it goes on in Fabric after that
VERIFIED, DIFFERS, NOT_CHECKED = "verified", "differs", "not checked"     # verify_build.STATES
pause = time.sleep                                      # the wait between reads of a run (the tests set it to nothing)


# ------------------------------------------------------------------ the change list in the plan marker ----------------

def digest(ids) -> str:
    """The change list as the marker carries it: sha256 of its ids in order, 16 hexadecimal digits."""
    return "sha256:" + hashlib.sha256(json.dumps(list(ids)).encode("utf-8")).hexdigest()[:16]


def changes_of(mark: dict | None) -> dict:
    """{"changes", "digest"} an item's marker records. A marker without a change part (before LFD6) is zero changes;
    no marker at all is not recorded (None)."""
    if not mark:
        return {"changes": None, "digest": None, "said": "no plan marker: the change list is not recorded"}
    n = int(mark.get("changes") or 0)
    return {"changes": n, "digest": mark.get("changes_digest") if n else digest([]),
            "said": f"{n} change{'' if n == 1 else 's'} recorded" if n else "a marker without changes: zero changes"}


def new_mark(plan_mark: dict, schema: str, links: int, ids) -> dict:
    ids = list(ids)
    return {**plan_mark, "schema": schema, "links": links, "changes": len(ids), "changes_digest": digest(ids)}


def ours(description) -> bool:
    """Whether Krusgraph made the item: the plan marker, or Krusgraph's own words in the description."""
    from .workload_api import MARK
    text = str(description or "")
    return bool(MARK.search(text)) or "krusgraph" in text.lower()


# ------------------------------------------------------------------ the run ------------------------------------------

def run_needed(diff: dict) -> dict:
    """Whether the change needs a pipeline run: a notebook that writes rows (silver, gold) changes."""
    upd = [x for x in diff.get("items") or [] if x.get("item") in RUN_ITEMS and x.get("status") == _diff.UPDATE]
    if upd:
        return {"needed": True, "said": f"Yes: the {' and the '.join(x['label'] for x in upd)} change the rows; the pipeline runs once "
                                        "so that the silver tables and gold views hold them (apply_change starts that run "
                                        "after the notebooks, before the semantic model)."}
    return {"needed": False, "said": "No: no notebook that writes rows changes; the change reaches Fabric through the definitions alone."}


def steps(diff: dict) -> list[dict]:
    """What apply_change does, in order: each item the diff marks update in place, the run when rows change, the
    refresh after the model or the run."""
    items = {x["item"]: x for x in diff.get("items") or []}
    out = []
    for k in ORDER:
        x = items.get(k)
        if x and x.get("status") == _diff.UPDATE:
            out.append({"item": k, "name": x["name"], "action": "update definition", "summary": x.get("summary", "")})
        if k == "pipeline" and run_needed(diff)["needed"]:
            out.append({"item": "pipeline", "name": items["pipeline"]["name"], "action": "run once"})
    model = items.get("semantic_model")
    if model and (model.get("status") == _diff.UPDATE or run_needed(diff)["needed"]):
        out.append({"item": "semantic_model", "name": model["name"], "action": "refresh once"})
    for i, s in enumerate(out, 1):
        s["step"] = i
    return out


# ------------------------------------------------------------------ comparisons (verify_build's) ---------------------

def differences(item: str, expected, actual: dict, names_by_id: dict | None = None) -> list[dict]:
    """verify_build's comparison of an expected definition with the parts read from Fabric: a notebook's code line by
    line (metadata left out), a model's tables, relationships and measures, a pipeline's steps."""
    from . import verify_build as _v
    if item in NOTEBOOKS:
        return _v.compare_notebook(expected, actual.get("notebook-content.py") or "")["differences"]
    if item == "semantic_model":
        return _v.compare_model(expected, actual)["differences"]
    content = json.loads(actual.get("pipeline-content.json") or "{}")
    return _v.compare_pipeline(expected, content, None, names_by_id or {})["differences"]


def definition_parts(parts: dict) -> dict:
    """A model's parts as Fabric holds them: the README is not a part of the item (semantic_model.envelope)."""
    return {k: v for k, v in parts.items() if not k.lower().startswith("readme")}


# ------------------------------------------------------------------ the numbers ---------------------------------------

def numbers(execute):
    """LFD4's counter as change_diff's numbers layer: every change of the list, before and after it."""
    from . import change_numbers as _cn
    return lambda *, before, after: _cn.count(after["applied"], after["plan"], execute)


def _quote(name: str) -> str:
    return "[" + str(name).replace("]", "]]") + "]"


def numbers_after_run(counted: dict | None, targets: dict, execute, reverts: dict | None = None) -> dict:
    """After a run that succeeded: the rows of each silver table a filter changes, counted (SELECT COUNT_BIG(*)) and
    compared with the numbers layer's "after" for the last change that counted that table. Only counts; a table
    the numbers layer did not count, or a statement that fails, is not checked, with the reason.

    LFD9: for a revert (`reverts`, the numbers layer's {"id", "type"}) the layer counted the list with the reverted change
    in it, so a table that change counted is compared with its "before", the rows the revert brings back; a later filter
    on the same table was counted with the reverted one in place, so that table is not checked, with the reason."""
    if not isinstance(counted, dict) or not counted.get("changes"):
        return {"state": NOT_CHECKED, "said": "the numbers layer counted nothing to compare with", "rows": []}
    back_id = (reverts or {}).get("id")
    last: dict[str, int] = {}
    brought_back: set[str] = set()
    unsure: set[str] = set()
    for c in counted["changes"]:
        if c.get("type") != "filter_rows":
            continue
        back = back_id is not None and c.get("id") == back_id
        for n in c.get("numbers") or []:
            if n.get("what") != "rows" or n.get("untouched"):   # LFD9: only the tables the filter changes; an
                continue                                          # untouched one the silver notebook may check for orphans
            side = n.get("before") if back else n.get("after")
            if not isinstance(side, int):
                continue
            if back:
                brought_back.add(n["table"])
            elif n["table"] in brought_back:
                unsure.add(n["table"])
            last[n["table"]] = side
    if not last:
        return {"state": NOT_CHECKED, "said": "no filter in the list: no row count of a silver table to compare", "rows": []}
    rows = []
    for table, want in sorted(last.items()):
        if table in unsure:
            rows.append({"table": table, "state": NOT_CHECKED, "said": "a later filter on this table was counted with the "
                                                                       "reverted change in place"})
            continue
        target = targets.get(table)
        if not target:
            rows.append({"table": table, "state": NOT_CHECKED, "said": "the silver notebook writes no table for it"})
            continue
        sql = f"SELECT COUNT_BIG(*) AS n FROM {'.'.join(_quote(x) for x in target)}"
        try:
            got = int((list(execute(sql)) or [{}])[0].get("n"))
        except Exception as e:                                      # noqa: BLE001 - said on its own row
            rows.append({"table": table, "silver": ".".join(target), "state": NOT_CHECKED, "said": f"not counted ({type(e).__name__})",
                         "sql": sql})
            continue
        rows.append({"table": table, "silver": ".".join(target), "expected": want, "counted": got, "sql": sql,
                     "state": VERIFIED if got == want else DIFFERS})
    states = {r["state"] for r in rows}
    state = DIFFERS if DIFFERS in states else NOT_CHECKED if NOT_CHECKED in states else VERIFIED
    return {"state": state, "said": {VERIFIED: "the silver tables hold the rows the numbers layer counted",
                                     DIFFERS: "a silver table holds another number of rows than the numbers layer counted",
                                     NOT_CHECKED: "not every silver table could be counted"}[state], "rows": rows}


# ------------------------------------------------------------------ the answer within the tool's limit ---------------

RECEIPT_SAID = ("One receipt row per statement; each number above carries its statement, and change_numbers.statements "
                "gives them all without running them.")
SQL_OMITTED = "the SQL of each number did not fit in this answer; change_numbers.statements gives every statement"


def _numbers_trimmed(out: dict, limit: int) -> dict:
    """The numbers layer summarised: the receipt as its count, and when the answer is still too long, each number
    without its SQL (before, after and difference stay)."""
    out = copy.deepcopy(out)
    d = out.get("diff")
    if not isinstance(d, dict):
        return out
    out.setdefault("pipeline_run", run_needed(d))
    counted = (d.get("numbers") or {}).get("counted")
    if not isinstance(counted, dict):
        return out
    if isinstance(counted.get("receipt"), list):
        counted["receipt"] = {"rows": len(counted["receipt"]), "said": RECEIPT_SAID}
    if len(json.dumps(out, indent=2)) > limit:
        for c in counted.get("changes") or []:
            for n in c.get("numbers") or []:
                for k in [k for k in n if k == "sql" or k.endswith("_sql")]:
                    n.pop(k)
        counted["sql_omitted"] = SQL_OMITTED
    return out


def answer(out: dict, limit: int) -> str:
    """propose_change's JSON: change_diff.answer after the numbers layer is trimmed and the run is said."""
    return _diff.answer(_numbers_trimmed(out, limit), limit)


def fit(out: dict, limit: int) -> str:
    """apply_change's JSON within `limit`: as answer(), with apply_change's own `writes` sentence."""
    out = _numbers_trimmed(out, limit)
    text = json.dumps(out, indent=2, default=str)
    items = (out.get("diff") or {}).get("items") or []
    while len(text) > limit and any(x.get("diff") for x in items):
        biggest = max((x for x in items if x.get("diff")), key=lambda x: len(x["diff"]))
        biggest.pop("diff")
        biggest["diff_omitted"] = "the unified diff did not fit in this answer; the summary and the line counts stand"
        text = json.dumps(out, indent=2, default=str)
    return text
