"""AP1: the guided chat at /app, hidden and closed by default (the founder's decision of 24 November 2026, "5a").

A person signs in with Microsoft Entra and is walked through the read-only half of the Start Krusgraph path as a chat:
the workspace, the source, the schema, then Krusgraph reads the tables, proposes keys and links by its fixed rules and
counts them against the rows. The mascots say each step (Onto points the way, the Thinker checks, the Builder builds);
the person answers with buttons. There is no AI model anywhere in it: every answer is the `start` tool's own (server.start,
start_flow.guide), the same engine and step logic the MCP connector uses, called with the person's own sign-in. Free text
is taken only where a fixed rule resolves it: a typed name is matched against the names offered (match_choice). Nothing
here writes to Fabric; Decide, the dry run and Create come in AP2, and the step endpoint refuses them.

Closed by default. Every route answers the site's ordinary 404 unless KRUSGRAPH_APP_TENANTS names at least one tenant id
(comma separated, read on every request) and the server runs with Entra sign-in. A sign-in from a tenant that is not on
the list gets the same 404 and no session. The page is not linked from the navigation, the sitemap, robots.txt or
llms.txt, and it says noindex (meta and X-Robots-Tag).

Sign-in (the smallest secure design for a page on this site). The server is a confidential OAuth client of the existing
Krusgraph MCP Entra app (ENTRA_CLIENT_ID, its secret through EntraConfig.secret, which also reads Key Vault): the
authorization code flow with PKCE (S256), state taken once, and a cookie that binds Entra's answer to the browser that
started it (the same pattern as registration_flow.py). The redirect address is <origin of MCP_PUBLIC_URL>/app/callback,
registered on that app as a Web redirect URI by the maintainer. The access token Entra returns is for this app's
user_impersonation scope; it is validated like a token at /mcp (entra.Validator: signature, audience, issuer, scope) and
then exchanged on-behalf-of the person for Fabric and SQL tokens by the same OnBehalfOf cache the MCP server uses. No
refresh token is asked for (no offline_access): when the access token expires, the session ends and the person signs in
again.

What the browser holds: one random session id in a cookie (__Host-, HttpOnly, Secure, SameSite=Lax, Path=/, at most
SESSION_TTL seconds and never past the token's expiry). The token stays in this process's memory, keyed by a digest of
the session id, and is never written to a page, a log or a store. Several replicas do not share sessions: a request
that reaches another replica is sent to sign in again.
"""
from __future__ import annotations

import hashlib
import hmac
import html
import json
import os
import re
import secrets
import sys
import threading
import time
from urllib.parse import urlencode, urlsplit

from .entra import AUTHORITY, FABRIC_SCOPE, SQL_SCOPE, TenantNotAllowed, TokenError

PATH = "/app"
LOGIN = PATH + "/login"
CALLBACK = PATH + "/callback"
LOGOUT = PATH + "/logout"
STEP = PATH + "/api/step"
ENV = "KRUSGRAPH_APP_TENANTS"
SESSION_COOKIE = "__Host-kg_app"
FLOW_COOKIE = "__Host-kg_app_flow"
SESSION_TTL = 3600                      # seconds; never longer than the access token
TXN_TTL = 600                           # a sign-in on its way through Entra
MAX_SESSIONS, MAX_TXNS = 500, 1000      # bounded memory: the oldest go first
MAX_BODY = 4096
NAME_MAX = 256
TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{16,128}")
# The steps this round serves: choosing the data and the check. Everything after (decide, dry_run, create) is AP2.
READ_STEPS = ("", "workspace", "source", "schema", "data", "check")
NEXT_LINE = "Next: decide and dry run (coming next)"
NOTHING_WRITTEN = "Nothing was changed in Fabric: this page only reads."


def allowed_tenants() -> frozenset[str]:
    """KRUSGRAPH_APP_TENANTS as a set of lower-case tenant ids; empty when unset. Read on every request."""
    return frozenset(t.strip().lower() for t in os.environ.get(ENV, "").split(",") if t.strip())


def log(event: str, **fields) -> None:
    """One JSON line for the operator. Never a token, a tenant id, a user id or a session id."""
    line = {"event": f"krusgraph.app.{event}", **{k: v for k, v in fields.items() if v is not None}}
    sys.stdout.write(json.dumps(line, separators=(",", ":")) + "\n")


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def s256(verifier: str) -> str:
    import base64
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode()


class Store:
    """A small in-memory store with expiry, bounded: when full, the entries closest to their expiry go first."""

    def __init__(self, cap: int) -> None:
        self.cap = cap
        self._d: dict[str, tuple[dict, float]] = {}
        self._lock = threading.Lock()

    def put(self, key: str, value: dict, until: float) -> None:
        with self._lock:
            now = time.time()
            if len(self._d) >= self.cap:
                self._d = {k: v for k, v in self._d.items() if v[1] > now}
                while len(self._d) >= self.cap:
                    del self._d[min(self._d, key=lambda k: self._d[k][1])]
            self._d[key] = (value, until)

    def get(self, key: str) -> dict | None:
        with self._lock:
            hit = self._d.get(key)
            if hit and hit[1] <= time.time():
                del self._d[key]
                return None
            return hit[0] if hit else None

    def take(self, key: str) -> dict | None:
        with self._lock:
            hit = self._d.pop(key, None)
        return hit[0] if hit and hit[1] > time.time() else None

    def drop(self, key: str) -> None:
        with self._lock:
            self._d.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._d.clear()

    def __len__(self) -> int:
        return len(self._d)


SESSIONS = Store(MAX_SESSIONS)
TXNS = Store(MAX_TXNS)


class SessionTokens:
    """Fabric and SQL tokens for the signed-in person, from the on-behalf-of exchange of the session's own token: the
    same shape as workload_api.Tokens, so server.workload_tokens routes every tool's token through it. `who` names the
    person for the guided path's shared state (server._flow_who), as a digest."""

    def __init__(self, obo, user_token: str, tenant: str, who: str) -> None:
        self.obo, self.user_token, self.tenant, self.who = obo, user_token, tenant, who

    def fabric(self) -> str:
        return self.obo.token(self.user_token, self.tenant, FABRIC_SCOPE)

    def sql(self) -> str:
        return self.obo.token(self.user_token, self.tenant, SQL_SCOPE)

    def onelake(self) -> str:
        from .csn_onelake import STORAGE_SCOPE
        return self.obo.token(self.user_token, self.tenant, STORAGE_SCOPE)


# ------------------------------------------------------------------ fixed rules for typed text ----------------------

def match_choice(text: str, names: list[str]) -> tuple[str | None, list[str]]:
    """A typed name against the names offered, by fixed rules in order: the same name (ignoring case and the spaces
    around it), else the one name that starts with the text, else the one name that contains it. (name, []) when one
    rule finds exactly one; (None, candidates) otherwise, so the page can say what matched. No guessing beyond that."""
    t = " ".join(str(text or "").split()).casefold()
    if not t:
        return None, []
    folded = [(n, n.casefold()) for n in names if isinstance(n, str) and n.strip()]
    for rule in (lambda f: f == t, lambda f: f.startswith(t), lambda f: t in f):
        hits = [n for n, f in folded if rule(f)]
        if len(hits) == 1:
            return hits[0], []
        if len(hits) > 1:
            return None, hits[:8]
    return None, []


# ------------------------------------------------------------------ the start tool's answer, for the page ----------

def _args(a: dict | None) -> dict | None:
    """A button's arguments as the page may send them back: the three names and a read-only step, nothing else."""
    if not isinstance(a, dict):
        return None
    out = {k: str(a[k])[:NAME_MAX] for k in ("workspace", "source", "schema") if isinstance(a.get(k), str) and a[k].strip()}
    step = str(a.get("step") or "").strip().lower()
    if step not in READ_STEPS:
        return None
    if step:
        out["step"] = step
    return out


def view(out: dict) -> dict:
    """What the page shows of one `start` answer: the mascot, the sentence, the buttons (choices of steps 1-3, Change,
    Next: Check) and, on Check, the counts and the map as names, keys, rules and counts. No row value is in a start
    answer, and nothing is added here: this only leaves out what the page does not draw."""
    if not isinstance(out, dict):
        return {"error": "No answer.", "kind": "internal"}
    if out.get("error"):
        return {k: str(out[k])[:400] for k in ("error", "kind", "hint") if out.get(k)}
    from . import coach
    stage = str(out.get("stage") or "")
    v: dict = {"stage": stage, "who": out.get("who") if out.get("who") in coach.NAMES else "onto",
               "say": str(out.get("say") or ""), "chosen": out.get("chosen") or {}}
    step = out.get("step") or {}
    v["step"] = {k: step.get(k) for k in ("n", "of", "short")}
    if out.get("line"):
        v["line"] = str(out["line"])
    choices = []
    for a in out.get("actions") or []:
        if not isinstance(a, dict) or a.get("kind") != "choose":
            continue
        args = _args(a.get("arguments"))
        if args is None:
            continue
        choices.append({"label": str(a.get("label") or ""), "hint": str(a.get("hint") or ""), "arguments": args,
                        **({"selected": True} if a.get("selected") else {}),
                        **({"disabled": str(a["disabled"])} if a.get("disabled") else {})})
    if choices:
        v["choices"] = choices
    for k in ("choices_error", "review_error"):
        if out.get(k):
            v[k] = str(out[k])[:200]
    buttons = []
    after = out.get("after") if isinstance(out.get("after"), dict) else None
    nxt = _args(after.get("arguments")) if after else None
    if nxt is not None and after:
        buttons.append({"label": str(after.get("label") or "Next"), "arguments": nxt, "primary": True})
    if stage == "data":
        buttons.append({"label": "Change", "arguments": {"step": "workspace"}})
    if buttons:
        v["buttons"] = buttons
    if stage == "check":
        v["lines"] = [str(x) for x in out.get("lines") or []][:6]
        if isinstance(out.get("counts"), dict):
            v["counts"] = {k: out["counts"][k] for k in ("tables", "links", "checks", "hold", "open_decisions",
                                                          "doubled_totals") if k in out["counts"]}
        m = out.get("map") if isinstance(out.get("map"), dict) else {}
        v["map"] = {"tables": [{"name": t.get("name"), "key": t.get("key") or [], "rule": t.get("key_rule") or ""}
                               for t in (m.get("tables") or []) if isinstance(t, dict)][:200],
                    "links": [{k: r.get(k) for k in ("source", "source_cols", "target", "target_cols", "rule", "state",
                                                       "orphans", "rows_with_value")}
                              for r in (m.get("relationships") or []) if isinstance(r, dict)][:400]}
        rules = ((out.get("found") or {}).get("rules")) or []
        if rules:
            v["rules"] = [str(x) for x in rules][:10]
        v["next"] = NEXT_LINE                         # AP1 stops here: deciding and the dry run come in AP2
    return v


def run_start(tokens: SessionTokens, args: dict) -> dict:
    """The `start` tool, as the MCP connector registers it (instrumented, guarded), with the session's tokens."""
    from . import server
    with server.workload_tokens(tokens):
        return json.loads(server.start(**args))


# ------------------------------------------------------------------ the page ---------------------------------------

def page_html(name: str = "") -> str:
    """The chat column. The mascots' first lines are the coach's own (coach.LINE), passed as data, never as script."""
    from . import coach
    from .pages import _shell, asset_version
    lines = {"hello": coach.LINE["data"], "read": coach.LINE["read"], "check": coach.LINE["check"], "next": NEXT_LINE,
             "nothing": NOTHING_WRITTEN, "error": coach.LINE["error"], "names": coach.NAMES}
    who = f"Signed in as {html.escape(name[:80])}. " if name else "Signed in. "
    body = f"""<section class="wrap app-wrap" aria-labelledby="app-h">
  <div class="app-chat">
    <div class="app-head">
      <span class="app-fig" data-mascot="onto" data-pose="rest" data-label=""></span>
      <div class="app-title"><h1 id="app-h">Your data, step by step</h1>
        <p class="muted tiny">{who}Krusgraph only reads here: nothing is changed in Fabric.</p></div>
      <form method="post" action="{LOGOUT}" class="app-out"><button type="submit" class="btn ghost small">Sign out</button></form>
    </div>
    <ol class="app-log" id="app-log" role="log" aria-live="polite" aria-relevant="additions" aria-label="Conversation"></ol>
    <div class="app-input" id="app-input" aria-label="Your answer" role="group"></div>
  </div>
  <noscript><p class="muted">This page needs JavaScript for its buttons.</p></noscript>
</section>
<script type="application/json" id="app-lines">{json.dumps(lines, ensure_ascii=False).replace("<", "\\u003c")}</script>
<script src="/static/app.js?v={asset_version()}" defer></script>"""
    return _shell("Your data, step by step — {{PRODUCT}}", "A guided path through your Fabric data.", body, page="app",
                  nav="", noindex=True, head=f'<link rel="stylesheet" href="/static/app.css?v={asset_version()}">')


def message_html(title: str, text: str, again: bool = True) -> str:
    from .pages import _shell
    link = f'<div class="ctas"><a class="btn primary" href="{LOGIN}">Sign in again</a></div>' if again else ""
    body = (f'<section class="wrap app-wrap"><div class="app-chat app-note"><h1>{html.escape(title)}</h1>'
            f'<p class="lede">{html.escape(text)}</p>{link}</div></section>')
    return _shell(f"{title} — {{{{PRODUCT}}}}", title, body, page="app", nav="", noindex=True,
                  head='<link rel="stylesheet" href="/static/app.css">')


# ------------------------------------------------------------------ the routes -------------------------------------

def callback_url(cfg) -> str:
    p = urlsplit(cfg.public_url)
    return f"{p.scheme}://{p.netloc}{CALLBACK}"


def page_headers() -> dict:
    """The site's page headers (server.build_app's PAGE_HEADERS), so a 404 here is byte for byte the site's."""
    from .pages import THEME_HASH
    return {"Content-Security-Policy": "default-src 'self'; script-src 'self' " + THEME_HASH + "; style-src 'self' 'unsafe-inline'; "
                                       "img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; "
                                       "base-uri 'self'; form-action 'self'",
            "X-Content-Type-Options": "nosniff", "Referrer-Policy": "strict-origin-when-cross-origin"}


class App:
    def __init__(self, cfg, validator, obo, entra_post=None, run=None) -> None:
        from .limits import Limiter, parse
        self.cfg, self.validator, self.obo = cfg, validator, obo
        self._post = entra_post
        self.run = run or run_start
        self.sign_in_limit = Limiter(parse("30/minute,300/hour"), [])        # per network
        self.step_limit = Limiter(parse("60/minute,1200/hour"), [])          # per session

    # -- what every route checks first
    def on(self) -> bool:
        return self.cfg is not None and bool(allowed_tenants())

    def session(self, request) -> dict | None:
        sid = request.cookies.get(SESSION_COOKIE) or ""
        if not TOKEN_RE.fullmatch(sid):
            return None
        s = SESSIONS.get(_digest(sid))
        if s is None:
            return None
        if s["tid"] not in allowed_tenants():          # the list changed after the sign-in: the session ends
            SESSIONS.drop(_digest(sid))
            return None
        return s

    @staticmethod
    def not_found(request):
        """Exactly the site's 404 (server.build_app's handler), so the page cannot be told apart from no page."""
        from starlette.responses import HTMLResponse, PlainTextResponse
        if request.method in ("GET", "HEAD") and "text/html" in request.headers.get("accept", ""):
            from .pages import not_found_html
            return HTMLResponse(not_found_html(request.url.path), status_code=404, headers={"X-Robots-Tag": "noindex", **page_headers()})
        return PlainTextResponse("not found", status_code=404)

    @staticmethod
    def _headers() -> dict:
        return {**page_headers(), "Cache-Control": "no-store", "Pragma": "no-cache", "X-Robots-Tag": "noindex, nofollow",
                "Referrer-Policy": "no-referrer", "X-Frame-Options": "DENY"}

    def _html(self, body: str, status: int = 200, cookies=(), delete=()):
        from starlette.responses import HTMLResponse
        resp = HTMLResponse(body, status_code=status, headers=self._headers())
        self._cookies(resp, cookies, delete)
        return resp

    def _redirect(self, url: str, status: int = 302, cookies=(), delete=()):
        from starlette.responses import RedirectResponse
        resp = RedirectResponse(url, status_code=status, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
                                                                  "X-Robots-Tag": "noindex, nofollow"})
        self._cookies(resp, cookies, delete)
        return resp

    @staticmethod
    def _cookies(resp, cookies, delete) -> None:
        for name, value, age in cookies:
            resp.set_cookie(name, value, max_age=age, path="/", secure=True, httponly=True, samesite="lax")
        for name in delete:
            resp.delete_cookie(name, path="/", secure=True, httponly=True, samesite="lax")

    @staticmethod
    def _same_origin(request) -> bool:
        """A state-changing request must come from this site's own page: the Origin header, when sent, names this
        host (SameSite=Lax already keeps the cookie off a cross-site POST; this is the second lock)."""
        origin = request.headers.get("origin")
        if origin is None:
            return request.headers.get("sec-fetch-site", "same-origin") in ("same-origin", "none")
        host = request.headers.get("host", "")
        return bool(host) and urlsplit(origin).netloc == host

    # -- Entra
    def _entra_post(self, data: dict) -> dict:
        url = f"{AUTHORITY}/organizations/oauth2/v2.0/token"
        if self._post is not None:
            return self._post(url, data)
        import requests
        try:
            r = requests.post(url, data=data, timeout=15)
        except requests.RequestException as e:
            raise TokenError(f"Microsoft Entra could not be reached ({type(e).__name__})") from e
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        if r.status_code != 200 or not isinstance(body, dict) or not body.get("access_token"):
            raise TokenError(str((body or {}).get("error") or f"http_{r.status_code}"))
        return body

    def _redeem(self, code: str, verifier: str) -> dict:
        data = {"client_id": self.cfg.client_id, "grant_type": "authorization_code", "code": code,
                "redirect_uri": callback_url(self.cfg), "code_verifier": verifier, "scope": self.cfg.scope}
        try:
            return self._entra_post({**data, "client_secret": self.cfg.secret()})
        except TokenError as e:                                 # a secret rotated in Key Vault: read it again once
            if getattr(self.cfg, "secret_reader", None) is None or not any(
                    c in str(e) for c in ("AADSTS7000215", "AADSTS7000222", "invalid_client")):
                raise
            return self._entra_post({**data, "client_secret": self.cfg.secret(refresh=True)})

    def _limited(self, limiter, key: str) -> bool:
        return limiter.check(key, None) is not None

    # -- the endpoints
    def page(self, request):
        if not self.on():
            return self.not_found(request)
        s = self.session(request)
        if s is None:
            return self._redirect(LOGIN)
        return self._html(page_html(s.get("name") or ""))

    def login(self, request):
        if not self.on():
            return self.not_found(request)
        from .registration_flow import client_ip
        if self._limited(self.sign_in_limit, client_ip(request)):
            return self._html(message_html("Too many sign-ins", "Wait a minute and try again.", False), 429)
        if self.session(request) is not None:
            return self._redirect(PATH)
        state, verifier, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(64), secrets.token_urlsafe(32)
        TXNS.put(state, {"verifier": verifier, "nonce": _digest(nonce)}, time.time() + TXN_TTL)
        url = f"{AUTHORITY}/organizations/oauth2/v2.0/authorize?" + urlencode({
            "client_id": self.cfg.client_id, "response_type": "code", "redirect_uri": callback_url(self.cfg),
            "response_mode": "query", "scope": self.cfg.scope, "state": state, "prompt": "select_account",
            "code_challenge": s256(verifier), "code_challenge_method": "S256"})
        return self._redirect(url, cookies=[(FLOW_COOKIE, nonce, TXN_TTL)])

    def callback(self, request):
        if not self.on():
            return self.not_found(request)
        from .registration_flow import client_ip
        if self._limited(self.sign_in_limit, client_ip(request)):
            return self._html(message_html("Too many sign-ins", "Wait a minute and try again.", False), 429)
        q = request.query_params
        state = q.get("state", "")
        txn = TXNS.take(state) if TOKEN_RE.fullmatch(state) else None
        if not txn:
            return self._html(message_html("This sign-in has expired", "Start it again."), 400, delete=[FLOW_COOKIE])
        nonce = request.cookies.get(FLOW_COOKIE) or ""
        if not nonce or not hmac.compare_digest(_digest(nonce), txn["nonce"]):
            log("refused", reason="other_browser")
            return self._html(message_html("This sign-in was started in another browser", "Start it again here."), 403,
                              delete=[FLOW_COOKIE])
        if q.get("error"):
            log("refused", reason="entra_error")
            return self._html(message_html("Sign-in stopped", "Microsoft Entra did not complete the sign-in."), 400,
                              delete=[FLOW_COOKIE])
        try:
            tokens = self._redeem(q.get("code", ""), txn["verifier"])
            claims = self.validator.validate(tokens["access_token"])
        except TenantNotAllowed:
            log("refused", reason="tenant")
            return self.not_found(request)
        except (TokenError, KeyError, TypeError):
            log("refused", reason="token")
            return self._html(message_html("Sign-in stopped", "The sign-in could not be completed."), 403,
                              delete=[FLOW_COOKIE])
        tid = str(claims.get("tid") or "").lower()
        if tid not in allowed_tenants() or not claims.get("oid"):
            log("refused", reason="tenant")
            resp = self.not_found(request)
            self._cookies(resp, (), [FLOW_COOKIE])
            return resp
        now = time.time()
        until = min(float(claims.get("exp") or now) - 60, now + SESSION_TTL)
        if until <= now:
            return self._html(message_html("Sign-in stopped", "The sign-in has already expired."), 403, delete=[FLOW_COOKIE])
        sid = secrets.token_urlsafe(32)
        from .flow_state import who_of
        SESSIONS.put(_digest(sid), {"token": tokens["access_token"], "tid": tid,
                                    "who": who_of({"oid": str(claims["oid"]), "tid": tid}, None),
                                    "name": str(claims.get("name") or "")[:80]}, until)
        log("signed_in")
        return self._redirect(PATH, cookies=[(SESSION_COOKIE, sid, int(until - now))], delete=[FLOW_COOKIE])

    def logout(self, request):
        if not self.on():
            return self.not_found(request)
        if not self._same_origin(request):
            from starlette.responses import PlainTextResponse
            return PlainTextResponse("forbidden", status_code=403)
        sid = request.cookies.get(SESSION_COOKIE) or ""
        if TOKEN_RE.fullmatch(sid):
            SESSIONS.drop(_digest(sid))
        return self._redirect("/", status=303, delete=[SESSION_COOKIE])

    def step(self, request, body: bytes):
        """POST /app/api/step {workspace?, source?, schema?, step?, text?}: one `start` call with the session's tokens,
        as view() trims it. `text` is a typed name for the current choice, resolved by match_choice."""
        from starlette.responses import JSONResponse
        nostore = {"Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow"}

        def answer(payload: dict, status: int = 200):
            return JSONResponse(payload, status_code=status, headers=nostore)
        if not self.on():
            return self.not_found(request)
        if not self._same_origin(request) or not request.headers.get("content-type", "").startswith("application/json"):
            return answer({"error": "This address takes JSON from Krusgraph's own page.", "kind": "bad_request"}, 403)
        s = self.session(request)
        if s is None:
            return answer({"error": "Sign in first.", "kind": "sign_in", "login": LOGIN}, 401)
        if self._limited(self.step_limit, _digest(s["token"])[:24]):
            return answer({"error": "Too many steps at once. Wait a minute.", "kind": "rate_limited"}, 429)
        try:
            data = json.loads(body[:MAX_BODY]) if len(body) <= MAX_BODY else None
        except ValueError:
            data = None
        if not isinstance(data, dict):
            return answer({"error": "The step is not readable.", "kind": "bad_request"}, 400)
        step = str(data.get("step") or "").strip().lower()
        if step not in READ_STEPS:
            return answer({"error": "Deciding, the dry run and creating come in the next version of this page.",
                           "kind": "not_yet"}, 400)
        args = {k: str(data[k]).strip()[:NAME_MAX] for k in ("workspace", "source", "schema")
                if isinstance(data.get(k), str) and data[k].strip()}
        if step:
            args["step"] = step
        text = str(data.get("text") or "").strip()[:NAME_MAX]
        tokens = SessionTokens(self.obo, s["token"], s["tid"], s["who"])
        out = self.run(tokens, args)
        if text:
            out = self._typed(tokens, args, out, text)
        return answer(view(out) if not out.get("match") else {**view(out), "match": out["match"]})

    def _typed(self, tokens, args: dict, out: dict, text: str) -> dict:
        """A typed name for the choice on screen: matched by fixed rules against the names start offered; one match
        is taken like a tap on it, otherwise the same step comes back with what matched."""
        offered = [a for a in out.get("actions") or [] if isinstance(a, dict) and a.get("kind") == "choose" and not a.get("disabled")]
        name, candidates = match_choice(text, [str(a.get("label") or "") for a in offered])
        if name is None:
            say = (f"More than one name matches “{text}”: {', '.join(candidates)}. Tap the one you mean."
                   if candidates else f"No name here matches “{text}”. Tap one of the names, or type part of it.")
            return {**out, "match": {"text": text, "candidates": candidates, "say": say}}
        hit = next(a for a in offered if a.get("label") == name)
        picked = _args(hit.get("arguments"))
        return self.run(tokens, picked) if picked is not None else out

    def routes(self) -> list:
        """Every method is routed here, so a method a route does not take answers the same 404 as no route (a 405
        would say that something lives at the address)."""
        from starlette.concurrency import run_in_threadpool
        from starlette.routing import Route
        every = ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]

        def route(path: str, method: str, fn, threaded: bool = False, body: bool = False):
            async def handler(request):
                if request.method not in ((method, "HEAD") if method == "GET" else (method,)):
                    return self.not_found(request)
                args = (request, await request.body()) if body else (request,)
                return await run_in_threadpool(fn, *args) if threaded else fn(*args)
            return Route(path, handler, methods=every)
        return [route(PATH, "GET", self.page), route(LOGIN, "GET", self.login),
                route(CALLBACK, "GET", self.callback, threaded=True), route(LOGOUT, "POST", self.logout),
                route(STEP, "POST", self.step, threaded=True, body=True)]


def routes(cfg, validator, obo, entra_post=None, run=None) -> list:
    """The /app routes (server.build_app adds them in Entra mode). Each answers 404 while KRUSGRAPH_APP_TENANTS is empty."""
    return App(cfg, validator, obo, entra_post, run).routes()
