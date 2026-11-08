"""The hosted Krusgraph Model editor on its own host name (n168; docs/WORKLOAD-DEV.md, "Hosted (no laptop)").

Fabric shows the workload's editor in an iframe loaded from the frontend URL in the workload package
(workload/scripts/build-package). For publishing, that URL must be a subdomain of the tenant's verified domain with at
most one extra path segment (docs/WORKLOAD-FEASIBILITY.md, sections 2 and 4), so the editor is served from
https://workload.krusgraph.com by the same container app that serves krusgraph.com.

With KRUSGRAPH_WORKLOAD_HOST set (e.g. workload.krusgraph.com), a request whose Host header is that name gets only:

  /workload/v1/*   the engine API (workload_api.py), handled by the app as on every host
  /close           the sign-in redirect page: an HTML page whose one script is window.close() [S9]
  everything else  the editor's production build (KRUSGRAPH_WORKLOAD_DIST, default /app/workload-dist, built by the
                   Dockerfile), with index.html for a path without a file extension (the editor's routes)

Never the website, /mcp, /healthz or the docs. Every other host name is passed to the app untouched, so krusgraph.com
keeps serving the site and /mcp exactly as before. With the variable unset nothing here is installed.

Headers on the workload host: Content-Security-Policy with frame-ancestors for Fabric's domains only, CORS headers only
for an Origin under *.fabric.microsoft.com or *.powerbi.com, HSTS with includeSubDomains, nosniff, and no Set-Cookie
(the editor gets its tokens from the Fabric host only [S9]; this host never sets a cookie).
"""
from __future__ import annotations

import base64
import hashlib
import html
import mimetypes
import os
from pathlib import Path

from .workload_api import FABRIC_ORIGIN, FRAME_ANCESTORS, PREFIX, cors_headers

HOST_ENV = "KRUSGRAPH_WORKLOAD_HOST"
DIST_ENV = "KRUSGRAPH_WORKLOAD_DIST"
DEFAULT_DIST = "/app/workload-dist"
SCOPE_META = "krusgraph-engine-scope"

CLOSE_SCRIPT = "window.close();"
CLOSE_HASH = "'sha256-" + base64.b64encode(hashlib.sha256(CLOSE_SCRIPT.encode()).digest()).decode() + "'"
CLOSE_HTML = ("<!doctype html><html><head><meta charset=\"utf-8\"><title>Signed in</title></head>"
              f"<body><script>{CLOSE_SCRIPT}</script></body></html>").encode()

# The editor (React, Fluent UI) loads its scripts from this host only; Fluent injects styles at run time, and the editor
# calls Fabric's APIs and OneLake from the browser, so connect-src and style-src stay open to what the starter kit needs.
EDITOR_CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https:; "
              "font-src 'self' data: https:; connect-src 'self' https:; object-src 'none'; base-uri 'self'; "
              f"form-action 'self'; frame-ancestors {FRAME_ANCESTORS}")
CLOSE_CSP = f"default-src 'none'; script-src {CLOSE_HASH}; base-uri 'none'; form-action 'none'; frame-ancestors {FRAME_ANCESTORS}"
HOST_HEADERS = {
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
}
# The server's own paths that never belong to the editor: a clear 404 on the workload host, not the editor's page.
SITE_ONLY = {"mcp", ".well-known", "oauth", "healthz", "health", "metrics", "docs", "static", "check", "privacy", "blog"}
TYPES = {".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".html": "text/html; charset=utf-8",
         ".json": "application/json", ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon",
         ".woff": "font/woff", ".woff2": "font/woff2", ".map": "application/json", ".txt": "text/plain; charset=utf-8"}


def configured_host() -> str:
    """The workload host name from the environment, lower case, without port or scheme; "" when unset."""
    value = os.environ.get(HOST_ENV, "").strip().lower()
    for prefix in ("https://", "http://"):
        value = value.removeprefix(prefix)
    value = value.split("/")[0].split(":")[0]
    if value and not all(c.isalnum() or c in ".-" for c in value):
        raise ValueError(f"{HOST_ENV} must be a host name such as workload.krusgraph.com")
    return value


def engine_scope() -> str:
    """The scope the hosted editor asks the Fabric host for, from the server's own workload settings (entra.WorkloadConfig):
    <KRUSGRAPH_WORKLOAD_APP_ID_URI>/<KRUSGRAPH_WORKLOAD_SCOPE>. Injected into index.html, so the image needs no rebuild
    when the Entra app changes."""
    uri = os.environ.get("KRUSGRAPH_WORKLOAD_APP_ID_URI", "").strip().rstrip("/")
    scope = os.environ.get("KRUSGRAPH_WORKLOAD_SCOPE", "").strip() or "user_impersonation"
    return f"{uri}/{scope}" if uri else ""


def request_host(scope) -> str:
    for key, value in scope.get("headers") or []:
        if key == b"host":
            return value.decode("latin-1").strip().lower().split(":")[0]
    return ""


class Editor:
    """The editor's build directory: files under it, and index.html with the engine scope injected."""

    def __init__(self, dist: Path) -> None:
        self.dist = dist.resolve()

    def file(self, path: str) -> Path | None:
        rel = path.lstrip("/")
        if not rel or rel.endswith("/"):
            return None
        target = (self.dist / rel).resolve()
        if self.dist not in target.parents or not target.is_file():
            return None
        return target

    def index(self) -> bytes | None:
        index = self.dist / "index.html"
        if not index.is_file():
            return None
        body = index.read_text(encoding="utf-8")
        meta = f'<meta name="{SCOPE_META}" content="{html.escape(engine_scope(), quote=True)}">'
        body = body.replace("<head>", "<head>" + meta, 1) if "<head>" in body else meta + body
        return body.encode("utf-8")


def wrap(app, host: str | None = None, dist: Path | None = None):
    """The ASGI wrapper. `host` and `dist` default to the environment; with no host the app is returned unchanged."""
    host = configured_host() if host is None else host
    if not host:
        return app
    editor = Editor(dist or Path(os.environ.get(DIST_ENV, "").strip() or DEFAULT_DIST))

    async def answer(scope, receive, send, status: int, body: bytes, content_type: str, csp: str, cache: str):
        origin = None
        for key, value in scope.get("headers") or []:
            if key == b"origin":
                origin = value.decode("latin-1")
        headers = {**HOST_HEADERS, "Content-Security-Policy": csp, "Cache-Control": cache, "Content-Type": content_type,
                   "Content-Length": str(len(body)), **cors_headers(origin)}
        if "Access-Control-Allow-Methods" in headers:
            headers["Access-Control-Allow-Methods"] = "GET, HEAD, OPTIONS"
        await send({"type": "http.response.start", "status": status,
                    "headers": [(k.lower().encode(), v.encode("latin-1")) for k, v in headers.items()]})
        await send({"type": "http.response.body", "body": b"" if scope.get("method") == "HEAD" else body})

    async def through(scope, receive, send):
        """The engine API on the workload host: the app's own answer, with this host's HSTS and never a cookie."""
        async def send_clean(message):
            if message["type"] == "http.response.start":
                drop = (b"set-cookie", b"strict-transport-security", b"referrer-policy")
                kept = [(k, v) for k, v in message.get("headers") or [] if k.lower() not in drop]
                kept += [(b"strict-transport-security", HOST_HEADERS["Strict-Transport-Security"].encode()),
                         (b"referrer-policy", HOST_HEADERS["Referrer-Policy"].encode())]
                message = {**message, "headers": kept}
            await send(message)
        await app(scope, receive, send_clean)

    async def wrapped(scope, receive, send):
        if scope["type"] != "http" or request_host(scope) != host:
            return await app(scope, receive, send)
        path = scope.get("path") or "/"
        if path == PREFIX or path.startswith(PREFIX + "/"):
            return await through(scope, receive, send)
        method = scope.get("method", "GET")
        if path.rstrip("/").split("/")[1:2] and path.rstrip("/").split("/")[1] in SITE_ONLY:
            return await answer(scope, receive, send, 404, b"not found", "text/plain; charset=utf-8", EDITOR_CSP, "no-store")
        if method == "OPTIONS":
            return await answer(scope, receive, send, 204, b"", "text/plain", EDITOR_CSP, "no-store")
        if method not in ("GET", "HEAD"):
            return await answer(scope, receive, send, 405, b"method not allowed", "text/plain; charset=utf-8", EDITOR_CSP, "no-store")
        if path.rstrip("/") == "/close":
            return await answer(scope, receive, send, 200, CLOSE_HTML, "text/html; charset=utf-8", CLOSE_CSP, "no-store")
        found = editor.file(path)
        if found is not None and found.name != "index.html":
            suffix = found.suffix.lower()
            kind = TYPES.get(suffix) or mimetypes.guess_type(found.name)[0] or "application/octet-stream"
            hashed = suffix in (".js", ".css") and "." in found.stem       # bundle.<hash>.js never changes
            cache = "public, max-age=31536000, immutable" if hashed else "public, max-age=300"
            return await answer(scope, receive, send, 200, found.read_bytes(), kind, EDITOR_CSP, cache)
        last = path.rstrip("/").rsplit("/", 1)[-1]
        if "." in last:                                                   # a missing file, not an editor route
            return await answer(scope, receive, send, 404, b"not found", "text/plain; charset=utf-8", EDITOR_CSP, "no-store")
        index = editor.index()
        if index is None:
            return await answer(scope, receive, send, 503, b"the editor is not in this image", "text/plain; charset=utf-8",
                                EDITOR_CSP, "no-store")
        return await answer(scope, receive, send, 200, index, "text/html; charset=utf-8", EDITOR_CSP, "no-cache")
    return wrapped


def same_host_origin(origin: str | None) -> bool:
    """True for the editor's own origin (https://<KRUSGRAPH_WORKLOAD_HOST>): its calls to /workload/v1 are same-origin."""
    host = configured_host()
    return bool(origin and host and origin.lower().rstrip("/") == f"https://{host}")


__all__ = ["wrap", "configured_host", "engine_scope", "same_host_origin", "CLOSE_HTML", "CLOSE_CSP", "EDITOR_CSP",
           "FABRIC_ORIGIN"]
