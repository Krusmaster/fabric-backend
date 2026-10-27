"""The HTTP side of the client registration layer (registration.py): the metadata for /mcp/connect and /oauth, the
authorization endpoint with Krusgraph's own consent page, the callback from Entra, the token endpoint and, when it is
switched on, dynamic client registration. Built only when KRUSGRAPH_CLIENT_REGISTRATION is on (server.build_app).

What the browser carries: a CSRF cookie for the consent form, a cookie per sign-in that binds Entra's answer to the
browser that approved it (set only after the approval, MCP Security Best Practices "OAuth State Parameter
Validation"), and a signed cookie with the keyed user hash after a sign-in, so a remembered approval can skip the
page. All three are __Host-, Secure, HttpOnly, SameSite=Lax.
"""
from __future__ import annotations

import hashlib
import hmac
import html
import json
import os
import secrets
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from . import registration as reg
from .entra import AUTHORITY, TokenError

CSRF_COOKIE = "__Host-kg_csrf_"                 # + the first 16 hex characters of the CSRF value's SHA-256
USER_COOKIE = "__Host-kg_user"
FLOW_COOKIE = "__Host-kg_flow_"                 # + the first 16 hex characters of the state's SHA-256
ENTRA_ERRORS_DENIED = {"access_denied", "consent_required", "interaction_required", "login_required"}
# Entra answers that end a refresh line for good; anything else (an outage, a 5xx) leaves it to be tried again
ENTRA_ERRORS_FINAL = {"invalid_grant", "interaction_required", "consent_required", "login_required", "unauthorized_client",
                      "invalid_scope"}
HANDLER_THREADS = 8                     # threads for this layer's endpoints, apart from the pool the MCP tools use


class EntraError(Exception):
    def __init__(self, code: str, description: str = "") -> None:
        super().__init__(code)
        self.code, self.description = code, description


def client_ip(request) -> str:
    """The network a request comes from, for the limits: the right-most X-Forwarded-For entry (the one Container Apps'
    ingress added, so a client cannot pick its own bucket by sending the header itself), else the socket peer; an IPv6
    address counts as its /64, the block one subscriber usually holds."""
    import ipaddress
    xff = request.headers.get("x-forwarded-for", "")
    raw = xff.split(",")[-1].strip()[:64] if xff.strip() else (request.client.host if request.client else "unknown")
    try:
        ip = ipaddress.ip_address(raw.strip("[]"))
    except ValueError:
        return raw
    return str(ipaddress.ip_network(f"{ip}/64", strict=False)) if ip.version == 6 else str(ip)


def _with_query(uri: str, params: dict) -> str:
    """Append parameters to a redirect address, keeping a query it already has (RFC 6749 section 3.1.2)."""
    p = urlsplit(uri)
    query = parse_qsl(p.query, keep_blank_values=True) + [(k, v) for k, v in params.items() if v is not None]
    return urlunsplit((p.scheme, p.netloc, p.path, urlencode(query), ""))


class Layer:
    def __init__(self, cfg, validator, keys: reg.Keys, store, resolver: reg.CimdResolver, dcr: bool = False,
                 rate_ip: str = reg.DEFAULT_RATE_IP, rate_client: str = reg.DEFAULT_RATE_CLIENT,
                 rate_register: str = reg.DEFAULT_RATE_REGISTER, entra_post=None) -> None:
        from .limits import Limiter, parse
        self.cfg, self.validator, self.keys, self.store, self.resolver, self.dcr = cfg, validator, keys, store, resolver, dcr
        self.limiter = Limiter(parse(rate_ip), parse(rate_client))           # "user" = an IP address, "organisation" = a client
        self.register_limiter = Limiter(parse(rate_register), [])
        self._post = entra_post
        self.product = os.environ.get("PRODUCT_NAME", "Krusgraph")

    @classmethod
    def from_env(cls, cfg, validator) -> "Layer":
        from .registration_store import from_env as store_from_env
        domains = {d.strip().lower() for d in os.environ.get("KRUSGRAPH_REGISTRATION_CLIENT_DOMAINS", "").split(",") if d.strip()}
        return cls(cfg, validator, reg.keys_from_env(), store_from_env(), reg.CimdResolver(allow_domains=domains),
                   dcr=reg.dcr_enabled(),
                   rate_ip=os.environ.get("KRUSGRAPH_REGISTRATION_RATE_IP") or reg.DEFAULT_RATE_IP,
                   rate_client=os.environ.get("KRUSGRAPH_REGISTRATION_RATE_CLIENT") or reg.DEFAULT_RATE_CLIENT,
                   rate_register=os.environ.get("KRUSGRAPH_REGISTRATION_RATE_REGISTER") or reg.DEFAULT_RATE_REGISTER)

    # ------------------------------------------------------------------ Entra ---------------------------------------
    def _entra_post(self, data: dict) -> dict:
        url = f"{AUTHORITY}/organizations/oauth2/v2.0/token"
        if self._post is not None:
            status, body = self._post(url, data)
        else:
            import requests
            try:
                r = requests.post(url, data=data, timeout=15)
            except requests.RequestException as e:
                raise EntraError("temporarily_unavailable", f"Microsoft Entra could not be reached ({type(e).__name__})") from e
            status = r.status_code
            body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        if status != 200 or not isinstance(body, dict) or not body.get("access_token"):
            body = body if isinstance(body, dict) else {}
            raise EntraError(str(body.get("error") or f"http_{status}"),
                             str(body.get("error_description") or "").splitlines()[0][:300] if body.get("error_description") else "")
        return body

    def _entra_token(self, grant: dict) -> dict:
        """A token request to Entra as the confidential app (the same secret the on-behalf-of exchange uses)."""
        data = {"client_id": self.cfg.client_id, "scope": f"{self.cfg.scope} offline_access", **grant}
        try:
            return self._entra_post({**data, "client_secret": self.cfg.secret()})
        except EntraError as e:                       # a secret rotated in Key Vault: read it again once
            if getattr(self.cfg, "secret_reader", None) is None or not any(
                    c in f"{e.code} {e.description}" for c in ("AADSTS7000215", "AADSTS7000222", "invalid_client")):
                raise
            return self._entra_post({**data, "client_secret": self.cfg.secret(refresh=True)})

    # ------------------------------------------------------------------ pages ---------------------------------------
    def _page(self, title: str, body: str, status: int = 200, form_targets: tuple[str, ...] = (), cookies=(), delete=()):
        from starlette.responses import HTMLResponse
        targets = " ".join(dict.fromkeys(("'self'", "https://login.microsoftonline.com") + tuple(form_targets)))
        csp = (f"default-src 'none'; style-src 'self'; font-src 'self'; img-src 'self' data:; form-action {targets}; "
               "frame-ancestors 'none'; base-uri 'none'")
        doc = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>{html.escape(title)} — {html.escape(self.product)}</title>
<link rel="stylesheet" href="/static/site.css"><link rel="stylesheet" href="/static/oauth.css"></head>
<body class="oauth"><main class="wrap">{body}</main></body></html>"""
        resp = HTMLResponse(doc, status_code=status, headers={
            "Cache-Control": "no-store", "Pragma": "no-cache", "Content-Security-Policy": csp, "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer", "X-Robots-Tag": "noindex"})
        for name, value, age in cookies:
            resp.set_cookie(name, value, max_age=age, path="/", secure=True, httponly=True, samesite="lax")
        for name in delete:
            resp.delete_cookie(name, path="/", secure=True, httponly=True, samesite="lax")
        return resp

    def _error_page(self, text: str, status: int = 400):
        reg.log("refused", reason=text[:160], status=status)
        return self._page("Sign-in stopped", f"""<span class="kicker">Sign-in stopped</span>
<h1>This sign-in cannot continue</h1><p class="lede">{html.escape(text)}</p>
<p>Nothing was shared. Start the sign-in again from your MCP client; if it keeps happening, the client may not be set
up for this server.</p>""", status)

    def _consent_page(self, client: reg.Client, req: dict, csrf: str, warn_other_user: bool = False):
        redirect = req["redirect_uri"]
        p = urlsplit(redirect)
        name = html.escape(client.name)
        if client.kind == "cimd":
            who = (f"<p><strong>{name}</strong> is identified by <code>{html.escape(client.client_id)}</code>: the domain "
                   f"<strong>{html.escape(client.domain)}</strong> publishes this client's name and addresses.</p>")
        else:
            who = (f"<p><strong>{name}</strong> registered itself with this server. <strong>Its name is not verified</strong>: "
                   "any program can call itself anything. Check the address below.</p>")
        if reg.is_loopback(redirect):
            where = (f"<p>The answer goes to <strong>a program on this computer</strong> "
                     f"(<code>{html.escape(p.hostname or '')}</code>, port {html.escape(str(p.port or 80))}): "
                     f"<code>{html.escape(redirect)}</code>.</p><p><strong>Continue only if you started this sign-in in "
                     f"{name} on this computer just now.</strong> Any program on the computer can listen on a local port "
                     "and claim a well-known name.</p>")
        else:
            where = (f"<p>The answer goes to <strong>{html.escape(p.hostname or '')}</strong>: "
                     f"<code>{html.escape(redirect)}</code>.</p>")
        other = ("<p><strong>You signed in with a different account than the last time.</strong> This approval is for the "
                 "account you choose at Microsoft next.</p>") if warn_other_user else ""
        memory = (f"{html.escape(self.product)} remembers this approval for this client and this address for 180 days."
                  if reg.remembered(redirect) else
                  f"Because the answer goes to a program on this computer, {html.escape(self.product)} asks every time.")
        signed = self.keys.sign("consent", {**req, "csrf": hashlib.sha256(csrf.encode()).hexdigest(),
                                            "j": secrets.token_urlsafe(16)}, reg.TXN_TTL)
        body = f"""<span class="kicker">{html.escape(self.product)} · approve a client</span>
<h1>Allow {name} to use {html.escape(self.product)} as you?</h1>
{who}{where}{other}
<p><strong>What it gets:</strong> after you continue, you sign in with Microsoft. {name} then holds a
{html.escape(self.product)} access token for your account, and {html.escape(self.product)} works in Microsoft Fabric with
your own permissions (Entra permission <code>{html.escape(self.cfg.scope)}</code>, plus <code>offline_access</code> to stay
signed in). {memory}</p>
<form method="post" action="{reg.ISSUER_PATH}/consent" class="ctas">
<input type="hidden" name="request" value="{html.escape(signed, quote=True)}">
<input type="hidden" name="csrf" value="{html.escape(csrf, quote=True)}">
<button class="btn primary" type="submit" name="decision" value="allow">Allow and sign in with Microsoft</button>
<button class="btn secondary" type="submit" name="decision" value="deny">Deny</button>
</form>
<p>Did not expect this page? Choose Deny or close it.</p>"""
        return self._page(f"Allow {client.name}?", body, form_targets=(reg.origin_of(redirect),),
                          cookies=[(CSRF_COOKIE + reg.sha256_hex(csrf)[:16], csrf, reg.TXN_TTL)])

    # ------------------------------------------------------------------ helpers -------------------------------------
    def _limited(self, ip: str | None = None, client: str | None = None):
        """None, or the seconds to wait. A client's bucket is per network too: a client id is not a secret (VS Code's is
        the same for every VS Code user), so a bucket for the client alone would let anyone lock all its users out."""
        hit = self.limiter.check(None, f"{client}|{ip}") if client else self.limiter.check(ip, None)
        return hit["retry_after"] if hit else None

    def _redirect(self, uri: str, status: int = 302, cookies=(), delete=()):
        from starlette.responses import RedirectResponse
        resp = RedirectResponse(uri, status_code=status, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})
        for name, value, age in cookies:
            resp.set_cookie(name, value, max_age=age, path="/", secure=True, httponly=True, samesite="lax")
        for name in delete:
            resp.delete_cookie(name, path="/", secure=True, httponly=True, samesite="lax")
        return resp

    def _back_to_client(self, req: dict, error: str, description: str, status: int = 302, delete=()):
        """An error for the client, at its (already validated) redirect address, with state and iss (RFC 9207)."""
        reg.log("error_to_client", error=error, client=self._client_label(req.get("client_id", "")))
        return self._redirect(_with_query(req["redirect_uri"], {"error": error, "error_description": description[:300],
                                                                 "state": req.get("state"), "iss": reg.issuer(self.cfg)}),
                              status, delete=delete)

    @staticmethod
    def _client_label(client_id: str) -> str:
        return "dcr" if client_id.startswith(reg.DCR_PREFIX) else (urlsplit(client_id).hostname or "?")[:120]

    def _resolve(self, client_id) -> reg.Client:
        if not isinstance(client_id, str) or not client_id or len(client_id) > 4096:
            raise reg.ClientError("the request names no client, or a client id longer than 4096 characters")
        if client_id.startswith("https://"):
            return self.resolver.resolve(client_id)
        if client_id.startswith(reg.DCR_PREFIX):
            if not self.dcr:
                raise reg.ClientError("dynamically registered clients are not accepted on this server")
            return reg.dcr_client(client_id, self.keys)
        raise reg.ClientError("this server knows clients by a client ID metadata document URL (https://...)"
                              + (" or a client id from its registration endpoint" if self.dcr else ""))

    def consent_key(self, user: str, client_id: str, redirect_uri: str) -> str:
        return hashlib.sha256(f"{user}\n{client_id}\n{reg.redirect_key(redirect_uri)}".encode()).hexdigest()

    @staticmethod
    def _single(params) -> dict | None:
        """Each OAuth parameter at most once (RFC 6749 section 3.1); None when one is repeated."""
        out = {}
        for k, v in params.multi_items():
            if k in out:
                return None
            out[k] = v
        return out

    def _start_entra(self, req: dict, status: int, consented: bool, remembered: str = "", csrf_cookie: str = ""):
        """Store the sign-in (single use, 10 minutes), bind it to this browser, and send the browser to Entra with this
        server's own redirect address, state and PKCE. Called only after an approval, given now or remembered."""
        state, verifier, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(64), secrets.token_urlsafe(32)
        self.store.put("txn", state, {"req": req, "verifier": verifier, "nonce": hashlib.sha256(nonce.encode()).hexdigest(),
                                      "consented": consented, "remembered": remembered}, ttl=reg.TXN_TTL)
        url = f"{AUTHORITY}/organizations/oauth2/v2.0/authorize?" + urlencode({
            "client_id": self.cfg.client_id, "response_type": "code", "redirect_uri": reg.callback_url(self.cfg),
            "response_mode": "query", "scope": f"{self.cfg.scope} offline_access", "state": state,
            "code_challenge": reg.s256(verifier), "code_challenge_method": "S256"})
        return self._redirect(url, status, cookies=[(FLOW_COOKIE + reg.sha256_hex(state)[:16], nonce, reg.TXN_TTL)],
                              delete=[csrf_cookie] if csrf_cookie else ())

    # ------------------------------------------------------------------ endpoints -----------------------------------
    def authorize(self, request):
        """GET /oauth/authorize. Every error here stays on this server's own page: anyone can publish a client with any
        redirect address, so before the user has approved a client, this server never sends the browser to it
        (MCP 2026-07-28 "Open Redirection", RFC 9700 section 4.11.1). After the page, Deny and Entra's errors go back."""
        ip = client_ip(request)
        if self._limited(ip=ip):
            return self._error_page("Too many sign-in attempts from this network. Wait a minute and try again.", 429)
        q = self._single(request.query_params)
        if q is None:
            return self._error_page("A parameter appears twice in the sign-in request.")
        try:
            client = self._resolve(q.get("client_id"))
        except reg.ClientError as e:
            return self._error_page(str(e))
        if self._limited(ip=ip, client=client.client_id):
            return self._error_page("Too many sign-in attempts for this client. Wait a minute and try again.", 429)
        redirect = q.get("redirect_uri", "")
        if not redirect or not client.allows(redirect):
            return self._error_page(f"The redirect address {redirect[:200] or '(none)'} is not registered for {client.name}.")
        state = q.get("state")
        if state is not None and len(state) > 2048:
            return self._error_page("The client's state value is longer than 2048 characters.")
        req = {"client_id": client.client_id, "redirect_uri": redirect, "state": state,
               "code_challenge": q.get("code_challenge", ""), "resource": q.get("resource") or reg.connect_url(self.cfg)}
        if q.get("response_type") != "code":
            return self._error_page(f"{client.name} asked for response_type {str(q.get('response_type'))[:40]}; only code is supported.")
        if q.get("response_mode") not in (None, "query"):
            return self._error_page(f"{client.name} asked for response_mode {str(q.get('response_mode'))[:40]}; only query is supported.")
        if q.get("code_challenge_method") != "S256" or not reg.CHALLENGE_RE.fullmatch(req["code_challenge"]):
            return self._error_page(f"{client.name} did not send PKCE (code_challenge with code_challenge_method=S256), "
                                    "which this server requires.")
        if not reg.same_resource(req["resource"], self.cfg):
            return self._error_page(f"{client.name} asked for a token for another resource; this server issues tokens for "
                                    f"{reg.connect_url(self.cfg)} only.")
        problem = reg.scope_problem(q.get("scope"), self.cfg)
        if problem:
            return self._error_page(f"{client.name} asked for a scope this server does not give: {problem}.")
        user = (self.keys.verify("user", request.cookies.get(USER_COOKIE)) or {}).get("u")
        if user and q.get("prompt") != "consent" and reg.remembered(redirect):
            found = self.store.get("consent", self.consent_key(user, client.client_id, redirect))
            if found and found[0].get("name") == client.name:          # a renamed client is asked again
                reg.log("consent_remembered", client=self._client_label(client.client_id))
                return self._start_entra(req, 302, consented=False, remembered=user)
        if q.get("prompt") == "none":
            return self._error_page(f"{client.name} asked to sign in without showing any page, but it has not been "
                                    "approved here yet. Start the sign-in again from the client.")
        return self._consent_page(client, req, secrets.token_urlsafe(32), warn_other_user=bool(q.get("kg_other")))

    def consent(self, request, form: dict):
        """POST /oauth/consent: the user's answer on the consent page."""
        if self._limited(ip=client_ip(request)):
            return self._error_page("Too many sign-in attempts from this network. Wait a minute and try again.", 429)
        origin = request.headers.get("origin")
        if (origin and origin != reg.origin(self.cfg)) or request.headers.get("sec-fetch-site", "same-origin") not in ("same-origin", "none"):
            return self._error_page("The approval did not come from this server's own page.", 403)
        csrf = form.get("csrf") or ""
        csrf_cookie = CSRF_COOKIE + reg.sha256_hex(csrf)[:16]
        cookie = request.cookies.get(csrf_cookie) or ""
        req = self.keys.verify("consent", form.get("request"))
        if not csrf or not cookie or not hmac.compare_digest(csrf.encode(), cookie.encode()) or not req or \
                not hmac.compare_digest(str(req.get("csrf", "")).encode(), hashlib.sha256(csrf.encode()).hexdigest().encode()):
            return self._error_page("The approval page has expired or was opened in another browser. Start the sign-in again from your client.", 403)
        if not self.store.add("used", "consent-" + reg.sha256_hex(str(req.get("j"))), {}, ttl=reg.USED_TTL):
            return self._error_page("This approval was already sent. Start the sign-in again from your client.", 409)
        req = {k: req.get(k) for k in ("client_id", "redirect_uri", "state", "code_challenge", "resource")}
        try:                                                  # the client and its address are checked again, now
            client = self._resolve(req["client_id"])
        except reg.ClientError as e:
            return self._error_page(str(e))
        if not client.allows(req["redirect_uri"]):
            return self._error_page("The client no longer lists this redirect address.")
        if form.get("decision") != "allow":
            reg.log("consent_denied", client=self._client_label(client.client_id))
            return self._back_to_client(req, "access_denied", "the user denied the request", 303, delete=[csrf_cookie])
        reg.log("consent_given", client=self._client_label(client.client_id))
        req["client_name"] = client.name
        return self._start_entra(req, 303, consented=True, csrf_cookie=csrf_cookie)

    def callback(self, request):
        """GET /oauth/callback: Entra's answer. The state is taken (once), the browser must be the one that approved."""
        if self._limited(ip=client_ip(request)):
            return self._error_page("Too many sign-in attempts from this network. Wait a minute and try again.", 429)
        q = self._single(request.query_params) or {}
        state = q.get("state", "")
        txn = self.store.take("txn", state) if reg.TOKEN_RE.fullmatch(state) else None
        if not txn:
            return self._error_page("This sign-in has expired or was already completed. Start it again from your client.")
        cookie_name = FLOW_COOKIE + reg.sha256_hex(state)[:16]
        nonce = request.cookies.get(cookie_name) or ""
        if not nonce or not hmac.compare_digest(hashlib.sha256(nonce.encode()).hexdigest(), txn.get("nonce", "")):
            return self._error_page("This sign-in was started in another browser. Start it again from your client.", 403)
        req = txn["req"]
        if q.get("error"):
            code = "access_denied" if q["error"] in ENTRA_ERRORS_DENIED else "server_error"
            text = f"Microsoft Entra answered {q['error'][:60]}: " + (q.get("error_description") or "").splitlines()[0][:200] if q.get("error_description") else f"Microsoft Entra answered {q['error'][:60]}"
            return self._back_to_client(req, code, text, delete=[cookie_name])
        try:
            tokens = self._entra_token({"grant_type": "authorization_code", "code": q.get("code", ""),
                                        "redirect_uri": reg.callback_url(self.cfg), "code_verifier": txn["verifier"]})
            claims = self.validator.validate(tokens["access_token"])
        except EntraError as e:
            return self._back_to_client(req, "server_error", f"Microsoft Entra did not complete the sign-in: {e.code} {e.description}".strip(),
                                        delete=[cookie_name])
        except TokenError as e:
            return self._back_to_client(req, "access_denied", f"the token from Microsoft Entra is not accepted here: {e}", delete=[cookie_name])
        if not claims.get("oid"):
            return self._back_to_client(req, "server_error", "the token from Microsoft Entra names no user", delete=[cookie_name])
        user = self.keys.user_key(str(claims["tid"]), str(claims["oid"]))
        ckey = self.consent_key(user, req["client_id"], req["redirect_uri"])
        if txn.get("consented") and reg.remembered(req["redirect_uri"]):
            self.store.put("consent", ckey, {"client": req["client_id"][:512], "name": req.get("client_name", ""),
                                             "redirect": reg.redirect_key(req["redirect_uri"]),
                                             "at": time.strftime("%Y-%m-%d", time.gmtime())}, ttl=reg.CONSENT_TTL)
        elif not txn.get("consented") and txn.get("remembered") != user and not self.store.get("consent", ckey):
            # The approval that skipped the page belonged to another account than the one that signed in: show the
            # page for this account (the tokens just obtained are dropped, nothing reaches the client).
            reg.log("consent_other_user", client=self._client_label(req["client_id"]))
            again = {"client_id": req["client_id"], "redirect_uri": req["redirect_uri"], "response_type": "code",
                     "code_challenge": req["code_challenge"], "code_challenge_method": "S256", "resource": req["resource"],
                     "kg_other": "1", **({"state": req["state"]} if req.get("state") is not None else {})}
            return self._redirect(f"{reg.ISSUER_PATH}/authorize?" + urlencode(again), delete=[cookie_name, USER_COOKIE])
        code = secrets.token_urlsafe(32)
        self.store.put("code", reg.sha256_hex(code), {
            "client_id": req["client_id"], "redirect_uri": req["redirect_uri"], "code_challenge": req["code_challenge"],
            "user": user, "family": secrets.token_urlsafe(18),
            "tokens": self.keys.seal("code", {"access_token": tokens["access_token"], "refresh_token": tokens.get("refresh_token"),
                                              "expires_at": int(time.time()) + int(tokens.get("expires_in") or 3600)})},
            ttl=reg.CODE_TTL)
        reg.log("code_issued", client=self._client_label(req["client_id"]))
        return self._redirect(_with_query(req["redirect_uri"], {"code": code, "state": req.get("state"), "iss": reg.issuer(self.cfg)}),
                              cookies=[(USER_COOKIE, self.keys.sign("user", {"u": user}, reg.CONSENT_TTL), reg.CONSENT_TTL)],
                              delete=[cookie_name])

    def token(self, request, form: dict | None, basic: bool):
        """POST /oauth/token -> (status, JSON body, extra headers)."""
        def err(error: str, text: str, status: int = 400, headers: dict | None = None):
            if error != "rate_limited":
                reg.log("token_refused", error=error, reason=text[:120])
            return status, {"error": error, "error_description": text}, headers or {}

        ip = client_ip(request)
        wait = self._limited(ip=ip)
        if wait:
            return err("temporarily_unavailable", "too many token requests from this network", 429, {"Retry-After": str(wait)})
        if form is None:
            return err("invalid_request", "send the parameters once each, as application/x-www-form-urlencoded")
        if basic:
            return err("invalid_client", "this server has public clients only; send client_id without a secret", 401,
                       {"WWW-Authenticate": 'Basic realm="krusgraph"'})
        if form.get("client_secret") or form.get("client_assertion"):
            return err("invalid_client", "this server has public clients only; send client_id without a secret")
        client_id = form.get("client_id") or ""
        if not client_id or len(client_id) > 4096:
            return err("invalid_request", "client_id is required")
        wait = self._limited(ip=ip, client=client_id)
        if wait:
            return err("temporarily_unavailable", "too many token requests for this client", 429, {"Retry-After": str(wait)})
        if form.get("resource") and not reg.same_resource(form["resource"], self.cfg):
            return err("invalid_target", f"this server issues tokens for {reg.connect_url(self.cfg)} only")
        grant = form.get("grant_type")
        if grant == "authorization_code":
            return self._redeem_code(form, client_id, err)
        if grant == "refresh_token":
            problem = reg.scope_problem(form.get("scope"), self.cfg)
            if problem:
                return err("invalid_scope", problem)
            return self._refresh(form, client_id, err)
        return err("unsupported_grant_type", "grant_type must be authorization_code or refresh_token")

    def _answer(self, tokens: dict, family: str | None, secret: str | None) -> tuple[int, dict, dict]:
        out = {"access_token": tokens["access_token"], "token_type": "Bearer",
               "expires_in": max(1, int(tokens.get("expires_at") or time.time() + int(tokens.get("expires_in") or 3600)) - int(time.time())),
               "scope": self.cfg.scope}
        if family and secret:
            out["refresh_token"] = f"{family}.{secret}"
        return 200, out, {}

    def _redeem_code(self, form: dict, client_id: str, err):
        code, verifier = form.get("code") or "", form.get("code_verifier") or ""
        if not code or len(code) > 128:
            return err("invalid_grant", "the code is missing or malformed")
        key = reg.sha256_hex(code)
        rec = self.store.take("code", key)
        if rec is None:
            used = self.store.get("used", "code-" + key)
            if used and used[0].get("family"):           # a second redemption: revoke what the first one got
                self.store.delete("family", used[0]["family"])
                reg.log("code_reused", client=self._client_label(client_id))
            return err("invalid_grant", "the code is unknown, expired or already used")
        self.store.put("used", "code-" + key, {"family": rec["family"]}, ttl=reg.USED_TTL)
        if not hmac.compare_digest(client_id.encode(), rec["client_id"].encode()):
            return err("invalid_grant", "the code was issued to another client")
        if form.get("redirect_uri") != rec["redirect_uri"]:
            return err("invalid_grant", "redirect_uri must be the one used in the authorization request")
        if not reg.VERIFIER_RE.fullmatch(verifier) or not hmac.compare_digest(reg.s256(verifier).encode(), rec["code_challenge"].encode()):
            return err("invalid_grant", "the PKCE code_verifier does not match the code_challenge")
        tokens = self.keys.open("code", rec["tokens"])
        if not tokens or not tokens.get("access_token"):
            return err("invalid_grant", "the code can no longer be read (the server's key changed)")
        secret = None
        if tokens.get("refresh_token"):
            secret = secrets.token_urlsafe(32)
            self.store.put("family", rec["family"], {
                "client_id": client_id, "user": rec["user"], "hash": reg.sha256_hex(secret),
                "rt": self.keys.seal("family:" + rec["family"], {"rt": tokens["refresh_token"]}),
                "until": int(time.time()) + reg.FAMILY_TTL}, ttl=reg.FAMILY_TTL)
        reg.log("token_issued", client=self._client_label(client_id), grant="authorization_code")
        return self._answer(tokens, rec["family"] if secret else None, secret)

    def _refresh(self, form: dict, client_id: str, err):
        presented = form.get("refresh_token") or ""
        family, _, secret = presented.partition(".")
        if not reg.TOKEN_RE.fullmatch(family) or not secret or len(presented) > 256:
            return err("invalid_grant", "the refresh token is malformed")
        found = self.store.get("family", family)
        if not found:
            return err("invalid_grant", "the refresh token is unknown, expired or revoked")
        rec, etag = found
        if not hmac.compare_digest(rec.get("client_id", "").encode(), client_id.encode()) or \
                not hmac.compare_digest(rec.get("hash", ""), reg.sha256_hex(secret)):
            self.store.delete("family", family)          # an old or stolen token: the whole line ends here
            reg.log("refresh_reused", client=self._client_label(client_id))
            return err("invalid_grant", "the refresh token was already used or belongs to another client; sign in again")
        inner = self.keys.open("family:" + family, rec.get("rt", ""))
        if not inner:
            self.store.delete("family", family)
            return err("invalid_grant", "the refresh token can no longer be read; sign in again")
        try:
            tokens = self._entra_token({"grant_type": "refresh_token", "refresh_token": inner["rt"]})
            claims = self.validator.validate(tokens["access_token"])
        except EntraError as e:
            if e.code not in ENTRA_ERRORS_FINAL:                 # an outage: keep the line, the client tries again
                return err("temporarily_unavailable", f"Microsoft Entra did not answer as expected ({e.code}); try again", 503)
            self.store.delete("family", family)
            return err("invalid_grant", f"Microsoft Entra did not renew the sign-in ({e.code}); sign in again")
        except TokenError as e:
            self.store.delete("family", family)
            return err("invalid_grant", f"the renewed token is not accepted here ({e}); sign in again")
        if self.keys.user_key(str(claims.get("tid", "")), str(claims.get("oid", ""))) != rec.get("user"):
            self.store.delete("family", family)
            return err("invalid_grant", "the renewed token is for another user; sign in again")
        new_secret = secrets.token_urlsafe(32)
        until = int(rec.get("until") or time.time() + reg.FAMILY_TTL)
        updated = {**rec, "hash": reg.sha256_hex(new_secret),
                   "rt": self.keys.seal("family:" + family, {"rt": tokens.get("refresh_token") or inner["rt"]})}
        if not self.store.replace("family", family, updated, etag, ttl=max(60, until - int(time.time()))):
            return err("invalid_grant", "the refresh token was used by another request at the same moment; sign in again")
        reg.log("token_issued", client=self._client_label(client_id), grant="refresh_token")
        return self._answer(tokens, family, new_secret)

    def register(self, request, body):
        if self.register_limiter.check(client_ip(request), None):
            return 429, {"error": "temporarily_unavailable", "error_description": "too many registrations from this network"}
        status, out = reg.register(body, self.keys)
        reg.log("registered" if status == 201 else "registration_refused",
                reason=None if status == 201 else out.get("error_description", "")[:160])
        return status, out

    # ------------------------------------------------------------------ routes --------------------------------------
    def routes(self) -> list:
        import functools
        import anyio
        from starlette.responses import JSONResponse, Response
        from starlette.routing import Route
        from .registration_store import StoreError

        cors = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, MCP-Protocol-Version", "Access-Control-Max-Age": "600"}

        threads = anyio.CapacityLimiter(HANDLER_THREADS)

        async def run_in_threadpool(fn, *args):
            """Blocking work (the store, Entra, metadata fetches) on this layer's own threads, so a slow client host or
            a flood of sign-ins can never take the threads the MCP tools at /mcp run on."""
            return await anyio.to_thread.run_sync(functools.partial(fn, *args), limiter=threads)

        def json_response(body: dict, status: int = 200, headers: dict | None = None, cache: str = "no-store"):
            return JSONResponse(body, status_code=status, headers={"Cache-Control": cache, **cors, **(headers or {})})

        def guarded(fn):
            async def handler(request):
                if request.method == "OPTIONS":
                    return Response(status_code=204, headers=cors)
                try:
                    return await fn(request)
                except StoreError as e:
                    reg.log("store_error", reason=str(e)[:160])
                    if request.url.path.endswith(("/token", "/register")):
                        return json_response({"error": "temporarily_unavailable", "error_description": "try again in a moment"}, 503)
                    return self._error_page("The sign-in service is briefly unavailable. Try again in a moment.", 503)
                except ValueError:                                 # a malformed key or value that slipped past the checks
                    if request.url.path.endswith(("/token", "/register")):
                        return json_response({"error": "invalid_request", "error_description": "malformed request"}, 400)
                    return self._error_page("The sign-in request is malformed.")
            return handler

        async def prm(_request):
            return json_response(reg.protected_resource_metadata(self.cfg), cache="public, max-age=300")

        async def asm(_request):
            return json_response(reg.authorization_server_metadata(self.cfg, self.dcr), cache="public, max-age=300")

        async def authorize(request):
            return await run_in_threadpool(self.authorize, request)

        async def consent(request):
            if not request.headers.get("content-type", "").startswith("application/x-www-form-urlencoded"):
                return self._error_page("The approval must be sent from the approval page.", 415)
            raw = await request.body()
            if len(raw) > 16 * 1024:
                return self._error_page("The approval is too large.", 413)
            fields = parse_qsl(raw.decode("latin-1"), keep_blank_values=True)
            if len({k for k, _ in fields}) != len(fields):
                return self._error_page("A field appears twice in the approval.")
            return await run_in_threadpool(self.consent, request, dict(fields))

        async def callback(request):
            return await run_in_threadpool(self.callback, request)

        async def token(request):
            form = None
            if request.headers.get("content-type", "").split(";")[0].strip() == "application/x-www-form-urlencoded":
                raw = await request.body()
                fields = parse_qsl(raw.decode("utf-8", "replace"), keep_blank_values=True) if len(raw) <= 16 * 1024 else []
                if fields and len({k for k, _ in fields}) == len(fields):
                    form = dict(fields)
            basic = request.headers.get("authorization", "").lower().startswith("basic ")
            status, body, headers = await run_in_threadpool(self.token, request, form, basic)
            return json_response(body, status, {"Pragma": "no-cache", **headers})

        async def register(request):
            raw = await request.body()
            if len(raw) > 16 * 1024:
                return json_response({"error": "invalid_client_metadata", "error_description": "request too large"}, 413)
            try:
                body = json.loads(raw) if raw else None
            except ValueError:
                body = None
            status, out = await run_in_threadpool(self.register, request, body)
            return json_response(out, status)

        out = [
            Route("/.well-known/oauth-protected-resource" + reg.CONNECT_PATH, guarded(prm), methods=["GET", "OPTIONS"]),
            Route("/.well-known/oauth-authorization-server" + reg.ISSUER_PATH, guarded(asm), methods=["GET", "OPTIONS"]),
            Route(reg.ISSUER_PATH + "/.well-known/oauth-authorization-server", guarded(asm), methods=["GET", "OPTIONS"]),
            Route(reg.ISSUER_PATH + "/authorize", guarded(authorize), methods=["GET"]),
            Route(reg.ISSUER_PATH + "/consent", guarded(consent), methods=["POST"]),
            Route(reg.ISSUER_PATH + "/callback", guarded(callback), methods=["GET"]),
            Route(reg.ISSUER_PATH + "/token", guarded(token), methods=["POST", "OPTIONS"]),
        ]
        if self.dcr:
            out.append(Route(reg.ISSUER_PATH + "/register", guarded(register), methods=["POST", "OPTIONS"]))
        return out


def install(cfg, validator):
    """The Layer when KRUSGRAPH_CLIENT_REGISTRATION is on and its configuration is complete; None otherwise. An
    incomplete configuration is reported on stderr and leaves the layer off, so Claude's sign-in never depends on it."""
    if not reg.enabled():
        return None
    import sys
    try:
        return Layer.from_env(cfg, validator)
    except ValueError as e:
        sys.stderr.write(f"krusgraph: client registration is switched on but not configured, so it stays off: {e}\n")
        return None
