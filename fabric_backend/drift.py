"""Plan drift: today's plan against the definition of an existing API for GraphQL item. What is new, what the API
still refers to that is gone, which relationships the plan no longer supports, and whether a `create_backend`
with the same name would change anything."""
from __future__ import annotations

from .graphql import decode, definition
from .infer import Plan


def _objects(body: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for ds in body.get("datasources", []):
        for o in ds.get("objects", []):
            out[str(o.get("sourceObject", ""))] = o
    return out


def _rel_key(o: dict, r: dict) -> tuple:
    return (o.get("sourceObject"), r.get("field"), r.get("targetObject"), tuple(r.get("sourceFields") or []), tuple(r.get("targetFields") or []))


def compare(plan: Plan, existing: dict, name: str, workspace_id: str, source_id: str, source_type: str,
            writable: bool = False, tables: list[str] | None = None) -> dict:
    """existing: the API's graphql-definition.json. The plan is rendered the way create_backend would render it,
    and the two definitions are compared object by object."""
    wanted_env = definition(plan, name, workspace_id, source_id, source_type, writable=writable, tables=tables)
    wanted = decode(wanted_env)
    old, new = _objects(existing), _objects(wanted)
    schema_tables = {f"{t.schema}.{t.name}": t for t in plan.schema}

    new_tables = sorted(set(new) - set(old))
    gone = []
    for so in sorted(set(old) - set(new)):
        why = "the table is no longer in the schema" if so not in schema_tables else "the table is excluded by `tables`"
        gone.append({"table": so, "why": why})
    new_columns, removed_columns = [], []
    for so in sorted(set(old) & set(new)):
        o_cols = set((old[so].get("fieldMappings") or {}).keys())
        n_cols = set((new[so].get("fieldMappings") or {}).keys())
        for c in sorted(n_cols - o_cols):
            new_columns.append({"table": so, "column": c})
        for c in sorted(o_cols - n_cols):
            removed_columns.append({"table": so, "column": c, "why": "the API still maps a column the source no longer has"})
    old_rels = {_rel_key(o, r): (o, r) for o in old.values() for r in o.get("relationships", [])}
    new_rels = {_rel_key(o, r): (o, r) for o in new.values() for r in o.get("relationships", [])}
    unsupported = []
    for k in sorted(set(old_rels) - set(new_rels), key=str):
        o, r = old_rels[k]
        target = r.get("targetObject")
        if o.get("sourceObject") not in new:
            why = "its table is gone"
        elif target not in new:
            why = f"its target {target} is gone"
        elif not set(r.get("sourceFields") or []) <= set((new[o["sourceObject"]].get("fieldMappings") or {}).keys()):
            why = "a column it joins on is gone"
        else:
            why = "the plan no longer infers it (a key or rule changed); pass it in `confirmed` to keep it"
        entry = {"table": o.get("sourceObject"), "field": r.get("field"), "target": target,
                 "columns": list(r.get("sourceFields") or []), "why": why}
        if why.startswith("the plan no longer infers it") and r.get("cardinality") == "ManyToOne":
            entry["confirmed"] = {"source": str(o.get("sourceObject")).split(".")[-1], "source_cols": entry["columns"],
                                  "target": str(target).split(".")[-1], "target_cols": list(r.get("targetFields") or []),
                                  "field_name": r.get("field") or ""}
        unsupported.append(entry)
    new_relationships = [{"table": o.get("sourceObject"), "field": r.get("field"), "target": r.get("targetObject"),
                          "columns": list(r.get("sourceFields") or [])}
                         for k, (o, r) in sorted(new_rels.items(), key=lambda kv: str(kv[0])) if k not in old_rels]
    actions_changed = [{"table": so, "from": old[so].get("actions"), "to": new[so].get("actions")}
                       for so in sorted(set(old) & set(new)) if (old[so].get("actions") or {}) != (new[so].get("actions") or {})]
    source_changed = [ds for ds in existing.get("datasources", []) if ds.get("sourceItemId") not in (None, source_id)]

    would_change = bool(new_tables or gone or new_columns or removed_columns or unsupported or new_relationships
                        or actions_changed or source_changed)
    pieces = []
    if new_tables:
        pieces.append(f"{len(new_tables)} new table(s)")
    if gone:
        pieces.append(f"{len(gone)} table(s) the API has that the plan does not")
    if new_columns:
        pieces.append(f"{len(new_columns)} new column(s)")
    if removed_columns:
        pieces.append(f"{len(removed_columns)} column(s) the API still references")
    if unsupported:
        pieces.append(f"{len(unsupported)} relationship(s) the plan no longer supports")
    if new_relationships:
        pieces.append(f"{len(new_relationships)} new relationship(s)")
    if actions_changed:
        pieces.append(f"{len(actions_changed)} table(s) with changed actions")
    summary = ("no drift: a create_backend with this name would rewrite the same definition" if not would_change
               else "drift: " + ", ".join(pieces) + f"; a create_backend named {name!r} would update the item with these changes")
    return {"summary": summary, "would_change": would_change, "new_tables": new_tables, "tables_gone": gone,
            "new_columns": new_columns, "removed_columns": removed_columns, "relationships_unsupported": unsupported,
            "new_relationships": new_relationships, "actions_changed": actions_changed,
            "source_changed": [{"api_source_item": ds.get("sourceItemId"), "plan_source_item": source_id} for ds in source_changed],
            "skipped_relationships": wanted_env.get("skipped_relationships", []),
            "keep_with_confirmed": [u["confirmed"] for u in unsupported if "confirmed" in u]}
