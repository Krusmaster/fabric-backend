"""SAP mirror metadata (round n129): keys and descriptions a mirrored SAP source declares, used before the SAP pack and
the name rules, and a drafted source-to-mirror check. Nothing here connects to anything: Krusgraph reads metadata it
is given and writes query text the customer runs with their own tools.

What the Microsoft Learn documentation says about mirroring SAP into Fabric
--------------------------------------------------------------------------
Read on 6 November 2026 from the public source of the Learn pages, github.com/MicrosoftDocs/fabric-docs at commit
951e7d305a3d5ef8409076c7c6a248fb834807f4, folder docs/mirroring (learn.microsoft.com itself could not be reached from
the session that wrote this; the pages are published from these files). Dates are each page's ms.date.

- "Mirroring SAP", learn.microsoft.com/fabric/mirroring/sap (sap.md, 02/26/2026): mirroring for SAP goes "via SAP
  Datasphere": a Datasphere replication flow "extracts data (initial snapshot and changed records) from your SAP source
  system and lands it in an Azure Data Lake Storage (ADLS) Gen2 container"; the mirroring engine "continuously merges
  the data with the mirrored database tables in OneLake". It creates "a mirrored database and a SQL analytics endpoint";
  the endpoint "provides a read-only analytical experience on top of the Delta tables created by the mirroring process".
  Sources: "SAP S/4HANA, SAP ECC, SAP BW/4HANA, SAP BW, and SAP Datasphere itself".
- "Tutorial: Configure Microsoft Fabric mirrored databases from SAP via SAP Datasphere" (sap-datasphere-tutorial.md,
  02/26/2026): target settings "Group Delta" None and "File Type" Parquet; load type "Initial and Delta" or "Initial
  Only"; a lakehouse shortcut to the container; the example source container is CDS_EXTRACTION (CDS views); after
  creation "you'll see the number of rows replicated and can view your data in the SQL analytics endpoint".
- "Limitations in Microsoft Fabric mirrored databases from SAP" (sap-limitations.md, 02/26/2026): the mirror
  "replicates all the data under the lakehouse shortcut path".
- "Monitor mirrored database replication" (monitor.md, 09/05/2025): "Rows replicated" is "The cumulative count of
  replicated rows, including all inserts, updates, and deletes applied to the target table" — not a table's row count,
  so the check below counts rows itself. "Fabric Mirroring Public REST API" (mirrored-database-rest-api.md,
  03/18/2026): getTablesMirroringStatus returns per table sourceSchemaName, sourceTableName, status and metrics
  processedBytes, processedRows, lastSyncDateTime; nothing about keys or descriptions.
- "Open mirroring landing zone requirements and formats" (open-mirroring-landing-zone-format.md, 09/09/2025), the
  route the SAP extraction tools in open-mirroring-partners-ecosystem.md use: "Every table folder must contain a
  `_metadata.json` file", which specifies "only the unique key columns as `keyColumns`" (the page also shows the
  spelling "KeyColumns"); "If `keyColumns` or `_metadata.json` isn't specified, then update/deletes aren't possible";
  "once added `keyColumns` can't be changed". The file lies in the mirrored database's landing zone in OneLake.

What the docs do not say (and Krusgraph does not assume): none of the three SAP pages says that table descriptions,
field descriptions, key columns or SAP technical names are carried into the mirrored tables, how SAP data types map to
the Delta tables, whether the replication flow adds columns of its own, or that the mirrored database's item definition
or an API returns keys or descriptions. The item definition page (learn.microsoft.com/rest/api/fabric/articles/
item-management/definitions/mirrored-database-definition) is not in that repository and was not read. So:

- keys: read from a table's `_metadata.json` `keyColumns` (documented for open mirroring), passed in by the caller;
- data types and column names: what the SQL analytics endpoint shows, read as for any other source (schema.py);
- descriptions: accepted when the caller passes them, labelled as such ("description_from"); no documented place in
  the Fabric SAP mirror provides them.

Tested on synthetic SAP-like tables only (tests/test_sap_mirror.py); not run against a mirrored SAP database.

    read(files, descriptions=None)     -> {table: {keys, key_from, description, description_from, columns}}
    plan(schema, metadata, ...)        -> (plan, match): the plan with rule "SAP mirror metadata" on mirror keys and on
                                          the links into them
    check_draft(schema, metadata, ...) -> per mirrored table: the queries to run on the SAP side and on the mirror, and
                                          how to compare them
    compare(check, sap, mirror)        -> the comparison of the numbers the customer brings back
"""
from __future__ import annotations

from . import sap_pack
from .sap_pack import CLIENT_COLUMNS, MIRROR_RULE, RULE

KEY_FROM = "_metadata.json keyColumns (open mirroring landing zone format)"
DESCRIPTION_FROM = "given with the metadata by the caller (the Fabric SAP mirroring pages document no place that carries descriptions)"
# a column to count by, so that a difference is found per year or organisation and not only in the total (first present wins)
GROUP_COLUMNS = ("GJAHR", "BUKRS", "VKORG", "EKORG", "WERKS", "KAPPL")


def read(files: dict[str, dict], descriptions: dict[str, dict] | None = None) -> dict[str, dict]:
    """Normalise mirror metadata. files: table -> the parsed `_metadata.json` of its landing-zone folder (`keyColumns` or
    `KeyColumns`; other properties are ignored). descriptions: table -> {"table": text, "columns": {column: text}}.
    A table can have either or both."""
    out: dict[str, dict] = {}
    for table, meta in (files or {}).items():
        if not isinstance(meta, dict):
            raise ValueError(f"{table}: _metadata.json must be a JSON object")
        keys = meta.get("keyColumns", meta.get("KeyColumns"))
        if keys is None:
            continue
        if not isinstance(keys, list) or not keys or not all(isinstance(c, str) and c for c in keys):
            raise ValueError(f"{table}: keyColumns must be a non-empty list of column names")
        out.setdefault(table, {})["keys"] = list(keys)
        out[table]["key_from"] = KEY_FROM
    for table, d in (descriptions or {}).items():
        e = out.setdefault(table, {})
        if d.get("table"):
            e["description"] = str(d["table"])
            e["description_from"] = DESCRIPTION_FROM
        if d.get("columns"):
            e["columns"] = {str(c): str(v) for c, v in d["columns"].items()}
    return out


def _entry(metadata: dict, table: str) -> dict | None:
    return sap_pack._mirror_entry(metadata, table, sap_pack.table_name(table))


def plan(schema, metadata: dict[str, dict], **kwargs):
    """infer.plan with the mirror's keys first: (plan, match). metadata is read()'s answer. A table whose metadata names
    key columns it has gets that key with rule MIRROR_RULE, over the SAP pack and the name rules (K2-K5); the pack's
    relationships into it are applied only where they join on that key, and then carry MIRROR_RULE, others RULE.
    Keys the caller passes (keys=) still win, as everywhere. Without SAP tables the mirror keys still apply."""
    from .infer import plan as _plan
    m = sap_pack.match(schema, "sap", mirror=metadata)
    given = {k.lower() for k in (kwargs.get("keys") or {})}
    mine: dict[str, tuple[list[str], str]] = {}
    if m is not None:
        mine = {t: (cols, m.key_rules.get(t, RULE)) for t, cols in m.keys.items()}
    for t in schema:                                       # mirror keys of tables the pack does not know
        e = _entry(metadata, t.name)
        if t.name not in mine and e and e.get("keys") and all(t.has(c) for c in e["keys"]):
            mine[t.name] = ([t.col(c) for c in e["keys"]], MIRROR_RULE)
    mine = {t: v for t, v in mine.items() if t.lower() not in given}
    links = [] if m is None else [r for r in m.relationships if r.get("kind", "key") == "key" and not r.get("where")]
    confirmed = [{"source": r["source"], "source_cols": r["source_cols"], "target": r["target"], "target_cols": r["target_cols"]}
                 for r in links]
    p = _plan(schema, keys={**{t: cols for t, (cols, _) in mine.items()}, **kwargs.pop("keys", {})},
              confirmed=confirmed + list(kwargs.pop("confirmed", [])), **kwargs)
    for t, (cols, rule) in mine.items():                   # K1 -> the rule that gave the key
        if t in p.keys and p.keys[t][1] == "K1" and [c.lower() for c in p.keys[t][0]] == [c.lower() for c in cols]:
            p.keys[t] = (p.keys[t][0], rule)
    ours = {(r["source"], tuple(c.lower() for c in r["source_cols"]), r["target"]): r for r in links}
    for rel in p.relationships:
        r = ours.get(rel.key)
        if r is None or rel.rule != "confirmed":
            continue
        rel.rule = MIRROR_RULE if mine.get(rel.target, ([], ""))[1] == MIRROR_RULE else RULE
        why = f"target key from the mirror's {KEY_FROM}" if rel.rule == MIRROR_RULE else "target key from the pack"
        rel.note = f"sap pack ({r.get('module', '')}): {why}; source: " + "; ".join(
            sap_pack.load()["sources"][i]["title"].split(":")[0] for i in r.get("sources", []))
    return p, m


def _q(name: str, style: str) -> str:
    return f'"{name}"' if style == "sap" else f"[{name}]"


def _queries(table: str, key: list[str], client: str | None, group: str | None, style: str, schema: str | None) -> dict:
    """COUNT and key queries for one table in one dialect: sap (double quotes, for the customer's SQL console on the SAP
    database) or mirror (T-SQL brackets, for the SQL analytics endpoint)."""
    q = lambda n: _q(n, style)
    name = (f"{q(schema)}." if schema else "") + q(table)
    cl = next((c for c in key if c.upper() in CLIENT_COLUMNS), None)
    where = f" WHERE {q(cl)} = '{client}'" if cl and client else (f" WHERE {q(cl)} = '<client>'" if cl else "")
    k = ", ".join(q(c) for c in key)
    nulls = " OR ".join(f"{q(c)} IS NULL" for c in key)
    out = {
        "row_count": f"SELECT COUNT(*) AS row_count FROM {name}{where}",
        "distinct_keys": f"SELECT COUNT(*) AS distinct_keys FROM (SELECT DISTINCT {k} FROM {name}{where}) AS d",
        "null_keys": f"SELECT COUNT(*) AS null_keys FROM {name}" + (f"{where} AND ({nulls})" if where else f" WHERE {nulls}"),
        "duplicate_keys": f"SELECT COUNT(*) AS duplicate_keys FROM (SELECT {k} FROM {name}{where} GROUP BY {k} HAVING COUNT(*) > 1) AS d",
    }
    if group:
        out["rows_by_group"] = f"SELECT {q(group)} AS grp, COUNT(*) AS row_count FROM {name}{where} GROUP BY {q(group)} ORDER BY {q(group)}"
    return out


def check_draft(schema, metadata: dict[str, dict] | None = None, client: str | None = None, mirror_schema: str | None = None,
                tables: list[str] | None = None) -> dict:
    """A source-to-mirror check, drafted: per mirrored table (of `schema`, as the SQL analytics endpoint shows it), the
    key it is checked on (mirror metadata first, then the SAP pack), the same queries for the SAP side and for the
    mirror, and how to compare them. The customer runs the SAP queries with their own tools; Krusgraph runs nothing.
    client: the SAP client to count (a placeholder '<client>' otherwise). mirror_schema: the schema of the mirrored
    tables in the SQL analytics endpoint (the schema's own name otherwise)."""
    metadata = metadata or {}
    m = sap_pack.match(schema, "sap", mirror=metadata)
    mirror_schema = mirror_schema if mirror_schema is not None else getattr(schema, "schema", None)
    want = {t.lower() for t in tables} if tables else None
    out, skipped = [], []
    for t in schema:
        if want is not None and t.name.lower() not in want:
            continue
        e = _entry(metadata, t.name) or {}
        pack_name = sap_pack.table_name(t.name)
        if m is not None and t.name in m.keys:
            key, rule = m.keys[t.name], m.key_rules.get(t.name, RULE)
            sap_table = m.tables[t.name]
        elif e.get("keys") and all(t.has(c) for c in e["keys"]):
            key, rule, sap_table = [t.col(c) for c in e["keys"]], MIRROR_RULE, pack_name
        else:
            skipped.append({"table": t.name, "why": "no key from the mirror metadata or the SAP pack; counts alone would not "
                                                    "find a row that is missing on one side and doubled on the other"})
            continue
        group = next((c for c in GROUP_COLUMNS if t.has(c) and c not in [x.upper() for x in key[:1]]), None)
        sap_key = [c.upper() for c in key]                   # SAP's own names are upper case
        out.append({
            "table": t.name, "sap_table": sap_table, "key": key, "key_rule": rule,
            **({"key_from": e.get("key_from", KEY_FROM)} if rule == MIRROR_RULE else {}),
            "group_by": t.col(group) if group else None,
            "sap": _queries(sap_table, sap_key, client, group, "sap", None),
            "mirror": _queries(t.name, key, client, t.col(group) if group else None, "mirror", mirror_schema),
            "compare": {
                "row_count": "equal",
                "distinct_keys": "equal, and equal to row_count on each side (one row per key)",
                "null_keys": "0 on both sides",
                "duplicate_keys": "0 on the mirror (the SAP table's key is unique there by definition; a duplicate on the mirror "
                                  "means a change was applied twice or the key is not the key)",
                **({"rows_by_group": "equal per group; a group present on one side only is a difference"} if group else {}),
            },
        })
    return {
        "tables": out, "skipped": skipped,
        "how": ("Run each table's 'sap' queries on the SAP side with your own tools (an SQL console on the SAP database, "
                "or the equivalent your team uses) and its 'mirror' queries on the mirrored database's SQL analytics "
                "endpoint, at a point when no changes are in flight on that table, then pass both sets of numbers to "
                "sap_mirror.compare. Krusgraph connects to neither side."),
        "caveats": [
            "Count only what the replication flow replicates: with load type Initial Only the mirror stops at the initial "
            "load, so later changes on the SAP side are expected differences (sap-datasphere-tutorial, 02/26/2026).",
            "If the replication flow reads a CDS view (the tutorial's example container is CDS_EXTRACTION), run the SAP "
            "queries on that view, not on the table: the drafted SAP table name is the pack's, and Krusgraph does not "
            "know which object the flow reads.",
            "The mirror's 'Rows replicated' and the API's processedRows count inserts, updates and deletes applied "
            "(monitor.md, 09/05/2025); they are not row counts and are not compared here.",
            "Whether the mirrored tables carry columns the replication adds is not documented on the Fabric SAP pages; "
            "the queries use only the key and the group column.",
        ],
        **({"mirror_problems": m.mirror_problems} if m is not None and m.mirror_problems else {}),
        "status": "a draft: generated and tested on synthetic SAP-like tables only, never run against an SAP system or a mirror",
    }


def compare(check: dict, sap: dict[str, dict], mirror: dict[str, dict]) -> dict:
    """Compare the numbers brought back: sap and mirror map table -> {row_count, distinct_keys, null_keys,
    duplicate_keys, rows_by_group: {group: count}} (any subset). Per table: equal, different (with what), or incomplete."""
    rows = []
    for t in check["tables"]:
        name = t["table"]
        a, b = sap.get(name) or sap.get(t["sap_table"]) or {}, mirror.get(name) or {}
        diffs, missing = [], []
        for k in ("row_count", "distinct_keys"):
            if k not in a or k not in b:
                missing.append(k)
            elif int(a[k]) != int(b[k]):
                diffs.append(f"{k}: SAP {a[k]}, mirror {b[k]}")
        for side, v in (("SAP", a), ("mirror", b)):
            if v.get("null_keys") not in (None, 0, "0"):
                diffs.append(f"null_keys on {side}: {v['null_keys']}")
            if "row_count" in v and "distinct_keys" in v and int(v["row_count"]) != int(v["distinct_keys"]):
                diffs.append(f"{side}: {v['row_count']} rows for {v['distinct_keys']} keys")
        if b.get("duplicate_keys") not in (None, 0, "0"):
            diffs.append(f"duplicate_keys on mirror: {b['duplicate_keys']}")
        ga, gb = a.get("rows_by_group"), b.get("rows_by_group")
        if ga is not None and gb is not None:
            ga, gb = {str(k): int(v) for k, v in ga.items()}, {str(k): int(v) for k, v in gb.items()}
            for g in sorted(set(ga) | set(gb)):
                if ga.get(g) != gb.get(g):
                    diffs.append(f"group {g}: SAP {ga.get(g, 'none')}, mirror {gb.get(g, 'none')}")
        verdict = "different" if diffs else ("incomplete" if missing else "equal")
        rows.append({"table": name, "verdict": verdict, "differences": diffs, **({"missing": missing} if missing else {})})
    counts = {v: sum(1 for r in rows if r["verdict"] == v) for v in ("equal", "different", "incomplete")}
    return {"tables": rows, "counts": counts,
            "note": "Equal counts and keys on both sides at one moment; not a comparison of the values in the rows."}
