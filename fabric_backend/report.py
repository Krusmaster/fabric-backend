"""An empty Power BI report bound to a semantic model, as a Fabric item (round n64).

`POST /v1/workspaces/{workspaceId}/reports` takes either a `definition` (PBIR parts) or a `creationPayload`, never
both. With `creationPayload.semanticModelReference` (`referenceType: "ById"`, `itemId`, `workspaceId`) Fabric creates
a report with one blank page and no visuals, already bound to that model, and no PBIR is sent. Delegated scope
`Report.ReadWrite.All` or `Item.ReadWrite.All`; Contributor on the workspace and read permission on the model. The
call answers 201 with the item, or 202 with `x-ms-operation-id` (a long-running operation). Microsoft Learn, Report -
Items - Create Report (learn.microsoft.com/rest/api/fabric/report/items/create-report), read 29 October 2026.

A definition with pages and visuals is for a later round; this module never updates or deletes a report.
"""
from __future__ import annotations

from .deploy import FABRIC, _headers, _id_from, find_item, wait_operation

SCOPE = "Report.ReadWrite.All or Item.ReadWrite.All"
SPEC = "Microsoft Learn, Report - Items - Create Report (creationPayload.semanticModelReference), read 29 October 2026"
ROUTE = "reports"
ITEM_TYPE = "Report"


def payload(name: str, model_id: str, model_workspace_id: str, description: str = "") -> dict:
    """The request body: displayName, an optional description, and the model reference. No `definition` key."""
    body = {"displayName": name,
            "creationPayload": {"semanticModelReference": {"referenceType": "ById", "itemId": model_id, "workspaceId": model_workspace_id}}}
    if description:
        body["description"] = description[:256]
    return body


def create(body: dict, workspace: str, token_provider=None, poll_seconds: int = 3, max_polls: int = 60) -> dict:
    """POST the report. Succeeded with the item's id, or Failed with the HTTP status and body for the error layer
    (server._finish_create). Creates only: the caller checks the name first, and nothing here updates or deletes."""
    import requests
    headers = _headers(token_provider)
    r = requests.post(f"{FABRIC}/v1/workspaces/{workspace}/{ROUTE}", headers=headers, json=body, timeout=60)
    if r.status_code not in (200, 201, 202):
        return {"status": "Failed", "mode": "created", "http": r.status_code, "body": r.text}
    item_id = _id_from(r)
    op = r.headers.get("x-ms-operation-id")
    if op:
        s = wait_operation(op, headers, poll_seconds, max_polls)
        if s.get("status") != "Succeeded":
            s["mode"] = "created"
            return s
        if not item_id:
            item_id = find_item(workspace, body["displayName"], headers, ITEM_TYPE)
    return {"status": "Succeeded", "mode": "created", "id": item_id}
