"""CA1: what "Publish to OneLake catalog" would write as the signed-in user, shown before it is written.

Only two Fabric calls are ever sent, both documented for a caller with write permission on the item (apis.py):
Items - Update Item (the description) and Tags - Apply Tags (tags that already exist in the tenant, by id). Everything
else goes to a handover file for the person who may do it (handover.py).

Rules that keep it safe:
- A dry run by default. A write needs dry_run=false, the `confirm` the dry run returned (a hash of exactly the writes
  shown), and a workspace listed in KRUSGRAPH_CATALOG_WRITE_WORKSPACES (comma-separated ids; empty: no workspace). The
  list is the maintainer's: Kruse Consulting's demo workspace while this is tested.
- WB10 (Gustav's live test, 18 Nov 2026): a description is never replaced. The item's own first sentence is kept and
  the data-product sentence appended (the plan marker stays at the end); an earlier data-product sentence of
  Krusgraph's is replaced, so a second run does not repeat it. Items Krusgraph did not build (the source lakehouse)
  are not written to by default: they are offered unticked (`optional`), with one line why.
- Tags are only added, never removed; at most 10 per item; a tag that does not exist is not created here.
- Every write records what was there before, and the answer carries the calls that undo it (Update Item with the old
  description, Tags - Unapply Tags with the ids that were added).
"""
from __future__ import annotations

import hashlib
import json
import os
import re

DESCRIPTION_MAX = 256

FABRIC = "https://api.fabric.microsoft.com"
TAGS_PER_ITEM = 10
ALLOW_ENV = "KRUSGRAPH_CATALOG_WRITE_WORKSPACES"


def allowed_workspaces() -> set[str]:
    return {w.strip().lower() for w in os.environ.get(ALLOW_ENV, "").split(",") if w.strip()}


def _mark_tools():
    from .. import workload_api as _w                        # the n180 plan marker, kept at the end of a description
    return _w.MARK, _w.with_mark, _w.mark_of_description


def ours(item: dict, created_ids: set[str]) -> bool:
    """Built by Krusgraph: one of outputs.json's created ids, or Krusgraph's plan marker in its description."""
    mark, _, of = _mark_tools()
    return item.get("id") in created_ids or of(item.get("description")) is not None


_ours = ours
OURS_START = ("Data product ", "Data products ")
NOT_OURS_WHY = ("Krusgraph did not build {name}: its description and tags are its owner's, so nothing is written to it "
                "unless you tick it")


def own_first_sentence(description: str | None) -> str:
    """The item's own first sentence, without the plan marker and without a data-product sentence of Krusgraph's."""
    mark, _, _ = _mark_tools()
    base = " ".join(mark.sub("", str(description or "")).split())
    if not base or base.startswith(OURS_START):
        return ""
    m = re.match(r"(.+?[.!?])(?=\s|$)", base)
    first = (m.group(1) if m else base).strip()
    return first if first.endswith((".", "!", "?")) else first + "."


TYPE_WORDS = {"Notebook": "notebook", "DataPipeline": "pipeline", "SemanticModel": "semantic model", "Report": "report",
              "GraphQLApi": "API for GraphQL", "Lakehouse": "lakehouse", "Ontology": "ontology", "DataAgent": "data agent",
              "Warehouse": "warehouse", "SQLEndpoint": "SQL analytics endpoint", "AppBackend": "app"}


def built_first_sentence(item: dict) -> str:
    """ED3 (Gustav: the notebook's 'After' appended the data-product sentence to its starter text): one template for
    every item Krusgraph built, whatever its description said before: 'Krusgraph <type> <name>.'"""
    t = TYPE_WORDS.get(str(item.get("type") or ""), "item")
    return f"Krusgraph {t} {item.get('displayName') or item.get('id')}."


def new_description(item: dict, texts, built: bool = False) -> str:
    """The item's first sentence (its own; ED3: for an item Krusgraph built, the one template), then the data-product
    sentence (the longest of `texts` that fits), then Krusgraph's plan marker if the item has one: 256 characters."""
    _, with_mark, of = _mark_tools()
    texts = [texts] if isinstance(texts, str) else list(texts)
    m = of(item.get("description"))
    first = built_first_sentence(item) if built else own_first_sentence(item.get("description"))
    room = DESCRIPTION_MAX - (len(_mark_text(m)) + 1 if m else 0)
    body = ""
    for t in texts:
        body = f"{first} {t}".strip()
        if len(body) <= room:
            break
    if len(body) > room:
        body = first if 0 < len(first) <= room else body[:max(room - 1, 0)].rstrip() + "…"
    return with_mark(body, m) if m else body


def _mark_text(m: dict) -> str:
    from ..workload_api import mark_text
    return mark_text(m)


SOURCE_WHY = "{name} belongs to its own workspace; tick to describe it too"


def offer(item: dict, writes: list[dict], source: bool = False, other_workspace: bool = False) -> dict:
    """WB10: an item Krusgraph did not build, offered unticked: what would be written if the person ticks it. ED3: the
    source lakehouse in another workspace says so in one line."""
    name = item.get("displayName") or item["id"]
    why = SOURCE_WHY.format(name=name) if (source and other_workspace) else NOT_OURS_WHY.format(name=name)
    return {"item": name, "item_id": item["id"], "type": item.get("type"), "why": why,
            "fields": [w["field"] for w in writes], "writes": [{k: w[k] for k in ("field", "before", "after")} for w in writes]}


def item_writes(workspace_id: str, item: dict, text, tag_names: list[str], tenant_tags: list[dict] | None,
                created_ids: set[str], built: bool | None = None) -> tuple[list[dict], list[dict], list[dict]]:
    """(writes, kept, missing_tags) for one item {id, displayName, type, description, tags: [{id, displayName}]}.
    ED3: `workspace_id` is the item's own workspace (a source lakehouse may live in another); `built`: whether this
    data product built it (default: ours())."""
    writes, kept, missing = [], [], []
    url = f"{FABRIC}/v1/workspaces/{item.get('workspace') or workspace_id}/items/{item['id']}"
    name = item.get("displayName") or item["id"]
    before = item.get("description") or ""
    after = new_description(item, text, ours(item, created_ids) if built is None else built)
    if after != before:
        writes.append({"operation": "Items_UpdateItem", "method": "PATCH", "url": url, "body": {"description": after},
                       "item": name, "item_id": item["id"], "type": item.get("type"), "field": "description",
                       "before": before, "after": after,
                       "undo": {"operation": "Items_UpdateItem", "method": "PATCH", "url": url,
                                "body": {"description": before}}})
    have = {str(t.get("displayName", "")).lower() for t in item.get("tags") or []}
    by_name = {str(t.get("displayName", "")).lower(): t for t in tenant_tags or []}
    add, add_names = [], []
    for t in tag_names:
        if t.lower() in have:
            continue
        found = by_name.get(t.lower())
        if found is None:
            missing.append({"tag": t, "item": name})
            continue
        add.append(found["id"])
        add_names.append(found.get("displayName", t))
    room = TAGS_PER_ITEM - len(have)
    if len(add) > room:
        kept.append({"item": name, "type": item.get("type"), "field": "tags", "why": f"an item can have at most {TAGS_PER_ITEM} tags; "
                     f"{len(add) - max(room, 0)} left out", "suggested": add_names[max(room, 0):]})
        add, add_names = add[:max(room, 0)], add_names[:max(room, 0)]
    if add:
        writes.append({"operation": "Tags_ApplyTags", "method": "POST", "url": url + "/applyTags", "body": {"tags": add},
                       "item": name, "item_id": item["id"], "type": item.get("type"), "field": "tags",
                       "before": sorted(t.get("displayName", "") for t in item.get("tags") or []),
                       "after": sorted([t.get("displayName", "") for t in item.get("tags") or []] + add_names),
                       "undo": {"operation": "Tags_UnapplyTags", "method": "POST", "url": url + "/unapplyTags",
                                "body": {"tags": add}}})
    return writes, kept, missing


def confirm_of(workspace_id: str, writes: list[dict]) -> str:
    """A hash of exactly the writes shown: the write call must send it back, so what is written is what was seen."""
    core = [[w["method"], w["url"], w["body"], w["before"]] for w in writes]
    text = json.dumps([workspace_id.lower(), core], sort_keys=True, ensure_ascii=False)
    return "catalog-" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def diff(writes: list[dict], kept: list[dict], optional: list[dict] | None = None) -> list[dict]:
    """One row per item and field, in the order the items were listed: what is there now and what would be there; then
    (WB10) one row per item Krusgraph did not build, unticked, with what would be written if it is ticked."""
    # WB11: each row says its item's Fabric type, so the editor shows that item type's icon beside the name
    rows = [{"item": w["item"], "type": w.get("type"), "field": w["field"], "before": w["before"], "after": w["after"], "action": "write"}
            for w in writes]
    rows += [{"item": k["item"], "type": k.get("type"), "field": k["field"], "before": None, "after": k.get("suggested"), "action": "kept",
              "why": k["why"]} for k in kept]
    rows += [{"item": o["item"], "item_id": o["item_id"], "type": o.get("type"), "field": " and ".join(o["fields"]), "action": "optional",
              "before": next((w["before"] for w in o["writes"] if w["field"] == "description"), None),
              "after": next((w["after"] for w in o["writes"] if w["field"] == "description"), None),
              "why": o["why"]} for o in optional or []]
    return rows


class NotAllowed(Exception):
    """A write the guard refuses: no confirm, a confirm for other writes, or a workspace not on the list."""


def check_write(workspace_id: str, writes: list[dict], confirm: str | None) -> None:
    allowed = allowed_workspaces()
    if workspace_id.lower() not in allowed:
        raise NotAllowed(f"writing to the catalog is switched on only for the workspaces in {ALLOW_ENV} "
                         "(Kruse Consulting's demo workspace while it is tested); this one is not listed. "
                         "The dry run's writes and the handover files are yours to use.")
    # ED3: a ticked item in another workspace (the source lakehouse) is written only where writing is on there too
    other = sorted({w["url"].split("/workspaces/", 1)[1].split("/", 1)[0].lower() for w in writes if "/workspaces/" in w["url"]}
                   - allowed)
    if other:
        raise NotAllowed(f"writing to the catalog is not switched on in the workspace of a ticked item ({', '.join(other)}); "
                         "untick it, or use the handover files")
    want = confirm_of(workspace_id, writes)
    if not confirm:
        raise NotAllowed("send back the confirm value of the dry run, so what is written is what you saw")
    if confirm != want:
        raise NotAllowed("the items changed since the dry run (or the confirm belongs to another dry run): run the dry "
                         "run again and check the diff")


def apply(writes: list[dict], send) -> list[dict]:
    """Send each write once, in order (descriptions first, then tags), with `send(method, url, body)` returning the
    HTTP status. A failure is reported and the rest still go; nothing is retried here (deploy.send retries 429/503)."""
    out = []
    for w in writes:
        try:
            status = int(send(w["method"].lower(), w["url"], w["body"]))
        except Exception as e:  # noqa: BLE001 — reported per write, never raised past the others
            out.append({"item": w["item"], "field": w["field"], "ok": False, "error": type(e).__name__})
            continue
        res = {"item": w["item"], "field": w["field"], "ok": status < 400, "status": status}
        if status in (401, 403):
            res["hint"] = ("Fabric refused: Update Item needs read and write permission on the item, Apply Tags the "
                           "Contributor role on the workspace or higher")
        out.append(res)
    return out
