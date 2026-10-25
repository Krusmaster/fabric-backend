"""Sign-in with Microsoft Entra ID for the remote MCP server (the Claude connector directory path).

Entra has no dynamic client registration and no client ID metadata documents, so the connector is
listed with *Anthropic-held client credentials*: the publisher registers one multi-tenant Entra app,
Anthropic holds its client secret, and each user signs in with their own work account. The server
then exchanges the user's token for Fabric and SQL tokens with the on-behalf-of flow, so every
call runs with the user's own Fabric permissions and the server stores nothing.

What this module does:
  - protected resource metadata (RFC 9728) for /.well-known/oauth-protected-resource
  - the 401 + WWW-Authenticate challenge Claude needs to start sign-in
  - validating the user's access token (issuer per tenant, audience = the app, signature via JWKS)
  - on-behalf-of exchange to Fabric and SQL tokens, cached until shortly before expiry

Configuration (environment):
  MCP_PUBLIC_URL        https://<your domain>/mcp — must also be an Application ID URI on the app
  ENTRA_CLIENT_ID       the multi-tenant app's client id
  ENTRA_CLIENT_SECRET   its secret (the same one Anthropic holds; never logged)
  ENTRA_ALLOWED_TENANTS optional comma list of tenant ids; empty = any tenant whose admin consented
  ENTRA_REQUIRED       true on public deployments; missing configuration stops startup
"""
from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass, field

FABRIC_SCOPE = "https://api.fabric.microsoft.com/.default"
SQL_SCOPE = "https://database.windows.net/.default"
AUTHORITY = "https://login.microsoftonline.com"


@dataclass
class EntraConfig:
    public_url: str
    client_id: str
    client_secret: str = field(repr=False)
    allowed_tenants: set[str] = field(default_factory=set)

    @classmethod
    def from_env(cls) -> "EntraConfig | None":
        url, cid, sec = (os.environ.get(k) for k in ("MCP_PUBLIC_URL", "ENTRA_CLIENT_ID", "ENTRA_CLIENT_SECRET"))
        required = os.environ.get("ENTRA_REQUIRED", "").lower() in {"1", "true", "yes"}
        if not any((url, cid, sec)) and not required:
            return None
        if not all(value and value.strip() for value in (url, cid, sec)):
            raise ValueError("Entra sign-in requires MCP_PUBLIC_URL, ENTRA_CLIENT_ID and ENTRA_CLIENT_SECRET")
        from urllib.parse import urlsplit
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.path.rstrip("/") != "/mcp" or parsed.query or parsed.fragment:
            raise ValueError("MCP_PUBLIC_URL must be an HTTPS URL ending in /mcp")
        allowed = {t.strip().lower() for t in os.environ.get("ENTRA_ALLOWED_TENANTS", "").split(",") if t.strip()}
        return cls(url.rstrip("/"), cid, sec, allowed)

    @property
    def scope(self) -> str:
        """The delegated scope Claude asks for: <Application ID URI>/user_impersonation."""
        return f"{self.public_url}/user_impersonation"

    @property
    def audiences(self) -> list[str]:
        return [self.public_url, self.client_id, f"api://{self.client_id}"]

    @property
    def metadata_url(self) -> str:
        base = self.public_url.split("/", 3)
        return f"{base[0]}//{base[2]}/.well-known/oauth-protected-resource"


def protected_resource_metadata(cfg: EntraConfig) -> dict:
    """RFC 9728. `resource` must equal the URL the user enters; Claude uses only the first authorization server."""
    return {
        "resource": cfg.public_url,
        "authorization_servers": [f"{AUTHORITY}/organizations/v2.0"],
        "scopes_supported": [cfg.scope, "offline_access"],
        "bearer_methods_supported": ["header"],
        "resource_name": "Fabric tables with keys, relationships and rules",
    }


def challenge(cfg: EntraConfig, error: str | None = None) -> str:
    """The WWW-Authenticate value for a 401. Claude ignores it on a 200, so it must ride a 401."""
    parts = [f'resource_metadata="{cfg.metadata_url}"', f'scope="{cfg.scope} offline_access"']
    if error:
        parts.append(f'error="{error}"')
    return "Bearer " + ", ".join(parts)


class TokenError(Exception):
    pass


class Validator:
    """Validates Entra v2 access tokens issued for this app, from any consenting tenant."""

    def __init__(self, cfg: EntraConfig, jwks_client=None) -> None:
        self.cfg = cfg
        if jwks_client is None:
            import jwt
            jwks_client = jwt.PyJWKClient(f"{AUTHORITY}/common/discovery/v2.0/keys", cache_keys=True, lifespan=3600)
        self.jwks = jwks_client

    def validate(self, token: str) -> dict:
        import jwt
        try:
            key = self.jwks.get_signing_key_from_jwt(token).key
            claims = jwt.decode(token, key, algorithms=["RS256"], audience=self.cfg.audiences,
                                options={"require": ["exp", "iss", "aud", "tid"]})
        except Exception as e:  # noqa: BLE001 — every failure is the same answer to the caller: 401
            raise TokenError(f"invalid token: {type(e).__name__}") from e
        tid = str(claims.get("tid", "")).lower()
        if claims.get("iss") != f"{AUTHORITY}/{tid}/v2.0":
            raise TokenError("issuer does not match the token's tenant")
        if self.cfg.allowed_tenants and tid not in self.cfg.allowed_tenants:
            raise TokenError("tenant not allowed on this server")
        scopes = claims.get("scp")
        if not isinstance(scopes, str) or "user_impersonation" not in scopes.split():
            raise TokenError("user_impersonation delegated permission is required")
        return claims


class OnBehalfOf:
    """User token -> Fabric / SQL tokens for the same user, cached per (user token, scope)."""

    def __init__(self, cfg: EntraConfig, post=None) -> None:
        self.cfg = cfg
        self._post = post
        self._cache: dict[tuple[str, str], tuple[str, float]] = {}

    def _http_post(self, url: str, data: dict) -> dict:
        if self._post is not None:
            return self._post(url, data)
        import requests
        r = requests.post(url, data=data, timeout=15)
        if r.status_code != 200:
            body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            raise TokenError(f"on-behalf-of failed: {body.get('error', r.status_code)} — "
                             f"{(body.get('error_description') or '').splitlines()[0] if body else ''}".strip(" —"))
        return r.json()

    def token(self, user_token: str, tenant: str, scope: str) -> str:
        k = (hashlib.sha256(user_token.encode()).hexdigest(), scope)
        hit = self._cache.get(k)
        if hit and hit[1] - 120 > time.time():
            return hit[0]
        body = self._http_post(f"{AUTHORITY}/{tenant}/oauth2/v2.0/token", {
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "client_id": self.cfg.client_id, "client_secret": self.cfg.client_secret,
            "assertion": user_token, "scope": scope, "requested_token_use": "on_behalf_of",
        })
        self._cache[k] = (body["access_token"], time.time() + int(body.get("expires_in", 3600)))
        if len(self._cache) > 5000:                          # bounded: drop expired, then oldest
            now = time.time()
            self._cache = {kk: v for kk, v in self._cache.items() if v[1] > now} or {}
        return body["access_token"]


def admin_consent_url(cfg: EntraConfig, tenant: str = "organizations") -> str:
    """What a customer's Entra admin opens once, so their users can sign in and the app may call Fabric for them."""
    from urllib.parse import urlencode
    # This endpoint consents the app's configured permissions across resource APIs.
    # A v2 scope request cannot combine Fabric and SQL .default scopes.
    return f"{AUTHORITY}/{tenant}/adminconsent?" + urlencode({"client_id": cfg.client_id})
