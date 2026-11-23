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
from .cards import DESCRIPTION_MAX, counted_keys, counted_links, day_words, evidence, page_evidence

__all__ = ["prepare", "apply", "for_chat", "apis", "evidence", "page_evidence", "DESCRIPTION_MAX"]


def _item_texts(products: list[dict], label: str, ev: dict) -> list[str]:
    """WB10: the data-product sentence appended to an item's own first sentence, longest first: the page's totals (the
    same as the Thinker line) with the links between data products stated separately, then shorter forms."""
    names = " and ".join(c["name"] for c in products) if len(products) < 3 else f"{len(products)} data products"
    what = f"Data product{'s' if len(products) > 1 else ''} {names} over {label}"
    if not ev["counted"]:
        return [f"{what}; Krusgraph: {ev['line']}.", f"{what}."]
    return [f"{what}, checked by Krusgraph: {ev['line']}.", f"{what}, checked by Krusgraph: {ev['short']}.", f"{what}."]


def _plural(n: int, one: str) -> str:
    return f"{n} {one}" if n == 1 else f"{n} {one}s"


def model_texts(products: list[dict], label: str, validation: dict | None, checked_on: str | None, built: list[str]) -> list[str]:
    """W3: the Krusgraph Model item's description, longest first: "Krusgraph data product <name> over <source>: 6 of 6
    keys unique, 5 of 5 links holding, checked <date>. Built: <items>." A link holds when the check found no orphan
    row. The same recorded counts as the Thinker line and the other descriptions; the list of built items is shortened
    to fit 256 characters, never the counts."""
    names = " and ".join(c["name"] for c in products) if len(products) < 3 else f"{len(products)} data products"
    head = f"Krusgraph data product{'s' if len(products) > 1 else ''} {names} over {label}"
    keys, links = counted_keys(validation), counted_links(validation)
    if keys or links:
        unique = sum(1 for k in keys if (k.get("status") == "passed" if k.get("status") else str(k.get("verdict", "")).startswith("unique")))
        holding = sum(1 for r in links if r.get("orphans") == 0)
        bits = ([f"{unique} of {_plural(len(keys), 'key')} unique"] if keys else []) + \
               ([f"{holding} of {_plural(len(links), 'link')} holding"] if links else [])
        proof = ", ".join(bits) + (f", checked {day_words(checked_on)}" if checked_on else "")
    else:
        proof = "keys and links not yet checked against the rows"
    base = f"{head}: {proof}."
    shown = [b for b in built if b]
    out = []
    if shown:
        out.append(f"{base} Built: {', '.join(shown)}.")
        for n in (4, 3, 2, 1):
            if len(shown) > n:
                out.append(f"{base} Built: {', '.join(shown[:n])} and {len(shown) - n} more.")
        out.append(f"{base} Built: {_plural(len(shown), 'item')}.")
    out.append(base)
    return out


def prepare(p, schema: str, workspace_id: str, items: list[dict], *, source: str = "", validation: dict | None = None,
            checked_on: str | None = None, owners: dict | None = None, names: dict | None = None,
            created_ids: set[str] | None = None, tenant_tags: list[dict] | None = None,
            tags_readable: bool = True, workspace_tags: list[dict] | None = None, include: set[str] | None = None,
            source_id: str | None = None, model_item: dict | None = None) -> dict:
    """The whole answer for one plan. `items`: the Fabric items the products live in, as read now
    ({id, displayName, type, description, tags}); `created_ids`: the ones this Model (or tool) built; `tenant_tags`:
    GET /v1/tags as read now; with tags_readable=False (List Tags needs Tag.Read.All, which the apps do not hold) the
    ids come from `workspace_tags`, the tags already on the workspace's items, and the rest go to the handover.
    WB10: `include`, ids of items Krusgraph did not build that the person ticked: only those are written to; the others
    are offered, unticked, in `optional`. W3: `model_item`, the Krusgraph Model item as listed now ({id, displayName,
    type, description}): its description says which data product it holds and what it built (writes.model_writes)."""
    created_ids = set(created_ids or ())
    got = _cards.cards(p, schema, source, validation, checked_on, owners, names)
    products = got["products"]
    ev = page_evidence(validation, [{"name": c["name"], "tables": c["tables"]} for c in products], checked_on)
    label = source or schema
    texts = _item_texts(products, label, ev) if products else []
    tag_names = list(dict.fromkeys(t for c in products for t in c["tags"]))
    pool = list(tenant_tags or []) if tags_readable else list(workspace_tags or [])
    writes, kept, missing, optional = [], [], [], []
    include = set(include or ())
    if products:
        for it in items:
            # ED3 (Gustav: the preview wrote onto the source shop_lh, in its own workspace): the source is never this
            # data product's, whatever its description carries; it is offered unticked, like any item not built here
            built = _writes.ours(it, created_ids) and (not source_id or it.get("id") != source_id)
            w, k, m = _writes.item_writes(workspace_id, it, texts, tag_names, pool, created_ids, built)
            if built or it.get("id") in include:
                writes += w
                kept += k
            elif w:
                optional.append(_writes.offer(it, w, source=bool(source_id) and it.get("id") == source_id,
                                              other_workspace=bool(it.get("workspace")) and str(it["workspace"]).lower() != workspace_id.lower()))
            missing += m
    writes.sort(key=lambda w: (w["field"] != "description", [i.get("id") for i in items].index(w["item_id"])))
    if products and model_item and model_item.get("id"):           # W3: the Model item first, a description only
        ids = {str(i).lower() for i in created_ids}
        built_names = [str(it.get("displayName")) for it in items if str(it.get("id", "")).lower() in ids and it.get("displayName")]
        writes = _writes.model_writes(workspace_id, model_item, model_texts(products, label, validation, ev.get("checked_on") or checked_on,
                                                                            built_names)) + writes
    missing_tags = sorted({m["tag"] for m in missing}, key=str.lower)
    hand = _handover.build(products, schema, label, missing_tags, ev, tags_readable)
    n_desc = sum(1 for w in writes if w["field"] == "description")
    n_tags = sum(1 for w in writes if w["field"] == "tags")
    summary = (f"{len(products)} data product card(s); as you: {n_desc} description(s) and tags on {n_tags} item(s) to "
               f"write; for others: {len(hand['requests'])} request(s) in the handover files"
               + (f"; {len(kept)} kept as they are" if kept else "")
               + (f"; {len(optional)} item(s) Krusgraph did not build left out unless you tick them" if optional else ""))
    return {
        "summary": summary,
        "products": products,
        "unassigned": got["unassigned"],
        "evidence": ev,
        "writes": writes,
        "diff": _writes.diff(writes, kept, optional),
        "optional": optional,
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
