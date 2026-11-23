"""BL64: the plan as a Fabric semantic view (preview), as a YAML file for a lakehouse's `Context/Semantic Views/<view>/`
folder. Nothing is written to Fabric or OneLake; the answer is the file text and what did not fit.

A semantic view is part of Fabric IQ: YAML files in a lakehouse define datasets, relationships and metrics; Publish
compiles them to TMDL in `SystemContext/` and creates a read-only Direct Lake semantic model named after the view's
folder. The format is open YAML based on Apache Ossie (incubating), with Fabric's own requirements.

Format followed: the Microsoft Learn pages as they stand in MicrosoftDocs/fabric-docs at commit 0374a4d (read 23
November 2026): docs/fundamentals/semantic-views-yaml-reference.md ("Semantic view YAML syntax reference", ms.date
2026-10-20), semantic-views-create.md (ms.date 2026-11-18) and semantic-views-overview.md (ms.date 2026-11-18,
"Considerations and limitations"). What the draft takes from them, and nothing beyond it:

- `version: 0.2.0.dev0` and `name` in every file; the folder name, not `name`, becomes the view and model name.
- A dataset is `name` and `source` (a schema-qualified lakehouse table) with an optional `description`. Columns come
  from the table; `fields`, `primary_key` and `unique_keys` are omitted by Publish with a warning, so none is written.
- A relationship is `name`, `from` (the many side), `to` (the one side), `from_columns` and `to_columns` with exactly
  one column each. The `to` column must hold unique values. Every relationship is active, so only one filter path may
  join two tables. Relationships do not support `description`: the rule and the counts behind each one are YAML comments.
  Datasets are inferred by Publish and relationships are not, so the view has exactly the relationships written here.
- A metric is `name` and `expression.dialects` with a `dialect: DAX` entry; it becomes a measure of a table named
  `Metrics`. Columns are referenced as 'dataset'[column] by the dataset's `name`. A metric name cannot match a table name.
- `ai_context` and `custom_extensions` are omitted with warnings, so none is written.

The relationships are the semantic model draft's own active set (semantic_model.active_set, with validate_plan's
counts deciding when they are given, BL51), on the source tables, and of those only the ones whose `to` side
validate_plan counted as a unique key. A relationship that needs more than one column on a side, or whose one side is
keyed on several columns (SAP's MANDT+VBELN), does not fit and is listed under `needs_key_column`; one whose one side the
counts show is not unique is listed under `not_unique`. The metrics are the row counts semantic_model.suggested_measures
gives the fact tables, COUNTROWS of one dataset, and nothing else.
"""
from __future__ import annotations

import json
import re

from . import privacy as _privacy
from . import semantic_model as _sm
from .infer import Plan

VERSION = "0.2.0.dev0"                                # "Currently supported version" (semantic-views-yaml-reference.md)
FOLDER = "Context/Semantic Views"
LEARN = "https://learn.microsoft.com/fabric/fundamentals/semantic-views-yaml-reference"
LEARN_CREATE = "https://learn.microsoft.com/fabric/fundamentals/semantic-views-create"
LEARN_LIMITS = "https://learn.microsoft.com/fabric/fundamentals/semantic-views-overview#considerations-and-limitations"
SOURCE_READ = "MicrosoftDocs/fabric-docs at commit 0374a4d, read 23 November 2026"

LIMITS = (
    "Semantic views are in lakehouses only.",
    "A published metric needs a DAX expression; other dialects are kept in the file but not published.",
    "A relationship has a single column on each side, and its `to` column must hold unique values.",
    "Only .yaml files are published (.yml is ignored without a warning), at most 20 files and 16 MB per view.",
    "The view's folder name becomes the view name and the semantic model's name; the YAML `name` is not used.",
    "No Git integration or deployment pipelines, for the view or its model.",
    "The List and Publish APIs are in beta and do not accept a third-party token.",
    "Creating an ontology from the generated semantic model is not supported.",
)
LEFT_FOR_LATER = ("Writing the file to the lakehouse's Context/Semantic Views folder (a create with dry_run=false) and "
                  "publishing the view are left for a later round. Today a person uploads the file (Upload files on the view "
                  "folder in the lakehouse) and publishes the view from the lakehouse.")
NEEDS_KEY_COLUMN = ("A semantic view relates tables on one column per side. These relationships need several columns, or point "
                    "at a table keyed on several columns. A combined key column in silver or gold (one column holding the "
                    "key's parts, on both tables) makes them fit; relate on that column.")
NOT_CHECKED = ("The `to` side of a relationship in a semantic view must hold unique values. These relationships are in the "
               "active set but point at a key that validate_plan has not counted as unique, so they are not in the view. "
               "Run the draft with validate=true (or validate_plan) and they are added where the key holds.")

_PLAIN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")
_RESERVED = {"yes", "no", "true", "false", "null", "on", "off", "y", "n"}
_BAD_NAME = re.compile(r"[\\/:*?\"<>|\x00-\x1f]")


def _y(value: str) -> str:
    """A YAML scalar: bare when it is a plain identifier, otherwise a double-quoted string (JSON's escaping is valid in
    YAML's double-quoted style)."""
    s = str(value)
    if _PLAIN.match(s) and s.lower() not in _RESERVED:
        return s
    return json.dumps(s, ensure_ascii=False)


def _comment(text: str) -> str:
    return "# " + " ".join(str(text).split())


def view_name_problem(name: str) -> str | None:
    """Why `name` cannot be a view folder's name, or None. The folder name becomes the semantic model's name."""
    if not name or not name.strip():
        return "the view needs a name: it becomes the folder under Context/Semantic Views and the semantic model's name"
    if name != name.strip():
        return "the view name starts or ends with a space"
    if _BAD_NAME.search(name):
        return "the view name holds a character a folder name cannot have (\\ / : * ? \" < > |)"
    return None


def file_path(view: str) -> str:
    """Where the file goes: the view folder, with the name Fabric's own starter file uses (<view>_semantic_view.yaml),
    which this file replaces when the view was started with New semantic view."""
    return f"{FOLDER}/{view}/{view}_semantic_view.yaml"


def counts_text(e: dict | None) -> str:
    """validate_plan's counts of one link (graphs.link_counts), counts only, never a row value."""
    if not e or e.get("rows_with_value") is None:
        return "not counted by validate_plan" if not e else f"validate_plan: {e.get('state')}"
    return (f"validate_plan counted {e['rows_with_value']} rows with a value, {e['matched']} matched, "
            f"{e['orphans']} orphans ({e['state']})")


def checked_unique(plan: Plan, validation: dict | None) -> set[str]:
    """The tables whose one-column key validate_plan counted as unique with no NULLs (its verdict "unique in all n
    rows"), or that the review stands behind as checked against the rows (plan.checked_keys with how "rows"). Only these
    can be the `to` side of a relationship in the view: the reference says that column must hold unique values."""
    out = set()
    for k in (validation or {}).get("keys", []):
        key = plan.keys.get(k.get("table"), ([], ""))[0]
        if (len(key) == 1 and [c.lower() for c in k.get("columns", [])] == [key[0].lower()]
                and str(k.get("verdict", "")).startswith("unique")):
            out.add(k["table"])
    for t, c in (plan.checked_keys or {}).items():
        key = plan.keys.get(t, ([], ""))[0]
        if c.get("how") == "rows" and len(key) == 1 and [x.lower() for x in c.get("columns", [])] == [key[0].lower()]:
            out.add(t)
    return out


def draft(plan: Plan, info: dict, name: str = "semantic_view", tables: list[str] | None = None, validation: dict | None = None,
          show_personal_data: bool = False) -> dict:
    """info: item_name, item_kind, schema (server._source_inputs). Returns {"parts": {path: yaml}, "summary": ...,
    "needs_key_column", "not_unique", "to_side_not_checked", "not_in_view_inactive", "not_in_view_personal_data",
    "personal_data", "written": False}. `validation` (evidence.validate's answer): its counts choose the active set
    exactly as in the semantic model draft (BL51), show which `to` sides are unique, and go into each comment."""
    from . import graphs
    problem = view_name_problem(name)
    if problem:
        raise ValueError(problem)
    wanted = {t.lower() for t in tables} if tables else None
    chosen = [t for t in plan.schema if not wanted or t.name.lower() in wanted]
    names = {t.name for t in chosen}
    schema = info.get("schema") or plan.schema.schema or "dbo"
    kind = info.get("item_kind") or "Lakehouse"

    # Dataset names are the table names; a second table whose name differs only by case gets a suffix, because the
    # generated model's table names are not case-sensitive.
    dataset: dict[str, str] = {}
    taken: set[str] = set()
    for t in chosen:
        n, i = t.name, 2
        while n.lower() in taken:
            n, i = f"{t.name}_{i}", i + 1
        taken.add(n.lower())
        dataset[t.name] = n

    # The relationships: the semantic model draft's own split and active set, on the source tables (its combined=False).
    dup = _sm.keys_not_unique(plan, validation)
    single = [r for r in plan.relationships if r.source in names and r.target in names and r.target not in dup
              and len(r.source_cols) == 1 and len(r.target_cols) == 1 and len(plan.keys.get(r.target, ([], ""))[0]) == 1]
    other = [r for r in plan.relationships if r.source in names and r.target in names and r not in single]
    active, inactive, _evidence = _sm.active_set(plan, single, validation, plan)
    counted = graphs.link_counts(plan, validation)           # every counted link, composite ones too; counts only
    unique = checked_unique(plan, validation)
    unchecked = [r for r in active if r.target not in unique]
    flagged = _privacy.personal_columns(plan.schema, sorted(names))
    personal = {(t, c.lower()) for t, c in flagged}
    on_personal = [] if show_personal_data else [
        r for r in active if r.target in unique
        and ((r.source, r.source_cols[0].lower()) in personal or (r.target, r.target_cols[0].lower()) in personal)]
    emitted = [r for r in active if r.target in unique and r not in on_personal]

    analysis = graphs.analyze(plan, validation)
    role_of = {t: r["role"] for t, r in analysis["roles"].items()}
    ref_cols = {(r.source, r.source_cols[0].lower()) for r in single}
    measures = [m for m in _sm.suggested_measures(plan, chosen, role_of, ref_cols) if m["column"] is None]
    metrics_why = ""
    if "metrics" in taken:
        metrics_why = ("A table is named Metrics, the name of the table Publish creates for the metrics, so no metric is drafted; "
                       "give that dataset another name first.")
        measures = []

    lines = [_comment("Drafted by Krusgraph from the plan; nothing was written to OneLake or Fabric."),
             _comment(f"Format: Fabric semantic view YAML {VERSION}, {LEARN}"),
             _comment(f"Upload to {FOLDER}/{name}/ in the lakehouse; the folder name becomes the view and semantic model name."),
             f"version: {VERSION}",
             f"name: {_y(name)}",
             "description: " + _y(f"Tables of {schema} with the relationships Krusgraph inferred and checked; drafted from the plan."),
             "datasets:"]
    for t in chosen:
        key, krule = plan.keys.get(t.name, ([], ""))
        desc = f"Table {schema}.{t.name}; its role in the plan's graph: {role_of.get(t.name, 'other')}."
        if key and t.name not in dup:
            desc += f" Key: {' + '.join(key)} (rule {krule})."
        cols = sorted(c for (tt, c) in personal if tt == t.name)
        if cols:
            lines.append("  " + _comment(f"{t.name} holds columns named like personal data ({', '.join(cols)}); the view reads "
                                         "every column of the table. See personal_data in Krusgraph's answer."))
        lines += [f"  - name: {_y(dataset[t.name])}", f"    source: {_y(schema + '.' + t.name)}", f"    description: {_y(desc)}"]

    rel_names: set[str] = set()
    out_rels = []
    if emitted:
        lines.append("relationships:")
    for r in emitted:
        rname = f"{dataset[r.source]}_to_{dataset[r.target]}"
        if rname.lower() in rel_names:
            rname = f"{dataset[r.source]}_{r.source_cols[0]}_to_{dataset[r.target]}"
        rel_names.add(rname.lower())
        e = counted.get(r.key)
        lines += ["  " + _comment(f"rule {r.rule}; {counts_text(e)}"),
                  f"  - name: {_y(rname)}", f"    from: {_y(dataset[r.source])}", f"    to: {_y(dataset[r.target])}",
                  "    from_columns:", f"      - {_y(r.source_cols[0])}", "    to_columns:", f"      - {_y(r.target_cols[0])}"]
        out_rels.append({"name": rname, "from": dataset[r.source], "to": dataset[r.target], "from_column": r.source_cols[0],
                         "to_column": r.target_cols[0], "rule": r.rule,
                         **({k: e.get(k) for k in ("state", "rows_with_value", "matched", "orphans")} if e else {"state": "not_counted"})})
    out_metrics = []
    if measures:
        lines.append("metrics:")
    for m in measures:
        ds = dataset[m["table"]]
        expr = f"COUNTROWS({_sm._dax_table(ds)})"
        lines += [f"  - name: {_y(m['name'])}", f"    description: {_y('The number of rows in ' + ds + '.')}",
                  "    expression:", "      dialects:", "        - dialect: DAX", f"          expression: {json.dumps(expr)}"]
        out_metrics.append({"name": m["name"], "dax": expr, "why": m["why"]})
    text = "\n".join(lines) + "\n"

    def item(r, why: str) -> dict:
        return {"from": r.source, "columns": list(r.source_cols), "to": r.target, "to_columns": list(r.target_cols),
                "rule": r.rule, "counts": counts_text(counted.get(r.key)), "why": why}
    why_inactive = {id(r): w for r, w in inactive}
    inactive_items = [item(r, why_inactive[id(r)]) for r, _w in inactive]
    personal_items = [item(r, "a column on one side is named like personal data; show_personal_data=true includes the relationship")
                      for r in on_personal]
    unchecked_items = [item(r, f"{r.target}.{r.target_cols[0]} has not been counted as unique") for r in unchecked]
    needs_key = [item(r, _sm.not_expressible_why(plan, r)) for r in other if r.target not in dup]
    not_unique = [item(r, _sm.not_unique_why(r.target, dup[r.target])) for r in other if r.target in dup]

    personal_list = [{"table": t, "column": c, "rule": f["rule"], "what": f["what"]} for (t, c), f in sorted(flagged.items())]
    if personal_list:
        personal_note = ("A semantic view reads every column of a dataset's table; it cannot leave a column out (Publish omits "
                         "`fields`). Krusgraph's relationships, metrics and descriptions do not use the columns named like personal "
                         "data" + ("" if show_personal_data else " unless show_personal_data=true")
                         + ". To keep them out of the generated model, point the dataset at a gold view without them "
                         "(gold_views_draft leaves them out) or restrict them with OneLake security.")
    else:
        personal_note = "No column is named like personal data."
    out = {
        "view": name,
        "parts": {file_path(name): text},
        "summary": {
            "datasets": len(chosen), "relationships": len(out_rels), "metrics": len(out_metrics),
            "needs_key_column": len(needs_key), "not_unique": len(not_unique), "to_side_not_checked": len(unchecked_items),
            "not_in_view_inactive": len(inactive_items), "not_in_view_personal_data": len(personal_items),
            "source": f"{kind} {info.get('item_name') or ''}".strip() + f", schema {schema}",
            "counted": bool(validation),
            "relationships_list": out_rels, "metrics_list": out_metrics,
            **({"active_set_rule": _sm.COUNTED_SAID} if _evidence is not None else {}),
        },
        "needs_key_column": {"say": NEEDS_KEY_COLUMN if needs_key else "", "relationships": needs_key},
        "not_unique": not_unique,
        "to_side_not_checked": {"say": NOT_CHECKED if unchecked_items else "", "relationships": unchecked_items},
        "not_in_view_inactive": inactive_items,
        "not_in_view_personal_data": personal_items,
        "personal_data": {"columns": personal_list, "shown": bool(show_personal_data), "note": personal_note},
        "metrics_note": metrics_why or ("Only the row count of each fact table (COUNTROWS of one dataset), as the semantic model draft "
                                        "suggests it. Sums are left out: an amount at the level of a header repeats on its lines, and "
                                        "the semantic model draft decides those level by level."),
        "limits": {"from": LEARN_LIMITS, "read": SOURCE_READ, "items": list(LIMITS)},
        "left_for_later": LEFT_FOR_LATER,
        "written": False,
    }
    if kind != "Lakehouse":
        out["gate"] = (f"Semantic views are in lakehouses only, and this source is a {kind}. The file fits a lakehouse whose "
                       "tables have the same names (for example through shortcuts).")
    return out
