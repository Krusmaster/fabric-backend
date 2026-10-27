"""Client registration for MCP clients other than Claude (VS Code, Cursor, Glama, ...), behind KRUSGRAPH_CLIENT_REGISTRATION=1.

Off by default. With the flag off nothing here is served, and with it on Claude's sign-in is still exactly as before:
Claude keeps https://<domain>/mcp, whose protected resource metadata names Entra as before. The clients that register
themselves use a second address for the same server, https://<domain>/mcp/connect, whose metadata names this server's
own authorization server, https://<domain>/oauth. Why a second address: a client picks the authorization server from
the resource's metadata, so one address cannot send Claude to Entra and VS Code to /oauth, and Claude's pre-registered
credentials are bound to Entra's issuer (MCP 2026-07-28, client-registration "Authorization Server Binding").

Microsoft Entra ID has neither client ID metadata documents (CIMD) nor dynamic client registration (RFC 7591), so
/oauth is a thin authorization server in front of the one Entra app:
  1. the client names itself with a CIMD URL (preferred; MCP 2026-07-28 lists DCR as deprecated) or, when
     KRUSGRAPH_CLIENT_REGISTRATION_DCR=1, with a client id from POST /oauth/register (signed by this server, nothing
     stored); only public clients, no secret is ever issued;
  2. GET /oauth/authorize checks the client, the exact redirect address (https, or http://localhost / 127.0.0.1 with
     any port), PKCE S256 and the resource (an error here is a page on this server, never a redirect to a client
     nobody has approved), then shows Krusgraph's own consent page for that client: its name, its domain and where
     the answer goes. Because every client shares one Entra app, Entra's consent cannot tell them apart; this page is
     what stops a client the user never chose from riding on an earlier Entra consent (the confused deputy in MCP's
     Security Best Practices). The approval is remembered per user and client for an https redirect address, and
     asked again at every sign-in for a program on the user's computer (a loopback address);
  3. only after the approval does the browser go to Entra, with this server's own redirect address (/oauth/callback,
     the one address the operator adds to the Entra app), its own state and its own PKCE;
  4. /oauth/callback redeems Entra's code, checks the token exactly as /mcp does (audience = this app, issuer per
     tenant, user_impersonation, allowed tenants), and hands the client a one-time code of its own;
  5. POST /oauth/token gives the client, for its code and PKCE verifier, the Entra access token for this app (the
     same kind of token Claude holds) and a refresh token of this server's own that rotates at every use.
The MCP endpoint validates every token as before; no token is passed on to Fabric (the on-behalf-of exchange gets
separate ones), and a token for any other audience is refused.

Configuration (environment):
  KRUSGRAPH_CLIENT_REGISTRATION       1 / true / yes / on turns it on; anything else leaves every route here unserved
  KRUSGRAPH_REGISTRATION_KEY          32 random bytes, base64 (`openssl rand -base64 32`): encrypts the Entra tokens
                                      while this server holds them, signs cookies and DCR client ids, keys user hashes
  KRUSGRAPH_REGISTRATION_KEY_KEYVAULT_URI   or read that key from Azure Key Vault (keyvault.py; same identity)
  KRUSGRAPH_REGISTRATION_STORE        `memory` (one replica) or https://<account>.table.core.windows.net/<table>
                                      (registration_store.py)
  KRUSGRAPH_CLIENT_REGISTRATION_DCR   1 also serves POST /oauth/register (dynamic client registration, strict)
  KRUSGRAPH_REGISTRATION_CLIENT_DOMAINS  optional comma list of hosts allowed as CIMD client ids; empty = any https host
  KRUSGRAPH_REGISTRATION_RATE_IP / _RATE_CLIENT / _RATE_REGISTER   limits per network (IPv6 per /64), per client and
                                      network, and for registrations: 60/minute,600/hour; 300/minute,6000/hour; 10/hour
A configuration that is switched on but incomplete leaves the layer off and says why on stderr: Claude's sign-in
never depends on it.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import socket
import sys
import threading
import time
import unicodedata
from dataclasses import dataclass
from urllib.parse import unquote, urlsplit

CONNECT_PATH = "/mcp/connect"
ISSUER_PATH = "/oauth"
TXN_TTL = 600                          # a sign-in on its way through Entra
CODE_TTL = 60                          # an authorization code of this server's
USED_TTL = 600                         # remembering that a code or a consent form was used
CONSENT_TTL = 180 * 86400              # a remembered approval (and the cookie that says who approved)
FAMILY_TTL = 90 * 86400                # a refresh token line, at most (Entra's own refresh tokens last up to 90 days)
MAX_CIMD_BYTES = 5 * 1024              # draft-ietf-oauth-client-id-metadata-document: read at most 5 kilobytes
CIMD_CACHE_DEFAULT, CIMD_CACHE_MAX, CIMD_CACHE_ENTRIES = 300, 3600, 500
MAX_REDIRECTS = 10
MAX_NAME = 60
LOOPBACK_HOSTS = ("localhost", "127.0.0.1")
ALLOWED_SCOPES_IGNORED = {"openid", "profile", "email"}          # harmless OIDC scopes some clients add; never forwarded
CHALLENGE_RE = re.compile(r"[A-Za-z0-9_-]{43}")                  # base64url of a SHA-256: S256 challenges only (fullmatch)
VERIFIER_RE = re.compile(r"[A-Za-z0-9._~-]{43,128}")             # RFC 7636 section 4.1 (fullmatch)
TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{16,128}")                  # this server's own state values and refresh-line ids
DNS_NAME_RE = re.compile(r"(?i)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?")
FETCH_DEADLINE = 6.0                   # seconds for a whole metadata fetch, the name lookup included
FETCH_SLOTS = 4                        # metadata fetches at the same time, per replica (errors are never cached: CIMD draft)
# Per client is generous on purpose: a CIMD client id (VS Code's) is shared by every user of that program, so a tight
# bucket would let anyone lock all of them out; it caps a runaway client, the per-network bucket does the rest.
DEFAULT_RATE_IP, DEFAULT_RATE_CLIENT, DEFAULT_RATE_REGISTER = "60/minute,600/hour", "300/minute,6000/hour", "10/hour"


def enabled() -> bool:
    return os.environ.get("KRUSGRAPH_CLIENT_REGISTRATION", "").strip().lower() in {"1", "true", "yes", "on"}


def dcr_enabled() -> bool:
    return os.environ.get("KRUSGRAPH_CLIENT_REGISTRATION_DCR", "").strip().lower() in {"1", "true", "yes", "on"}


def b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def unb64u(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def s256(verifier: str) -> str:
    return b64u(hashlib.sha256(verifier.encode("ascii")).digest())


# ------------------------------------------------------------------ the server's key ------------------------------

class Keys:
    """Everything secret this layer needs, derived (HKDF-SHA256) from one 32-byte key the operator sets: AES-GCM for
    the Entra tokens while they sit in the store, HMAC for signed values, and a keyed hash for user ids. A new key
    makes every stored token, remembered approval and DCR client id unreadable, which only means signing in again."""

    def __init__(self, source) -> None:
        self._source = source                             # callable -> the key as text (env value or Key Vault)
        self._derived: tuple[str, dict[str, bytes]] | None = None
        self._lock = threading.Lock()

    @staticmethod
    def decode(text: str) -> bytes:
        raw = (text or "").strip()
        try:
            key = base64.b64decode(raw + "=" * (-len(raw) % 4), altchars=b"-_" if ("-" in raw or "_" in raw) else None,
                                   validate=True)
        except (ValueError, TypeError) as e:
            raise ValueError("KRUSGRAPH_REGISTRATION_KEY must be base64 (openssl rand -base64 32)") from e
        if len(key) < 32:
            raise ValueError("KRUSGRAPH_REGISTRATION_KEY must be at least 32 random bytes (openssl rand -base64 32)")
        return key

    def _sub(self, label: str) -> bytes:
        text = self._source()
        with self._lock:
            if self._derived is None or self._derived[0] != text:
                from cryptography.hazmat.primitives import hashes
                from cryptography.hazmat.primitives.kdf.hkdf import HKDF
                master = self.decode(text)
                subs = {}
                for name in ("seal", "sign", "user"):
                    subs[name] = HKDF(algorithm=hashes.SHA256(), length=32, salt=None,
                                      info=b"krusgraph client registration/" + name.encode()).derive(master)
                self._derived = (text, subs)
            return self._derived[1][label]

    def seal(self, purpose: str, data: dict) -> str:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        nonce = secrets.token_bytes(12)
        return b64u(nonce + AESGCM(self._sub("seal")).encrypt(nonce, json.dumps(data).encode(), purpose.encode()))

    def open(self, purpose: str, sealed: str) -> dict | None:
        from cryptography.exceptions import InvalidTag
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        try:
            raw = unb64u(sealed)
            return json.loads(AESGCM(self._sub("seal")).decrypt(raw[:12], raw[12:], purpose.encode()))
        except (InvalidTag, ValueError, TypeError):
            return None

    def sign(self, purpose: str, payload: dict, ttl: int | None) -> str:
        body = dict(payload)
        if ttl:
            body["exp"] = int(time.time()) + ttl
        text = b64u(json.dumps(body, separators=(",", ":")).encode())
        mac = hmac.new(self._sub("sign"), f"{purpose}.{text}".encode(), hashlib.sha256).digest()
        return f"{text}.{b64u(mac)}"

    def verify(self, purpose: str, token: str | None) -> dict | None:
        if not isinstance(token, str) or token.count(".") != 1 or len(token) > 8192:
            return None
        text, mac = token.split(".")
        want = hmac.new(self._sub("sign"), f"{purpose}.{text}".encode(), hashlib.sha256).digest()
        try:
            if not hmac.compare_digest(unb64u(mac), want):
                return None
            body = json.loads(unb64u(text))
        except (ValueError, TypeError):
            return None
        if not isinstance(body, dict) or ("exp" in body and not (isinstance(body["exp"], int) and body["exp"] > time.time())):
            return None
        return body

    def user_key(self, tid: str, oid: str) -> str:
        """A keyed hash of the user (tenant id + object id): the same user gives the same value on every replica, and
        without the server's key the value cannot be turned back into the ids or matched against them."""
        return hmac.new(self._sub("user"), f"{tid.lower()}:{oid.lower()}".encode(), hashlib.sha256).hexdigest()[:40]


def keys_from_env() -> Keys:
    uri = os.environ.get("KRUSGRAPH_REGISTRATION_KEY_KEYVAULT_URI", "").strip()
    if uri:
        from .keyvault import SecretReader
        try:
            reader = SecretReader(uri)
        except ValueError as e:
            raise ValueError("KRUSGRAPH_REGISTRATION_KEY_KEYVAULT_URI must look like https://<vault>.vault.azure.net/secrets/<name>") from e
        return Keys(reader.get)
    value = os.environ.get("KRUSGRAPH_REGISTRATION_KEY", "")
    Keys.decode(value)                                     # a missing or short key is a configuration error now
    return Keys(lambda: value)


# ------------------------------------------------------------------ redirect addresses ----------------------------

def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]"))
        return True
    except ValueError:
        return False


def dns_name(netloc: str) -> str | None:
    """The host of an authority that is a plain DNS name (letters, digits, hyphens, dots; a letter in the last label),
    with an optional numeric port; None for anything else (IP literals, percent-encoding, odd characters). What this
    returns is safe to put in a header such as Content-Security-Policy."""
    host, _, port = netloc.partition(":")
    if not DNS_NAME_RE.fullmatch(host) or len(host) > 253 or (port and not (port.isdigit() and 0 < int(port) < 65536)):
        return None
    return host.lower()


def origin_of(uri: str) -> str:
    """scheme://host[:port] of an address that passed redirect_problem, rebuilt from its checked parts."""
    p = urlsplit(uri)
    return f"{p.scheme}://{p.hostname}" + (f":{p.port}" if p.port else "")


def is_loopback(uri: str) -> bool:
    try:
        p = urlsplit(uri)
        p.port                                            # an invalid port raises here
    except ValueError:
        return False
    return p.scheme == "http" and p.hostname in LOOPBACK_HOSTS


def redirect_problem(uri) -> str | None:
    """Why a redirect address is not acceptable, or None. Accepted: https://<a DNS name>/... and, for programs on the
    user's own computer, http://localhost or http://127.0.0.1 with any port (RFC 8252 section 7.3). Never a wildcard,
    a fragment, credentials in the address, http to any other host, or another scheme."""
    if not isinstance(uri, str) or not uri or len(uri) > 2000 or not uri.isascii():
        return "a redirect address must be a URL of at most 2000 ASCII characters"
    if any(c in uri for c in " \t\r\n\\*<>\"{}|^`"):
        return "wildcards, spaces and quotes are not allowed in a redirect address"
    try:
        p = urlsplit(uri)
        port = p.port
    except ValueError:
        return "the redirect address has an invalid port"
    if "#" in uri:
        return "a redirect address may not contain a fragment"
    if "@" in p.netloc or p.username or p.password:
        return "a redirect address may not contain credentials"
    host = p.hostname or ""
    if p.scheme == "https":
        if dns_name(p.netloc) is None or host in LOOPBACK_HOSTS:
            return "an https redirect address needs a plain DNS name (not an IP address, localhost or encoded characters)"
        return None
    if p.scheme == "http":
        if host in LOOPBACK_HOSTS and p.netloc.split(":")[0].lower() == host:
            return None
        return "http is allowed only for http://localhost and http://127.0.0.1"
    return "only https and loopback (http://localhost, http://127.0.0.1) redirect addresses are allowed"


def redirect_matches(requested: str, registered: str) -> bool:
    """Exact string comparison, except that a loopback address matches on any port (RFC 8252 section 7.3,
    OAuth 2.1 section 8.4.2): scheme, host, path and query must still be identical."""
    if redirect_problem(requested) or redirect_problem(registered):
        return False
    if requested == registered:
        return True
    if not (is_loopback(requested) and is_loopback(registered)):
        return False
    a, b = urlsplit(requested), urlsplit(registered)
    return (a.scheme, a.hostname, a.path or "/", a.query) == (b.scheme, b.hostname, b.path or "/", b.query)


def redirect_key(uri: str) -> str:
    """The redirect address as kept with a consent. Only https addresses are remembered (see remembered())."""
    return uri


def remembered(uri: str) -> bool:
    """Whether an approval for this redirect address may be remembered. Not for loopback addresses: any program on the
    computer can listen on a local port and use a well-known client's id, so the page (with its warning) is shown at
    every sign-in to a program on this computer (MCP 2026-07-28, "Localhost Redirect URI Risks")."""
    return not is_loopback(uri)


# ------------------------------------------------------------------ clients -----------------------------------------

class ClientError(Exception):
    """The client cannot be accepted. Shown to the user on an error page, never sent to the redirect address."""


@dataclass(frozen=True)
class Client:
    client_id: str
    name: str
    kind: str                         # "cimd": its domain vouches for it; "dcr": it registered itself, nothing verified
    domain: str                       # the client id's host for CIMD; "" for DCR
    redirect_uris: tuple[str, ...]

    def allows(self, redirect_uri: str) -> bool:
        return any(redirect_matches(redirect_uri, r) for r in self.redirect_uris)


_INVISIBLE = re.compile("[\u200b-\u200f\u202a-\u202e\u2060-\u2069\ufeff]")
MAX_MARKS = 2                          # combining marks kept per base character (a stack of them can cover other text)


def clean_name(name) -> str:
    """A display name without control, formatting or direction characters, at most two combining marks per character,
    whitespace collapsed, at most 60 characters."""
    if not isinstance(name, str):
        return ""
    text = unicodedata.normalize("NFC", name)
    out, marks = [], 0
    for c in _INVISIBLE.sub("", text):
        cat = unicodedata.category(c)
        if cat[0] == "C" and c not in " \t":
            continue
        if cat in ("Mn", "Me"):
            marks += 1
            if marks > MAX_MARKS or not out:
                continue
        else:
            marks = 0
        out.append(c)
    return " ".join("".join(out).split())[:MAX_NAME].strip()


def client_id_problem(url) -> str | None:
    """Why a URL cannot be a CIMD client id here, or None (draft-ietf-oauth-client-id-metadata-document section 3,
    plus this server's policy: no explicit port, no query, a DNS name, not an IP address)."""
    if not isinstance(url, str) or len(url) > 512 or not url.isascii() or any(c in url for c in " \t\r\n\\"):
        return "the client id must be an https URL of at most 512 characters"
    try:
        p = urlsplit(url)
        port = p.port
    except ValueError:
        return "the client id URL has an invalid port"
    host = p.hostname or ""
    if p.scheme != "https" or not host:
        return "the client id must be an https URL"
    if "@" in p.netloc or p.username or p.password:
        return "the client id URL may not contain credentials"
    if port is not None or ":" in p.netloc:
        return "the client id URL may not name a port"
    if dns_name(p.netloc) is None or host in LOOPBACK_HOSTS:
        return "the client id URL needs a plain DNS name"
    if p.query or p.fragment or "#" in url or "?" in url:
        return "the client id URL may not have a query or a fragment"
    segments = p.path.split("/")
    if p.path in ("", "/") or any(unquote(s) in (".", "..") for s in segments):
        return "the client id URL needs a path, without . or .. segments"
    return None


def _special_address(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%")[0])
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped
    return not ip.is_global or ip.is_multicast or ip.is_reserved or ip.is_loopback or ip.is_link_local or ip.is_private


_fetch_slots = threading.BoundedSemaphore(FETCH_SLOTS)
_lookup_slots = threading.BoundedSemaphore(FETCH_SLOTS)
_lookups = None
_lookups_lock = threading.Lock()


def _lookup(resolve, host: str, port: int, deadline: float):
    """The name lookup, bounded in time: getaddrinfo has no timeout of its own, so it runs on a small pool and the
    caller stops waiting at the deadline. A lookup holds one of FETCH_SLOTS lookup slots until it really ends, so a slow
    DNS server can hold at most those threads and nothing queues up behind them (new lookups are refused instead)."""
    import concurrent.futures
    global _lookups
    with _lookups_lock:
        if _lookups is None:
            _lookups = concurrent.futures.ThreadPoolExecutor(max_workers=FETCH_SLOTS, thread_name_prefix="cimd-lookup")
    if not _lookup_slots.acquire(timeout=0.5):
        raise ClientError("the server is busy looking up other clients' domains; try again in a moment")

    def run():
        try:
            return resolve(host, port, type=socket.SOCK_STREAM)
        finally:
            _lookup_slots.release()
    try:
        future = _lookups.submit(run)
    except RuntimeError:
        _lookup_slots.release()
        raise
    try:
        return future.result(timeout=max(0.05, deadline - time.monotonic()))
    except concurrent.futures.TimeoutError as e:
        raise ClientError(f"the client's domain {host} did not resolve in time") from e
    except OSError as e:
        raise ClientError(f"the client's domain {host} could not be resolved") from e


def _cut(sock) -> None:
    try:
        sock.shutdown(socket.SHUT_RDWR)                  # wakes a read that is waiting on this socket in another thread
    except OSError:
        pass


def fetch_https(url: str, resolve=socket.getaddrinfo, ca_certs: str | None = None, port: int = 443) -> tuple[int, dict, bytes]:
    """GET one https URL the safe way for an address someone else chose (SSRF, MCP Security Best Practices and the
    CIMD draft section 6): every address the name resolves to must be a global unicast one, the connection goes to
    a vetted address (no second lookup an attacker could change; IPv4 first, then the others), the certificate must
    match the name, redirects are not followed, at most MAX_CIMD_BYTES + 1 bytes are read, and the whole fetch ends
    after FETCH_DEADLINE seconds however slowly the server sends: a timer shuts the socket at the deadline, so a
    server that drips its headers is cut off as surely as one that drips its body. At most FETCH_SLOTS run at once."""
    import http.client
    import os
    import certifi
    import urllib3
    from urllib3.connection import HTTPSConnection
    from urllib3.util.ssl_match_hostname import CertificateError
    if not _fetch_slots.acquire(timeout=1.0):
        raise ClientError("the server is busy fetching other clients' metadata; try again in a moment")
    try:
        deadline = time.monotonic() + FETCH_DEADLINE
        p = urlsplit(url)
        host = p.hostname or ""
        infos = _lookup(resolve, host, port, deadline)
        addresses = list(dict.fromkeys(info[4][0] for info in infos))
        if not addresses or any(_special_address(a) for a in addresses):
            raise ClientError(f"the client's domain {host} resolves to an address this server does not fetch from")
        addresses.sort(key=lambda a: ":" in a)                   # IPv4 first: the container may have no IPv6 route
        failure = "timeout"
        for address in addresses[:4]:
            left = deadline - time.monotonic()
            if left <= 0:
                break
            conn = HTTPSConnection(address, port, timeout=min(3.0, left), cert_reqs="CERT_REQUIRED",
                                   ca_certs=ca_certs or certifi.where(), assert_hostname=host, server_hostname=host)
            killer = timer = None
            try:
                conn.connect()                                    # TCP and TLS, the certificate checked against the name
                killer = socket.socket(fileno=os.dup(conn.sock.fileno()))
                timer = threading.Timer(max(0.0, deadline - time.monotonic()), _cut, args=(killer,))
                timer.daemon = True
                timer.start()
                conn.sock.settimeout(2.0)
                conn.request("GET", p.path or "/", headers={"Host": host, "Accept": "application/json",
                                                            "User-Agent": "Krusgraph (client metadata)"}, preload_content=False)
                r = conn.getresponse()
                chunks, size = [], 0
                while size <= MAX_CIMD_BYTES:
                    chunk = r.read1(MAX_CIMD_BYTES + 1 - size)       # whatever has arrived
                    if not chunk:
                        break
                    chunks.append(chunk)
                    size += len(chunk)
                if time.monotonic() >= deadline:
                    raise ClientError(f"the client's metadata at {url} took longer than {FETCH_DEADLINE:g} seconds")
                return r.status, {k.lower(): v for k, v in r.headers.items()}, b"".join(chunks)
            except (urllib3.exceptions.HTTPError, http.client.HTTPException, OSError, CertificateError) as e:
                if time.monotonic() >= deadline:
                    raise ClientError(f"the client's metadata at {url} took longer than {FETCH_DEADLINE:g} seconds") from e
                failure = type(e).__name__
            finally:
                if timer is not None:
                    timer.cancel()
                if killer is not None:
                    killer.close()
                conn.close()
        raise ClientError(f"the client's metadata at {url} could not be fetched ({failure})")
    finally:
        _fetch_slots.release()


def _cache_seconds(headers: dict) -> int:
    cc = (headers.get("cache-control") or "").lower()
    if "no-store" in cc or "no-cache" in cc or "private" in cc:
        return 0
    m = re.search(r"max-age\s*=\s*(\d+)", cc)
    return min(int(m.group(1)), CIMD_CACHE_MAX) if m else CIMD_CACHE_DEFAULT


def _same_site(redirect_host: str, client_host: str) -> bool:
    """An https redirect address must be on the client id's host or under it (vscode.dev -> vscode.dev, insiders.vscode.dev),
    so the domain shown on the consent page is also where the answer goes."""
    return redirect_host == client_host or redirect_host.endswith("." + client_host)


def client_from_document(url: str, doc) -> Client:
    """A Client from a fetched metadata document, or ClientError. Public clients only: no secret, no private_key_jwt."""
    if not isinstance(doc, dict):
        raise ClientError("the client's metadata is not a JSON object")
    if doc.get("client_id") != url:
        raise ClientError("the client's metadata names a different client id than its address")
    if "client_secret" in doc or "client_secret_expires_at" in doc:
        raise ClientError("the client's metadata contains a secret, which a metadata document may not")
    method = doc.get("token_endpoint_auth_method", "none")
    if method != "none":
        raise ClientError(f"this server accepts public clients only (token_endpoint_auth_method none), not {str(method)[:40]}")
    grants = doc.get("grant_types", ["authorization_code"])
    if not isinstance(grants, list) or "authorization_code" not in grants:
        raise ClientError("the client's metadata does not use the authorization code grant")
    responses = doc.get("response_types", ["code"])
    if not isinstance(responses, list) or "code" not in responses:
        raise ClientError("the client's metadata does not use response type code")
    name = clean_name(doc.get("client_name"))
    if not name:
        raise ClientError("the client's metadata has no client_name")
    uris = doc.get("redirect_uris")
    if not isinstance(uris, list) or not uris:
        raise ClientError("the client's metadata lists no redirect_uris")
    host = urlsplit(url).hostname or ""
    kept = tuple(u for u in uris[:20] if isinstance(u, str) and redirect_problem(u) is None
                 and (is_loopback(u) or _same_site(urlsplit(u).hostname or "", host)))
    if not kept:
        raise ClientError("none of the client's redirect addresses is https on its own domain or http://localhost / 127.0.0.1")
    return Client(url, name, "cimd", host, kept[:MAX_REDIRECTS])


class CimdResolver:
    """Client id URL -> Client: checks the URL, fetches the document (fetch_https), validates it, caches valid ones per
    their Cache-Control (5 minutes when silent, at most an hour; errors and invalid documents are never cached)."""

    def __init__(self, fetch=None, allow_domains: set[str] | None = None, clock=time.time) -> None:
        self._fetch = fetch or fetch_https
        self.allow_domains = {d.lower() for d in (allow_domains or set())}
        self.clock = clock
        self._cache: dict[str, tuple[Client, float]] = {}
        self._lock = threading.Lock()

    def resolve(self, url: str) -> Client:
        problem = client_id_problem(url)
        if problem:
            raise ClientError(problem)
        host = urlsplit(url).hostname or ""
        if self.allow_domains and host not in self.allow_domains:
            raise ClientError(f"clients from {host} are not accepted on this server")
        now = self.clock()
        with self._lock:
            hit = self._cache.get(url)
            if hit and hit[1] > now:
                return hit[0]
        try:
            status, headers, body = self._fetch(url)
        except ClientError:
            raise
        except Exception as e:  # noqa: BLE001 — any failure to fetch aborts the sign-in (CIMD draft: SHOULD abort)
            raise ClientError(f"the client's metadata at {url} could not be fetched ({type(e).__name__})") from e
        if status != 200:
            raise ClientError(f"the client's metadata at {url} answered HTTP {status}, not 200")
        if len(body) > MAX_CIMD_BYTES:
            raise ClientError("the client's metadata is larger than 5 KB")
        try:
            doc = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as e:
            raise ClientError("the client's metadata is not valid JSON") from e
        client = client_from_document(url, doc)
        ttl = _cache_seconds(headers)
        if ttl:
            with self._lock:
                if len(self._cache) >= CIMD_CACHE_ENTRIES:
                    for k in sorted(self._cache, key=lambda k: self._cache[k][1])[:CIMD_CACHE_ENTRIES // 2]:
                        del self._cache[k]
                self._cache[url] = (client, now + ttl)
        return client


DCR_PREFIX = "kgdcr."


def register(body, keys: Keys) -> tuple[int, dict]:
    """RFC 7591, strictly: public clients only (no secret is issued), the authorization code grant, 1 to 5 redirect
    addresses that pass redirect_problem. The client id carries the accepted metadata, signed with the server's key, so
    nothing is stored. Returns (HTTP status, JSON body)."""
    def bad(error: str, text: str) -> tuple[int, dict]:
        return 400, {"error": error, "error_description": text}

    if not isinstance(body, dict):
        return bad("invalid_client_metadata", "the request body must be a JSON object")
    uris = body.get("redirect_uris")
    if not isinstance(uris, list) or not 1 <= len(uris) <= 5 or not all(isinstance(u, str) for u in uris):
        return bad("invalid_redirect_uri", "redirect_uris must list 1 to 5 addresses")
    for u in uris:
        problem = redirect_problem(u) or ("a registered redirect address may be at most 500 characters" if len(u) > 500 else None)
        if problem:
            return bad("invalid_redirect_uri", f"{problem}: {u[:200]}")
    if "client_secret" in body or body.get("token_endpoint_auth_method", "none") != "none":
        return bad("invalid_client_metadata", "only public clients (token_endpoint_auth_method none) can register; no secret is issued")
    grants = body.get("grant_types", ["authorization_code"])
    if not isinstance(grants, list) or "authorization_code" not in grants or not set(grants) <= {"authorization_code", "refresh_token"}:
        return bad("invalid_client_metadata", "grant_types may only be authorization_code and refresh_token")
    responses = body.get("response_types", ["code"])
    if not isinstance(responses, list) or set(responses) != {"code"}:
        return bad("invalid_client_metadata", "response_types may only be code")
    app_type = body.get("application_type", "native" if all(is_loopback(u) for u in uris) else "web")
    if app_type not in ("native", "web"):
        return bad("invalid_client_metadata", "application_type must be native or web")
    name = clean_name(body.get("client_name")) or "Unnamed client"
    issued = int(time.time())
    client_id = DCR_PREFIX + keys.sign("dcr", {"n": name, "r": list(dict.fromkeys(uris)), "t": issued}, None)
    return 201, {"client_id": client_id, "client_id_issued_at": issued, "client_name": name,
                 "redirect_uris": list(dict.fromkeys(uris)), "grant_types": ["authorization_code", "refresh_token"],
                 "response_types": ["code"], "token_endpoint_auth_method": "none", "application_type": app_type}


def dcr_client(client_id: str, keys: Keys) -> Client:
    body = keys.verify("dcr", client_id[len(DCR_PREFIX):]) if client_id.startswith(DCR_PREFIX) else None
    if not body or not isinstance(body.get("r"), list) or not isinstance(body.get("n"), str):
        raise ClientError("this client id was not issued by this server (or the server's key has changed); "
                          "the client has to register again")
    uris = tuple(u for u in body["r"] if isinstance(u, str) and redirect_problem(u) is None)
    if not uris:
        raise ClientError("the registered client has no acceptable redirect address")
    return Client(client_id, clean_name(body["n"]) or "Unnamed client", "dcr", "", uris)


# ------------------------------------------------------------------ metadata ----------------------------------------

def origin(cfg) -> str:
    p = urlsplit(cfg.public_url)
    return f"{p.scheme}://{p.netloc}"


def connect_url(cfg) -> str:
    return origin(cfg) + CONNECT_PATH


def issuer(cfg) -> str:
    return origin(cfg) + ISSUER_PATH


def callback_url(cfg) -> str:
    return origin(cfg) + ISSUER_PATH + "/callback"


def connect_metadata_url(cfg) -> str:
    return origin(cfg) + "/.well-known/oauth-protected-resource" + CONNECT_PATH


def protected_resource_metadata(cfg) -> dict:
    """RFC 9728 for /mcp/connect. No offline_access here: MCP 2026-07-28 says a resource SHOULD NOT list it."""
    return {
        "resource": connect_url(cfg),
        "authorization_servers": [issuer(cfg)],
        "scopes_supported": [cfg.scope],
        "bearer_methods_supported": ["header"],
        "resource_name": "Fabric tables with keys, relationships and rules (for MCP clients that register themselves)",
    }


def authorization_server_metadata(cfg, dcr: bool) -> dict:
    """RFC 8414 for https://<domain>/oauth, served at /.well-known/oauth-authorization-server/oauth."""
    base = issuer(cfg)
    meta = {
        "issuer": base,
        "authorization_endpoint": f"{base}/authorize",
        "token_endpoint": f"{base}/token",
        "response_types_supported": ["code"],
        "response_modes_supported": ["query"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_methods_supported": ["none"],
        "code_challenge_methods_supported": ["S256"],
        "scopes_supported": [cfg.scope, "offline_access"],
        "client_id_metadata_document_supported": True,
        "authorization_response_iss_parameter_supported": True,
        "service_documentation": origin(cfg) + "/docs",
    }
    if dcr:
        meta["registration_endpoint"] = f"{base}/register"
    return meta


def challenge(cfg, error: str | None = None) -> str:
    """WWW-Authenticate for a 401 on /mcp/connect: the metadata of this address, the one scope it needs."""
    parts = [f'resource_metadata="{connect_metadata_url(cfg)}"', f'scope="{cfg.scope}"']
    if error:
        parts.append(f'error="{error}"')
    return "Bearer " + ", ".join(parts)


def same_resource(value: str, cfg) -> bool:
    """RFC 8707 resource as the client sends it: this address, scheme and host compared without case, no trailing slash."""
    try:
        a, b = urlsplit(value), urlsplit(connect_url(cfg))
    except ValueError:
        return False
    return (a.scheme.lower(), a.netloc.lower(), a.path.rstrip("/"), a.query, a.fragment) == \
           (b.scheme, b.netloc.lower(), b.path, "", "")


def scope_problem(scope: str | None, cfg) -> str | None:
    """The scopes a client may ask for: this app's user_impersonation and offline_access; openid, profile and email are
    tolerated and dropped. Anything else is refused (invalid_scope)."""
    if not scope:
        return None
    unknown = set(scope.split()) - {cfg.scope, "offline_access"} - ALLOWED_SCOPES_IGNORED
    return f"unknown scope {sorted(unknown)[0][:80]}" if unknown else None


def log(event: str, **fields) -> None:
    """One JSON line on stdout for the operator: what happened and to which client host. Never a token, an IP address,
    a user id or a client's state."""
    line = {"event": f"krusgraph.client_registration.{event}", **{k: v for k, v in fields.items() if v is not None}}
    sys.stdout.write(json.dumps(line, separators=(",", ":")) + "\n")
    sys.stdout.flush()
