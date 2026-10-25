"""Create or update the GraphQLApi item, and hand back what an app builder needs to connect.

What this can do through the REST API:  create the item, update it in place by name, find the SQL
analytics endpoint behind a lakehouse, and compute the endpoint URL.

What it cannot do (portal only, as of Oct 2026 — see README "Two clicks remain"):
  - turn on *introspection* on the item (workspace admin, item Settings -> Introspection)
  - grant a service principal "Run Queries and Mutations" on the item
`connection_card()` prints both as a checklist next to the values that go into Lovable.
"""
from __future__ import annotations

import subprocess
import time

FABRIC = "https://api.fabric.microsoft.com"


def token_from_az() -> str:
    r = subprocess.run(["az", "account", "get-access-token", "--resource", FABRIC, "--query", "accessToken", "-o", "tsv"],
                       capture_output=True, text=True, check=True)
    return r.stdout.strip()


def token_from_fabric() -> str:
    import notebookutils  # type: ignore
    return notebookutils.credentials.getToken(FABRIC)


def default_token_provider():
    try:
        import notebookutils  # type: ignore  # noqa: F401
        return token_from_fabric
    except Exception:
        return token_from_az


def _headers(token_provider=None) -> dict:
    return {"Authorization": f"Bearer {(token_provider or default_token_provider())()}", "Content-Type": "application/json"}


def find_item(workspace: str, display_name: str, headers: dict, item_type: str = "GraphQLApi") -> str | None:
    import requests
    url = f"{FABRIC}/v1/workspaces/{workspace}/items?type={item_type}"
    while url:
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        body = r.json()
        for it in body.get("value", []):
            if it.get("displayName") == display_name:
                return it["id"]
        url = body.get("continuationUri")
    return None


SOURCE_ITEM_TYPES = ("Lakehouse", "Warehouse", "SQLDatabase", "MirroredDatabase", "MirroredAzureDatabricksCatalog")


def find_item_by_name(workspace: str, display_name: str, headers: dict,
                      types: tuple[str, ...] = SOURCE_ITEM_TYPES) -> dict | None:
    """Resolve a lakehouse/warehouse/SQL database/mirrored database given by name.

    A lakehouse's SQL analytics endpoint carries the SAME display name and is listed before the
    lakehouse, so the lookup is restricted to source item types (issue #1, bug A)."""
    import requests
    url = f"{FABRIC}/v1/workspaces/{workspace}/items"
    while url:
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        body = r.json()
        for it in body.get("value", []):
            if it.get("displayName") == display_name and it.get("type") in types:
                return it
        url = body.get("continuationUri")
    return None


def sql_endpoint_id_for_lakehouse(workspace_id: str, lakehouse_id: str, headers: dict) -> str:
    import requests
    r = requests.get(f"{FABRIC}/v1/workspaces/{workspace_id}/lakehouses/{lakehouse_id}", headers=headers, timeout=30)
    r.raise_for_status()
    props = r.json().get("properties", {}).get("sqlEndpointProperties", {})
    if not props.get("id"):
        raise RuntimeError("lakehouse has no SQL analytics endpoint yet (provisioningStatus=%s)" % props.get("provisioningStatus"))
    return props["id"]


def source_for(workspace_id: str, item: dict, headers: dict) -> tuple[str, str]:
    """(source_item_id, source_type) for a lakehouse / warehouse / SQL database item dict."""
    t = item["type"]
    if t == "SQLEndpoint":          # a source resolved to its SQL analytics endpoint: that id is the one the definition needs
        return item["id"], "SqlAnalyticsEndpoint"
    if t == "Lakehouse":
        return sql_endpoint_id_for_lakehouse(workspace_id, item["id"], headers), "SqlAnalyticsEndpoint"
    if t == "Warehouse":
        return item["id"], "Warehouse"
    if t == "SQLDatabase":
        return item["id"], "SqlDbNative"
    if t in ("MirroredDatabase", "MirroredAzureDatabricksCatalog"):
        # mirrored data (Snowflake, Azure SQL, Cosmos DB, SAP, a Databricks catalog, ...) is read through the item's
        # SQL analytics endpoint too; the endpoint id lives on the item
        import requests
        route = "mirroredDatabases" if t == "MirroredDatabase" else "mirroredAzureDatabricksCatalogs"
        r = requests.get(f"{FABRIC}/v1/workspaces/{workspace_id}/{route}/{item['id']}", headers=headers, timeout=30)
        r.raise_for_status()
        ep = r.json().get("properties", {}).get("sqlEndpointProperties", {}).get("id")
        if not ep:
            raise RuntimeError(f"{'mirrored database' if t == 'MirroredDatabase' else 'mirrored Databricks catalog'} has no SQL "
                               "analytics endpoint yet; pass its SQL analytics endpoint item as the source once it exists")
        return ep, "SqlAnalyticsEndpoint"
    raise ValueError(f"cannot expose item type {t} through GraphQL")


def deploy(env: dict, workspace: str, token_provider=None, poll_seconds: int = 3, max_polls: int = 60,
           update_existing: bool = True) -> dict:
    """POST /graphQLApis, or updateDefinition if an item with this name exists. Returns status + id + mode."""
    import requests
    headers = _headers(token_provider)
    body = {k: v for k, v in env.items() if k not in ("skipped_relationships", "type")}
    existing = find_item(workspace, env["displayName"], headers) if update_existing else None
    if existing:
        r = requests.post(f"{FABRIC}/v1/workspaces/{workspace}/items/{existing}/updateDefinition",
                          headers=headers, json={"definition": env["definition"]}, timeout=60)
        mode = "updated"
    else:
        r = requests.post(f"{FABRIC}/v1/workspaces/{workspace}/graphQLApis", headers=headers, json=body, timeout=60)
        mode = "created"
    if r.status_code not in (200, 201, 202):
        return {"status": "Failed", "mode": mode, "http": r.status_code, "body": r.text}
    item_id = existing or _id_from(r)
    op = r.headers.get("x-ms-operation-id")
    if op:
        for _ in range(max_polls):
            poll = requests.get(f"{FABRIC}/v1/operations/{op}", headers=headers, timeout=30)
            http = getattr(poll, "status_code", 200)
            if http in (401, 403, 404):                   # the sign-in or the access went away mid-operation: say so
                return {"status": "Failed", "mode": mode, "operation": op, "http": http, "body": getattr(poll, "text", "")}
            try:
                s = poll.json() if http < 400 else {}
            except ValueError:
                s = {}                                     # throttled or a transient server error: keep polling
            if s.get("status") in ("Succeeded", "Failed"):
                break
            time.sleep(poll_seconds)
        else:
            return {"status": "Timeout", "mode": mode, "operation": op}
        if s.get("status") == "Failed":
            s["mode"] = mode
            return s
        if not item_id:
            item_id = find_item(workspace, env["displayName"], headers)
    return {"status": "Succeeded", "mode": mode, "id": item_id}


def _id_from(r) -> str | None:
    """POST /graphQLApis answers 202 with body `null` (issue #1, bug B); the id comes from the item list after the LRO."""
    try:
        body = r.json()
    except ValueError:
        return None
    return body.get("id") if isinstance(body, dict) else None


def endpoint_url(workspace: str, item_id: str) -> str:
    return f"{FABRIC}/v1/workspaces/{workspace}/graphqlapis/{item_id}/graphql"


def connection_card(workspace: str, item_id: str, display_name: str = "") -> str:
    """What to paste into Lovable (or any client), plus the two portal clicks the API cannot do."""
    return "\n".join([
        f"GraphQL endpoint:  {endpoint_url(workspace, item_id)}",
        "Tenant ID / Client ID / Client secret: from your Entra app registration",
        "",
        "Still to do in the Fabric portal (no API for these yet):",
        f"  [ ] {display_name or 'the API'} -> Settings -> Introspection -> On   (workspace admin; Lovable needs this)",
        f"  [ ] {display_name or 'the API'} -> Manage permissions -> add the service principal with 'Run Queries and Mutations'",
        "  [ ] once per tenant: Admin portal -> 'Service principals can call Fabric public APIs' = enabled",
    ])
