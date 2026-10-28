"""One plan, several integration tools: text and files only, nothing is connected or created.

- `krusgraph_plan(plan)`: the plan as the `keys` and `confirmed` arguments every Krusgraph tool takes, so a reviewed
  plan (or a pack's) can be passed back unchanged.
- dbt sources with tests: `dbt.schema_yml` (dbt.py; its sources are cited there).
- `dab_config(plan, ...)`: a Data API builder configuration with one entity per table and its relationships.
- `extraction_list(plan, match)`: the tables to extract, each with its key and the columns a delta load can watch,
  in a neutral JSON a pipeline or a mirroring tool can read; plus, per table, the `_metadata.json` that Fabric open
  mirroring's landing zone expects (`keyColumns`).

Formats followed (read 28 October 2026 from the documentation's own repositories, as learn.microsoft.com could not be
reached from the session):
- Data API builder: MicrosoftDocs/data-api-builder-docs, data-api-builder/configuration/entities.md (entity `source`
  with `object`, `type`, `key-fields` — deprecated in DAB 2.0 in favour of `fields[].primary-key`, and the two cannot
  coexist; `relationships.<name>` with `cardinality` "one"/"many", `target.entity`, `source.fields`, `target.fields`;
  `permissions` with `role` and `actions`) and configuration/data-source.md (`database-type` `dwsql` for a Fabric
  Warehouse or SQL analytics endpoint, `connection-string` as `@env('...')`); checked in the tests against
  Azure/data-api-builder schemas/dab.draft.schema.json.
- Fabric open mirroring: MicrosoftDocs/fabric-docs, docs/mirroring/open-mirroring-landing-zone-format.md ("Every
  table folder must contain a `_metadata.json` file", `{"keyColumns": ["C1", "C2"]}`, and `keyColumns` cannot be
  changed once added).
Not built, because no public specification of the file could be verified: an SAP Datasphere replication flow
definition, and the configuration files of third-party SAP extractors. The neutral extraction list is meant to be
translated into those by hand or by their own tooling.
"""
from __future__ import annotations

import re

from .infer import Plan

DAB_SCHEMA = "https://github.com/Azure/data-api-builder/releases/latest/download/dab.draft.schema.json"
EXTRACTION_FORMAT = "krusgraph.extraction/1"


def krusgraph_plan(plan: Plan) -> dict:
    """`keys` for every table with a key, `confirmed` for every relationship: plan_backend(keys=..., confirmed=...)
    reproduces the plan without re-inferring it."""
    return {"keys": {t: list(cols) for t, (cols, _) in plan.keys.items()},
            "confirmed": [{"source": r.source, "source_cols": list(r.source_cols), "target": r.target,
                           "target_cols": list(r.target_cols), "rule": r.rule} for r in plan.relationships],
            # joins that are not key joins (a knowledge pack's): for the reader; confirmed= takes key joins only
            **({"extended": [{"source": r.source, "source_cols": list(r.source_cols), "target": r.target, "target_cols": list(r.target_cols),
                              "kind": r.kind, "join": r.join_sql(), **({"valid_on": r.valid_on} if r.valid_on else {})}
                             for r in plan.extended]} if plan.extended else {})}


def _entity(name: str) -> str:
    words = [w for w in re.split(r"[^A-Za-z0-9]+", name) if w]
    s = "".join(w[:1].upper() + w[1:] for w in words) or "Entity"
    return s if not s[0].isdigit() else "T" + s


def dab_config(plan: Plan, schema: str | None = None, database_type: str = "dwsql", dab2: bool = False,
               env_var: str = "SQL_CONNECTION_STRING", role: str = "authenticated") -> dict:
    """A read-only Data API builder configuration: an entity per table that has a key (DAB needs one), each
    many-to-one relationship in both directions ("one" on the line, "many" on the header). dab2=True writes the key
    as `fields[].primary-key` (DAB 2.0) instead of `source.key-fields`."""
    schema = schema if schema is not None else plan.schema.schema
    names: dict[str, str] = {}
    for t in plan.schema:
        if t.name in plan.keys:
            n, i = _entity(t.name), 2
            while n in names.values():
                n, i = f"{_entity(t.name)}{i}", i + 1
            names[t.name] = n
    entities: dict[str, dict] = {}
    for t in plan.schema:
        if t.name not in names:
            continue
        key = plan.keys[t.name][0]
        src = {"object": f"{schema}.{t.name}" if schema else t.name, "type": "table"}
        e: dict = {"source": src}
        if dab2:
            e["fields"] = [{"name": c, "primary-key": True} for c in key]
        else:
            src["key-fields"] = list(key)
        e["graphql"] = {"enabled": True}
        e["rest"] = {"enabled": True}
        e["permissions"] = [{"role": role, "actions": ["read"]}]
        entities[names[t.name]] = e
    used: dict[str, set[str]] = {n: set() for n in entities}

    def rel_name(entity: str, want: str) -> str:
        n, i = want, 2
        while n in used[entity]:
            n, i = f"{want}_{i}", i + 1
        used[entity].add(n)
        return n

    # a join on a unique column that is not the target's key (kind "unique") is written like any other: the format takes
    # any source.fields/target.fields. A join valid on a date has no form in Data API builder and is left out.
    for r in list(plan.relationships) + [r for r in plan.extended if r.kind == "unique"]:
        if r.source not in names or r.target not in names:
            continue
        s, g = names[r.source], names[r.target]
        one_to_one = sorted(c.lower() for c in plan.keys[r.source][0]) == sorted(c.lower() for c in r.source_cols)
        entities[s].setdefault("relationships", {})[rel_name(s, r.field_name or _entity(r.target).lower())] = {
            "cardinality": "one", "target.entity": g, "source.fields": list(r.source_cols), "target.fields": list(r.target_cols)}
        entities[g].setdefault("relationships", {})[rel_name(g, r.reverse_name or _entity(r.source).lower() + "s")] = {
            "cardinality": "one" if one_to_one else "many", "target.entity": s,
            "source.fields": list(r.target_cols), "target.fields": list(r.source_cols)}
    return {"$schema": DAB_SCHEMA,
            "data-source": {"database-type": database_type, "connection-string": f"@env('{env_var}')"},
            "runtime": {"rest": {"enabled": True}, "graphql": {"enabled": True}},
            "entities": entities}


def extraction_list(plan: Plan, match=None) -> dict:
    """Per table: key, the columns a delta load can watch (from the pack when it knows the table, else date-like
    names), and the open-mirroring `_metadata.json`. A table without a key is listed with `full_load_only`."""
    from . import sap_pack
    tables = []
    for t in plan.schema:
        key, rule = plan.keys.get(t.name, ([], "K3"))
        have = {c.upper(): c for c in t.column_names}
        delta, origin = [], ""
        if match is not None and t.name in match.tables:
            info = sap_pack.table_info(match.tables[t.name], match.pack)
            delta = [have[c] for c in info.get("delta", []) if c in have]
            origin = f"{match.pack} pack ({info['module']})"
        if not delta:
            delta = [c for c in t.column_names if re.search(r"(^|_)(modified|updated|changed|aedat|laeda)|(_at|_on|date|time)$", c, re.I)
                     and re.search(r"modif|updat|chang|aedat|laeda|creat|erdat", c, re.I)]
            origin = origin or ("column names" if delta else "")
        entry = {"table": t.name, "key": list(key), "key_rule": rule, "delta_columns": delta}
        if origin:
            entry["delta_from"] = origin
        if match is not None and t.name in match.tables:
            entry["pack_table"] = match.tables[t.name]
        if key:
            entry["open_mirroring_metadata"] = {"keyColumns": list(key)}
        else:
            entry["full_load_only"] = "no key: updates and deletes cannot be applied by key, so load the table in full"
        tables.append(entry)
    return {"format": EXTRACTION_FORMAT, "schema": plan.schema.schema, "tables": tables,
            "note": "Delta columns are change dates where the source has them; a date column alone misses deletions, "
                    "so a log-based or CDC extractor is the safer delta where available. keyColumns cannot be changed "
                    "once an open-mirroring table has them."}
