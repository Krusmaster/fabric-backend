"""A data contract beside the data product, from the counted checks (round BL38, 23 November 2026; backlog P-29).

`draft(plan, validation, counted_on=...)` writes an Open Data Contract Standard (ODCS) v3.1.0 contract
(https://github.com/bitol-io/open-data-contract-standard, schema/odcs-json-schema-v3.1.0-20251208.json, Apache 2.0, read
23 November 2026) for the tables of a plan: per table its columns with their types and the primary key, the
relationships as foreign keys, and a quality rule per key and link that validate_plan counted, with the count and the
date it was counted. A rule says what must hold (`mustBe: 0`) and the contract records what was counted, so a planted or
real fault shows as a failing rule with its number; it is never smoothed into a passing one.

A key or link that was not counted (validate did not reach it, it errored, or it is a conditional link) is written as a
`text` rule "declared, not counted", never as SQL with a passing value. A header amount that a join would repeat is a
`text` rule with the counted explanation. No row value is written: names, types, counts, SQL and dates only.

Deterministic: the same plan and validation give the same YAML, byte for byte (`to_yaml`); no clock is read, the caller
passes `counted_on`. No dependency: the YAML is written here (double-quoted scalars, which every YAML 1.2 reader
reads as the JSON strings they are)."""
from __future__ import annotations

import json
import re

API_VERSION = "v3.1.0"
SPEC = "https://github.com/bitol-io/open-data-contract-standard (schema/odcs-json-schema-v3.1.0-20251208.json)"
NOT_COUNTED = "declared, not counted"
_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _logical(data_type: str) -> str:
    t = (data_type or "").lower()
    if any(w in t for w in ("int", "long", "short")):
        return "integer"
    if any(w in t for w in ("decimal", "numeric", "double", "float", "real", "money")):
        return "number"
    if "bool" in t or t == "bit":
        return "boolean"
    if "date" in t or "time" in t:
        return "date"
    return "string"


def _sid(*parts: str) -> str:
    """A StableId (letters, digits, '-' and '_')."""
    return re.sub(r"[^A-Za-z0-9_-]+", "_", "_".join(parts)).strip("_")


def _custom(**kv) -> list[dict]:
    return [{"property": k, "value": v} for k, v in kv.items() if v is not None]


def draft(plan, validation: dict | None, *, counted_on: str, product: dict | None = None, schemas_enabled: bool = True) -> dict:
    """The contract as a dict (see the module text). `product`: optional {"name", "version", "owner"}."""
    from . import evidence
    from .dialects import DATABRICKS
    from .health import _spark_sql
    if not _ISO.match(counted_on or ""):
        raise ValueError("counted_on must be an ISO date (YYYY-MM-DD)")
    validation = validation or {}
    product = product or {}
    schema = plan.schema.schema
    spark = lambda sql: _spark_sql(sql, schema, schemas_enabled)          # noqa: E731
    vkeys = {k["table"]: k for k in validation.get("keys", [])}
    vrels = {(r["source"], tuple(r.get("columns", [])), r["target"]): r for r in validation.get("relationships", [])}
    keys = {t: list(cols) for t, (cols, _rule) in (plan.keys or {}).items()}
    objects = []
    for tname, table in plan.schema.tables.items():
        pk = keys.get(tname, [])
        props = []
        for c in table.columns:
            p = {"name": c.name, "logicalType": _logical(c.data_type), "physicalType": c.data_type or "string"}
            if c.name in pk:
                p.update(primaryKey=True, primaryKeyPosition=pk.index(c.name) + 1, required=True)
            props.append(p)
        obj = {"name": tname, "physicalName": f"{schema}.{tname}", "physicalType": "table", "logicalType": "object",
               "properties": props}
        rels, quality = [], []
        if pk:
            k = vkeys.get(tname)
            rid = _sid("key", tname)
            if k and "distinct" in k and "rows" in k:
                bad = int(k["rows"]) - int(k["distinct"])        # rows with an empty key or a repeated one (distinct leaves NULL out)
                cols = list(k.get("columns") or pk)
                quality.append({
                    "id": rid, "name": f"{tname} key {'+'.join(cols)} is unique and not empty", "type": "sql",
                    "dimension": "uniqueness", "unit": "rows",
                    "description": f"Rows with an empty or repeated {'+'.join(cols)}. Counted {bad} on {counted_on}: {k.get('verdict', '')}.",
                    "query": spark(f"SELECT n - distinct_keys AS n FROM ({evidence.key_sql(schema, tname, cols, DATABRICKS)}) AS k"),
                    "mustBe": 0,
                    "customProperties": _custom(countedValue=bad, countedOn=counted_on, status="passed" if bad == 0 else "failed",
                                                rule=k.get("rule")),
                })
            else:
                why = (k or {}).get("error") or (k or {}).get("verdict") or "not counted"
                quality.append({"id": rid, "name": f"{tname} key {'+'.join(pk)}", "type": "text",
                                "description": f"{NOT_COUNTED}: the key {'+'.join(pk)} of {tname} ({why})."})
        for r in plan.relationships:
            if r.source != tname:
                continue
            frm = [f"{r.source}.{c}" for c in r.source_cols]
            to = [f"{r.target}.{c}" for c in r.target_cols]
            rels.append({"type": "foreignKey", "from": frm[0] if len(frm) == 1 else frm, "to": to[0] if len(to) == 1 else to})
            v = vrels.get((r.source, tuple(r.source_cols), r.target))
            rid = _sid("link", r.source, *r.source_cols, r.target)
            label = f"{r.source}.{'+'.join(r.source_cols)} -> {r.target}"
            if v and "orphans" in v and "kind" not in v:
                orphans = int(v["orphans"])
                target_unique = evidence.target_key_unique(validation.get("keys", []), r.target, list(r.target_cols))
                rel_sql = evidence.relationship_sql(schema, r.source, list(r.source_cols), r.target, list(r.target_cols),
                                                    DATABRICKS, target_unique=target_unique)
                quality.append({
                    "id": rid, "name": f"every {label} row finds its {r.target} row", "type": "sql",
                    "dimension": "consistency", "unit": "rows",
                    "description": f"{r.source} rows with a value in {'+'.join(r.source_cols)} and no {r.target} row. "
                                   f"Counted {orphans} on {counted_on}: {v.get('verdict', '')}.",
                    "query": spark(f"SELECT COALESCE(orphans, 0) AS n FROM ({rel_sql}) AS r"),
                    "mustBe": 0,
                    "customProperties": _custom(countedValue=orphans, countedOn=counted_on,
                                                status="passed" if orphans == 0 else "failed", rule=v.get("rule") or r.rule),
                })
            else:
                why = "a conditional link, not a key join" if v and "kind" in v else ((v or {}).get("error") or "not counted")
                quality.append({"id": rid, "name": label, "type": "text", "description": f"{NOT_COUNTED}: {label} ({why})."})
        if rels:
            obj["relationships"] = rels
        if quality:
            obj["quality"] = quality
        objects.append(obj)
    by_name = {o["name"]: o for o in objects}
    for f in (validation.get("amount_levels") or {}).get("findings", []):
        o = by_name.get(f["header"])
        if not o:
            continue
        for col in f["amount_columns"]:
            o.setdefault("quality", []).append({
                "id": _sid("amount", f["header"], col, f["line"]), "name": f"{f['header']}.{col} is summed per {f['header']} row",
                "type": "text",
                "description": (f"{f['header']}.{col} is an amount on {f['header']}; a join with {f['line']} repeats it on every "
                                f"line, so sum it per {f['header']} row, not over {f['line']} rows. Counted on {counted_on}: "
                                f"{f.get('explanation', '')}")})
    name = product.get("name") or f"{schema} data product"
    contract = {
        "apiVersion": API_VERSION, "kind": "DataContract",
        "id": _sid("krusgraph", schema, product.get("name") or ""),
        "name": name, "version": product.get("version") or "0.1.0", "status": "draft",
        "description": {
            "purpose": f"The tables of {schema} as Krusgraph planned and checked them: keys, links and the rules counted on the rows.",
            "limitations": (f"Every rule's counted value is from {counted_on}. A key or link marked '{NOT_COUNTED}' was proposed "
                            "but not counted and is not a rule. No row values are in this contract."),
            "usage": "Review with the data product's owner; the SQL rules run on the lakehouse's Spark SQL as written.",
        },
        "schema": objects,
        "customProperties": _custom(generatedBy="Krusgraph (fabric_backend.data_contract)", countedOn=counted_on,
                                    specification=SPEC, owner=product.get("owner")),
    }
    return contract


def _scalar(v) -> str:
    if v is True:
        return "true"
    if v is False:
        return "false"
    if v is None:
        return "null"
    if isinstance(v, (int, float)):
        return json.dumps(v)
    return json.dumps(str(v), ensure_ascii=False)


def _emit(v, indent: int, out: list[str]) -> None:
    pad = " " * indent
    if isinstance(v, dict):
        for k, x in v.items():
            if isinstance(x, (dict, list)) and x:
                out.append(f"{pad}{k}:")
                _emit(x, indent + 2, out)
            else:
                out.append(f"{pad}{k}: {_scalar(x) if not isinstance(x, (dict, list)) else ('{}' if isinstance(x, dict) else '[]')}")
    elif isinstance(v, list):
        for x in v:
            if isinstance(x, dict) and x:
                inner: list[str] = []
                _emit(x, indent + 2, inner)
                out.append(f"{pad}- {inner[0].lstrip()}")
                out.extend(inner[1:])
            elif isinstance(x, list) and x:
                out.append(f"{pad}-")
                _emit(x, indent + 2, out)
            else:
                out.append(f"{pad}- {_scalar(x)}")


def to_yaml(contract: dict) -> str:
    out: list[str] = []
    _emit(contract, 0, out)
    return "\n".join(out) + "\n"
