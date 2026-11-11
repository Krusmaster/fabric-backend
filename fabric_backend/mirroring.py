"""Round n201: the Krusgraph Model reads mirrored databases (SAP mirrored through SAP Datasphere among them), warehouses and
SQL databases, and writes what it builds with Spark to a lakehouse the person picks.

What Microsoft Learn says, read on 11 November 2026 from learn.microsoft.com (each page's ms.date):

- "Microsoft Fabric Mirrored Databases From SAP" (learn.microsoft.com/fabric/mirroring/sap, 26 February 2026): "Mirroring
  creates a mirrored database and a SQL analytics endpoint in your Fabric workspace. The mirrored database manages
  replication of data into OneLake and conversion to Parquet"; the endpoint "provides a read-only analytical experience on
  top of the Delta tables created by the mirroring process". Via SAP Datasphere, a replication flow "extracts data (initial
  snapshot and changed records) from your SAP source system and lands it in an Azure Data Lake Storage (ADLS) Gen2
  container"; the mirroring engine "continuously merges the data with the mirrored database tables in OneLake". "SAP
  Datasphere Premium Outbound Integration pricing applies when mirroring SAP data via SAP Datasphere."
- "Limitations in Microsoft Fabric mirrored databases from SAP" (.../sap-limitations, 26 February 2026): target settings
  "Group Delta" None and "File Type" Parquet; "SAP mirroring supports replication flow load type as Initial and Delta or
  Initial Only".
- "Tutorial: Configure Microsoft Fabric mirrored databases to mirror SAP via SAP Datasphere" (.../sap-datasphere-tutorial,
  26 February 2026): prerequisite "An SAP Datasphere environment with Premium Outbound Integration"; the mirrored database
  "creates a read-only, continuously replicated copy of your SAP data in OneLake".
- "Items - Get Mirrored Database" (learn.microsoft.com/rest/api/fabric/mirroreddatabase/items/get-mirrored-database, page
  updated 6 November 2026): properties.oneLakeTablesPath, "OneLake path to the mirrored database tables directory", e.g.
  https://onelake.dfs.fabric.microsoft.com/<workspace id>/<item id>/Tables; sqlEndpointProperties {connectionString, id,
  provisioningStatus}; defaultSchema. Scopes MirroredDatabase.Read.All, MirroredDatabase.ReadWrite.All, Item.Read.All or
  Item.ReadWrite.All.
- "How do I connect to OneLake?" (learn.microsoft.com/fabric/onelake/onelake-access-api, 18 May 2026): workspaces and
  items may be named by GUIDs, https://onelake.dfs.fabric.microsoft.com/<workspaceGUID>/<itemGUID>/<path>, and the ABFS form
  is abfss://<workspace>@onelake.dfs.fabric.microsoft.com/<item>/<path>.
- "Explore data in your mirrored database with notebooks" (learn.microsoft.com/fabric/mirroring/explore-onelake-shortcut,
  19 November 2024): the other documented route, a OneLake shortcut in a lakehouse to the mirrored tables.

So the silver notebook reads the mirrored tables at the documented path, oneLakeTablesPath in its abfss form, with Spark in
Fabric: nothing is copied outside Fabric and no shortcut is created (nothing to consent to). Not documented, so not
assumed: how the folders under Tables are laid out per schema. The notebook reads Tables/<schema>/<table> when that folder
holds a Delta log and Tables/<table> otherwise (silver.MIRROR_SOURCE). Tested on a fake endpoint and on generated notebook
text only (tests/test_n201_mirrored.py); not run against a mirrored database in Fabric.

    SOURCE_TYPES                  the item types the editor's source picker offers
    WRITES_WITH_SPARK             the outputs that need a lakehouse to write to
    abfss(tables_path, ws, item)  oneLakeTablesPath (or the GUID form) -> abfss://<ws>@onelake.dfs.fabric.microsoft.com/<item>/Tables
    choose_target(items, chosen)  the lakehouse to write to: the person's, else the first of the workspace by name
    sap_offer(plan)               the SAP pack's keys and links in this plan, each "from the SAP pack" with its public source
    MIRRORING_NOTE, SAP_NOTE      what mirroring delivers and whose licence matter SAP Datasphere is, per Learn
"""
from __future__ import annotations

import re

# The editor's source picker (Fabric's OneLake catalog dialog takes these item type names); the same types list_sources
# lists (deploy.SOURCE_ITEM_TYPES), minus the catalogs the workload has not been tried on.
SOURCE_TYPES = ("Lakehouse", "Warehouse", "SQLDatabase", "MirroredDatabase")
READ_ONLY = {"MirroredDatabase": "mirrored database", "Warehouse": "warehouse", "SQLDatabase": "SQL database"}
WRITES_WITH_SPARK = ("silver_notebook", "gold_views", "pipeline")
ONELAKE_HOST = "onelake.dfs.fabric.microsoft.com"

LEARN = {
    "sap": "https://learn.microsoft.com/fabric/mirroring/sap",
    "sap_limitations": "https://learn.microsoft.com/fabric/mirroring/sap-limitations",
    "sap_tutorial": "https://learn.microsoft.com/fabric/mirroring/sap-datasphere-tutorial",
    "get_mirrored_database": "https://learn.microsoft.com/rest/api/fabric/mirroreddatabase/items/get-mirrored-database",
    "onelake_uri": "https://learn.microsoft.com/fabric/onelake/onelake-access-api",
    "explore_shortcut": "https://learn.microsoft.com/fabric/mirroring/explore-onelake-shortcut",
    "overview": "https://learn.microsoft.com/fabric/mirroring/overview",
}
READ_PATH_WORDS = ("read where mirroring keeps them in OneLake (oneLakeTablesPath, Get Mirrored Database on Microsoft Learn), "
                   "with Spark in Fabric; nothing is copied outside Fabric and no shortcut is created")
MIRRORING_NOTE = ("What mirroring delivers, per Microsoft Learn: the mirrored database replicates the data into OneLake as "
                  "Delta tables (converted to Parquet) with a read-only SQL analytics endpoint; for SAP via SAP Datasphere the "
                  "replication flow writes Parquet files with load type Initial and Delta, or Initial Only. Krusgraph reads "
                  "what has arrived; it does not start or watch the replication.")
SAP_NOTE = ("Mirroring SAP via SAP Datasphere needs SAP Datasphere with Premium Outbound Integration (Microsoft Learn's "
            "tutorial prerequisite; its pricing applies). That licence is between the customer and SAP; Krusgraph needs "
            "none and does not check it.")
SAP_FROM = "from the SAP pack"
_GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def is_read_only(item_type: str | None) -> bool:
    """A source Spark cannot write into: everything but a lakehouse."""
    return (item_type or "Lakehouse") != "Lakehouse"


def kind_words(item_type: str | None) -> str:
    return READ_ONLY.get(item_type or "", (item_type or "lakehouse").lower())


def abfss(tables_path: str | None, workspace_id: str = "", item_id: str = "") -> str | None:
    """The tables folder of an item in the ABFS form Spark reads. From oneLakeTablesPath when Fabric gives it
    (https://onelake.dfs.fabric.microsoft.com/<ws>/<item>/Tables), else from the two GUIDs (the OneLake URI page)."""
    m = re.fullmatch(r"https://([a-z0-9-]*onelake\.dfs\.fabric\.microsoft\.com)/([^/]+)/(.+?)/?", (tables_path or "").strip())
    if m:
        return f"abfss://{m.group(2)}@{m.group(1)}/{m.group(3)}"
    if _GUID.match(workspace_id or "") and _GUID.match(item_id or ""):
        return f"abfss://{workspace_id}@{ONELAKE_HOST}/{item_id}/Tables"
    return None


def choose_target(lakehouses: list[dict], chosen: str | None = None) -> tuple[dict | None, str]:
    """(the lakehouse to write to, how it was chosen). `lakehouses`: the workspace's Lakehouse items ({id, displayName}).
    The person's choice by id or name wins; else the first by name, said as the default; None when there is none."""
    if chosen:
        for it in lakehouses:
            if chosen in (it.get("id"), it.get("displayName")):
                return it, "chosen"
        return None, "not_found"
    ordered = sorted(lakehouses, key=lambda it: (str(it.get("displayName") or "").lower(), str(it.get("id"))))
    return (ordered[0], "default") if ordered else (None, "none")


def target_words(target: dict, how: str, source_name: str, source_type: str) -> str:
    what = kind_words(source_type)
    head = (f"The {what} {source_name} is read-only, so the silver tables, the gold views and the pipeline's check are "
            f"written to the lakehouse {target.get('displayName')}")
    tail = (" (your choice)." if how == "chosen" else
            ", the first lakehouse of this workspace by name: the default. Choose another under Target lakehouse.")
    read = (f" The silver notebook reads the mirrored tables {READ_PATH_WORDS}." if source_type == "MirroredDatabase" else
            f" The silver notebook reads the {what}'s tables through OneLake in Fabric; nothing is copied outside Fabric.")
    return head + tail + read


def no_target_words(source_name: str, source_type: str, how: str, chosen: str | None) -> str:
    if how == "not_found":
        return (f"The target lakehouse {chosen!r} is not a lakehouse of this workspace; nothing was written. Choose a lakehouse "
                "of this workspace under Target lakehouse.")
    return (f"The {kind_words(source_type)} {source_name} is read-only and this workspace has no lakehouse to write the silver "
            "tables, the gold views and the pipeline's check to; nothing was written. Create a lakehouse (with Lakehouse "
            "schemas for the gold views) in this workspace, then choose it under Target lakehouse.")


# ------------------------------------------------------------------ n221: a build in another workspace ------------------
# The Krusgraph Model builds in its own workspace by default, and its source may be a lakehouse of another workspace. Its
# silver notebook is attached to a lakehouse of the build's workspace (its default lakehouse: "if multiple lakehouse are
# added into the notebook, make sure when Spark SQL is used, the target lakehouse and the current default lakehouse are
# from the same workspace", Explore the lakehouse data with a notebook, learn.microsoft.com/fabric/data-engineering/
# lakehouse-notebook-explore, read 11 November 2026) and reads the source's Delta tables by their OneLake path
# (abfss://<workspace GUID>@onelake.dfs.fabric.microsoft.com/<item GUID>/Tables/..., "you can refer to anything in your
# tenant by its workspace, item, and path", How do I connect to OneLake?, learn.microsoft.com/fabric/onelake/
# onelake-access-api, ms.date 18 May 2026). The person who runs the notebook needs read access to the source.
CROSS_DOCS = ({"title": "How do I connect to OneLake? (URI syntax)", "url": "https://learn.microsoft.com/fabric/onelake/onelake-access-api"},
              {"title": "Explore the lakehouse data with a notebook (default lakehouse, Spark SQL in the same workspace)",
               "url": "https://learn.microsoft.com/fabric/data-engineering/lakehouse-notebook-explore"},
              {"title": "Items - Create Lakehouse (creationPayload.enableSchemas)",
               "url": "https://learn.microsoft.com/rest/api/fabric/lakehouse/items/create-lakehouse"})
PLANNED_LAKEHOUSE = "<the lakehouse Create makes first>"


def cross_target_words(target: dict, how: str, source_name: str, source_kind: str, workspace_name: str) -> str:
    where = f"the workspace {workspace_name}" if workspace_name else "the workspace this Krusgraph Model builds in"
    head = (f"The silver tables, the gold views and the pipeline's check are written to the lakehouse {target.get('displayName')} "
            f"in {where}")
    tail = {"chosen": " (your choice).",
            "made": " (the lakehouse you asked Krusgraph to make; it is there now).",
            "create": ": Create makes it first, with Lakehouse schemas, because you ticked Create a lakehouse. Nothing is made in "
                      "the dry run.",
            }.get(how, f", the first lakehouse of {where} by name: the default. Choose another under Lakehouse for silver and gold.")
    read = (f" The silver notebook reads the {kind_words(source_kind)} {source_name}'s tables through OneLake (its abfss path in "
            "the other workspace); nothing is copied outside Fabric, and whoever runs the notebook needs read access to "
            f"{source_name}.")
    return head + tail + read


def no_cross_target_words(how: str, chosen: str | None, workspace_name: str) -> str:
    where = f"the workspace {workspace_name}" if workspace_name else "the workspace this Krusgraph Model builds in"
    if how == "not_found":
        return (f"The lakehouse {chosen!r} is not a lakehouse of {where}; nothing was written. Choose a lakehouse of that "
                "workspace under Lakehouse for silver and gold.")
    return (f"{where[0].upper() + where[1:]} has no lakehouse for the silver tables, the gold views and the pipeline's check; "
            "nothing was written. Tick Create a lakehouse (Create makes one with Lakehouse schemas, after this dry run), or "
            "choose a lakehouse of that workspace.")


# ------------------------------------------------------------------ the SAP pack in the review -------------------------

def sap_offer(plan) -> dict | None:
    """The SAP pack's keys and links in the plan, by review item id, each marked SAP_FROM with the pack's public sources
    (title and url, as the pack cites them). None when the plan has no SAP pack: nothing is guessed beyond the pack.
    The person accepts or rejects each in the review as any other item."""
    from . import sap_pack
    from .infer import PACK_RULE
    from .review import key_id, rel_id
    pack = getattr(plan, "pack", None)
    if not pack or pack.get("pack") != "sap":
        return None
    p = sap_pack.load("sap")
    tables = pack.get("tables") or {}            # plan table -> pack table

    def cite(ids) -> list[dict]:
        return [{"title": p["sources"][i]["title"], "url": p["sources"][i].get("url", "")} for i in ids if i in p["sources"]]
    items: dict[str, dict] = {}
    for table, (cols, rule) in plan.keys.items():
        if rule != PACK_RULE or table not in tables:
            continue
        t = p["tables"][tables[table]]
        client = [c for c in cols if c.upper() in sap_pack.CLIENT_COLUMNS]
        items[key_id(table)] = {"from": SAP_FROM, "pack_table": t["name"], "text": t.get("en", ""),
                                **({"client": client[0]} if client else {}), "sources": cite(t["sources"])}
    by_pair = {}
    for r in p["relationships"]:
        by_pair.setdefault((r["source"], r["target"]), []).append(r)
    for r in plan.relationships:
        if r.rule != PACK_RULE:
            continue
        src, tgt = tables.get(r.source), tables.get(r.target)
        cands = by_pair.get((src, tgt), [])
        plain = lambda cols: [x.upper() for x in cols if x.upper() not in sap_pack.CLIENT_COLUMNS]  # noqa: E731
        hit = next((c for c in cands if plain(c["source_cols"]) == plain(r.source_cols)), None)
        hit = hit or (cands[0] if cands else None)
        if hit is None:
            continue
        items[rel_id(r.source, r.source_cols, r.target)] = {"from": SAP_FROM, "module": hit["module"], "sources": cite(hit["sources"])}
    return {"pack": "sap", "label": "SAP pack", "items": items, "tables": dict(tables),
            "status": pack.get("status", "documented, not verified against data"),
            "client_dropped": bool(pack.get("client_dropped")),
            "note": ("These keys and links are " + SAP_FROM + ": the pack's documentation of SAP's tables, with its public "
                     "sources, not checked against your rows. Accept or reject each as any other; Check the rows counts them."),
            "mirroring": MIRRORING_NOTE, "licence": SAP_NOTE, "learn": {k: LEARN[k] for k in ("sap", "sap_limitations", "sap_tutorial")}}
