"""Dynamic client registration for agents outside Claude (Lovable, Cursor, ...), behind KRUSGRAPH_DCR=1.

Off by default. With the flag off nothing in this module is served and sign-in for Claude is exactly as before.

Why a facade and not an authorization server of our own: Microsoft Entra ID has neither dynamic client registration
(RFC 7591) nor client ID metadata documents, and this server's promise is that it stores nothing. So, with the flag
on, the server publishes RFC 8414 authorization-server metadata at /.well-known/oauth-authorization-server whose
authorization and token endpoints are Entra's own, plus a registration endpoint (POST /oauth/register) that answers
an RFC 7591 request with the one Entra app's client id as a *public* client (PKCE, token_endpoint_auth_method
"none") when every redirect URI the request names is on KRUSGRAPH_DCR_REDIRECTS, the allow-list of URIs the
maintainer has registered on the Entra app (platform "Mobile and desktop applications" or "Web", public client flows
on). There is no client database, no secret is issued, and the tokens are Entra's and are validated as before.
docs/AUTH-DCR.md compares this with the alternatives and lists what the maintainer has to do on the Entra app.

Configuration (environment):
  KRUSGRAPH_DCR            1 / true / yes turns the facade on; anything else leaves the two routes unserved
  KRUSGRAPH_DCR_REDIRECTS  comma-separated redirect URIs allowed to register: exact https URIs, or a loopback origin
                           (http://127.0.0.1 or http://localhost, no path) that matches any port and path, as RFC 8252
                           section 7.3 allows for native apps
"""
from __future__ import annotations

import os
import time
from urllib.parse import urlsplit

from .entra import AUTHORITY, EntraConfig

MAX_REDIRECTS = 10
MAX_NAME = 80
MAX_BODY = 16 * 1024
LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")


def enabled() -> bool:
    return os.environ.get("KRUSGRAPH_DCR", "").strip().lower() in ("1", "true", "yes")


def allowed_redirects() -> list[str]:
    return [u.strip() for u in os.environ.get("KRUSGRAPH_DCR_REDIRECTS", "").split(",") if u.strip()]


def origin(cfg: EntraConfig) -> str:
    p = urlsplit(cfg.public_url)
    return f"{p.scheme}://{p.netloc}"


def is_loopback(uri: str) -> bool:
    p = urlsplit(uri)
    return p.scheme == "http" and p.hostname in LOOPBACK_HOSTS


def redirect_allowed(uri: str, allowed: list[str]) -> bool:
    """Exact match for https URIs; a loopback origin on the allow-list matches any port and path on that host."""
    p = urlsplit(uri)
    if p.fragment or not p.netloc:
        return False
    if is_loopback(uri):
        for a in allowed:
            q = urlsplit(a)
            if is_loopback(a) and q.hostname == p.hostname and (q.path in ("", "/") or a == uri):
                return True
        return False
    return p.scheme == "https" and uri in allowed


def authorization_server_metadata(cfg: EntraConfig) -> dict:
    """RFC 8414. The issuer is this server; the user still signs in at Entra, with the same app and scope."""
    base = f"{AUTHORITY}/organizations/oauth2/v2.0"
    return {
        "issuer": origin(cfg),
        "authorization_endpoint": f"{base}/authorize",
        "token_endpoint": f"{base}/token",
        "registration_endpoint": f"{origin(cfg)}/oauth/register",
        "jwks_uri": f"{AUTHORITY}/common/discovery/v2.0/keys",
        "scopes_supported": [cfg.scope, "offline_access"],
        "response_types_supported": ["code"],
        "response_modes_supported": ["query"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_methods_supported": ["none"],
        "code_challenge_methods_supported": ["S256"],
        "client_id_metadata_document_supported": False,
        "service_documentation": f"{origin(cfg)}/docs",
    }


def register(cfg: EntraConfig, body, allowed: list[str] | None = None) -> tuple[int, dict]:
    """RFC 7591 registration. The answer is the Entra app's public client id for the redirect URIs the request names,
    when every one of them is allowed; otherwise the RFC's error document. Returns (HTTP status, JSON body)."""
    allowed = allowed_redirects() if allowed is None else allowed
    if not isinstance(body, dict):
        return 400, {"error": "invalid_client_metadata", "error_description": "the request body must be a JSON object"}
    uris = body.get("redirect_uris")
    if not isinstance(uris, list) or not uris or len(uris) > MAX_REDIRECTS or not all(isinstance(u, str) for u in uris):
        return 400, {"error": "invalid_redirect_uri", "error_description": f"redirect_uris must list 1 to {MAX_REDIRECTS} URIs"}
    refused = [u for u in uris if not redirect_allowed(u, allowed)]
    if refused:
        return 400, {"error": "invalid_redirect_uri",
                     "error_description": "a redirect URI is not registered on this server's Entra app: " + ", ".join(refused[:3])
                     + ". The operator registers it on the app (an https URI, or a loopback origin for a desktop agent) and adds it to the allow-list."}
    grants = body.get("grant_types") or ["authorization_code"]
    if not isinstance(grants, list) or not grants or not set(grants) <= {"authorization_code", "refresh_token"}:
        return 400, {"error": "invalid_client_metadata", "error_description": "only authorization_code and refresh_token are supported"}
    out = {
        "client_id": cfg.client_id,
        "client_id_issued_at": int(time.time()),
        "redirect_uris": uris,
        "token_endpoint_auth_method": "none",
        "grant_types": sorted(set(grants) | {"refresh_token"}),
        "response_types": ["code"],
        "scope": f"{cfg.scope} offline_access",
    }
    name = body.get("client_name")
    if isinstance(name, str) and name.strip():
        out["client_name"] = name.strip()[:MAX_NAME]
    return 201, out
