"""Create or update the GraphQLApi item, and hand back what an app builder needs to connect.

What this can do through the REST API:  create the item, update it in place by name, find the SQL
analytics endpoint behind a lakehouse, and compute the endpoint URL.

What it cannot do (portal only, as of Oct 2026 — see README "Two clicks remain"):
  - turn on *introspection* on the item (workspace admin, item Settings -> Introspection)
  - grant a service principal "Run Queries and Mutations" on the item
`connection_card()` prints both as a checklist next to the values that go into Lovable.
"""
from __future__ import annotations

import email.utils
import math
import re
import subprocess
import time
from datetime import datetime, timezone

FABRIC = "https://api.fabric.microsoft.com"

# ------------------------------------------------------------------ long-running operations, throttling ---------------
# Behaviour as Microsoft documents it for the Fabric REST API (microsoft/mcp at commit
# 7257a94355dd63ba4f1ba43fc5ae5dfcd1a7203d, MIT: tools/Fabric.Mcp.Tools.Docs/src/Resources/long-running-operation.md and
# throttling.md), and the safety rules of its operation runner (tools/Fabric.Mcp.Tools.Core/src/Services/
# FabricOperationRunner.cs, FabricOperationHttp.cs), written again in Python; no code was copied. Copyright (c)
# Microsoft Corporation for the material read; see THIRD_PARTY_NOTICES.md.
#
#   - a create answers 200/201 (done) or 202 with x-ms-operation-id, Location and Retry-After;
#   - GET /v1/operations/{id} gives the state, GET /v1/operations/{id}/result the result once it has Succeeded;
#   - 429 (and 503) carry Retry-After, in seconds or as an HTTP date; the caller waits that long.
#
# The rules here: only 429 and 503 are sent again, because both mean Fabric did not take the request; a write is never
# sent again after anything that may mean it was carried out (2xx, another 5xx, a read timeout or a dropped
# connection). A 202 without an operation id is "unknown, do not send it again", and a wait that stops (time budget,
# polls spent, lost sign-in, interrupted) says that the operation may go on in Fabric.

RETRY_STATUSES = (429, 503)            # Fabric did not take the request: safe to send again, reads and writes alike
WRITE_ATTEMPTS = 3                     # a write, at most, counting the first
READ_ATTEMPTS = 4                      # a read, at most, counting the first
READ_FAILURES = 3                      # status reads in a row that may fail (network) before the wait stops
FALLBACK_RETRY_SECONDS = 5.0           # a 429/503 without Retry-After: 5, 10, 20 s (throttling.md's backoff)
MIN_POLL_SECONDS = 1.0

NO_OPERATION_ID = ("Fabric accepted the request (HTTP 202) but sent no operation id, so whether it was carried out is "
                   "unknown. It was not sent again; do not send it again before checking the item in Fabric.")
MAY_HAVE_ARRIVED = ("Fabric did not answer the request in time, so it may have been carried out. It was not sent again; "
                    "check the item in Fabric before sending it again.")
WAIT_STOPPED = ("The wait stopped, not the operation: Fabric may still finish it. Check operation {op} or the item in "
                "Fabric before sending the request again.")


def retry_after_seconds(value, now: datetime | None = None) -> float | None:
    """Seconds to wait from a Retry-After value: delta-seconds ("30") or an HTTP date ("Wed, 21 Oct 2026 07:28:00 GMT",
    counted from `now`, never below 0). None when it is missing or unreadable."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        seconds = float(text)
    except ValueError:
        seconds = None
    if seconds is not None:
        return seconds if math.isfinite(seconds) and seconds >= 0 else None
    try:
        when = email.utils.parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        return None
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return max(0.0, (when - (now or datetime.now(timezone.utc))).total_seconds())


def _header(r, name: str):
    headers = getattr(r, "headers", None) or {}
    value = headers.get(name)
    if value is None and isinstance(headers, dict):          # a plain dict is case-sensitive; HTTP headers are not
        value = next((v for k, v in headers.items() if str(k).lower() == name.lower()), None)
    return value


def _retry_after(r) -> float | None:
    return retry_after_seconds(_header(r, "Retry-After"))


_OPERATION_URL = re.compile(r"/operations/([^/?#]+)/?(?:[?#].*)?$")


def operation_id(r) -> str | None:
    """The operation of a 202: x-ms-operation-id, or the id at the end of a Location .../operations/{id}."""
    op = str(_header(r, "x-ms-operation-id") or "").strip()
    if op:
        return op
    m = _OPERATION_URL.search(str(_header(r, "Location") or ""))
    return m.group(1) if m else None


class Budget:
    """A time budget for one call (its write, the operation's polls and the result), on the monotonic clock."""

    def __init__(self, seconds: float):
        self.seconds, self.start = float(seconds), time.monotonic()

    def remaining(self) -> float:
        return self.seconds - (time.monotonic() - self.start)

    def pause(self, seconds: float) -> bool:
        """Sleep `seconds`, never past the budget. False when the budget is spent (then nothing more is sent)."""
        left = self.remaining()
        if left <= 0:
            return False
        if seconds > 0:
            time.sleep(min(seconds, left))
        return self.remaining() > 0


def send(method: str, url: str, headers: dict, *, write: bool, budget: Budget | None = None, **kw):
    """One Fabric request, sent again only after 429 or 503 (Fabric did not take it), after Retry-After or a short
    backoff, within the budget. Every other answer, and every exception, goes back to the caller as it is: a write
    that may have been carried out is never sent twice. When the wait Fabric asks for does not fit in the budget, the
    429/503 itself is the answer."""
    import requests
    budget = budget or Budget(60)
    attempts = WRITE_ATTEMPTS if write else READ_ATTEMPTS
    for attempt in range(attempts):
        r = getattr(requests, method)(url, headers=headers, **kw)
        if getattr(r, "status_code", 200) not in RETRY_STATUSES or attempt == attempts - 1:
            return r
        delay = _retry_after(r)
        delay = FALLBACK_RETRY_SECONDS * 2 ** attempt if delay is None else delay
        if delay >= budget.remaining() or not budget.pause(delay):
            return r
    return r


class WaitInterrupted(KeyboardInterrupt):
    """The wait for an operation was interrupted (Ctrl-C); the operation itself goes on in Fabric."""


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
    url = f"{FABRIC}/v1/workspaces/{workspace}/items?type={item_type}"
    while url:
        r = send("get", url, headers, write=False, timeout=30)
        r.raise_for_status()
        body = r.json()
        for it in body.get("value", []):
            if it.get("displayName") == display_name:
                return it["id"]
        url = body.get("continuationUri")
    return None


# Item types that carry tables behind a SQL analytics endpoint or a SQL connection string (Fabric REST item types).
SOURCE_ITEM_TYPES = ("Lakehouse", "Warehouse", "SQLDatabase", "MirroredDatabase", "MirroredAzureDatabricksCatalog",
                     "SnowflakeDatabase", "MirroredCatalog")
# Item types whose data is read through their SQL analytics endpoint (properties.sqlEndpointProperties) → REST route.
ENDPOINT_ITEM_ROUTES = {"MirroredDatabase": "mirroredDatabases", "MirroredAzureDatabricksCatalog": "mirroredAzureDatabricksCatalogs",
                        "SnowflakeDatabase": "snowflakeDatabases", "MirroredCatalog": "mirroredCatalogs"}


def find_item_by_name(workspace: str, display_name: str, headers: dict,
                      types: tuple[str, ...] = SOURCE_ITEM_TYPES) -> dict | None:
    """Resolve a lakehouse/warehouse/SQL database/mirrored database given by name.

    A lakehouse's SQL analytics endpoint carries the SAME display name and is listed before the
    lakehouse, so the lookup is restricted to source item types (issue #1, bug A)."""
    url = f"{FABRIC}/v1/workspaces/{workspace}/items"
    while url:
        r = send("get", url, headers, write=False, timeout=30)
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


def _kind_words(t: str) -> str:
    return {"MirroredDatabase": "mirrored database", "MirroredAzureDatabricksCatalog": "mirrored Databricks catalog",
            "SnowflakeDatabase": "Snowflake database", "MirroredCatalog": "mirrored catalog"}.get(t, t)


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
    if t in ENDPOINT_ITEM_ROUTES:
        # mirrored or external data (Snowflake, Azure SQL, Cosmos DB, SAP, a Databricks catalog, a mirrored catalog, ...) is
        # read through the item's SQL analytics endpoint too; the endpoint id lives on the item
        import requests
        r = requests.get(f"{FABRIC}/v1/workspaces/{workspace_id}/{ENDPOINT_ITEM_ROUTES[t]}/{item['id']}", headers=headers, timeout=30)
        r.raise_for_status()
        ep = r.json().get("properties", {}).get("sqlEndpointProperties", {}).get("id")
        if not ep:
            raise RuntimeError(f"{_kind_words(t)} has no SQL analytics endpoint yet; pass its SQL analytics endpoint item as the source once it exists")
        return ep, "SqlAnalyticsEndpoint"
    raise ValueError(f"cannot expose item type {t} through GraphQL")


def _budget_seconds(poll_seconds: float, max_polls: int, max_wait_seconds: float | None) -> float:
    """The default budget is what the polls alone used to take (3 s x 60 = 3 minutes)."""
    return float(max_wait_seconds) if max_wait_seconds is not None else float(poll_seconds) * max_polls


def write_and_wait(url: str, body: dict, headers: dict, *, mode: str, item_id: str | None = None, find=None,
                   item_type: str = "", poll_seconds: float = 3, max_polls: int = 60, max_wait_seconds: float | None = None) -> dict:
    """POST a create or updateDefinition and see it through: Succeeded with the item's id, Failed with Fabric's HTTP
    status and body (the error layer reads both), or Timeout with a `note` when the outcome is not known (a 202
    without an operation id, a request that timed out, a wait that stopped). The id of a created item comes from the
    answer, else from GET /operations/{id}/result, else from `find()` (the item list by name). The definition's parts
    are checked first (limits.check_definition), and a wrong one raises DefinitionError with nothing sent."""
    import requests
    from .limits import check_definition
    if isinstance(body.get("definition"), dict):
        check_definition(body["definition"], item_type)
    budget = Budget(_budget_seconds(poll_seconds, max_polls, max_wait_seconds))
    try:
        r = send("post", url, headers, write=True, budget=budget, json=body, timeout=60)
    except requests.exceptions.ReadTimeout:                # sent, and maybe carried out: never sent again
        return {"status": "Timeout", "mode": mode, "note": MAY_HAVE_ARRIVED}
    if r.status_code not in (200, 201, 202):
        return {"status": "Failed", "mode": mode, "http": r.status_code, "body": r.text}
    item_id = item_id or _id_from(r)
    op = operation_id(r)
    if r.status_code == 202 and not op:
        return {"status": "Timeout", "mode": mode, "note": NO_OPERATION_ID}
    if op:
        s = _wait(op, headers, poll_seconds, max_polls, budget, _retry_after(r))
        if s.get("status") != "Succeeded":
            s["mode"] = mode
            return s
        if not item_id:
            result = operation_result(op, headers, budget)
            item_id = result.get("id") if isinstance(result, dict) and isinstance(result.get("id"), str) else None
    if not item_id and find:
        item_id = find()
    return {"status": "Succeeded", "mode": mode, "id": item_id}


def deploy(env: dict, workspace: str, token_provider=None, poll_seconds: int = 3, max_polls: int = 60,
           update_existing: bool = True, max_wait_seconds: float | None = None) -> dict:
    """POST /graphQLApis, or updateDefinition if an item with this name exists. Returns status + id + mode."""
    headers = _headers(token_provider)
    body = {k: v for k, v in env.items() if k not in ("skipped_relationships", "type")}
    existing = find_item(workspace, env["displayName"], headers) if update_existing else None
    if existing:
        url, body, mode = f"{FABRIC}/v1/workspaces/{workspace}/items/{existing}/updateDefinition", {"definition": env["definition"]}, "updated"
    else:
        url, mode = f"{FABRIC}/v1/workspaces/{workspace}/graphQLApis", "created"
    return write_and_wait(url, body, headers, mode=mode, item_id=existing, find=lambda: find_item(workspace, env["displayName"], headers), item_type="GraphQLApi",
                          poll_seconds=poll_seconds, max_polls=max_polls, max_wait_seconds=max_wait_seconds)


def wait_operation(op: str, headers: dict, poll_seconds: int = 3, max_polls: int = 60,
                   max_wait_seconds: float | None = None, retry_after: float | None = None) -> dict:
    """Poll a Fabric long-running operation. Succeeded/Failed as Fabric reports them. Timeout, with a `note` that the
    operation may go on in Fabric, when the polls or the time budget are spent or the status could not be read; a lost
    sign-in or access (401/403/404) ends the wait at once as Failed with the HTTP status and body (and the same note).
    Waits Retry-After between polls when Fabric sends it (`retry_after`: the first wait, from the 202), else
    poll_seconds; 429 and 503 while polling are waited out the same way."""
    return _wait(op, headers, poll_seconds, max_polls, Budget(_budget_seconds(poll_seconds, max_polls, max_wait_seconds)), retry_after)


def _wait(op: str, headers: dict, poll_seconds: float, max_polls: int, budget: Budget, first_delay: float | None) -> dict:
    import requests
    stopped = {"status": "Timeout", "operation": op, "note": WAIT_STOPPED.format(op=op)}
    delay, failures = first_delay, 0
    try:
        for _ in range(max_polls):
            if delay is not None and not budget.pause(max(delay, MIN_POLL_SECONDS)):   # at least 1 s between polls
                return stopped
            if budget.remaining() <= 0:
                return stopped
            try:
                poll = requests.get(f"{FABRIC}/v1/operations/{op}", headers=headers, timeout=30)
            except requests.exceptions.RequestException:   # reading is always safe to repeat; a few in a row end the wait
                failures += 1
                if failures >= READ_FAILURES:
                    return stopped
                delay = poll_seconds
                continue
            failures = 0
            http = getattr(poll, "status_code", 200)
            if http in (401, 403, 404):
                return {"status": "Failed", "operation": op, "http": http, "body": getattr(poll, "text", ""),
                        "note": WAIT_STOPPED.format(op=op)}
            try:
                s = poll.json() if http < 400 else {}
            except ValueError:
                s = {}                                     # throttled or a transient server error: keep polling
            if isinstance(s, dict) and s.get("status") in ("Succeeded", "Failed"):
                s.setdefault("operation", op)
                return s
            ra = _retry_after(poll)                        # NotStarted, Running, Undefined, or a status not known yet
            delay = poll_seconds if ra is None else ra
    except KeyboardInterrupt:
        raise WaitInterrupted(WAIT_STOPPED.format(op=op)) from None
    return stopped


def operation_result(op: str, headers: dict, budget: Budget | None = None):
    """GET /operations/{id}/result once the operation has Succeeded: the JSON, or None when there is no result (some
    operations have none), it could not be read, or the budget is spent. A read, so 429/503 are waited out."""
    budget = budget or Budget(60)
    if budget.remaining() <= 0:
        return None
    try:                                   # best effort: the operation has Succeeded, so nothing here may undo that
        r = send("get", f"{FABRIC}/v1/operations/{op}/result", headers, write=False, budget=budget, timeout=60)
        return r.json() if getattr(r, "status_code", 200) < 400 else None
    except Exception:                      # noqa: BLE001 — network, JSON, an answer of an unexpected shape
        return None


def create_ontology(envelope: dict, workspace: str, token_provider=None, poll_seconds: int = 3, max_polls: int = 60,
                    update_existing: bool = True, max_wait_seconds: float | None = None) -> dict:
    """POST /ontologies with a definition, or updateDefinition when an ontology of that name exists. Needs the delegated
    scope Item.ReadWrite.All and Contributor on the workspace (the ontology item is in preview)."""
    return create_item_with_definition("ontologies", "Ontology", envelope, workspace, token_provider, poll_seconds, max_polls,
                                       update_existing, max_wait_seconds)


def create_item_with_definition(route: str, item_type: str, envelope: dict, workspace: str, token_provider=None,
                                poll_seconds: int = 3, max_polls: int = 60, update_existing: bool = True,
                                max_wait_seconds: float | None = None) -> dict:
    """POST /workspaces/{ws}/{route} with a definition, or POST .../{route}/{id}/updateDefinition when an item of that
    name and type exists (the pattern of create_backend and create_ontology; fabric-rest-api-specs <item>/swagger.json).
    Never deletes. Returns status + id + mode, or Failed with the HTTP status and body for the error layer."""
    headers = _headers(token_provider)
    existing = find_item(workspace, envelope["displayName"], headers, item_type) if update_existing else None
    if existing:
        url, body, mode = f"{FABRIC}/v1/workspaces/{workspace}/{route}/{existing}/updateDefinition", {"definition": envelope["definition"]}, "updated"
    else:
        url, body, mode = f"{FABRIC}/v1/workspaces/{workspace}/{route}", envelope, "created"
    return write_and_wait(url, body, headers, mode=mode, item_id=existing,
                          find=lambda: find_item(workspace, envelope["displayName"], headers, item_type), item_type=item_type,
                          poll_seconds=poll_seconds, max_polls=max_polls, max_wait_seconds=max_wait_seconds)


def create_semantic_model(envelope: dict, workspace: str, token_provider=None, poll_seconds: int = 3, max_polls: int = 60,
                          update_existing: bool = True) -> dict:
    """POST /semanticModels (Items_CreateSemanticModel) or updateDefinition (Items_UpdateSemanticModelDefinition);
    delegated scope SemanticModel.ReadWrite.All or Item.ReadWrite.All, Contributor on the workspace."""
    return create_item_with_definition("semanticModels", "SemanticModel", envelope, workspace, token_provider, poll_seconds, max_polls, update_existing)


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
