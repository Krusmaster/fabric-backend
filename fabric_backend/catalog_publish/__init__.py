"""CA1, the OneLake catalog accelerator: "Publish to OneLake catalog" in one step, a dry run by default.

The OneLake catalog is part of every Fabric tenant; nothing is provisioned. Krusgraph fills and organises it for the
data products it has proven: per product a card (cards.py: description, owner, proposed domain, tags, ODCS contract,
glossary terms, the row-check evidence and the quality rules derived from it), then

- what the signed-in user may write (writes.py): item descriptions and existing tags, shown as a diff first, written
  only with the dry run's confirm and only in a workspace on the allow list;
- what needs someone else (handover.py): tags to create and the domain and its workspace assignment (a Fabric or
  domain admin), the governance domain, data product, glossary terms and data quality rules for Microsoft Purview (a
  Purview data steward and data quality steward), and endorsement, which always stays a person's decision.

What each API allows and which role it needs is in apis.py, with the Microsoft Learn page and the day it was read.
No AI model is used anywhere here: the same plan and counts give the same answer."""
from __future__ import annotations

from . import apis, cards as _cards, handover as _handover, writes as _writes
from .cards import DESCRIPTION_MAX, evidence

__all__ = ["prepare", "apply", "for_chat", "apis", "evidence", "DESCRIPTION_MAX"]


def _item_text(products: list[dict], label: str, ev: dict) -> str:
    if len(products) == 1:
        return products[0]["description"]
    names = ", ".join(c["name"] for c in products)
    tail = f" Checked by Krusgraph: {ev['line']}." if ev["counted"] else f" Krusgraph: {ev['line']}."
    return _cards._fit(f"Data products {names} over {label}.{tail}", f"{len(products)} data products over {label}.{tail}")


def prepare(p, schema: str, workspace_id: str, items: list[dict], *, source: str = "", validation: dict | None = None,
            checked_on: str | None = None, owners: dict | None = None, names: dict | None = None,
            created_ids: set[str] | None = None, tenant_tags: list[dict] | None = None,
            tags_readable: bool = True, workspace_tags: list[dict] | None = None) -> dict:
    """The whole answer for one plan. `items`: the Fabric items the products live in, as read now
    ({id, displayName, type, description, tags}); `created_ids`: the ones this Model (or tool) built; `tenant_tags`:
    GET /v1/tags as read now; with tags_readable=False (List Tags needs Tag.Read.All, which the apps do not hold) the
    ids come from `workspace_tags`, the tags already on the workspace's items, and the rest go to the handover."""
    created_ids = set(created_ids or ())
    got = _cards.cards(p, schema, source, validation, checked_on, owners, names)
    products = got["products"]
    every = sorted({t for c in products for t in c["tables"]}, key=str.lower)
    ev = evidence(validation, every, checked_on)
    label = source or schema
    text = _item_text(products, label, ev) if products else ""
    tag_names = list(dict.fromkeys(t for c in products for t in c["tags"]))
    pool = list(tenant_tags or []) if tags_readable else list(workspace_tags or [])
    writes, kept, missing = [], [], []
    if products:
        for it in items:
            w, k, m = _writes.item_writes(workspace_id, it, text, tag_names, pool, created_ids)
            writes += w
            kept += k
            missing += m
    writes.sort(key=lambda w: (w["field"] != "description", [i.get("id") for i in items].index(w["item_id"])))
    missing_tags = sorted({m["tag"] for m in missing}, key=str.lower)
    hand = _handover.build(products, schema, label, missing_tags, ev, tags_readable)
    n_desc = sum(1 for w in writes if w["field"] == "description")
    n_tags = sum(1 for w in writes if w["field"] == "tags")
    summary = (f"{len(products)} data product card(s); as you: {n_desc} description(s) and tags on {n_tags} item(s) to "
               f"write; for others: {len(hand['requests'])} request(s) in the handover files"
               + (f"; {len(kept)} kept as they are" if kept else ""))
    return {
        "summary": summary,
        "products": products,
        "unassigned": got["unassigned"],
        "evidence": ev,
        "writes": writes,
        "diff": _writes.diff(writes, kept),
        "kept": kept,
        "confirm": _writes.confirm_of(workspace_id, writes) if writes else None,
        "undo": [w["undo"] | {"item": w["item"]} for w in writes],
        "handover": hand,
        "who_may_do_what": apis.ROLES,
        "sources": apis.SOURCES,
    }


def apply(answer: dict, workspace_id: str, confirm: str | None, send) -> dict:
    """Write the dry run's writes as the signed-in user, after the guard (writes.check_write). Returns the results."""
    _writes.check_write(workspace_id, answer["writes"], confirm)
    return {"results": _writes.apply(answer["writes"], send), "undo": answer["undo"]}


def for_chat(answer: dict) -> dict:
    """The answer the MCP tool returns: the contracts' YAML and the Purview request bodies left out (domain_draft
    gives the contracts; the workload's step downloads every file), the rest as it is."""
    out = dict(answer)
    out["products"] = [{**c, "contract": {k: v for k, v in c["contract"].items() if k != "yaml"}} for c in answer["products"]]
    h = answer["handover"]
    pv = h["purview"]
    out["handover"] = {
        "requests": h["requests"], "approvals": h["approvals"],
        "files": {k: v for k, v in h["files"].items() if k.endswith(".md")},
        "also": sorted(k for k in h["files"] if not k.endswith(".md")),
        "purview": {"retiring": pv["retiring"], "auth": pv["auth"],
                    "products": [{"name": x["name"], "requests": [{"step": r["step"], "by": r["by"]} for r in x["requests"]],
                                  "rules": x["rules"]} for x in pv["products"]]},
    }
    return out
