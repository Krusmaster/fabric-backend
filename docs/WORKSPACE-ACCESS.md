<!-- 2026-11-21, round BL35 (sprint item BL35, backlog B-25). -->

# Workspace roles and sensitivity labels: a proposal, dry run only

After "who sees which rows" (`security_roles.py`, BL17) a Fabric administrator asks
two more questions before a pilot: which workspace role does each group need, and does a sensitivity label carry over
to what Krusgraph builds. `fabric_backend/workspace_access.py` answers both with a proposal. **Nothing is written**: no
role is assigned, no label is set, nothing is sent to Fabric, Entra or Purview.

## Roles

`workspace_access.propose(outputs, groups=None)` gives, per built item, the least role each group needs, with the
reason and the Learn row it rests on. Groups are placeholders; each stands for what its people do.

| Item | data engineers (build) | report readers (read) | access managers (add people) |
| --- | --- | --- | --- |
| Lakehouse | Contributor | Viewer (SQL analytics endpoint; OneLake or Spark reads need Contributor) | Member |
| Notebook | Contributor | Viewer | Member |
| Pipeline | Contributor | Viewer | Member |
| Semantic model | Contributor | Viewer (the role that enforces BL17's row-level security) | Member |
| Report | Contributor | Viewer | Member |
| Ontology, Data agent, API for GraphQL | Contributor, unverified | Viewer, unverified | Member |
| OneLake catalog write | not an item; no role | | |

A workspace role covers the whole workspace, so each group gets the highest role any of its items needs. Admin is
never proposed: only Admin updates or deletes the workspace, connects Git or creates a workspace identity, and nothing
Krusgraph builds needs that. A Member can add people with lower roles but cannot change or remove an existing role.

## The request bodies, never sent

`workspace_access.request_bodies(proposal)` writes Fabric's "Add Workspace Role Assignment" call per group:

```
POST https://api.fabric.microsoft.com/v1/workspaces/{workspaceId}/roleAssignments
{"principal": {"id": "<object id of the Entra security group, filled in by a person>", "type": "Group"}, "role": "Contributor"}
```

The group's object id and the workspace id are left for a person: Krusgraph invents no group or user id. The call
needs the delegated scope `Workspace.ReadWrite.All`, which is **not asked for today** (the hosted app lists it under
"not requested" in `access.py`), and a caller with Member or higher in the workspace.

## Sensitivity labels

`workspace_access.labels(outputs)`, per Learn:

- **Semantic model: not inherited from its source.** Inheritance from data sources covers Excel on OneDrive or
  SharePoint, Azure Synapse Analytics and Azure SQL Database in Import mode; Krusgraph's model is Direct Lake on a
  lakehouse.
- **Report: inherited from the semantic model it is built on**, upon creation. Later label changes flow down per the
  tenant's downstream setting and never overwrite a manually applied label.
- **Lakehouse, notebook, pipeline, ontology, data agent, API for GraphQL: not stated** on either page; unverified.

For every item the label is set by a person with the right to apply it, in the Fabric portal. Krusgraph never sets
one; `privacy.label_of` only reads the label id an item already has.

## The dry-run text

`workspace_access.markdown(outputs, groups=None)` writes one summary line per item (at most 25 words), the role per
group, the bodies and the labels, and says that nothing is written.

## What wiring into the dry run needs (after the chain)

Not done in this round; it touches the chain's files, which SM7 holds tonight:

1. `start_flow.py`'s closing step (or the dry run of `create_semantic_model` in `server.py`) calls
   `workspace_access.markdown(outputs)` with the outputs the plan will build, next to `tenant_settings.markdown`.
2. The check card in `mcp_apps*.py` shows it as a collapsed "Who needs which role" section; the click-through
   `tests/test_wb15_click_through.py` is kept green.
3. A way to name the customer's own groups (a `groups` parameter) only after the tool texts are agreed.
4. Assigning roles stays out: it needs `Workspace.ReadWrite.All` and Gustav's yes.

## Read on Microsoft Learn, 21 November 2026

- [Roles in workspaces in Microsoft Fabric](https://learn.microsoft.com/en-us/fabric/fundamentals/roles-workspaces) (2026-04-24)
- [Roles in workspaces in Power BI](https://learn.microsoft.com/en-us/power-bi/collaborate-share/service-roles-new-workspaces) (2025-12-01)
- [Workspaces - Add Workspace Role Assignment](https://learn.microsoft.com/en-us/rest/api/fabric/core/workspaces/add-workspace-role-assignment) (updated 2026-11-10)
- [Sensitivity label inheritance from data sources in Power BI](https://learn.microsoft.com/en-us/fabric/governance/service-security-sensitivity-label-inheritance-from-data-sources) (2026-07-13)
- [Sensitivity label downstream inheritance in Power BI](https://learn.microsoft.com/en-us/fabric/governance/service-security-sensitivity-label-downstream-inheritance) (2026-07-13)
