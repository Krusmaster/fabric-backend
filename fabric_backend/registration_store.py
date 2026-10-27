"""Where the client registration layer (registration.py) keeps its few records: in memory, or in Azure Table Storage.

Five kinds of record, all small, all with an expiry except consent:
  txn       a sign-in on its way through Entra: the client's request and the PKCE verifier for Entra; 10 minutes,
            taken (read and deleted in one step) when Entra sends the browser back, so a state works once
  code      an authorization code this server gave a client: the Entra tokens, encrypted; 60 seconds, taken when the
            client redeems it, so a code works once
  used      that a code was redeemed, so a second attempt revokes what the first one got; 10 minutes
  family    a refresh token's line: the hash of the current refresh token and the Entra refresh token, encrypted;
            replaced at every refresh (rotation), deleted when an old one comes back or Entra refuses
  consent   that a user (a keyed hash of tenant and object id, never the ids) approved a client for one redirect
            address; 180 days, or until the operator deletes it or the server's key changes
Nothing else: no names, no e-mail, no IP addresses, no tokens in clear.

MemoryStore is for tests and a single replica (the records are lost at a restart, which only means signing in again).
TableStore is for the hosted service, which runs up to two replicas: every replica sees the same records, and "taken
once" holds across them because a take is a read followed by a delete that names the entity's ETag (If-Match), which
Table Storage lets succeed only once.

Table Storage with the container app's managed identity (role "Storage Table Data Contributor" on the table), REST
only, no Azure SDK: Microsoft Entra authorization for tables, x-ms-version 2019-02-02 with x-ms-date and the OData 3.0
headers, bearer token for https://storage.azure.com. One entity per record: PartitionKey = the kind, RowKey = the
record's key (base64url or hex, so no character Table Storage forbids), `data` = the record as JSON, `exp` = its expiry
(Unix seconds, 0 = none) as an Edm.Int64, which the Table service's JSON format writes as a string ("1761580800")
and its filters as a number with an L suffix (exp lt 1761580800L).
"""
from __future__ import annotations

import json
import os
import threading
import time
from urllib.parse import quote, urlsplit

KINDS = ("txn", "code", "used", "family", "consent")
STORAGE_RESOURCE = "https://storage.azure.com"
PURGE_EVERY = 600                     # seconds between two sweeps for expired records, per replica
PURGE_BATCH = 200                     # at most this many deletions per sweep and kind
MEMORY_SWEEP_AT = 10000               # MemoryStore drops expired records once it holds more than this


class StoreError(RuntimeError):
    """The store could not be read or written (no identity, no access, network). The sign-in fails; nothing is granted."""


def _check(kind: str, key: str) -> None:
    if kind not in KINDS:
        raise ValueError(f"unknown record kind {kind!r}")
    if not key or len(key) > 512 or any(c in key for c in "/\\#?'\t\n\r") or not key.isascii():
        raise ValueError("record keys are short base64url or hex strings")


class MemoryStore:
    """A dict behind a lock. take() and replace() are atomic within the process."""

    def __init__(self, clock=time.time) -> None:
        self.clock = clock
        self._rows: dict[tuple[str, str], tuple[dict, float, int]] = {}      # (kind, key) -> (data, exp, version)
        self._lock = threading.Lock()
        self._version = 0
        self._swept = clock()

    def _sweep(self) -> None:
        """Drop expired records (sign-ins nobody finished) once the store is large, at most every 30 seconds. Called
        with the lock held."""
        now = self.clock()
        if len(self._rows) > MEMORY_SWEEP_AT and now - self._swept >= 30:
            self._swept = now
            for k in [k for k, row in self._rows.items() if row[1] and row[1] <= now]:
                del self._rows[k]

    def _live(self, kind: str, key: str):
        row = self._rows.get((kind, key))
        if row and row[1] and row[1] <= self.clock():
            del self._rows[(kind, key)]
            return None
        return row

    def put(self, kind: str, key: str, data: dict, ttl: int | None = None) -> None:
        _check(kind, key)
        with self._lock:
            self._sweep()
            self._version += 1
            self._rows[(kind, key)] = (json.loads(json.dumps(data)), self.clock() + ttl if ttl else 0.0, self._version)

    def add(self, kind: str, key: str, data: dict, ttl: int | None = None) -> bool:
        """Write the record only if there is no live one; False when there is (the check and the write are one step)."""
        _check(kind, key)
        with self._lock:
            self._sweep()
            if self._live(kind, key):
                return False
            self._version += 1
            self._rows[(kind, key)] = (json.loads(json.dumps(data)), self.clock() + ttl if ttl else 0.0, self._version)
            return True

    def get(self, kind: str, key: str) -> tuple[dict, str] | None:
        """(data, etag) or None when there is no live record."""
        _check(kind, key)
        with self._lock:
            row = self._live(kind, key)
            return (json.loads(json.dumps(row[0])), str(row[2])) if row else None

    def take(self, kind: str, key: str) -> dict | None:
        """The record, deleted in the same step; None when it is missing, expired or already taken."""
        _check(kind, key)
        with self._lock:
            row = self._live(kind, key)
            if not row:
                return None
            del self._rows[(kind, key)]
            return row[0]

    def replace(self, kind: str, key: str, data: dict, etag: str, ttl: int | None = None) -> bool:
        """Replace the record only if it is still the version `etag` names; False when someone changed or deleted it."""
        _check(kind, key)
        with self._lock:
            row = self._live(kind, key)
            if not row or str(row[2]) != etag:
                return False
            self._version += 1
            self._rows[(kind, key)] = (json.loads(json.dumps(data)), self.clock() + ttl if ttl else 0.0, self._version)
            return True

    def delete(self, kind: str, key: str) -> None:
        _check(kind, key)
        with self._lock:
            self._rows.pop((kind, key), None)

    def count(self, kind: str) -> int:
        with self._lock:
            return sum(1 for (k, key) in list(self._rows) if k == kind and self._live(k, key))


class TableStore:
    """The same five operations on one Azure table. Errors other than "not there" / "changed" raise StoreError."""

    def __init__(self, table_url: str, http=None, token=None, clock=time.time) -> None:
        parts = urlsplit((table_url or "").strip().rstrip("/"))
        segments = [s for s in parts.path.split("/") if s]
        if (parts.scheme != "https" or not (parts.hostname or "").endswith(".table.core.windows.net") or len(segments) != 1
                or not segments[0].isalnum() or parts.query or parts.fragment):
            raise ValueError("KRUSGRAPH_REGISTRATION_STORE must be `memory` or https://<account>.table.core.windows.net/<table>")
        self.base = f"https://{parts.hostname}/{segments[0]}"
        self._http, self._token, self.clock = http, token, clock
        self._bearer_cache: tuple[str, float] = ("", 0.0)
        self._lock = threading.Lock()
        self._purged = clock()

    # -- plumbing ---------------------------------------------------------------------------------------------
    def _request(self, method: str, url: str, headers: dict, body: bytes | None = None, params: dict | None = None):
        if self._http is not None:
            return self._http(method, url, headers=headers, data=body, params=params)
        import requests
        try:
            return requests.request(method, url, headers=headers, data=body, params=params, timeout=10)
        except requests.RequestException as e:
            raise StoreError(f"the registration table could not be reached: {type(e).__name__}") from e

    def _bearer(self) -> str:
        if self._token is not None:
            return self._token()
        with self._lock:
            tok, exp = self._bearer_cache
            if tok and exp - 300 > self.clock():
                return tok
        endpoint, header = os.environ.get("IDENTITY_ENDPOINT"), os.environ.get("IDENTITY_HEADER")
        if not endpoint or not header:
            raise StoreError("no managed identity on this container (IDENTITY_ENDPOINT is not set)")
        params = {"resource": STORAGE_RESOURCE, "api-version": "2019-08-01"}
        if os.environ.get("AZURE_CLIENT_ID"):
            params["client_id"] = os.environ["AZURE_CLIENT_ID"]
        r = self._request("GET", endpoint, {"X-IDENTITY-HEADER": header}, params=params)
        body = r.json() if getattr(r, "status_code", 0) == 200 else {}
        if not (body or {}).get("access_token"):
            raise StoreError(f"the managed identity endpoint answered HTTP {getattr(r, 'status_code', '?')}"
                             " (is AZURE_CLIENT_ID the client id of the app's identity?)")
        try:
            exp = float(body.get("expires_on") or 0) or self.clock() + 3000
        except (TypeError, ValueError):
            exp = self.clock() + 3000
        with self._lock:
            self._bearer_cache = (body["access_token"], exp)
        return body["access_token"]

    def _headers(self, **extra) -> dict:
        from email.utils import formatdate
        return {"Authorization": f"Bearer {self._bearer()}", "x-ms-version": "2019-02-02",
                "x-ms-date": formatdate(self.clock(), usegmt=True), "DataServiceVersion": "3.0;NetFx",
                "MaxDataServiceVersion": "3.0;NetFx", "Accept": "application/json;odata=nometadata", **extra}

    def _url(self, kind: str, key: str) -> str:
        return f"{self.base}(PartitionKey='{kind}',RowKey='{quote(key, safe='')}')"

    def _parse(self, r) -> tuple[dict, str, float] | None:
        entity = r.json() or {}
        try:
            data = json.loads(entity.get("data") or "{}")
            exp = float(entity.get("exp") or 0)
        except (TypeError, ValueError):
            return None
        etag = r.headers.get("ETag") or entity.get("odata.etag") or ""
        return data, etag, exp

    def _body(self, kind: str, key: str, data: dict, ttl: int | None) -> bytes:
        exp = int(self.clock() + ttl) if ttl else 0
        return json.dumps({"PartitionKey": kind, "RowKey": key, "data": json.dumps(data, separators=(",", ":")),
                           "exp": str(exp), "exp@odata.type": "Edm.Int64"}).encode()       # Int64 travels as a string

    def _fail(self, what: str, r) -> StoreError:
        """The status and the Table service's own error code (AuthorizationPermissionMismatch, TableNotFound,
        InvalidInput, ...), so the console line says which setting is wrong. Never the request or a token."""
        code = ""
        try:
            error = (r.json() or {}).get("odata.error") or {}
            code = str(error.get("code") or "")
            message = error.get("message")
            text = message.get("value") if isinstance(message, dict) else message
            if text:
                code += ": " + str(text).splitlines()[0][:120]
        except Exception:  # noqa: BLE001 — an error body that is not JSON: the status is still there
            code = ""
        code = code or str((getattr(r, "headers", {}) or {}).get("x-ms-error-code") or "")
        return StoreError(f"the registration table answered HTTP {getattr(r, 'status_code', '?')} to {what}"
                          + (f" ({code})" if code else ""))

    # -- the five operations ---------------------------------------------------------------------------------
    def put(self, kind: str, key: str, data: dict, ttl: int | None = None) -> None:
        _check(kind, key)
        self._maybe_purge()
        r = self._request("PUT", self._url(kind, key), self._headers(**{"Content-Type": "application/json"}),
                          self._body(kind, key, data, ttl))                   # Insert Or Replace Entity
        if r.status_code not in (200, 201, 204):
            raise self._fail("a write", r)

    def add(self, kind: str, key: str, data: dict, ttl: int | None = None) -> bool:
        _check(kind, key)
        r = self._request("POST", self.base, self._headers(**{"Content-Type": "application/json", "Prefer": "return-no-content"}),
                          self._body(kind, key, data, ttl))                   # Insert Entity: 409 when it exists
        if r.status_code == 409:
            raw = self._raw(kind, key)                      # an expired leftover does not count: replace that version once
            if raw is None or not raw[2] or raw[2] > self.clock() or not raw[1]:
                return False
            return self.replace(kind, key, data, raw[1], ttl)
        if r.status_code not in (201, 204):
            raise self._fail("an insert", r)
        return True

    def _raw(self, kind: str, key: str) -> tuple[dict, str, float] | None:
        r = self._request("GET", self._url(kind, key), self._headers())
        if r.status_code == 404:
            return None
        if r.status_code != 200:
            raise self._fail("a read", r)
        return self._parse(r)

    def get(self, kind: str, key: str) -> tuple[dict, str] | None:
        _check(kind, key)
        parsed = self._raw(kind, key)
        if not parsed or (parsed[2] and parsed[2] <= self.clock()):
            return None
        return parsed[0], parsed[1]

    def take(self, kind: str, key: str) -> dict | None:
        _check(kind, key)
        parsed = self._raw(kind, key)
        if not parsed or not parsed[1]:
            return None
        d = self._request("DELETE", self._url(kind, key), self._headers(**{"If-Match": parsed[1]}))
        if d.status_code in (404, 412):                     # another request took it first
            return None
        if d.status_code != 204:
            raise self._fail("a delete", d)
        if parsed[2] and parsed[2] <= self.clock():          # expired: deleted, but not handed out
            return None
        return parsed[0]

    def replace(self, kind: str, key: str, data: dict, etag: str, ttl: int | None = None) -> bool:
        _check(kind, key)
        r = self._request("PUT", self._url(kind, key), self._headers(**{"Content-Type": "application/json", "If-Match": etag}),
                          self._body(kind, key, data, ttl))                   # Update Entity: only this version
        if r.status_code in (404, 412):
            return False
        if r.status_code not in (200, 204):
            raise self._fail("an update", r)
        return True

    def delete(self, kind: str, key: str) -> None:
        _check(kind, key)
        r = self._request("DELETE", self._url(kind, key), self._headers(**{"If-Match": "*"}))
        if r.status_code not in (204, 404):
            raise self._fail("a delete", r)

    def _maybe_purge(self) -> None:
        """Expired records (sign-ins nobody finished, codes nobody redeemed, lapsed lines and consents); best effort, at
        most every ten minutes per replica, in a thread of its own so no request waits for it."""
        now = self.clock()
        with self._lock:
            if now - self._purged < PURGE_EVERY:
                return
            self._purged = now
        threading.Thread(target=self._purge, args=(now,), daemon=True, name="registration-purge").start()

    def _purge(self, now: float) -> None:
        try:
            for kind in KINDS:
                flt = f"PartitionKey eq '{kind}' and exp gt 0L and exp lt {int(now)}L"
                r = self._request("GET", f"{self.base}()", self._headers(Accept="application/json;odata=minimalmetadata"),
                                  params={"$filter": flt, "$select": "PartitionKey,RowKey,exp", "$top": str(PURGE_BATCH)})
                if r.status_code != 200:
                    return
                for row in (r.json() or {}).get("value", [])[:PURGE_BATCH]:
                    if row.get("RowKey") and row.get("odata.etag"):      # only the expired version it saw, never a newer one
                        self._request("DELETE", self._url(kind, row["RowKey"]), self._headers(**{"If-Match": row["odata.etag"]}))
        except Exception:  # noqa: BLE001 — a failed sweep is retried at the next one; expired records are never handed out
            return


def from_env():
    """The store KRUSGRAPH_REGISTRATION_STORE names; ValueError when it is missing or malformed."""
    raw = os.environ.get("KRUSGRAPH_REGISTRATION_STORE", "").strip()
    if raw.lower() == "memory":
        return MemoryStore()
    if not raw:
        raise ValueError("KRUSGRAPH_REGISTRATION_STORE is required: `memory` (one replica) or "
                         "https://<account>.table.core.windows.net/<table>")
    return TableStore(raw)
