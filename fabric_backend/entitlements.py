"""Which organisation (Entra tenant id, `tid`) may use which paid feature. Dormant: off unless KRUSGRAPH_ENTITLEMENTS=1.

With the flag off (the default) nothing here runs and no tool changes its behaviour; tests lock that. With the flag
on, a call to a paid feature from an organisation without it answers in the usual error format with
`kind: upgrade` and a hint that links to the pricing page. Dry runs of the creating tools stay free: the dry run is
how someone sees what a paid feature would do.

Paid features (the split in docs/PRICING-NOTES.md: reading is free, creating and operating is paid):
  create         the creating tools with dry_run=false: create_semantic_model, create_views, create_data_agent,
                 create_ontology, create_silver_notebook (create_backend stays free: one API per workspace is the free
                 tier, and counting APIs needs the store PRICING-NOTES describes, which does not exist)
  lineage        lineage
  drift_monitor  drift_monitor_draft and create_drift_monitor, its dry run included (the dry run returns the same
                 notebook and pipeline as the draft, so a free dry run would give the paid feature away)

Where the entitlements come from (KRUSGRAPH_ENTITLEMENTS_SOURCE):
  env    KRUSGRAPH_ENTITLED_TENANTS = JSON {"<tid>": ["create", "lineage"], "<tid>": ["*"]}; for tests and a first
         customer or two
  table  Azure Table Storage: KRUSGRAPH_ENTITLEMENTS_TABLE = https://<account>.table.core.windows.net/<table>, one
         entity per organisation with PartitionKey "tenant", RowKey = the tenant id (lower case) and a string property
         `features` ("create,lineage" or "*"); read with the container app's managed identity (role "Storage Table
         Data Reader" on the table) and kept in memory for five minutes
A source that cannot be read answers as "not entitled" for that call and says so in the error, so a storage outage
never hands out paid features and never takes the free ones away.
"""
from __future__ import annotations

import json
import os
import threading
import time
from urllib.parse import quote, urlsplit

FEATURES = {
    "create": {"create_semantic_model", "create_views", "create_data_agent", "create_ontology", "create_silver_notebook"},
    "lineage": {"lineage"},
    "drift_monitor": {"drift_monitor_draft", "create_drift_monitor"},
}
ALWAYS_PAID = {"lineage", "drift_monitor_draft", "create_drift_monitor"}   # paid whatever dry_run says
TABLE_TTL = 300
STORAGE_RESOURCE = "https://storage.azure.com"


def enabled() -> bool:
    return os.environ.get("KRUSGRAPH_ENTITLEMENTS", "0").strip().lower() in {"1", "true", "yes", "on"}


def feature_of(tool: str, dry_run: bool | None) -> str | None:
    """The paid feature a call uses, or None when the call is free (every read-only tool, every dry run)."""
    for feature, tools in FEATURES.items():
        if tool in tools and (tool in ALWAYS_PAID or dry_run is False):
            return feature
    return None


def upgrade_url() -> str:
    """KRUSGRAPH_UPGRADE_URL, else /pricing on the operator's domain (a page that does not exist yet)."""
    explicit = os.environ.get("KRUSGRAPH_UPGRADE_URL", "").strip()
    if explicit:
        return explicit
    from .errors import site_origin
    return f"{site_origin()}/pricing"


class EnvSource:
    def features(self, tid: str) -> set[str]:
        raw = os.environ.get("KRUSGRAPH_ENTITLED_TENANTS", "").strip() or "{}"
        try:
            table = json.loads(raw)
        except ValueError as e:
            raise LookupError("KRUSGRAPH_ENTITLED_TENANTS is not valid JSON") from e
        if not isinstance(table, dict):
            raise LookupError("KRUSGRAPH_ENTITLED_TENANTS must be a JSON object of tenant id -> features")
        found = {str(k).lower(): v for k, v in table.items()}.get(tid.lower(), [])
        return {str(f).strip() for f in (found.split(",") if isinstance(found, str) else found) if str(f).strip()}


class TableSource:
    """One entity per organisation in Azure Table Storage, read with the managed identity (Microsoft Entra
    authorization for tables: x-ms-version 2019-02-02 or later, bearer token for https://storage.azure.com)."""

    def __init__(self, table_url: str, get=None, token=None, clock=time.time) -> None:
        parts = urlsplit(table_url.strip().rstrip("/"))
        segments = [s for s in parts.path.split("/") if s]
        if parts.scheme != "https" or not parts.hostname or len(segments) != 1:
            raise ValueError("KRUSGRAPH_ENTITLEMENTS_TABLE must look like https://<account>.table.core.windows.net/<table>")
        self.base = f"https://{parts.hostname}/{segments[0]}"
        self._get, self._token, self.clock = get, token, clock
        self._cache: dict[str, tuple[set[str], float]] = {}
        self._lock = threading.Lock()

    def _http_get(self, url: str, headers: dict, params: dict | None = None):
        if self._get is not None:
            return self._get(url, headers=headers, params=params)
        import requests
        return requests.get(url, headers=headers, params=params, timeout=10)

    def _bearer(self) -> str:
        if self._token is not None:
            return self._token()
        endpoint, header = os.environ.get("IDENTITY_ENDPOINT"), os.environ.get("IDENTITY_HEADER")
        if not endpoint or not header:
            raise LookupError("no managed identity on this container (IDENTITY_ENDPOINT is not set)")
        params = {"resource": STORAGE_RESOURCE, "api-version": "2019-08-01"}
        if os.environ.get("AZURE_CLIENT_ID"):
            params["client_id"] = os.environ["AZURE_CLIENT_ID"]
        r = self._http_get(endpoint, {"X-IDENTITY-HEADER": header}, params)
        if getattr(r, "status_code", 0) != 200 or not (r.json() or {}).get("access_token"):
            raise LookupError(f"the managed identity endpoint answered HTTP {getattr(r, 'status_code', '?')}")
        return r.json()["access_token"]

    def features(self, tid: str) -> set[str]:
        tid = tid.lower()
        with self._lock:
            hit = self._cache.get(tid)
            if hit and self.clock() - hit[1] < TABLE_TTL:
                return hit[0]
        url = f"{self.base}(PartitionKey='tenant',RowKey='{quote(tid.replace(chr(39), chr(39) * 2), safe='')}')"
        r = self._http_get(url, {"Authorization": f"Bearer {self._bearer()}", "x-ms-version": "2019-02-02",
                                 "Accept": "application/json;odata=nometadata"})
        status = getattr(r, "status_code", 0)
        if status == 404:
            found: set[str] = set()
        elif status == 200:
            raw = (r.json() or {}).get("features", "")
            found = {f.strip() for f in str(raw).split(",") if f.strip()}
        else:
            raise LookupError(f"the entitlements table answered HTTP {status}")
        with self._lock:
            self._cache[tid] = (found, self.clock())
        return found


_source = None
_source_lock = threading.Lock()


def source():
    global _source
    with _source_lock:
        kind = os.environ.get("KRUSGRAPH_ENTITLEMENTS_SOURCE", "env").strip().lower()
        if _source is None or getattr(_source, "_kind", None) != kind:
            _source = TableSource(os.environ.get("KRUSGRAPH_ENTITLEMENTS_TABLE", "")) if kind == "table" else EnvSource()
            _source._kind = kind
        return _source


def check(tool: str, dry_run: bool | None, tid: str | None) -> dict | None:
    """None when the call may run; the `kind: upgrade` answer otherwise. Never called while the flag is off."""
    feature = feature_of(tool, dry_run)
    if feature is None:
        return None
    note = ""
    if tid:
        try:
            have = source().features(tid)
        except Exception as e:  # noqa: BLE001 — an unreadable source denies the paid feature, never more
            have, note = set(), f" (the entitlement could not be read: {str(e)[:120]})"
        if "*" in have or feature in have:
            return None
    what = {"create": "Creating items in Fabric", "lineage": "Lineage across the workspace",
            "drift_monitor": "The nightly drift monitor"}[feature]
    return {"error": f"{what} is part of the paid plan, and your organisation does not have it on this server{note}.",
            "kind": "upgrade", "feature": feature,
            "hint": (f"See {upgrade_url()} for the plans. " + ("The dry run (dry_run=true) is free and shows exactly what would be created. "
                                                               if feature == "create" else "")
                     + "Planning, validation and the drafts stay free.")}
