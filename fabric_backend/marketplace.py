"""Krusgraph bought through Microsoft Marketplace (a transactable SaaS offer). Off unless KRUSGRAPH_MARKETPLACE=1: with
the flag off no route below exists and nothing else changes (server.build_app adds the routes only when it is on).

Three parts, each built only from what Microsoft documents (docs/MARKETPLACE-SETUP.md has the sources [M1]-[M9] with the
date read):

  /marketplace/landing?token=...   the landing page [M3]. The buyer signs in with Microsoft Entra (the site's existing
                                   multitenant app, scopes openid and profile only, authorization code flow with PKCE),
                                   the server resolves the purchase token with the SaaS fulfilment API [M1], shows offer,
                                   plan, quantity, status and the beneficiary tenant, and activates on the buyer's click
                                   [M1] (nothing to activate when the plan uses auto activation: the resolve already
                                   answers Subscribed and a Subscribe webhook follows [M1][M2]).
  /marketplace/webhook             the connection webhook [M2]. Each call carries an Entra bearer token: issuer our own
                                   tenant, audience the fulfilment app's id, appid or azp the Marketplace SaaS API
                                   resource 20e940b3-4c77-4b0b-9a53-9e16a1b010a7 [M2][M5]. The operation is then confirmed
                                   with Get operation [M2][M4], recorded once per operation id, and ChangePlan,
                                   ChangeQuantity and Reinstate are acknowledged with Patch operation, Success [M2][M4].
  the store                        one row per beneficiary tenant id in the Azure Table the entitlement check already
                                   reads (KRUSGRAPH_ENTITLEMENTS_TABLE, PartitionKey "marketplace", RowKey the tenant id):
                                   the best subscription's id, offer, plan, status, updated_at, and every subscription of
                                   that tenant in `subscriptions` (JSON), so a tenant with several resolves to the best
                                   active one. No user ids, names or e-mail addresses, nothing from the customer's data.

The fulfilment API is called as a separate single-tenant Entra app of the publisher (Microsoft's recommendation [M3][M5]),
with the client credentials flow and the scope 20e940b3-4c77-4b0b-9a53-9e16a1b010a7/.default [M5]:

  KRUSGRAPH_MARKETPLACE                       1 switches all of this on (default off)
  KRUSGRAPH_MARKETPLACE_TENANT_ID             the publisher's Entra tenant id (Partner Center: Microsoft Entra tenant ID)
  KRUSGRAPH_MARKETPLACE_CLIENT_ID             the fulfilment app's id (Partner Center: Microsoft Entra application ID)
  KRUSGRAPH_MARKETPLACE_CLIENT_SECRET         its client secret, as a container-app secret reference, or
  KRUSGRAPH_MARKETPLACE_CLIENT_SECRET_KEYVAULT_URI  https://<vault>.vault.azure.net/secrets/<name>, read with the managed
                                              identity (keyvault.py); then the variable above is not used
  KRUSGRAPH_MARKETPLACE_OFFER_URL             the offer's Marketplace page; the upgrade answer links to it
  KRUSGRAPH_MARKETPLACE_TABLE                 the table, default KRUSGRAPH_ENTITLEMENTS_TABLE; the identity needs
                                              "Storage Table Data Contributor" on it (it writes)
  KRUSGRAPH_MARKETPLACE_STORE                 "memory" keeps the rows in memory only (a local test, never production)

Tokens, the purchase token and the client secret are never logged and never shown. The log lines name the action, the
subscription id and the outcome only.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import logging
import os
import re
import secrets
import threading
import time
import uuid
from urllib.parse import quote, urlencode

AUTHORITY = "https://login.microsoftonline.com"
SAAS_RESOURCE = "20e940b3-4c77-4b0b-9a53-9e16a1b010a7"          # the Marketplace SaaS API [M5]; also appid/azp on webhooks [M2]
SAAS_SCOPE = f"{SAAS_RESOURCE}/.default"
API = "https://marketplaceapi.microsoft.com/api/saas"
API_VERSION = "2018-08-31"
MSA_TENANT = "9188040d-6c67-4c5b-b112-36a304b66dad"             # personal Microsoft accounts [M3]

LANDING_PATH, CALLBACK_PATH, ACTIVATE_PATH, WEBHOOK_PATH = (
    "/marketplace/landing", "/marketplace/callback", "/marketplace/activate", "/marketplace/webhook")
FLOW_COOKIE = "__Host-kg_mp_flow"        # the sign-in in progress: state, PKCE verifier, nonce, the purchase token
SESSION_COOKIE = "__Host-kg_mp_sub"      # after sign-in: the subscription the buyer may activate, and a CSRF value
FLOW_TTL = 600

ACTIONS = ("Subscribe", "ChangePlan", "ChangeQuantity", "Renew", "Suspend", "Reinstate", "Unsubscribe")
ACKNOWLEDGED = {"ChangePlan", "ChangeQuantity", "Reinstate"}       # answered with Patch operation [M4]
STATUS_AFTER = {"Subscribe": "Subscribed", "Renew": "Subscribed", "Reinstate": "Subscribed", "Suspend": "Suspended",
                "Unsubscribe": "Unsubscribed"}                     # ChangePlan and ChangeQuantity keep the status
RANK = {"Subscribed": 3, "Suspended": 2, "PendingFulfillmentStart": 1, "Unsubscribed": 0}
ACTIVE = {"Subscribed"}
PARTITION, OP_PARTITION = "marketplace", "marketplace-op"
GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
SUBSCRIPTION_TTL = 60                    # how long a tenant's row is cached for the licence check

log = logging.getLogger("krusgraph.marketplace")


def enabled() -> bool:
    return os.environ.get("KRUSGRAPH_MARKETPLACE", "0").strip().lower() in {"1", "true", "yes", "on"}


def offer_url() -> str:
    """Where the upgrade answer sends a tenant without a subscription: the offer, else the entitlement check's page."""
    explicit = os.environ.get("KRUSGRAPH_MARKETPLACE_OFFER_URL", "").strip()
    if explicit.startswith("https://"):
        return explicit
    from .entitlements import upgrade_url
    return upgrade_url()


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _http(method: str, url: str, **kw):
    import requests
    return requests.request(method, url, timeout=kw.pop("timeout", 8), **kw)


class MarketplaceError(Exception):
    """A call to Entra, the fulfilment API or the store did not give the answer needed. The text never holds a token."""

    def __init__(self, text: str, status: int = 0) -> None:
        super().__init__(text)
        self.status = status


# ------------------------------------------------------------------ configuration ----------------------------------

class Config:
    def __init__(self, tenant_id: str, client_id: str, secret: str = "", secret_reader=None) -> None:
        self.tenant_id, self.client_id = tenant_id.lower(), client_id.lower()
        self._secret, self._reader = secret, secret_reader

    def __repr__(self) -> str:                                     # the secret never appears in a repr
        return f"marketplace.Config(tenant_id={self.tenant_id!r}, client_id={self.client_id!r})"

    def secret(self, refresh: bool = False) -> str:
        return self._reader.get(refresh) if self._reader is not None else self._secret

    @classmethod
    def from_env(cls) -> "Config":
        tid = os.environ.get("KRUSGRAPH_MARKETPLACE_TENANT_ID", "").strip()
        cid = os.environ.get("KRUSGRAPH_MARKETPLACE_CLIENT_ID", "").strip()
        uri = os.environ.get("KRUSGRAPH_MARKETPLACE_CLIENT_SECRET_KEYVAULT_URI", "").strip()
        sec = os.environ.get("KRUSGRAPH_MARKETPLACE_CLIENT_SECRET", "").strip()
        missing = [n for n, v in (("KRUSGRAPH_MARKETPLACE_TENANT_ID", tid), ("KRUSGRAPH_MARKETPLACE_CLIENT_ID", cid)) if not v]
        if not (uri or sec):
            missing.append("KRUSGRAPH_MARKETPLACE_CLIENT_SECRET or KRUSGRAPH_MARKETPLACE_CLIENT_SECRET_KEYVAULT_URI")
        if missing:
            raise ValueError("KRUSGRAPH_MARKETPLACE=1 needs " + ", ".join(missing))
        if not (GUID.match(tid) and GUID.match(cid)):
            raise ValueError("KRUSGRAPH_MARKETPLACE_TENANT_ID and KRUSGRAPH_MARKETPLACE_CLIENT_ID must be GUIDs")
        reader = None
        if uri:
            from . import keyvault
            try:
                reader = keyvault.SecretReader(uri)
            except ValueError:
                raise ValueError("KRUSGRAPH_MARKETPLACE_CLIENT_SECRET_KEYVAULT_URI must look like "
                                 "https://<vault>.vault.azure.net/secrets/<name>") from None
        return cls(tid, cid, "" if reader else sec, reader)


# ------------------------------------------------------------------ the fulfilment API -----------------------------

class Fulfilment:
    """SaaS fulfilment APIs v2 [M1][M4] as the publisher's app (client credentials [M5]). `http(method, url, **kw)`
    is requests.request in production and a fake in tests."""

    def __init__(self, cfg: Config, http=None, clock=time.time) -> None:
        self.cfg, self.http, self.clock = cfg, http or _http, clock
        self._token: tuple[str, float] | None = None
        self._lock = threading.Lock()

    def token(self) -> str:
        with self._lock:
            if self._token and self.clock() < self._token[1]:
                return self._token[0]
        for attempt in (0, 1):
            r = self.http("POST", f"{AUTHORITY}/{self.cfg.tenant_id}/oauth2/v2.0/token", timeout=8, data={
                "grant_type": "client_credentials", "client_id": self.cfg.client_id,
                "client_secret": self.cfg.secret(refresh=attempt == 1), "scope": SAAS_SCOPE})
            body = _json(r)
            if r.status_code == 200 and body.get("access_token"):
                ttl = int(body.get("expires_in") or 3600)
                with self._lock:
                    self._token = (body["access_token"], self.clock() + max(60, ttl - 300))
                return body["access_token"]
            code = str(body.get("error") or "")
            if attempt == 0 and code in {"invalid_client", "unauthorized_client"} and getattr(self.cfg, "_reader", None):
                continue                                       # a secret rotated in Key Vault: read it again once
            raise MarketplaceError(f"Microsoft Entra refused the fulfilment app's token request ({code or r.status_code})",
                                   r.status_code)
        raise MarketplaceError("Microsoft Entra refused the fulfilment app's token request")

    def _call(self, method: str, path: str, timeout: float = 8, **kw):
        headers = {"Authorization": f"Bearer {self.token()}", "Content-Type": "application/json",
                   "x-ms-requestid": str(uuid.uuid4()), "x-ms-correlationid": str(uuid.uuid4()), **kw.pop("headers", {})}
        sep = "&" if "?" in path else "?"
        return self.http(method, f"{API}{path}{sep}api-version={API_VERSION}", headers=headers, timeout=timeout, **kw)

    def resolve(self, marketplace_token: str) -> dict:
        """POST subscriptions/resolve with x-ms-marketplace-token [M1]. 400 means the token is missing, malformed or
        expired (valid 24 hours)."""
        r = self._call("POST", "/subscriptions/resolve", headers={"x-ms-marketplace-token": marketplace_token})
        if r.status_code == 200:
            return _json(r)
        raise MarketplaceError({400: "expired"}.get(r.status_code, f"the fulfilment API answered HTTP {r.status_code}"),
                               r.status_code)

    def activate(self, subscription_id: str) -> None:
        """POST subscriptions/{id}/activate [M1]; 200 has no body."""
        r = self._call("POST", f"/subscriptions/{quote(subscription_id, safe='')}/activate")
        if r.status_code != 200:
            raise MarketplaceError(f"the fulfilment API answered HTTP {r.status_code} to activate", r.status_code)

    def subscription(self, subscription_id: str) -> dict:
        r = self._call("GET", f"/subscriptions/{quote(subscription_id, safe='')}")
        if r.status_code != 200:
            raise MarketplaceError(f"the fulfilment API answered HTTP {r.status_code} to get the subscription", r.status_code)
        return _json(r)

    def operation(self, subscription_id: str, operation_id: str, timeout: float = 4) -> dict:
        """GET subscriptions/{id}/operations/{operationId} [M4]: how a webhook call is confirmed [M2]."""
        r = self._call("GET", f"/subscriptions/{quote(subscription_id, safe='')}/operations/{quote(operation_id, safe='')}",
                       timeout=timeout)
        if r.status_code != 200:
            raise MarketplaceError(f"the fulfilment API answered HTTP {r.status_code} to get the operation", r.status_code)
        return _json(r)

    def acknowledge(self, subscription_id: str, operation_id: str, success: bool = True) -> int:
        """PATCH subscriptions/{id}/operations/{operationId} {"status": "Success"} [M4]."""
        r = self._call("PATCH", f"/subscriptions/{quote(subscription_id, safe='')}/operations/{quote(operation_id, safe='')}",
                       timeout=6, data=json.dumps({"status": "Success" if success else "Failure"}))
        return r.status_code


def _json(r) -> dict:
    try:
        body = r.json()
    except Exception:  # noqa: BLE001
        return {}
    return body if isinstance(body, dict) else {}


# ------------------------------------------------------------------ the webhook's token ----------------------------

class WebhookTokenError(Exception):
    pass


class WebhookValidator:
    """The bearer token on a webhook call [M2]: signed by Entra (keys of the publisher's tenant [M6]), issuer that tenant
    (v2.0 or v1.0 form [M6]), `tid` that tenant, `aud` the fulfilment app's id, `appid` or `azp` the Marketplace SaaS API
    resource, not expired."""

    def __init__(self, cfg: Config, jwks_client=None) -> None:
        self.cfg = cfg
        if jwks_client is None:
            import jwt
            jwks_client = jwt.PyJWKClient(f"{AUTHORITY}/{cfg.tenant_id}/discovery/v2.0/keys", cache_keys=True, lifespan=3600)
        self.jwks = jwks_client

    def validate(self, token: str) -> dict:
        import jwt
        try:
            key = self.jwks.get_signing_key_from_jwt(token).key
            claims = jwt.decode(token, key, algorithms=["RS256"], audience=self.cfg.client_id,
                                options={"require": ["exp", "iss", "aud", "tid"]}, leeway=60)
        except jwt.InvalidAudienceError:
            raise WebhookTokenError("wrong audience") from None
        except jwt.ExpiredSignatureError:
            raise WebhookTokenError("expired") from None
        except Exception as e:  # noqa: BLE001 — every other failure: not a token we accept
            raise WebhookTokenError(f"invalid token ({type(e).__name__})") from None
        tid = str(claims.get("tid", "")).lower()
        if tid != self.cfg.tenant_id:
            raise WebhookTokenError("wrong tenant")
        if str(claims.get("iss", "")).lower() not in {f"{AUTHORITY}/{tid}/v2.0", f"https://sts.windows.net/{tid}/"}:
            raise WebhookTokenError("wrong issuer")
        caller = str(claims.get("appid") or claims.get("azp") or "").lower()
        if caller != SAAS_RESOURCE:
            raise WebhookTokenError("wrong appid")
        return claims


# ------------------------------------------------------------------ the store --------------------------------------

def _best(subs: dict) -> tuple[str, dict] | None:
    """The subscription that decides for the tenant: the highest status (Subscribed first), then the latest change."""
    if not subs:
        return None
    return max(subs.items(), key=lambda kv: (RANK.get(kv[1].get("status"), -1), kv[1].get("updated_at", ""), kv[0]))


def tenant_row(tid: str, subs: dict) -> dict:
    """The row for one beneficiary tenant: the best subscription's fields, and all of them as JSON."""
    best = _best(subs)
    sid, b = best if best else ("", {})
    return {"PartitionKey": PARTITION, "RowKey": tid.lower(), "subscription_id": sid, "offer": b.get("offer", ""),
            "plan": b.get("plan", ""), "status": b.get("status", ""), "active": b.get("status") in ACTIVE,
            "updated_at": _now_iso(), "subscriptions": json.dumps(subs, sort_keys=True)}


class MemoryStore:
    """The same rows in memory: tests and a local try-out (KRUSGRAPH_MARKETPLACE_STORE=memory), never production."""

    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], dict] = {}
        self._lock = threading.Lock()

    def get(self, pk: str, rk: str) -> tuple[dict | None, str]:
        with self._lock:
            row = self.rows.get((pk, rk))
            return (dict(row), str(row.get("_etag"))) if row else (None, "")

    def put(self, row: dict, etag: str = "") -> bool:
        """Insert (etag "") or replace when the etag still matches; False when another write came first."""
        with self._lock:
            key = (row["PartitionKey"], row["RowKey"])
            old = self.rows.get(key)
            if (old is None) != (etag == "") or (old is not None and str(old.get("_etag")) != etag):
                return False
            self.rows[key] = {**row, "_etag": secrets.token_hex(4)}
            return True


class TableStore:
    """Azure Table Storage with the managed identity (Entra authorization, x-ms-version 2019-02-02), the same
    mechanism entitlements.TableSource reads with. Insert with POST, replace with PUT and If-Match (optimistic
    concurrency), so two webhook calls for one tenant never lose each other's subscription."""

    def __init__(self, table_url: str, http=None, token=None) -> None:
        from .entitlements import TableSource
        self._source = TableSource(table_url)          # parses the URL and fetches the identity token the same way
        self.base, self.http, self._token = self._source.base, http or _http, token

    def _headers(self) -> dict:
        bearer = self._token() if self._token is not None else self._source._bearer()
        return {"Authorization": f"Bearer {bearer}", "x-ms-version": "2019-02-02",
                "Accept": "application/json;odata=nometadata", "Content-Type": "application/json"}

    def _url(self, pk: str, rk: str) -> str:
        esc = lambda s: quote(s.replace("'", "''"), safe="")  # noqa: E731
        return f"{self.base}(PartitionKey='{esc(pk)}',RowKey='{esc(rk)}')"

    def get(self, pk: str, rk: str) -> tuple[dict | None, str]:
        r = self.http("GET", self._url(pk, rk), headers=self._headers(), timeout=4)
        if r.status_code == 404:
            return None, ""
        if r.status_code != 200:
            raise MarketplaceError(f"the table answered HTTP {r.status_code}", r.status_code)
        return _json(r), r.headers.get("ETag", "")

    def put(self, row: dict, etag: str = "") -> bool:
        body = json.dumps({k: v for k, v in row.items() if not k.startswith("_")})
        if etag:
            r = self.http("PUT", self._url(row["PartitionKey"], row["RowKey"]), headers={**self._headers(), "If-Match": etag},
                          data=body, timeout=4)
        else:
            r = self.http("POST", self.base, headers={**self._headers(), "Prefer": "return-no-content"}, data=body, timeout=4)
        if r.status_code in (409, 412):
            return False
        if r.status_code not in (200, 201, 204):
            raise MarketplaceError(f"the table answered HTTP {r.status_code}", r.status_code)
        return True


class Subscriptions:
    """The rows: per tenant (best active subscription first) and per webhook operation (idempotency)."""

    def __init__(self, store, clock=time.time) -> None:
        self.store, self.clock = store, clock
        self._cache: dict[str, tuple[dict | None, float]] = {}
        self._lock = threading.Lock()

    def tenant(self, tid: str, cached: bool = True) -> dict | None:
        tid = tid.lower()
        with self._lock:
            hit = self._cache.get(tid)
            if cached and hit and self.clock() - hit[1] < SUBSCRIPTION_TTL:
                return hit[0]
        row, _ = self.store.get(PARTITION, tid)
        with self._lock:
            self._cache[tid] = (row, self.clock())
        return row

    def active(self, tid: str) -> bool:
        row = self.tenant(tid)
        return bool(row and row.get("status") in ACTIVE)

    def record(self, tid: str, subscription_id: str, fields: dict, at: str = "") -> dict:
        """Merge one subscription's fields into its tenant's row. `at` (the operation's timeStamp) keeps an older
        operation that arrives late from overwriting a newer one."""
        tid, subscription_id = tid.lower(), subscription_id.lower()
        for _ in range(5):
            row, etag = self.store.get(PARTITION, tid)
            try:
                subs = json.loads((row or {}).get("subscriptions") or "{}")
            except ValueError:
                subs = {}
            old = subs.get(subscription_id) or {}
            if at and old.get("op_at") and old["op_at"] > at:
                return row or {}
            new = {**old, **{k: v for k, v in fields.items() if v not in (None, "")}, "updated_at": _now_iso()}
            if at:
                new["op_at"] = at
            subs[subscription_id] = new
            out = tenant_row(tid, subs)
            if self.store.put(out, etag):
                with self._lock:
                    self._cache.pop(tid, None)
                return out
        raise MarketplaceError("the tenant's row kept changing while it was written")

    def seen(self, operation_id: str) -> bool:
        row, _ = self.store.get(OP_PARTITION, operation_id.lower())
        return row is not None

    def mark(self, operation_id: str, action: str, subscription_id: str) -> None:
        self.store.put({"PartitionKey": OP_PARTITION, "RowKey": operation_id.lower(), "action": action,
                        "subscription_id": subscription_id.lower(), "at": _now_iso()})


_subs: Subscriptions | None = None
_subs_lock = threading.Lock()


def store() -> Subscriptions:
    """The process's store, from the environment (tests replace it with set_store)."""
    global _subs
    with _subs_lock:
        if _subs is None:
            if os.environ.get("KRUSGRAPH_MARKETPLACE_STORE", "").strip().lower() == "memory":
                _subs = Subscriptions(MemoryStore())
            else:
                url = (os.environ.get("KRUSGRAPH_MARKETPLACE_TABLE", "").strip()
                       or os.environ.get("KRUSGRAPH_ENTITLEMENTS_TABLE", "").strip())
                if not url:
                    raise MarketplaceError("no store: set KRUSGRAPH_ENTITLEMENTS_TABLE (or KRUSGRAPH_MARKETPLACE_TABLE)")
                _subs = Subscriptions(TableStore(url))
        return _subs


def set_store(subs: Subscriptions | None) -> None:
    global _subs
    with _subs_lock:
        _subs = subs


def features(tid: str | None) -> set[str]:
    """For the entitlement check: every paid feature while the tenant has an active subscription. A store that cannot
    be read raises, and the check then refuses the paid feature for that call (never the free ones)."""
    if not tid:
        return set()
    return {"*"} if store().active(tid) else set()


def subscription_fields(sub: dict) -> dict:
    """What is kept of a subscription: ids, offer, plan, quantity, status, trial and test flags. Never the beneficiary's
    or purchaser's e-mail address, object id or puid."""
    return {"offer": str(sub.get("offerId") or "")[:100], "plan": str(sub.get("planId") or "")[:100],
            "quantity": sub.get("quantity") if isinstance(sub.get("quantity"), int) else None,
            "status": str(sub.get("saasSubscriptionStatus") or "").strip()[:40],
            "free_trial": bool(sub.get("isFreeTrial")), "test": bool(sub.get("isTest"))}


def _tenant_of(sub: dict, who: str = "beneficiary") -> str:
    t = str(((sub.get(who) or {}) if isinstance(sub.get(who), dict) else {}).get("tenantId") or "").lower()
    return t if GUID.match(t) else ""


# ------------------------------------------------------------------ the webhook ------------------------------------

def handle_webhook(body: dict, fulfilment: Fulfilment, subs: Subscriptions, run_later=None) -> tuple[int, dict]:
    """One webhook call whose token is already valid -> (HTTP status, JSON answer). 200 acknowledges [M2]; 503 asks
    Microsoft to call again (its retry policy: 500 retries over eight hours [M2]); 4xx is never answered to a
    ChangePlan or ChangeQuantity, because there it means "rejected" [M2]."""
    if not isinstance(body, dict):
        return 400, {"error": "the body is not a JSON object"}
    op_id, sid, action = (str(body.get(k) or "").strip() for k in ("id", "subscriptionId", "action"))
    if not (GUID.match(op_id) and GUID.match(sid)):
        return 400, {"error": "id and subscriptionId must be GUIDs"}
    if action not in ACTIONS:
        log.info("marketplace webhook: action %s ignored (subscription %s)", action[:40], sid)
        return 200, {"ok": True, "ignored": action[:40]}
    try:
        if subs.seen(op_id):
            return 200, {"ok": True, "duplicate": True}
        op = fulfilment.operation(sid, op_id)
    except MarketplaceError as e:
        log.warning("marketplace webhook: %s on %s not confirmed yet: %s", action, sid, e)
        return 503, {"error": "the operation could not be confirmed yet; call again"}
    if str(op.get("subscriptionId") or "").lower() != sid.lower() or (op.get("action") and op.get("action") != action):
        log.warning("marketplace webhook: %s on %s does not match Get operation", action, sid)
        return (503 if action in {"ChangePlan", "ChangeQuantity"} else 400), {"error": "the operation does not match"}
    sub = body.get("subscription") if isinstance(body.get("subscription"), dict) else {}
    try:
        if not _tenant_of(sub):
            sub = fulfilment.subscription(sid)
        tid = _tenant_of(sub)
        if not tid:
            return 503, {"error": "the subscription names no beneficiary tenant yet"}
        fields = {"offer": str(body.get("offerId") or sub.get("offerId") or "")[:100],
                  "free_trial": bool(sub.get("isFreeTrial")), "test": bool(sub.get("isTest"))}
        if action == "ChangePlan":
            fields["plan"] = str(op.get("planId") or body.get("planId") or "")[:100]
        elif action == "ChangeQuantity":
            q = op.get("quantity", body.get("quantity"))
            fields["quantity"] = q if isinstance(q, int) else None
        else:
            fields["plan"] = str(body.get("planId") or sub.get("planId") or "")[:100]
            fields["status"] = STATUS_AFTER[action]
        if action in {"ChangePlan", "ChangeQuantity"}:      # the status the subscription has; empty keeps the row's
            fields["status"] = str(sub.get("saasSubscriptionStatus") or "").strip()
        subs.record(tid, sid, fields, at=str(body.get("timeStamp") or ""))
        subs.mark(op_id, action, sid)
    except MarketplaceError as e:
        log.warning("marketplace webhook: %s on %s not recorded: %s", action, sid, e)
        return 503, {"error": "not recorded; call again"}
    log.info("marketplace webhook: %s on %s recorded", action, sid)
    if action in ACKNOWLEDGED:
        def ack():
            try:
                status = fulfilment.acknowledge(sid, op_id, True)
                log.info("marketplace webhook: %s on %s acknowledged (HTTP %s)", action, sid, status)
            except Exception as e:  # noqa: BLE001 — unanswered means accepted [M2]; logged without the request
                log.warning("marketplace webhook: acknowledging %s on %s failed: %s", action, sid, type(e).__name__)
        (run_later or _background)(ack)
    return 200, {"ok": True}


def _background(fn) -> None:
    threading.Thread(target=fn, daemon=True, name="marketplace-ack").start()


# ------------------------------------------------------------------ the landing page -------------------------------

def _b64(data: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(data, separators=(",", ":")).encode()).decode().rstrip("=")


def _unb64(text: str) -> dict:
    try:
        out = json.loads(base64.urlsafe_b64decode(text + "=" * (-len(text) % 4)))
        return out if isinstance(out, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _s256(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")


class SignIn:
    """The buyer's sign-in on the landing page: OpenID Connect authorization code flow with PKCE and a nonce, against
    /organizations with the site's existing multitenant Entra app (ENTRA_CLIENT_ID), scopes `openid profile` only.
    The ID token is validated as Microsoft documents [M6][M7]: signature, audience = the app, issuer of the token's
    own tenant, the nonce of this sign-in. Only `tid` is used."""

    def __init__(self, entra_cfg, http=None, jwks_client=None) -> None:
        self.cfg, self.http = entra_cfg, http or _http
        self._jwks = jwks_client

    def redirect_uri(self, origin: str) -> str:
        return f"{origin}{CALLBACK_PATH}"

    def authorize_url(self, origin: str, state: str, verifier: str, nonce: str) -> str:
        return f"{AUTHORITY}/organizations/oauth2/v2.0/authorize?" + urlencode({
            "client_id": self.cfg.client_id, "response_type": "code", "redirect_uri": self.redirect_uri(origin),
            "response_mode": "query", "scope": "openid profile", "state": state, "nonce": nonce,
            "code_challenge": _s256(verifier), "code_challenge_method": "S256", "prompt": "select_account"})

    def redeem(self, origin: str, code: str, verifier: str, nonce: str) -> dict:
        r = self.http("POST", f"{AUTHORITY}/organizations/oauth2/v2.0/token", timeout=10, data={
            "grant_type": "authorization_code", "client_id": self.cfg.client_id, "client_secret": self.cfg.secret(),
            "code": code, "redirect_uri": self.redirect_uri(origin), "code_verifier": verifier, "scope": "openid profile"})
        body = _json(r)
        if r.status_code != 200 or not body.get("id_token"):
            raise MarketplaceError(f"Microsoft Entra did not complete the sign-in ({str(body.get('error') or r.status_code)[:60]})")
        return self.validate_id_token(body["id_token"], nonce)

    def validate_id_token(self, token: str, nonce: str) -> dict:
        import jwt
        jwks = self._jwks or jwt.PyJWKClient(f"{AUTHORITY}/common/discovery/v2.0/keys", cache_keys=True, lifespan=3600)
        self._jwks = jwks
        try:
            claims = jwt.decode(token, jwks.get_signing_key_from_jwt(token).key, algorithms=["RS256"],
                                audience=self.cfg.client_id, options={"require": ["exp", "iss", "aud", "tid", "nonce"]})
        except Exception as e:  # noqa: BLE001
            raise MarketplaceError(f"the ID token is not accepted ({type(e).__name__})") from None
        tid = str(claims.get("tid", "")).lower()
        if not GUID.match(tid) or str(claims.get("iss", "")).lower() != f"{AUTHORITY}/{tid}/v2.0":
            raise MarketplaceError("the ID token's issuer does not match its tenant")
        if not hmac.compare_digest(str(claims.get("nonce", "")), nonce):
            raise MarketplaceError("the ID token belongs to another sign-in")
        return claims


def _page(title: str, body: str, status: int = 200, cookies=(), delete=()):
    """A plain page in the site's look (site.css, the oauth pages' layout), no scripts, nothing from elsewhere."""
    from starlette.responses import HTMLResponse
    product = html.escape(os.environ.get("PRODUCT_NAME", "").strip() or "Krusgraph")
    doc = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>{html.escape(title)} — {product}</title>
<link rel="stylesheet" href="/static/site.css"><link rel="stylesheet" href="/static/oauth.css"></head>
<body class="oauth"><main class="wrap">{body}</main></body></html>"""
    resp = HTMLResponse(doc, status_code=status, headers={
        "Cache-Control": "no-store", "Pragma": "no-cache", "X-Frame-Options": "DENY", "X-Robots-Tag": "noindex",
        "Content-Security-Policy": ("default-src 'none'; style-src 'self'; font-src 'self'; img-src 'self' data:; "
                                    "form-action 'self'; frame-ancestors 'none'; base-uri 'none'"),
        # same-origin: the activation form's POST must carry the real Origin, which activate() checks
        "Referrer-Policy": "same-origin", "X-Content-Type-Options": "nosniff"})
    for name, value, age in cookies:
        resp.set_cookie(name, value, max_age=age, path="/", secure=True, httponly=True, samesite="lax")
    for name in delete:
        resp.delete_cookie(name, path="/", secure=True, httponly=True, samesite="lax")
    return resp


NEXT_STEPS = """<h2 class="h3">Next step: open Fabric, or connect Claude</h2>
<ol>
<li><strong>Open Fabric</strong>: in a workspace on a Fabric capacity, create a Krusgraph item, or use the set-up guide
for your organisation's administrator.</li>
<li><strong>Connect Claude</strong>: add Krusgraph as a connector and sign in with your work account; creating items
in Fabric is now included for your organisation.</li>
</ol>
<div class="ctas"><a class="btn primary" href="https://app.fabric.microsoft.com/">Open Fabric</a>
<a class="btn secondary" href="/start">Connect Claude</a></div>"""


def _expired_page():
    # The wording Microsoft asks for when the token cannot be resolved [M1]
    return _page("Purchase not found", """<span class="kicker">Microsoft Marketplace</span>
<h1>We couldn't identify this purchase.</h1>
<p class="lede">Reopen this SaaS subscription in the Azure portal or in Microsoft 365 Admin Center and select
<strong>Configure Account</strong> or <strong>Manage Account</strong> again.</p>
<p class="muted">Nothing was charged or changed on this page.</p>""", 400, delete=[FLOW_COOKIE])


def _problem_page(text: str, status: int = 502):
    return _page("Marketplace", f"""<span class="kicker">Microsoft Marketplace</span>
<h1>This step did not finish.</h1><p class="lede">{html.escape(text)}</p>
<p>Open the subscription again from the Azure portal or Microsoft 365 Admin Center (<strong>Configure Account</strong>);
if it keeps happening, <a href="/support">get help</a>. Nothing was charged on this page.</p>""", status)


def _subscription_page(sub: dict, signed_in_tid: str, csrf: str, activated: bool = False):
    e = html.escape
    f = subscription_fields(sub)
    beneficiary = _tenant_of(sub)
    status = f["status"] or "unknown"
    quantity = f["quantity"] if f["quantity"] is not None else "not applicable (flat rate)"
    rows = "".join(f"<li><strong>{k}</strong>: {v}</li>" for k, v in (
        ("Offer", f"<code>{e(f['offer'])}</code>"), ("Plan", f"<code>{e(f['plan'])}</code>"),
        ("Quantity", e(str(quantity))), ("Status", e(status) + (" (free trial)" if f["free_trial"] else "")),
        ("For the organisation (tenant id)", f"<code>{e(beneficiary or 'not named')}</code>"),
        ("Subscription", e(str(sub.get("name") or "")) or "<span class=\"muted\">no name</span>")))
    if activated:
        lede = "Activated. Your organisation can now create items in Fabric with Krusgraph."
        action = NEXT_STEPS
    elif status == "PendingFulfillmentStart":
        lede = "Check the details, then activate. Microsoft starts billing when the subscription is activated."
        action = f"""<form method="post" action="{ACTIVATE_PATH}" class="ctas">
<input type="hidden" name="csrf" value="{e(csrf)}">
<button type="submit" class="btn primary">Activate the subscription</button></form>
<p class="muted">Activating is the only thing this button does; nothing is created in Fabric.</p>"""
    elif status == "Subscribed":
        lede = "This subscription is active; there is nothing to activate."
        action = NEXT_STEPS
    else:
        lede = f"This subscription is {e(status)}; it cannot be activated from here."
        action = """<p>Manage it in the Azure portal or Microsoft 365 Admin Center. <a href="/support">Get help</a>.</p>"""
    other = ("" if signed_in_tid in {beneficiary, _tenant_of(sub, "purchaser")} else
             '<p class="warn">You signed in with an account from another organisation than the one this subscription '
             'is for. Sign in with an account of that organisation to activate it.</p>')
    if other and status == "PendingFulfillmentStart" and not activated:
        action = ""
    return _page("Your subscription", f"""<span class="kicker">Microsoft Marketplace</span>
<h1>Your Krusgraph subscription</h1><p class="lede">{lede}</p>
<ul>{rows}</ul>
{other}{action}
<p class="muted tiny">Billing, invoices and payment are handled by Microsoft; this page never asks for
payment details. Krusgraph keeps the tenant id and the subscription's state only.</p>""")


def routes(entra_cfg, fulfilment: Fulfilment | None = None, validator: WebhookValidator | None = None,
           subs: Subscriptions | None = None, signin: SignIn | None = None, run_later=None) -> list:
    """The four routes. Built only when KRUSGRAPH_MARKETPLACE=1 (server.build_app); every dependency can be a double."""
    from starlette.concurrency import run_in_threadpool
    from starlette.responses import JSONResponse, RedirectResponse
    from starlette.routing import Route
    cfg = Config.from_env() if fulfilment is None or validator is None else None
    fulfilment = fulfilment or Fulfilment(cfg)
    validator = validator or WebhookValidator(cfg)
    signin = signin or (SignIn(entra_cfg) if entra_cfg is not None else None)
    get_subs = (lambda: subs) if subs is not None else store

    def origin_of(request) -> str:
        from .errors import site_origin
        return site_origin()

    async def landing(request):
        token = request.query_params.get("token", "")
        if not token or len(token) > 4096:
            return _page("Marketplace", """<span class="kicker">Microsoft Marketplace</span>
<h1>Nothing to show yet.</h1><p class="lede">This is where Microsoft Marketplace sends you after buying Krusgraph.
Opened directly, there is no purchase to show.</p><div class="ctas"><a class="btn primary" href="/start">The set-up guide</a></div>""")
        if signin is None:
            return _problem_page("Sign-in with Microsoft is not configured on this server.", 503)
        state, verifier, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(64), secrets.token_urlsafe(32)
        flow = _b64({"s": state, "v": verifier, "n": nonce, "t": token, "at": int(time.time())})
        url = signin.authorize_url(origin_of(request), state, verifier, nonce)
        resp = RedirectResponse(url, status_code=302, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})
        resp.set_cookie(FLOW_COOKIE, flow, max_age=FLOW_TTL, path="/", secure=True, httponly=True, samesite="lax")
        return resp

    async def callback(request):
        q = request.query_params
        flow = _unb64(request.cookies.get(FLOW_COOKIE, ""))
        if not flow or time.time() - int(flow.get("at") or 0) > FLOW_TTL or not hmac.compare_digest(
                str(flow.get("s", "")), q.get("state", "")):
            return _page("Sign-in", """<span class="kicker">Microsoft Marketplace</span><h1>This sign-in has expired.</h1>
<p class="lede">Open the subscription again from the Azure portal or Microsoft 365 Admin Center
(<strong>Configure Account</strong>).</p>""", 400, delete=[FLOW_COOKIE])
        if q.get("error"):
            return _problem_page(f"Microsoft Entra answered {q['error'][:60]}.", 400)
        try:
            claims = await run_in_threadpool(signin.redeem, origin_of(request), q.get("code", ""), flow["v"], flow["n"])
            sub = await run_in_threadpool(fulfilment.resolve, flow["t"])
        except MarketplaceError as e:
            if str(e) == "expired":
                return _expired_page()
            log.warning("marketplace landing: %s", e)
            return _problem_page(str(e))
        detail = sub.get("subscription") if isinstance(sub.get("subscription"), dict) else {}
        detail = {**detail, "id": sub.get("id") or detail.get("id"), "offerId": sub.get("offerId") or detail.get("offerId"),
                  "planId": sub.get("planId") or detail.get("planId"),
                  "name": sub.get("subscriptionName") or detail.get("name"),
                  "quantity": sub.get("quantity") if sub.get("quantity") not in (None, "") else detail.get("quantity")}
        sid, tid = str(detail.get("id") or "").lower(), _tenant_of(detail)
        if not GUID.match(sid):
            return _problem_page("The fulfilment API answered without a subscription id.")
        try:
            if tid:
                await run_in_threadpool(get_subs().record, tid, sid, subscription_fields(detail))
        except MarketplaceError as e:
            log.warning("marketplace landing: recording %s failed: %s", sid, e)
        csrf = secrets.token_urlsafe(24)
        signed = str(claims.get("tid", "")).lower()
        resp = _subscription_page(detail, signed, csrf)
        resp.set_cookie(SESSION_COOKIE, _b64({"sub": sid, "csrf": csrf, "tid": signed, "at": int(time.time())}),
                        max_age=FLOW_TTL, path="/", secure=True, httponly=True, samesite="lax")
        resp.delete_cookie(FLOW_COOKIE, path="/", secure=True, httponly=True, samesite="lax")
        log.info("marketplace landing: subscription %s shown (%s)", sid, str(detail.get("saasSubscriptionStatus") or "").strip())
        return resp

    async def activate(request):
        sess = _unb64(request.cookies.get(SESSION_COOKIE, ""))
        form = await request.form()
        own = origin_of(request)
        if request.headers.get("origin") not in (None, own) or not sess or time.time() - int(sess.get("at") or 0) > FLOW_TTL \
                or not hmac.compare_digest(str(sess.get("csrf", "")), str(form.get("csrf", ""))):
            return _problem_page("This page has expired. Open the subscription again from Microsoft (Configure Account).", 400)
        sid = str(sess.get("sub", ""))
        try:
            sub = await run_in_threadpool(fulfilment.subscription, sid)
            tid = _tenant_of(sub)
            if str(sess.get("tid", "")) not in {tid, _tenant_of(sub, "purchaser")}:
                return _subscription_page(sub, str(sess.get("tid", "")), "")
            status = str(sub.get("saasSubscriptionStatus") or "").strip()
            if status == "PendingFulfillmentStart":
                await run_in_threadpool(fulfilment.activate, sid)
                sub = {**sub, "saasSubscriptionStatus": "Subscribed"}
            elif status != "Subscribed":
                return _subscription_page(sub, str(sess.get("tid", "")), "")
            if tid:
                await run_in_threadpool(get_subs().record, tid, sid, subscription_fields(sub))
        except MarketplaceError as e:
            log.warning("marketplace activate %s: %s", sid, e)
            return _problem_page(f"Microsoft did not activate the subscription: {e}.")
        log.info("marketplace activate: %s activated", sid)
        resp = _subscription_page(sub, str(sess.get("tid", "")), "", activated=True)
        resp.delete_cookie(SESSION_COOKIE, path="/", secure=True, httponly=True, samesite="lax")
        return resp

    async def webhook(request):
        a = request.headers.get("authorization", "")
        token = a[7:].strip() if a.lower().startswith("bearer ") else ""
        if not token:
            return JSONResponse({"error": "a bearer token is required"}, status_code=401,
                                headers={"WWW-Authenticate": 'Bearer error="invalid_request"'})
        try:
            await run_in_threadpool(validator.validate, token)
        except WebhookTokenError as e:
            log.warning("marketplace webhook refused: %s", e)
            return JSONResponse({"error": "the token is not accepted"}, status_code=401,
                                headers={"WWW-Authenticate": 'Bearer error="invalid_token"'})
        try:
            body = json.loads(await request.body() or b"null")
        except ValueError:
            return JSONResponse({"error": "the body is not valid JSON"}, status_code=400)
        try:
            subs_now = get_subs()
        except MarketplaceError as e:
            log.warning("marketplace webhook: %s", e)
            return JSONResponse({"error": "the store is not configured"}, status_code=503)
        status, out = await run_in_threadpool(handle_webhook, body, fulfilment, subs_now, run_later)
        return JSONResponse(out, status_code=status)

    return [Route(LANDING_PATH, landing, methods=["GET"]), Route(CALLBACK_PATH, callback, methods=["GET"]),
            Route(ACTIVATE_PATH, activate, methods=["POST"]), Route(WEBHOOK_PATH, webhook, methods=["POST"])]
