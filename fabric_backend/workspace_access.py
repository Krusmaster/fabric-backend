"""Workspace roles and sensitivity labels proposed for what Krusgraph builds, dry run only (round BL35, 21 November
2026; backlog B-25).

After "who sees which rows" (`security_roles.py`, BL17) a buyer's Fabric administrator asks the next two questions:
"which workspace role does each group need" and "does a sensitivity label carry over to what you build". This module
answers both with a proposal, never with a change: nothing here talks to Fabric, Entra or Purview, assigns a role or
sets a label.

- `propose(outputs, groups=None)`: per built item (the outputs of `tenant_settings.OUTPUTS`) the least workspace role
  each group needs, with the reason and the Learn row it rests on. Groups are placeholders ("data engineers",
  "report readers", "access managers"), each standing for what its people do: build, read or add people. A workspace
  role covers the whole workspace, so each group's role is the highest one any of its items needs. Admin is never
  proposed: only Admin updates or deletes the workspace, and nothing Krusgraph builds needs that.
- `request_bodies(proposal)`: the body of Fabric's "Add Workspace Role Assignment" call for each group, with the
  group's object id left for a person to fill in (Krusgraph invents no group or user id). Never sent: the call needs
  `Workspace.ReadWrite.All`, which the hosted app does not ask for (`access.NOT_REQUESTED`).
- `labels(outputs)`: per output, whether it takes a sensitivity label from its source or from the item it is built on,
  as the Learn pages state it, and a "set by a person" line. Krusgraph never sets a label (`privacy.label_of` only
  reads the label id an item already has).
- `markdown(outputs, groups=None)`: the dry run's text, one summary line of at most 25 words per item.
- `dry_run_line(outputs, groups=None)`: the start flow's one line on its dry-run step (round BL54), at most 25 words.

Read on Microsoft Learn on 21 November 2026 (READ_ON), each page's own date in LEARN:
- "Roles in workspaces in Microsoft Fabric", fabric/fundamentals/roles-workspaces (2026-04-24): the capability table.
- "Roles in workspaces in Power BI", power-bi/collaborate-share/service-roles-new-workspaces (2025-12-01): reports and
  semantic models ("View and interact with an item", "Create, edit, and delete content in the workspace", "Use the
  Viewer role to enforce row-level security").
- "Workspaces - Add Workspace Role Assignment", rest/api/fabric/core/workspaces/add-workspace-role-assignment
  (updated 2026-11-10): `POST https://api.fabric.microsoft.com/v1/workspaces/{workspaceId}/roleAssignments`, body
  `{"principal": {"id", "type"}, "role"}`, Required Delegated Scopes `Workspace.ReadWrite.All`, caller Member or higher.
- "Sensitivity label inheritance from data sources in Power BI", fabric/governance/
  service-security-sensitivity-label-inheritance-from-data-sources (2026-07-13): sources Excel on OneDrive or
  SharePoint, Azure Synapse Analytics, Azure SQL Database; Import mode only.
- "Sensitivity label downstream inheritance in Power BI", fabric/governance/
  service-security-sensitivity-label-downstream-inheritance (2026-07-13): a new report built on a labelled semantic
  model inherits its label upon creation; never overwrites a manually applied label.

Deterministic: fixed tables, no model call, no network.
"""
from __future__ import annotations

from .tenant_settings import OUTPUTS, _check_outputs

READ_ON = "2026-11-21"
CONFIRMED, UNVERIFIED = "confirmed", "unverified"

_L = "https://learn.microsoft.com/en-us/"
LEARN = {
    "fabric_roles": {"title": "Roles in workspaces in Microsoft Fabric", "url": _L + "fabric/fundamentals/roles-workspaces",
                     "page_date": "2026-04-24"},
    "pbi_roles": {"title": "Roles in workspaces in Power BI",
                  "url": _L + "power-bi/collaborate-share/service-roles-new-workspaces", "page_date": "2025-12-01"},
    "add_role": {"title": "Workspaces - Add Workspace Role Assignment",
                 "url": _L + "rest/api/fabric/core/workspaces/add-workspace-role-assignment", "page_date": "2026-11-10"},
    "label_sources": {"title": "Sensitivity label inheritance from data sources in Power BI",
                      "url": _L + "fabric/governance/service-security-sensitivity-label-inheritance-from-data-sources",
                      "page_date": "2026-07-13"},
    "label_downstream": {"title": "Sensitivity label downstream inheritance in Power BI",
                         "url": _L + "fabric/governance/service-security-sensitivity-label-downstream-inheritance",
                         "page_date": "2026-07-13"},
}

# least to most; Admin is listed so an order exists, never proposed
ROLES = ("Viewer", "Contributor", "Member", "Admin")

# placeholder group -> what its people do. A caller may pass other names with one of these activities.
GROUPS: dict[str, str] = {
    "data engineers": "build",
    "report readers": "read",
    "access managers": "manage",
}
ACTIVITIES = ("build", "read", "manage")

# The capability rows quoted from the Learn pages (the words as the tables print them).
_F_READ_ITEMS = "View and read content of pipelines, notebooks, Spark job definitions, ML models and experiments, and eventstreams."
_F_WRITE_ITEMS = "Write or delete pipelines, notebooks, Spark job definitions, ML models, and experiments, and eventstreams."
_F_RUN_NB = "Execute or cancel execution of notebooks, Spark job definitions, ML models, and experiments."
_F_RUN_PL = "Execute or cancel execution of pipelines."
_F_SQL = "Connect to SQL analytics endpoint of Lakehouse or the Warehouse"
_F_WRITE_LH = ("Write or delete Eventhouses, KQL Querysets, Real-Time Dashboards, digital twin builder data, and schema and "
               "data of KQL Databases, Lakehouses, data warehouses, and shortcuts.")
_F_READALL = "Read Lakehouse and Data warehouse data and shortcuts through OneLake APIs and Spark (ReadAll)."
_P_VIEW = "View and interact with an item"
_P_EDIT = "Create, edit, and delete content in the workspace"
_P_ADD = "Add members or others with lower permissions"

# output: activity -> (role, status, Learn key, the row or why)
NEEDS: dict[str, dict[str, tuple[str, str, str, str]]] = {
    "lakehouse": {
        "build": ("Contributor", CONFIRMED, "fabric_roles", _F_WRITE_LH),
        "read": ("Viewer", CONFIRMED, "fabric_roles", _F_SQL + "; reading through OneLake or Spark needs Contributor ("
                 + _F_READALL + ")"),
    },
    "notebook": {
        "build": ("Contributor", CONFIRMED, "fabric_roles", _F_WRITE_ITEMS + " " + _F_RUN_NB),
        "read": ("Viewer", CONFIRMED, "fabric_roles", _F_READ_ITEMS),
    },
    "pipeline": {
        "build": ("Contributor", CONFIRMED, "fabric_roles", _F_WRITE_ITEMS + " " + _F_RUN_PL),
        "read": ("Viewer", CONFIRMED, "fabric_roles", _F_READ_ITEMS),
    },
    "semantic_model": {
        "build": ("Contributor", CONFIRMED, "pbi_roles", _P_EDIT),
        "read": ("Viewer", CONFIRMED, "pbi_roles", _P_VIEW + "; the Viewer role enforces row-level security (BL17's roles)"),
    },
    "report": {
        "build": ("Contributor", CONFIRMED, "pbi_roles", _P_EDIT),
        "read": ("Viewer", CONFIRMED, "pbi_roles", _P_VIEW),
    },
    "ontology": {
        "build": ("Contributor", UNVERIFIED, "fabric_roles", "an ontology is a Fabric item; the table does not name it"),
        "read": ("Viewer", UNVERIFIED, "fabric_roles", "an ontology is a Fabric item; the table does not name it"),
    },
    "data_agent": {
        "build": ("Contributor", UNVERIFIED, "fabric_roles", "a data agent is a Fabric item; the table does not name it"),
        "read": ("Viewer", UNVERIFIED, "fabric_roles", "a data agent is a Fabric item; the table does not name it"),
    },
    "graphql_api": {
        "build": ("Contributor", UNVERIFIED, "fabric_roles", "an API for GraphQL is a Fabric item; the table does not name it"),
        "read": ("Viewer", UNVERIFIED, "fabric_roles", "an API for GraphQL is a Fabric item; the table does not name it"),
    },
}
NOT_AN_ITEM = {"catalog_write": "not an item in the workspace: descriptions and tags written to the OneLake catalog; "
                                "no workspace role is proposed for it"}

# Adding people is the same for every item: Member is the least role that can (Admin can too, and more).
_MANAGE = ("Member", CONFIRMED, "fabric_roles", _P_ADD + ". (Members cannot change or remove an existing role; that "
           "needs Admin, per the Power BI page.)")

ENDPOINT = "https://api.fabric.microsoft.com/v1/workspaces/{workspaceId}/roleAssignments"
SCOPE = "Workspace.ReadWrite.All"
SCOPE_STATE = "not asked for today: the hosted app does not request it, so Krusgraph cannot send this call"
FILL_GROUP = "<object id of the Entra security group, filled in by a person>"
FILL_WORKSPACE = "<workspace id, filled in by a person>"
NOT_SENT = "Not sent. A person with Member or Admin in the workspace makes this assignment, in the portal or with their own tools."

# output -> (inherits, from what, status, Learn key, why)
LABELS: dict[str, tuple[str, str, str, str, str]] = {
    "semantic_model": ("no", "its source", CONFIRMED, "label_sources",
                       "inheritance from data sources covers Excel on OneDrive or SharePoint, Azure Synapse Analytics and "
                       "Azure SQL Database in Import mode; Krusgraph's model is Direct Lake on a lakehouse"),
    "report": ("yes", "the semantic model it is built on", CONFIRMED, "label_downstream",
               "a new report built on a labelled semantic model inherits the label upon creation; later changes flow "
               "down per the tenant's downstream setting, never over a manually applied label"),
}
_LABEL_UNSTATED = ("not stated", "", UNVERIFIED, "label_sources",
                   "neither Learn page says that this item takes a label from its source")
SET_BY = "set by a person with the right to apply the label, in the Fabric portal; Krusgraph never sets one"


def _groups(groups) -> dict[str, str]:
    if groups is None:
        return dict(GROUPS)
    if isinstance(groups, dict):
        out = {}
        for name, act in groups.items():
            if act not in ACTIVITIES:
                raise ValueError(f"group {name!r}: unknown activity {act!r}; known: {', '.join(ACTIVITIES)}")
            out[str(name)] = act
        return out
    out = {}
    for name in groups:
        key = str(name).strip().lower()
        if key not in GROUPS:
            raise ValueError(f"unknown placeholder group {name!r}; known: {', '.join(GROUPS)} "
                             "(or pass a dict of name -> build, read or manage)")
        out[key] = GROUPS[key]
    return out


def _cite(key: str) -> dict:
    page = LEARN[key]
    return {"learn": page["url"], "learn_title": page["title"], "page_date": page["page_date"], "read_on": READ_ON}


def _need(output: str, activity: str) -> tuple[str, str, str, str]:
    return _MANAGE if activity == "manage" else NEEDS[output][activity]


def propose(outputs, groups=None) -> dict:
    """{items: [{output, label, roles: [{group, activity, role, status, reason, learn...}]}], groups: [{group, activity,
    role, because: [outputs]}], not_items: [...], written: False}. Unknown outputs or groups raise ValueError."""
    keys = _check_outputs(outputs)
    gs = _groups(groups)
    items, not_items = [], []
    for o in keys:
        if o in NOT_AN_ITEM:
            not_items.append({"output": o, "label": OUTPUTS[o], "reason": NOT_AN_ITEM[o]})
            continue
        roles = []
        for g, act in gs.items():
            role, status, src, why = _need(o, act)
            roles.append({"group": g, "activity": act, "role": role, "status": status, "reason": why, **_cite(src)})
        items.append({"output": o, "label": OUTPUTS[o], "roles": roles})
    per_group = []
    for g, act in gs.items():
        needed = [(r["role"], it["label"]) for it in items for r in it["roles"] if r["group"] == g]
        if not needed:
            continue
        top = max(needed, key=lambda x: ROLES.index(x[0]))[0]
        per_group.append({"group": g, "activity": act, "role": top,
                          "because": [lab for role, lab in needed if role == top]})
    return {"items": items, "groups": per_group, "not_items": not_items, "written": False}


def request_bodies(proposal: dict) -> list[dict]:
    """One Add Workspace Role Assignment call per group, never sent: method, url, scope, body."""
    out = []
    for g in proposal["groups"]:
        out.append({"group": g["group"], "method": "POST", "url": ENDPOINT.replace("{workspaceId}", FILL_WORKSPACE),
                    "scope": SCOPE, "scope_state": SCOPE_STATE,
                    "body": {"principal": {"id": FILL_GROUP, "type": "Group"}, "role": g["role"]},
                    "sent": False, "note": NOT_SENT, **_cite("add_role")})
    return out


def labels(outputs) -> list[dict]:
    """Per item output: does it take a sensitivity label, from what, and who sets it (always a person)."""
    out = []
    for o in _check_outputs(outputs):
        if o in NOT_AN_ITEM:
            continue
        inherits, frm, status, src, why = LABELS.get(o, _LABEL_UNSTATED)
        out.append({"output": o, "label": OUTPUTS[o], "inherits": inherits, "from": frm, "status": status,
                    "reason": why, "set_by": SET_BY, "set_by_krusgraph": False, **_cite(src)})
    return out


def _summary(item: dict, label: dict) -> str:
    roles = ", ".join(f"{r['group']} {r['role']}" for r in item["roles"])
    lab = {"yes": f"label inherited from {label['from']}", "no": "label not inherited"}.get(label["inherits"],
                                                                                          "label inheritance not stated")
    unv = " (unverified)" if any(r["status"] == UNVERIFIED for r in item["roles"]) else ""
    return f"{item['label']}: {roles}{unv}; {lab}; a person sets it."


def dry_run_line(outputs, groups=None) -> str:
    """BL54 (B-25): the start flow's dry-run line, at most 25 words: the role proposed per group for the workspace, that
    labels are read and never set, and that nothing is written. Unknown outputs raise ValueError."""
    p = propose(outputs, groups)
    roles = ", ".join(f"{g['group']} {g['role']}" for g in p["groups"])
    keys = set(_check_outputs(outputs))
    inherit = " (the report inherits the model's)" if {"report", "semantic_model"} <= keys else ""
    head = f"Workspace roles proposed: {roles}. " if roles else "No workspace role proposed. "
    return f"{head}Labels read, never set{inherit}. Nothing is written."


def markdown(outputs, groups=None) -> str:
    """The dry run's text: one summary per item (at most 25 words), the role per group, the bodies, the labels."""
    p = propose(outputs, groups)
    labs = {x["output"]: x for x in labels(outputs)}
    lines = ["**Workspace roles and sensitivity labels: a proposal, dry run.** Nothing is written: no role is assigned "
             "and no label is set.", ""]
    for it in p["items"]:
        lines.append(f"- {_summary(it, labs[it['output']])}")
    for n in p["not_items"]:
        lines.append(f"- {n['label']}: {n['reason']}.")
    if p["groups"]:
        lines += ["", "One role per group for the whole workspace (the highest any item needs):", ""]
        for g in p["groups"]:
            lines.append(f"- **{g['group']}** ({g['activity']}): **{g['role']}**, for {', '.join(g['because'])}.")
        lines += ["", f"Request body per group, for a person to send (`POST {ENDPOINT}`, scope `{SCOPE}`, {SCOPE_STATE}):",
                  ""]
        for b in request_bodies(p):
            lines.append(f"- {b['group']}: `{{\"principal\": {{\"id\": \"{FILL_GROUP}\", \"type\": \"Group\"}}, "
                         f"\"role\": \"{b['body']['role']}\"}}`")
    if labs:
        lines += ["", "Sensitivity labels:", ""]
        for x in labs.values():
            lines.append(f"- {x['label']}: {x['inherits']}{' from ' + x['from'] if x['from'] else ''} "
                         f"({x['status']}): {x['reason']}. Label {x['set_by']}.")
    lines += ["", "Read on Microsoft Learn " + READ_ON + ": " +
              "; ".join(f"[{v['title']}]({v['url']}) ({v['page_date']})" for v in LEARN.values()) + "."]
    return "\n".join(lines)
