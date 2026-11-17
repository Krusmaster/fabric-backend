"""CA1: reading what is in Fabric now, for the diff, and sending the writes, as the signed-in user. Reads: the
workspace's items (List Items: description and tags come with each item) and the tenant's tags (List Tags). Writes go
through deploy.send, which retries only 429 and 503."""
from __future__ import annotations

FABRIC = "https://api.fabric.microsoft.com"


def _pages(http, url: str) -> list[dict]:
    out = []
    while url:
        r = http("get", url)
        if getattr(r, "status_code", 200) >= 400:
            raise PermissionError(getattr(r, "status_code", 0))
        body = r.json() or {}
        out += body.get("value", [])
        url = body.get("continuationUri")
    return out


def items(http, workspace_id: str) -> list[dict]:
    return _pages(http, f"{FABRIC}/v1/workspaces/{workspace_id}/items")


def tenant_tags(http) -> tuple[list[dict], bool]:
    """(tags, readable). A 401/403 or any failure: ([], False), and the dry run then applies no tag and says why."""
    try:
        return _pages(http, f"{FABRIC}/v1/tags"), True
    except Exception:  # noqa: BLE001 — not readable is an answer: the handover lists every tag
        return [], False


def pick(listed: list[dict], source_id: str | None, created_ids: set[str], schema: str, names: list[str] | None = None) -> list[dict]:
    """The items the products live in: the source item, the items this Model or tool built (created ids, or Krusgraph's
    plan marker for this schema in the description) and any item named in `names`; in the listing's order."""
    from ..workload_api import mark_of_description
    names_l = {n.lower() for n in names or []}
    out = []
    for it in listed:
        mark = mark_of_description(it.get("description"))
        if (it.get("id") == source_id or it.get("id") in created_ids
                or (mark and str(mark.get("schema", "")).lower() == schema.lower())
                or str(it.get("displayName", "")).lower() in names_l):
            out.append(it)
    return out


def sender(headers: dict):
    from ..deploy import send

    def go(method: str, url: str, body: dict) -> int:
        r = send(method, url, headers, write=True, json=body, timeout=30)
        return getattr(r, "status_code", 200)
    return go


def reader(headers: dict):
    from ..deploy import send

    def get(method: str, url: str):
        return send(method, url, headers, write=False, timeout=30)
    return get
