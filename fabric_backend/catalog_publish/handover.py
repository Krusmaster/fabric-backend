"""CA1: what the signed-in person may not do, as ready requests and files for the person who may, each naming who must
approve. Nothing here is sent. Three readers:

- a Fabric administrator (or domain admin): the tags to create, the domain or subdomain, assigning the workspace;
- a Purview steward (only for a customer who uses Purview Unified Catalog, which is being retired): purview.py;
- the person who endorses: the evidence a reviewer wants. Promoted or Certified is always a person's decision."""
from __future__ import annotations

import json

from . import apis, purview as _purview


def _tag_requests(missing: list[str], readable: bool) -> list[dict]:
    if not missing:
        return []
    return [{"step": "Create the tags", "by": "fabric_admin", "method": "POST",
             "url": "https://api.fabric.microsoft.com/v1/admin/tags/bulkCreateTags",
             "body": {"createTagsRequest": [{"displayName": t} for t in missing]},
             "why": ("these tags were not found in the tenant" if readable else
                     "the tenant's tags could not be read (List Tags needs Tag.Read.All, which the app does not hold), "
                     "and no item in the workspace carries them"),
             "then": "run Publish to OneLake catalog again: it applies tags that exist",
             "domain_tag": "a domain admin can create them as domain tags in the admin portal instead"}]


def _domain_requests(products: list[dict]) -> list[dict]:
    out = []
    for c in products:
        name = c["domain"]["proposed"][:40]
        out.append({"step": f"Domain {name}", "by": "fabric_admin", "method": "POST",
                    "url": "https://api.fabric.microsoft.com/v1/admin/domains",
                    "body": {"displayName": name, "description": f"Proposed by Krusgraph: {c['domain']['why']}"[:256]},
                    "why": "only a Fabric administrator creates domains; a domain admin may create a subdomain instead",
                    "note": "only if no domain fits: the workspace may belong in one that exists"})
    if products:
        out.append({"step": "Assign the workspace to the domain", "by": "workspace_admin", "method": "POST",
                    "url": "https://api.fabric.microsoft.com/v1/workspaces/{workspace-id}/assignToDomain",
                    "body": {"domainId": "{domain-id}"},
                    "why": "a domain holds workspaces, not items; Krusgraph's apps do not hold Workspace.ReadWrite.All",
                    "portal": "Workspace settings > Domains (a workspace admin who is a domain contributor)"})
    return out


def _endorsement(products: list[dict], ev: dict) -> list[dict]:
    return [{"step": f"Endorse {c['name']}", "by": "reviewer", "method": None, "url": None,
             "evidence": c["evidence"]["line"],
             "rules": [f"{r['says']}: {r['status']}" for r in c["quality_rules"]],
             "how": "Item settings > Endorsement in Fabric: Promoted (write permission) or Certified (a named reviewer)",
             "why": "no REST API sets endorsement, and it is a person's judgement: Krusgraph never sets or requests it"}
            for c in products]


def _markdown(title: str, who: str, rows: list[dict], extra: str = "") -> str:
    lines = [f"# {title}", "", f"To approve: {who}.", "", "Prepared by Krusgraph; nothing was sent. Sources: "
             "docs/CATALOG-ACCELERATOR.md (Microsoft Learn, read 17 November 2026).", ""]
    if extra:
        lines += [extra, ""]
    for r in rows:
        lines.append(f"## {r['step']}")
        lines.append("")
        lines.append(f"Who: {apis.WHO[r['by']]}.")
        if r.get("why"):
            lines.append(f"Why: {r['why']}.")
        if r.get("evidence"):
            lines.append(f"Evidence: {r['evidence']}.")
        for x in r.get("rules", []):
            lines.append(f"- {x}")
        if r.get("how"):
            lines.append(f"How: {r['how']}.")
        if r.get("portal"):
            lines.append(f"In the portal: {r['portal']}.")
        if r.get("url"):
            lines += ["", "```", f"{r['method']} {r['url']}", json.dumps(r.get("body"), indent=2, ensure_ascii=False), "```"]
        for k in ("note", "then", "domain_tag"):
            if r.get(k):
                lines.append(f"{k.replace('_', ' ').capitalize()}: {r[k]}.")
        lines.append("")
    return "\n".join(lines)


def build(products: list[dict], schema: str, label: str, missing_tags: list[str], ev: dict, tags_readable: bool) -> dict:
    admin = _tag_requests(missing_tags, tags_readable) + _domain_requests(products)
    endorse = _endorsement(products, ev)
    pv = _purview.handover(products)
    files = {}
    if admin:
        files["handover/fabric-admin.md"] = _markdown(f"OneLake catalog for {label}: for the Fabric administrator",
                                                      "a Fabric administrator, and the workspace admin for the last step",
                                                      admin)
    if endorse:
        files["handover/endorsement.md"] = _markdown(f"OneLake catalog for {label}: endorsement", "the reviewer",
                                                     endorse, "Krusgraph does not endorse, and does not ask for it: "
                                                     "this is the evidence, for a person to judge.")
    if products:
        files["handover/purview.json"] = json.dumps(pv, indent=2, ensure_ascii=False) + "\n"
    for c in products:
        files[c["contract"]["file"]] = c["contract"]["yaml"]
    approvals = sorted({apis.WHO[r["by"]] for r in admin + endorse})
    return {"requests": admin + endorse, "purview": pv, "files": files, "approvals": approvals}
