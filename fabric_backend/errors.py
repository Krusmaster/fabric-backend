"""Tool errors a user can act on.

Every MCP tool runs inside `safe()`. Whatever Fabric, Entra or the SQL endpoint throws is turned into one JSON
answer with three keys: `error` (what happened, in plain words), `kind` (a stable code) and `hint` (what to do
next). Nothing else leaves the server: no tokens, no request headers, no stack traces. Fabric's own message is
quoted only after `scrub()`, which strips anything that looks like a bearer token and caps the length.

Kinds: sign_in, consent, no_access, not_found, capacity, source_not_ready, schema_not_found, table_not_found,
column_not_found, sql_sign_in, timeout, unreachable, throttled, fabric_unavailable, unsupported, bad_input, server_config,
fabric_error, sql_error, unexpected; and two the server's own tool wrapper answers with: rate_limited (limits.py, with
retry_after in seconds) and upgrade (entitlements.py, off unless KRUSGRAPH_ENTITLEMENTS=1).
"""
from __future__ import annotations

import functools
import inspect
import json
import os
import re
import socket

_TOKEN = re.compile(r"(?:eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{4,}|[Bb]earer\s+[A-Za-z0-9._~+/=-]{8,})")
_HEADERISH = re.compile(r"(?i)(authorization|x-fabric-sql-token|client_secret|secret)\s*[:=]\s*[^\n]+")
MAX = 300

HINTS = {
    "sign_in": "Sign in again in your MCP client (in Claude: Settings → Connectors → the connector → Reconnect). The sign-in has expired or was rejected.",
    "consent": "An administrator of your Microsoft Entra organisation has to grant consent once, then sign in again.",
    "mfa": "Your organisation requires multi-factor authentication for this app. Sign in again in your MCP client and complete it.",
    "no_access": "The signed-in account cannot open it. Ask for access to the workspace (Viewer is enough to plan, Contributor to create), then try again.",
    "not_found": "Check the workspace id and the source name: list_sources shows what the signed-in account can see.",
    "capacity": "The workspace needs an active Fabric capacity (a trial capacity is fine). Assign one, or resume the paused one, and try again.",
    "source_not_ready": "Fabric is still provisioning the SQL analytics endpoint for this source. Wait a minute and try again.",
    "schema_not_found": "Use list_tables with another schema; a lakehouse's default schema is 'dbo' unless it was created with schemas. "
                        "Tables created minutes ago may not be in the SQL analytics endpoint yet: open the endpoint in Fabric and refresh its metadata.",
    "table_not_found": "Check the table name in the SQL analytics endpoint. A table created minutes ago may not be exposed there yet: open the "
                       "endpoint in Fabric and refresh its metadata, then try again.",
    "column_not_found": "Check the column names: the keys you passed must exist in the table.",
    "sql_sign_in": "The SQL analytics endpoint refused the sign-in. Sign in again in your MCP client; if it persists, the account lacks access to the item.",
    "timeout": "Fabric or the SQL endpoint did not answer in time. Try again; a paused capacity or a cold SQL endpoint can cause this.",
    "unreachable": "The server could not reach Fabric. Try again in a moment.",
    "throttled": "Fabric is rate-limiting requests. Wait a little and try again.",
    "fabric_unavailable": "Fabric answered with a server error. Try again in a few minutes.",
    "unsupported": "Choose a lakehouse, warehouse, SQL database or mirrored database as the source.",
    "bad_input": "Check the keys and confirmed you passed: table and column names must match list_tables (case does not matter).",
    "server_config": "This is a configuration problem on the connector itself, not with your account. Contact the operator.",
    "fabric_error": "Check the message from Fabric above; list_sources and list_tables show what the account can see.",
    "sql_error": "Check the message from the SQL analytics endpoint above.",
    "unexpected": "Try again. If it keeps failing, report the kind and the message to the operator.",
    "rate_limited": "Wait the number of seconds in retry_after and try again.",
    "upgrade": "This feature is part of the paid plan; the hint names the page with the plans.",
}


def scrub(text: str, limit: int = MAX) -> str:
    """Remove anything that looks like a token or a secret-bearing header, collapse whitespace, cap the length."""
    s = _TOKEN.sub("[token removed]", str(text or ""))
    s = _HEADERISH.sub(r"\1: [removed]", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= limit else s[:limit - 1] + "…"


def _fabric_body(text: str) -> tuple[str, str]:
    """(errorCode, message) from a Fabric error body, or ("", scrubbed text)."""
    try:
        body = json.loads(text or "")
    except ValueError:
        return "", scrub(text)
    if isinstance(body, dict):
        err = body.get("error") if isinstance(body.get("error"), dict) else body
        code = str(err.get("errorCode") or err.get("code") or "")
        msg = str(err.get("message") or err.get("error_description") or "")
        return code, scrub(msg)
    return "", scrub(text)


FIRST_TIME = ("sign_in", "consent", "mfa", "no_access", "capacity", "schema_not_found", "sql_sign_in")   # what a new user meets first


def docs_url(anchor: str = "") -> str:
    """The operator's docs page (the origin of MCP_PUBLIC_URL; krusgraph.com when unset), with an anchor."""
    origin = os.environ.get("MCP_PUBLIC_URL", "https://krusgraph.com/mcp").split("/mcp")[0].rstrip("/") or "https://krusgraph.com"
    return f"{origin}/docs" + (f"#{anchor}" if anchor else "")


def _answer(kind: str, error: str) -> dict:
    hint = HINTS.get(kind, HINTS["unexpected"])
    if kind in FIRST_TIME:
        hint += f" Step by step: {docs_url('first-time-errors')}"
    return {"error": error, "kind": kind, "hint": hint}


def classify_http(status: int, body_text: str = "", where: str = "the request") -> dict:
    """A Fabric REST status (and body) → answer."""
    code, msg = _fabric_body(body_text)
    blob = f"{code} {msg}".lower()
    if status == 401:
        return _answer("sign_in", f"Fabric did not accept the sign-in for {where} (HTTP 401).")
    if re.search(r"capacity", blob) and re.search(r"paus|not active|inactive|suspend|not assigned|no capacity|not on|unavailable|notoncapacity|notactive", blob):
        return _answer("capacity", f"The workspace has no active Fabric capacity: {msg or code}.")
    if status == 403:
        return _answer("no_access", f"The signed-in account has no access to {where} (HTTP 403{(': ' + msg) if msg else ''}).")
    if status == 404:
        return _answer("not_found", f"{where[0].upper() + where[1:]} was not found (HTTP 404{(': ' + msg) if msg else ''}).")
    if status == 429:
        return _answer("throttled", f"Fabric is throttling {where} (HTTP 429).")
    if status >= 500:
        return _answer("fabric_unavailable", f"Fabric answered HTTP {status} for {where}{(': ' + msg) if msg else ''}.")
    return _answer("fabric_error", f"Fabric answered HTTP {status} for {where}{(': ' + (msg or code)) if (msg or code) else ''}.")


def _aadsts(text: str) -> dict | None:
    """Entra error codes that mean something specific to the user."""
    m = re.search(r"AADSTS(\d+)", text)
    code = m.group(1) if m else ""
    low = text.lower()
    if code == "65001" or "consent" in low:
        return _answer("consent", "Your organisation has not consented to this app yet (Entra AADSTS65001).")
    if code in ("50076", "50079", "50074", "53003") or "multi-factor" in low or "conditional access" in low:
        return _answer("mfa", f"Your organisation's sign-in policy blocked the token exchange (Entra AADSTS{code}).")
    if code in ("7000215", "7000222", "700016", "90002", "700025"):
        return _answer("server_config", f"The connector's own Entra registration was rejected (AADSTS{code}).")
    if code in ("50058", "50173", "70008", "700082", "500133", "50013", "50027"):
        return _answer("sign_in", f"The sign-in has expired or was revoked (Entra AADSTS{code}).")
    return None


def _sql(exc: Exception, where: str) -> dict | None:
    """pyodbc-style errors, by message, so the mapping does not need the driver installed."""
    text = scrub(str(exc))
    low = text.lower()
    name = type(exc).__name__
    sqlish = type(exc).__module__.startswith("pyodbc") or name in ("OperationalError", "ProgrammingError", "InterfaceError", "DatabaseError", "DataError")
    if not sqlish and not re.search(r"\[(?:SQL Server|ODBC)", text) and "hyt00" not in low:
        return None
    if "invalid object name" in low or "42s02" in low:
        return _answer("table_not_found", f"The SQL analytics endpoint has no such table for {where}: {text}")
    if "invalid column name" in low or "42s22" in low:
        return _answer("column_not_found", f"The SQL analytics endpoint has no such column for {where}: {text}")
    if "login failed" in low or "18456" in low or "28000" in low:
        return _answer("sql_sign_in", f"The SQL analytics endpoint refused the sign-in for {where}.")
    if "timeout" in low or "hyt00" in low or "hyt01" in low:
        return _answer("timeout", f"The SQL analytics endpoint timed out for {where}.")
    if "cannot open database" in low or "4060" in low or "cannot open server" in low:
        return _answer("not_found", f"The SQL analytics endpoint has no such database for {where}: {text}")
    if "08001" in low or "08s01" in low or "could not open a connection" in low or "unable to connect" in low:
        return _answer("unreachable", f"The server could not reach the SQL analytics endpoint for {where}.")
    return _answer("sql_error", f"The SQL analytics endpoint answered with an error for {where}: {text}")


class SchemaEmpty(LookupError):
    """INFORMATION_SCHEMA returned no tables: the schema does not exist in this source (or has no tables)."""


def explain(exc: BaseException, where: str = "the request") -> dict:
    """Any exception from a tool → the answer the user sees. Never includes headers, tokens or a traceback."""
    try:
        import requests
        req_exc: tuple = (requests.exceptions.RequestException,)
        timeout_exc: tuple = (requests.exceptions.Timeout,)
        conn_exc: tuple = (requests.exceptions.ConnectionError,)
        http_exc: tuple = (requests.exceptions.HTTPError,)
    except ImportError:  # pragma: no cover
        req_exc = timeout_exc = conn_exc = http_exc = ()
    text = scrub(str(exc))
    low = text.lower()
    if isinstance(exc, SchemaEmpty):
        return _answer("schema_not_found", text)
    if type(exc).__name__ == "PlanInputError":
        return _answer("bad_input", text)
    if isinstance(exc, PermissionError):
        return _answer("sign_in", "No signed-in user on this request.")
    if type(exc).__name__ == "KeyVaultError":
        return _answer("server_config", f"The connector could not read its own sign-in secret from Azure Key Vault: {text}")
    if type(exc).__name__ == "TokenError":
        hit = _aadsts(text)
        if hit:
            return hit
        if "on-behalf-of" in low:
            return _answer("sign_in", f"The sign-in could not be exchanged for a Fabric token: {text}")
        return _answer("sign_in", "The sign-in on this request is not valid any more.")
    if isinstance(exc, timeout_exc) or isinstance(exc, (socket.timeout, TimeoutError)):
        return _answer("timeout", f"Fabric did not answer in time for {where}.")
    if isinstance(exc, http_exc):
        resp = getattr(exc, "response", None)
        status = getattr(resp, "status_code", 0) or 0
        body = getattr(resp, "text", "") or ""
        return classify_http(int(status), body, where)
    if isinstance(exc, conn_exc):
        return _answer("unreachable", f"The server could not reach Fabric for {where}.")
    if isinstance(exc, req_exc):
        return _answer("unreachable", f"The request to Fabric failed for {where}: {type(exc).__name__}.")
    if isinstance(exc, ImportError) and "pyodbc" in low:
        return _answer("server_config", "The SQL driver is not installed on this server.")
    sql = _sql(exc, where)
    if sql:
        return sql
    if isinstance(exc, RuntimeError):
        if "no sql" in low or "sql analytics endpoint yet" in low or "no sql endpoint" in low:
            return _answer("source_not_ready", text)
        if "no bearer token" in low or "no fabric_tenant_id" in low:
            return _answer("server_config", "The connector has no sign-in and no service principal configured.")
        if "fabric_odbc" in low:
            return _answer("server_config", text)
        return _answer("fabric_error", text)
    if isinstance(exc, LookupError):
        return _answer("not_found", text)
    if isinstance(exc, ValueError) and "cannot expose item type" in low:
        return _answer("unsupported", text)
    if isinstance(exc, KeyError):
        return _answer("fabric_error", f"Fabric's answer for {where} was missing {text}.")
    return _answer("unexpected", f"{type(exc).__name__} while handling {where}: {text}" if text else f"{type(exc).__name__} while handling {where}.")


def where_from(fn, args, kwargs) -> str:
    """'workspace X, source Y, schema Z' from the tool's own arguments, for the messages."""
    try:
        bound = inspect.signature(fn).bind_partial(*args, **kwargs).arguments
    except TypeError:
        bound = dict(kwargs)
    parts = [f"{k} {bound[k]!r}" for k in ("workspace", "source", "api", "schema", "name") if bound.get(k) not in (None, "")]
    return ", ".join(parts) if parts else "the request"


def safe(fn):
    """Decorator for MCP tools: exceptions become the JSON answer; the signature stays intact for the schema."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 — every failure gets the same treatment: explained, never leaked
            answer = explain(exc, where_from(fn, args, kwargs))
            if os.environ.get("KRUSGRAPH_DEBUG_ERRORS"):
                answer["debug"] = f"{type(exc).__module__}.{type(exc).__name__}"
            return json.dumps(answer, indent=2)
    return wrapper
