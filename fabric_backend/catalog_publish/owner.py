"""WB10 (Gustav's live test, 18 Nov 2026): the catalog's owner is a person or a group, never an item.

The field showed 'demo_lh_api9', an API for GraphQL item's name (most likely the browser's autofill from the output
name field; the editor's field now has autocomplete off, a name of its own and the people picker). The engine refuses
any value that is not a person or group with a role in the workspace, or the signed-in person (Me)."""
from __future__ import annotations

import re

_UPN = re.compile(r"^(?P<name>.+?)\s*\((?P<upn>[^()]+@[^()]+)\)$")


def _forms(p: dict) -> set[str]:
    out = {p.get("name", "").strip().lower()}
    if p.get("upn"):
        out |= {p["upn"].strip().lower(), f"{p.get('name', '').strip()} ({p['upn'].strip()})".lower()}
    return out - {""}


def check(owner: str, people: list[dict] | None, items: list[dict], me: str | None = None) -> str | None:
    """None when `owner` may stand; else the sentence that says why not. `people`: the workspace's role assignments
    (product_life.people), None when Fabric did not answer; `items`: the workspace's items as listed."""
    v = " ".join(str(owner or "").split())
    if not v:
        return None
    low = v.lower()
    if me and low == me.strip().lower():
        return None
    if people:
        known = set().union(*(_forms(p) for p in people))
        m = _UPN.match(v)
        if low in known or (m and m.group("upn").lower() in known):
            return None
    item = next((it for it in items if str(it.get("displayName", "")).strip().lower() == low), None)
    if item is not None:
        return (f"'{v}' is an item in this workspace ({item.get('type') or 'an item'}), not a person or group. "
                "The owner is the person or group who answers for the data products.")
    if people:
        return f"'{v}' is not a person or group with a role in this workspace."
    return None                                  # role assignments unreadable: a name that is no item's may stand
