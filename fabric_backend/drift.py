"""Plan drift: today's plan against the definition of an existing API for GraphQL item. What is new, what the API
still refers to that is gone, which relationships the plan no longer supports, and whether a `create_backend`
with the same name would change anything."""
from __future__ import annotations

import dataclasses

from .graphql import decode, definition, graphql_name
from .infer import Plan


def _objects(body: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for ds in body.get("datasources", []):
        for o in ds.get("objects", []):
            out[str(o.get("sourceObject", ""))] = o
    return out


def _rel_key(o: dict, r: dict) -> tuple:
    return (o.get("sourceObject"), r.get("field"), r.get("targetObject"), tuple(r.get("sourceFields") or []), tuple(r.get("targetFields") or []))


def _shape(obj, target, source_fields, target_fields, cardinality) -> tuple:
    """A relationship without its name: the same columns in the same direction (case does not matter)."""
    return (str(obj or "").lower(), str(target or "").lower(), tuple(str(c).lower() for c in source_fields or []),
            tuple(str(c).lower() for c in target_fields or []), cardinality)


def _names_by_shape(body: dict) -> dict[tuple, str]:
    return {_shape(o.get("sourceObject"), r.get("targetObject"), r.get("sourceFields"), r.get("targetFields"), r.get("cardinality")): r.get("field")
            for o in _objects(body).values() for r in o.get("relationships", [])}


def keep_api_names(plan: Plan, existing: dict, confirmed: list[dict] | None = None) -> tuple[Plan, list[dict]]:
    """The plan with an existing API's field names wherever the API has the same relationship (the same columns in
    the same direction) under another name, so that an update keeps the names an app already queries instead of
    removing one field and adding another (finding 7 of the live test of 27 October 2026: the API had addresses.orders,
    the plan said orders_as_ship_to). A field_name or reverse_name given in `confirmed` wins; a name that would clash
    with another field of the same type is not taken. Returns the plan and what was kept."""
    api = _names_by_shape(existing)
    given = {(str(c.get("source", "")).lower(), tuple(str(x).lower() for x in c.get("source_cols") or []), str(c.get("target", "")).lower()):
             (bool(c.get("field_name")), bool(c.get("reverse_name"))) for c in confirmed or []}
    obj = {t.name: f"{t.schema}.{t.name}" for t in plan.schema}
    rels = [dataclasses.replace(r) for r in plan.relationships]

    def taken(table: str, rel, attr: str) -> set[str]:
        names = {graphql_name(c.name.lstrip("_")) for c in plan.schema[table].columns}
        for x in rels:
            if x.source == table and not (x is rel and attr == "field_name"):
                names.add(x.field_name)
            if x.target == table and not (x is rel and attr == "reverse_name"):
                names.add(x.reverse_name)
        return names
    kept = []
    for r in rels:
        if r.source not in obj or r.target not in obj:
            continue
        given_field, given_reverse = given.get((r.source.lower(), tuple(c.lower() for c in r.source_cols), r.target.lower()), (False, False))
        for attr, shape, was_given, table in (
                ("field_name", _shape(obj[r.source], obj[r.target], r.source_cols, r.target_cols, "ManyToOne"), given_field, r.source),
                ("reverse_name", _shape(obj[r.target], obj[r.source], r.target_cols, r.source_cols, "OneToMany"), given_reverse, r.target)):
            name = api.get(shape)
            if not name or was_given or name == getattr(r, attr) or name in taken(table, r, attr):
                continue
            kept.append({"table": obj[table], "field": name, "instead_of": getattr(r, attr),
                         "relationship": f"{r.source}.{'+'.join(r.source_cols)} -> {r.target}.{'+'.join(r.target_cols)}"})
            setattr(r, attr, name)
    return dataclasses.replace(plan, relationships=rels), kept


def _keep_entry(o: dict, r: dict, api: dict[tuple, str]) -> dict:
    """The `confirmed` entry that keeps the relationship behind one of the API's fields, with both of the API's names."""
    here, there = o.get("sourceObject"), r.get("targetObject")
    sf, tf = list(r.get("sourceFields") or []), list(r.get("targetFields") or [])
    if r.get("cardinality") == "ManyToOne":
        src, scols, tgt, tcols = here, sf, there, tf
    else:                                                                 # the reverse side: the reference is on the other table
        src, scols, tgt, tcols = there, tf, here, sf
    entry = {"source": str(src).split(".")[-1], "source_cols": scols, "target": str(tgt).split(".")[-1], "target_cols": tcols}
    for key, shape in (("field_name", _shape(src, tgt, scols, tcols, "ManyToOne")), ("reverse_name", _shape(tgt, src, tcols, scols, "OneToMany"))):
        if api.get(shape):
            entry[key] = api[shape]
    return entry


def compare(plan: Plan, existing: dict, name: str, workspace_id: str, source_id: str, source_type: str,
            writable: bool = False, tables: list[str] | None = None, confirmed: list[dict] | None = None) -> dict:
    """existing: the API's graphql-definition.json. The plan is rendered the way create_backend would render it (with
    the API's field names kept, keep_api_names), and the two definitions are compared object by object."""
    plan, kept = keep_api_names(plan, existing, confirmed)
    api_names, plan_names = _names_by_shape(existing), {}
    wanted_env = definition(plan, name, workspace_id, source_id, source_type, writable=writable, tables=tables)
    wanted = decode(wanted_env)
    old, new = _objects(existing), _objects(wanted)
    plan_names = _names_by_shape(wanted)
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
        renamed = plan_names.get(_shape(o.get("sourceObject"), target, r.get("sourceFields"), r.get("targetFields"), r.get("cardinality")))
        if o.get("sourceObject") not in new:
            why = "its table is gone"
        elif target not in new:
            why = f"its target {target} is gone"
        elif not set(r.get("sourceFields") or []) <= set((new[o["sourceObject"]].get("fieldMappings") or {}).keys()):
            why = "a column it joins on is gone"
        elif renamed:
            why = (f"the plan names the same relationship {renamed!r} (a name given in `confirmed`, or the API's name would clash "
                   "with another field); pass the API's names in `confirmed` to keep the field an app queries today")
        else:
            why = ("the plan does not infer it today (it was given as `confirmed` when the API was built, or a key or rule "
                   "changed); pass it in `confirmed` to keep it")
        entry = {"table": o.get("sourceObject"), "field": r.get("field"), "target": target,
                 "columns": list(r.get("sourceFields") or []), "why": why}
        if renamed or why.startswith("the plan does not infer it today"):
            entry["confirmed"] = _keep_entry(o, r, api_names)
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
            "names_kept_from_api": kept,
            "keep_with_confirmed": keep_entries(unsupported)}


def keep_entries(unsupported: list[dict]) -> list[dict]:
    """The `confirmed` entries that keep these relationships, one per relationship (its two fields give the same one)."""
    out: list[dict] = []
    for e in (u["confirmed"] for u in unsupported if "confirmed" in u):
        if e not in out:
            out.append(e)
    return out


# ------------------------------------------------------------------ the plan as data, and what changed ------------

def plan_snapshot(plan, exclude: tuple[str, ...] = ()) -> dict:
    """The plan as plain data: columns and types, keys and rules, relationships and rules (sorted, so the same plan gives
    the same snapshot). The drift monitor keeps one per night; the review file keeps one per review."""
    skip = {e.lower() for e in exclude}
    tables = {}
    for t in sorted(plan.schema, key=lambda x: x.name.lower()):
        if t.name.lower() in skip:
            continue
        key, rule = plan.keys.get(t.name, ([], "K3"))
        tables[t.name] = {"columns": {c.name: (c.data_type or "").lower() for c in t.columns if c.name in t.column_names},
                          "key": list(key), "key_rule": rule if key else "K3"}
    rels = sorted(({"source": r.source, "columns": list(r.source_cols), "target": r.target, "target_columns": list(r.target_cols), "rule": r.rule}
                   for r in plan.relationships if r.source in tables and r.target in tables),
                  key=lambda r: (r["source"].lower(), r["columns"], r["target"].lower()))
    return {"version": 1, "schema": plan.schema.schema, "tables": tables, "relationships": rels}


def _snapshot_rel_key(r: dict) -> tuple:
    return (r["source"].lower(), tuple(c.lower() for c in r["columns"]), r["target"].lower(), tuple(c.lower() for c in r["target_columns"]))


def snapshot_diff(old: dict | None, new: dict) -> dict:
    """What changed from `old` to `new`; `first_run` when there is nothing to compare with."""
    out = {"first_run": old is None, "tables_added": [], "tables_removed": [], "columns_added": [], "columns_removed": [],
           "types_changed": [], "keys_changed": [], "relationships_added": [], "relationships_removed": []}
    if old is None:
        out["changed"] = False
        return out
    o, n = old.get("tables", {}), new.get("tables", {})
    olow, nlow = {k.lower(): k for k in o}, {k.lower(): k for k in n}
    out["tables_added"] = sorted(nlow[k] for k in set(nlow) - set(olow))
    out["tables_removed"] = sorted(olow[k] for k in set(olow) - set(nlow))
    for k in sorted(set(olow) & set(nlow)):
        ot, nt = o[olow[k]], n[nlow[k]]
        name = nlow[k]
        oc = {c.lower(): (c, ty) for c, ty in ot["columns"].items()}
        nc = {c.lower(): (c, ty) for c, ty in nt["columns"].items()}
        out["columns_added"] += [{"table": name, "column": nc[c][0], "type": nc[c][1]} for c in nc if c not in oc]
        out["columns_removed"] += [{"table": name, "column": oc[c][0], "type": oc[c][1]} for c in oc if c not in nc]
        out["types_changed"] += [{"table": name, "column": nc[c][0], "from": oc[c][1], "to": nc[c][1]}
                                 for c in nc if c in oc and oc[c][1] != nc[c][1]]
        if [x.lower() for x in ot["key"]] != [x.lower() for x in nt["key"]]:
            out["keys_changed"].append({"table": name, "from": ot["key"], "from_rule": ot["key_rule"], "to": nt["key"], "to_rule": nt["key_rule"]})
    orels = {_snapshot_rel_key(r): r for r in old.get("relationships", [])}
    nrels = {_snapshot_rel_key(r): r for r in new.get("relationships", [])}
    out["relationships_added"] = [nrels[k] for k in sorted(set(nrels) - set(orels))]
    out["relationships_removed"] = [orels[k] for k in sorted(set(orels) - set(nrels))]
    out["changed"] = any(out[k] for k in out if k not in ("first_run",))
    return out
