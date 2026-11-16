"""The issue catalogue as data (docs/LIFECYCLE-DESIGN.md sections 2 to 4): fifteen classes, one recogniser each.

A diagnosis is a lookup, not a guess. `CLASSES` holds, per class, how it is recognised, its severity, the fix the design
proposes, what may happen at each autonomy level, and the policy in three words: a person always decides, the owner can
opt in to a rule, or nothing is ever applied. `diagnose()` takes the signals Krusgraph already produces and returns the
issues they amount to:

- health rows, as the check notebook writes them to krusgraph.health (health.py: check, object, rule, status, count,
  baseline), including the drift step's rows;
- failed runs, as run_results.failure() gives them (Fabric's error code and text, classified by run_results.classify);
- the state of each built item, as product_life.status() gives it (missing, changed_outside);
- reads of an output that Fabric refused (an HTTP status).

A signal that no class matches is returned under `unclassified` with its own fields, never forced into a class. Evidence
is names, rules, statuses and counts; the only free text carried is Fabric's own error text for a failed run, as
run_results.py already shows it. Nothing here calls Fabric, reads a row, or changes anything: it is a pure function of
its input, by rules.

Verified, and how (B3, 15 November 2026): unit tests on signals produced by the code that emits them (the health step
on the synthetic shop and mill lakehouses in SQLite, the drift step, run_results.classify on Fabric-shaped error texts,
product_life.status on listings), tests/test_b3_issue_catalogue.py. Not run against Fabric. No tool, pipeline cell or
workload screen uses it yet; proposals, approvals, autonomy levels and Undo (LIFECYCLE-DESIGN sections 3 to 5) are not
built.

Where this reads the design and where it had to choose is said in docs/ISSUE-POLICY.md, "What B3 chose".
"""
from __future__ import annotations

from . import run_results

SEVERITIES = ("info", "amber", "red")
POLICIES = ("always a person", "opt-in rule", "never automatic")
ACTIONS = ("suggest", "auto", "rule", "inform")
DEFAULTS = {"orphan_factor": 3, "orphan_floor": 10}      # LIFECYCLE-DESIGN section 2: the owner's factor and absolute floor

_PERSON = "always a person"
_OPT_IN = "opt-in rule"
_NEVER = "never automatic"


def _c(cid, signal, recognised_by, severity, fix, dry_run, levels, policy, why):
    return {"id": cid, "signal": signal, "recognised_by": recognised_by, "severity": severity, "proposed_fix": fix,
            "dry_run_shows": dry_run, "levels": dict(zip((0, 1, 2), levels)), "policy": policy, "why": why}


# The order is the design's table (section 2). `severity` is the class's lowest; a recogniser raises it where the design
# says "amber or red".
CLASSES: tuple[dict, ...] = (
    _c("schema_drift.added_column", "health: drift row, rule column_added",
       "A column in the source today that the plan does not have.", "amber",
       "Add it to silver (and to the model if the owner ticks it).",
       "The silver notebook's new cell; no model change unless ticked.",
       ("suggest", "suggest", "rule"), _OPT_IN,
       "It changes a definition and the model, so it is applied only under a rule the owner wrote."),
    _c("schema_drift.dropped_column", "health: drift row, rule column_removed",
       "A column in the plan that the source no longer has; red when a key, a relationship, an ordering or a gold view "
       "uses it.", "amber",
       "Remove it from silver, gold and the model, and list each measure, report visual and API field that used it.",
       "The removals and what breaks.",
       ("suggest", "suggest", "suggest"), _PERSON,
       "It breaks reports and apps."),
    _c("schema_drift.retyped_column", "health: drift row, rule type_changed",
       "The same column with another type family; red when the drift step says it breaks silver.", "amber",
       "Update the silver notebook's cast; for a narrowing type, quarantine the rows that do not cast.",
       "The changed cast and a count of rows that would not cast.",
       ("suggest", "suggest", "rule"), _OPT_IN,
       "Only a widening change (such as int to bigint) may run under the owner's rule; narrowing can lose data and "
       "stays with a person."),
    _c("schema_drift.new_table", "health: drift row, rule table_added",
       "A table in the source that is not in the plan.", "info",
       "Add it to the plan: the review step opens with the new table and its inferred keys and links.",
       "A new plan; the user checks it as usual.",
       ("suggest", "suggest", "suggest"), _PERSON,
       "A plan change needs the row check and a person's review."),
    _c("schema_drift.dropped_table", "health: drift row, rule table_removed",
       "A table in the plan that the source no longer has.", "red",
       "Take it out of the plan and every output, or stop and ask.",
       "The outputs that lose a table.",
       ("suggest", "suggest", "suggest"), _PERSON,
       "It breaks reports and apps."),
    _c("orphan_spike", "health: orphans row, or quarantine row of a reference rule (R...)",
       "The orphan count is above the previous run's count times the owner's factor (default 3) and above an absolute "
       "floor (default 10).", "amber",
       "Quarantine the orphans (they already go there by default) and alert the owner with the counts.",
       "The quarantine count per rule.",
       ("suggest", "auto", "auto"), _OPT_IN,
       "Silver already quarantines by default; when the owner opts in to level 1, only the alert is added."),
    _c("duplicate_keys", "health: key row, status fail",
       "A key that was declared, given by a person or counted has duplicates or NULLs.", "red",
       "Keep one row per key (with the winner rule), or quarantine.",
       "The changed silver step.",
       ("suggest", "suggest", "suggest"), _PERSON,
       "Which row wins is a business decision."),
    _c("sums_mismatch", "health: join_sums row, status fail",
       "A gold join adds or loses amounts.", "red",
       "Show the join that fans out and propose the header-amount split.",
       "The changed gold view.",
       ("suggest", "suggest", "suggest"), _PERSON,
       "How an amount is split is a business decision."),
    _c("row_drop", "health: row_count row, status warn",
       "A table's row count fell by the owner's threshold or more since the previous run (default: by half).", "amber",
       "No change. Ask the owner whether the source is complete.",
       "Nothing.",
       ("inform", "inform", "inform"), _NEVER,
       "There is nothing to apply; only a person knows whether the source is complete."),
    _c("stale_data", "health: freshness row, status warn or fail",
       "The last write to a source table is older than the owner's limit (default: warn after 2 schedule intervals, "
       "fail after 3).", "amber",
       "No change. Show the source's last write and the schedule.",
       "Nothing.",
       ("inform", "inform", "inform"), _NEVER,
       "There is nothing to apply; the load is the source's."),
    _c("failed_run", "run: a failed job instance",
       "A job instance that failed; the sub-class is run_results.classify's (import error, table not found, timeout, "
       "unknown), a heuristic on Fabric's error text.", "red",
       "Re-run once, with Fabric's error shown and the catalogue's next step.",
       "The run that would start.",
       ("suggest", "auto", "auto"), _OPT_IN,
       "A re-run changes no definition and is idempotent: silver overwrites, gold views are recreated. Once per run, "
       "never in a loop."),
    _c("capacity_limit", "run: a failed job instance whose error text says the capacity is paused or throttled",
       "run_results.classify gives capacity_paused_or_throttled.", "amber",
       "Re-run once after the owner's wait (default 30 minutes), with a link to the capacity.",
       "The run and when.",
       ("suggest", "auto", "auto"), _OPT_IN,
       "Not a data problem; waiting is the fix. Once per run, never in a loop."),
    _c("permission_lost", "run: error text that says permission denied; read: an output answers 403",
       "run_results.classify gives permission_denied, or the item's own read of an output answers 403.", "red",
       "No change. Say which identity lacks which role; a person grants it.",
       "The Entra or Fabric steps.",
       ("suggest", "suggest", "suggest"), _PERSON,
       "It needs a person with rights; Krusgraph grants nothing."),
    _c("item_deleted", "item: state missing",
       "An item Krusgraph made is no longer listed in its workspace.", "red",
       "Re-create the item from the recorded plan, or forget it.",
       "The Create dry run for that one output.",
       ("suggest", "suggest", "suggest"), _PERSON,
       "It needs a person with rights, and only a person knows whether the deletion was meant."),
    _c("item_changed_outside", "item: state changed_outside",
       "The item exists, but it was renamed, is of another type, or its description names another plan.", "amber",
       "Show the difference; offer Update (overwrite) or Keep (record it as accepted).",
       "The Update dry run.",
       ("suggest", "suggest", "suggest"), _PERSON,
       "An Update overwrites what someone changed by hand; a person chooses."),
)
BY_ID = {c["id"]: c for c in CLASSES}
_DRIFT = {"column_added": "schema_drift.added_column", "column_removed": "schema_drift.dropped_column",
          "type_changed": "schema_drift.retyped_column", "table_added": "schema_drift.new_table",
          "table_removed": "schema_drift.dropped_table"}
_RANK = {s: i for i, s in enumerate(SEVERITIES)}
HEALTH_WORDS = {"red": "red", "amber": "amber", "info": "green", None: "green"}


def _issue(cid: str, obj: str, evidence: dict, severity: str | None = None, **more) -> dict:
    c = BY_ID[cid]
    return {"class": cid, "object": obj, "severity": severity or c["severity"], "evidence": evidence,
            "proposed_fix": c["proposed_fix"], "policy": c["policy"], "levels": dict(c["levels"]), **more}


def _counts(row: dict) -> dict:
    return {k: row.get(k) for k in ("check", "rule", "status", "count", "baseline")}


def _spike(row: dict, settings: dict) -> bool | None:
    """True when the count is a spike, False when it is not, None when there is no earlier run to compare with."""
    count, base = row.get("count"), row.get("baseline")
    if count is None or base is None:
        return None
    return count > base * settings["orphan_factor"] and count > settings["orphan_floor"]


def from_health(rows: list[dict], settings: dict | None = None) -> dict:
    """Issues, quiet signals and unclassified signals from health rows of one run."""
    s = {**DEFAULTS, **(settings or {})}
    issues, quiet, unclassified = [], [], []
    for r in rows:
        check, rule, status, obj = r.get("check"), str(r.get("rule") or ""), r.get("status"), str(r.get("object") or "")
        is_orphans = check == "orphans" or (check == "quarantine" and rule.upper().startswith("R"))
        if is_orphans and (r.get("count") or 0) > 0:
            spike = _spike(r, s)
            if spike:
                issues.append(_issue("orphan_spike", obj, _counts(r)))
            elif check == "orphans":                           # orphans left in silver that are not a spike: no class says what
                unclassified.append({"signal": "health", "object": obj, **_counts(r)})
            else:
                quiet.append({"object": obj, **_counts(r),
                              "why": "rows in quarantine, counted; not a spike" if spike is False else
                                     "rows in quarantine, counted; no earlier run with the same plan to compare with"})
            continue
        if status == "pass" or status is None:
            continue
        if check == "drift" and rule in _DRIFT:
            cid = _DRIFT[rule]
            issues.append(_issue(cid, obj, _counts(r), "red" if status == "fail" else BY_ID[cid]["severity"]))
        elif check == "key" and status == "fail":
            issues.append(_issue("duplicate_keys", obj, _counts(r)))
        elif check == "join_sums" and status == "fail":
            issues.append(_issue("sums_mismatch", obj, _counts(r)))
        elif check == "row_count" and status == "warn":
            issues.append(_issue("row_drop", obj, _counts(r)))
        elif check == "freshness":
            issues.append(_issue("stale_data", obj, _counts(r), "red" if status == "fail" else "amber"))
        elif check == "quarantine":                            # rows a key rule put aside: the silver notebook's own work
            quiet.append({"object": obj, **_counts(r), "why": "rows in quarantine, counted"})
        else:
            unclassified.append({"signal": "health", "object": obj, **_counts(r)})
    return {"issues": issues, "quiet": quiet, "unclassified": unclassified}


def from_run(item: str, failure: dict | None) -> dict | None:
    """The issue for one failed run. `failure` is run_results.failure()'s answer ({error_code, message, category, ...}) or
    Fabric's failureReason ({errorCode, message}); None or empty means the run did not fail."""
    if not failure:
        return None
    message = failure.get("message")
    code = failure.get("error_code") or failure.get("errorCode")
    category = failure.get("category") or run_results.classify(message, code).get("category") or "unknown"
    evidence = {"category": category, "error_code": code, "message": (message or "")[:run_results.MESSAGE_CAP] or None,
                "heuristic": run_results.HEURISTIC}
    if category == "capacity_paused_or_throttled":
        return _issue("capacity_limit", item, evidence)
    if category == "permission_denied":
        return _issue("permission_lost", item, evidence)
    return _issue("failed_run", item, evidence, sub_class=category)


def from_item(row: dict) -> dict | None:
    """The issue for one row of product_life.status(): a missing item, or one changed outside Krusgraph."""
    name = f"{row.get('type') or 'item'} {row.get('name') or row.get('id') or ''}".strip()
    if row.get("state") == "missing":
        return _issue("item_deleted", name, {"state": "missing", "id": row.get("id")})
    if row.get("state") == "changed_outside":
        return _issue("item_changed_outside", name, {"state": "changed_outside", "id": row.get("id"), "why": row.get("why")})
    return None


def from_read(read: dict) -> dict | None:
    """The issue for one read of an output: {"object": name, "http_status": 403}. Other statuses are not a class."""
    if read.get("http_status") == 403:
        return _issue("permission_lost", str(read.get("object") or ""), {"http_status": 403})
    return None


def diagnose(health: list[dict] | None = None, runs: list[dict] | None = None, items: list[dict] | None = None,
             reads: list[dict] | None = None, settings: dict | None = None) -> dict:
    """Every signal looked up in the catalogue.

    `runs` are {"item": name, "failure": {...}}; `items` are product_life.status() rows; `reads` are
    {"object", "http_status"}. Returns the issues (worst first, then in the order given), the quiet signals, the
    unclassified ones, and the product's health word: red when any issue is red, amber when any is amber, else green.
    Unclassified signals do not change the word; they are shown beside it."""
    h = from_health(health or [], settings)
    issues, unclassified = list(h["issues"]), list(h["unclassified"])
    for r in runs or []:
        got = from_run(str(r.get("item") or ""), r.get("failure"))
        if got:
            issues.append(got)
    for row in items or []:
        got = from_item(row)
        if got:
            issues.append(got)
    for read in reads or []:
        got = from_read(read)
        if got:
            issues.append(got)
        elif read.get("http_status") not in (None, 200):
            unclassified.append({"signal": "read", "object": str(read.get("object") or ""), "http_status": read.get("http_status")})
    issues.sort(key=lambda i: -_RANK[i["severity"]])                       # stable: the given order within a severity
    worst = max((i["severity"] for i in issues), key=_RANK.get, default=None)
    return {"health": HEALTH_WORDS[worst], "issues": issues, "quiet": h["quiet"], "unclassified": unclassified,
            "counts": {s: sum(1 for i in issues if i["severity"] == s) for s in reversed(SEVERITIES)}}


def action(cid: str, level: int) -> str:
    """What happens to a class at an autonomy level: suggest, auto, rule or inform. Level 0 never applies anything."""
    if level not in (0, 1, 2):
        raise ValueError("The autonomy level is 0 (suggest only), 1 (safe classes) or 2 (the owner's rules).")
    return BY_ID[cid]["levels"][level]


def policy_table() -> list[dict]:
    """One row per class for the public policy table (backlog H-01): the policy in words, the action per level, and why."""
    return [{"class": c["id"], "policy": c["policy"], "level_0": c["levels"][0], "level_1": c["levels"][1],
             "level_2": c["levels"][2], "why": c["why"]} for c in CLASSES]


def policy_markdown() -> str:
    """The policy table as Markdown; docs/ISSUE-POLICY.md holds exactly this between its markers (a test keeps them equal)."""
    lines = ["| Issue class | Policy | Level 0 | Level 1 | Level 2 | Why |", "| --- | --- | --- | --- | --- | --- |"]
    lines += [f"| `{r['class']}` | {r['policy']} | {r['level_0']} | {r['level_1']} | {r['level_2']} | {r['why']} |" for r in policy_table()]
    return "\n".join(lines)


def catalogue_markdown() -> str:
    """The catalogue as Markdown: class, the signal it is recognised on, how, severity and the proposed fix."""
    lines = ["| Issue class | Signal | Recognised by | Severity | Proposed fix |", "| --- | --- | --- | --- | --- |"]
    lines += [f"| `{c['id']}` | {c['signal']} | {c['recognised_by']} | {c['severity']} | {c['proposed_fix']} |" for c in CLASSES]
    return "\n".join(lines)
