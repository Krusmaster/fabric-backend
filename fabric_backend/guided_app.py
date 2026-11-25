"""AP1: the guided chat at /app, hidden and closed by default (the founder's decision of 24 November 2026, "5a").

A person signs in with Microsoft Entra and is walked through the read-only half of the Start Krusgraph path as a chat:
the workspace, the source, the schema, then Krusgraph reads the tables, proposes keys and links by its fixed rules and
counts them against the rows. The mascots say each step (Onto points the way, the Thinker checks, the Builder builds);
the person answers with buttons. There is no AI model anywhere in it: every answer is the `start` tool's own (server.start,
start_flow.guide), the same engine and step logic the MCP connector uses, called with the person's own sign-in. Free text
is taken only where a fixed rule resolves it: a typed name is matched against the names offered (match_choice).

AP2 (guided_build.py) adds the writing half: Decide (the start tool's own decide step and buttons), the dry run of
what would be built (the Fabric workload's build, each item through its MCP tool), Create only after a confirm dialog
that lists each item by name and the dry run's token, and verify_build's check of what was built. The step endpoint
takes the read steps and Decide; the dry run, Create and the check after it have their own endpoint, /app/api/build.

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
BUILD = PATH + "/api/build"               # AP2: dry run, Create, verify (guided_build.py)
ENV = "KRUSGRAPH_APP_TENANTS"
SESSION_COOKIE = "__Host-kg_app"
FLOW_COOKIE = "__Host-kg_app_flow"
SESSION_TTL = 3600                      # seconds; never longer than the access token
TXN_TTL = 600                           # a sign-in on its way through Entra
MAX_SESSIONS, MAX_TXNS = 500, 1000      # bounded memory: the oldest go first
MAX_BODY = 4096
NAME_MAX = 256
TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{16,128}")
# The steps of the start tool this endpoint serves: choosing the data, the check and (AP2) Decide. The dry run and
# Create are not start steps here: they go to BUILD (guided_build.py), which the page calls for a button with step dry_run.
READ_STEPS = ("", "workspace", "source", "schema", "data", "check", "decide")
BUTTON_STEPS = READ_STEPS + ("dry_run",)
NEXT_LINE = "Next: decide what needs you, then a dry run of what would be built."
# AP2b (finding 5): /app writes after an explicit confirm, so the page says when it writes and what this session wrote.
HEADER = "Nothing is written to Fabric until you confirm a Create."
NOTHING_WRITTEN = ("Nothing has been written to Fabric in this session: the check, Decide and the dry run only read, "
                   "and Create writes only the names you confirm.")
REVIEWS = ("accepted", "rejected", "skipped")
BUILD_ACTIONS = ("places", "lakehouses", "dry_run", "confirm", "create", "state", "verify")


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

    def powerbi(self) -> str:
        """AP2: for the Power BI REST API (Create's one refresh of a new semantic model), as workload_api.Tokens."""
        from .workload_api import POWERBI_SCOPE
        return self.obo.token(self.user_token, self.tenant, POWERBI_SCOPE)


# ------------------------------------------------------------------ fixed rules for typed text ----------------------

MATCH_RULES = (lambda f, t: f == t, lambda f, t: f.startswith(t), lambda f, t: t in f)


def _fold(text: str) -> str:
    return " ".join(str(text or "").split()).casefold()


def match_choice(text: str, names: list[str]) -> tuple[str | None, list[str]]:
    """A typed name against the names offered, by fixed rules in order: the same name (ignoring case and the spaces
    around it), else the one name that starts with the text, else the one name that contains it. (name, []) when one
    rule finds exactly one; (None, candidates) otherwise, so the page can say what matched. No guessing beyond that."""
    t = _fold(text)
    if not t:
        return None, []
    folded = [(n, n.casefold()) for n in names if isinstance(n, str) and n.strip()]
    for rule in MATCH_RULES:
        hits = [n for n, f in folded if rule(f, t)]
        if len(hits) == 1:
            return hits[0], []
        if len(hits) > 1:
            return None, hits[:8]
    return None, []


# AP2b (finding 4): the names this session has already been shown (workspaces, sources, schemas), so a typed name that
# is not on screen can be found where it was listed before. Only names the start tool read for this session's own
# steps; nothing is read from Fabric for it. Kept in memory per session, never longer than the session.
SEEN = Store(MAX_SESSIONS)
SEEN_PLACES = 200
KIND = {0: "workspace", 1: "source", 2: "schema"}


def _place(out: dict) -> tuple | None:
    """Where the names of a choosing answer live: () for the workspaces, (ws,) for its sources, (ws, src) for schemas."""
    c = out.get("chosen") or {}
    stage = out.get("stage")
    if stage == "workspace":
        return ()
    if stage == "source" and c.get("workspace"):
        return (c["workspace"],)
    if stage == "schema" and c.get("workspace") and c.get("source"):
        return (c["workspace"], c["source"])
    return None


def remember(sid: str, out: dict) -> None:
    """The names of one start answer: the choices on screen, and the names it chose itself ("demo › demo_lh › dbo ✓")."""
    if not sid or not isinstance(out, dict) or out.get("error"):
        return
    st = SEEN.get(sid) or {}
    place = _place(out)
    names = [str(a.get("label")) for a in out.get("actions") or []
             if isinstance(a, dict) and a.get("kind") == "choose" and a.get("label") and "+" not in str(a["label"])]
    if place is not None and names:
        st[place] = names[:60]
    c = out.get("chosen") or {}
    path = [c.get(k) for k in ("workspace", "source", "schema")]
    for i, name in enumerate(path):
        if not isinstance(name, str) or not name or "+" in name or not all(path[:i]):
            break
        here = tuple(path[:i])
        if name not in st.get(here, []):
            st[here] = (st.get(here) or []) + [name]
    while len(st) > SEEN_PLACES:
        del st[next(iter(st))]
    SEEN.put(sid, st, time.time() + SESSION_TTL)


def elsewhere(sid: str, text: str, here: tuple | None) -> list[dict]:
    """A typed name among the names this session saw in other places, by match_choice's rules in order (the first rule
    that finds any wins): at most three, each {kind, name, where, arguments}. [] when none."""
    t = _fold(text)
    st = SEEN.get(sid) if sid else None
    if not t or not st:
        return []
    for rule in MATCH_RULES:
        hits = [(place, n) for place, names in st.items() if place != here for n in names if rule(n.casefold(), t)]
        if hits:
            break
    else:
        return []
    out = []
    for place, n in hits[:3]:
        keys = ("workspace", "source", "schema")[:len(place) + 1]
        args = dict(zip(keys, (*place, n)))
        if len(place) == 2:
            args["step"] = "check"
        out.append({"kind": KIND[len(place)], "name": n, "where": " › ".join(place), "arguments": args})
    return out


def elsewhere_words(text: str, hits: list[dict]) -> tuple[str, list[dict]]:
    """The sentence and the chips for elsewhere()'s hits: "“shop” is in demo › demo_lh." and "Go to demo › demo_lh › shop"."""
    said = []
    for h in hits:
        what = {"workspace": "a workspace", "source": "a source", "schema": "a schema"}[h["kind"]]
        said.append(f"“{h['name']}” is {what} in {h['where']}" if h["where"] else f"“{h['name']}” is {what} of yours")
    say = f"No name here matches “{text}”, but " + "; ".join(said) + "."
    chips = [{"label": "Go to " + " › ".join(x for x in (h["where"], h["name"]) if x), "arguments": _args(h["arguments"]),
              "primary": i == 0} for i, h in enumerate(hits)]
    return say, [c for c in chips if c["arguments"] is not None]


# ------------------------------------------------------------------ the start tool's answer, for the page ----------

def _args(a: dict | None) -> dict | None:
    """A button's arguments as the page may send them back: the three names and a step of this page, nothing else (a
    plan or a decision never travels through the page: Decide sends {item, review}, guided_build finds the start
    answer's own button for it)."""
    if not isinstance(a, dict):
        return None
    out = {k: str(a[k])[:NAME_MAX] for k in ("workspace", "source", "schema") if isinstance(a.get(k), str) and a[k].strip()}
    step = str(a.get("step") or "").strip().lower()
    if step not in BUTTON_STEPS:
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
    if stage == "schema" and v.get("choices"):
        _schema_choices(v)
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
        _table_count(v)
        v["next"] = NEXT_LINE
    if stage == "decide":                             # AP2: each decision as a card; the choices are the start tool's own
        from .guided_build import decisions_view
        v["decisions"] = decisions_view(out)
        v["open"] = int(out.get("open_decisions") or 0)
        if out.get("decided"):
            v["decided"] = [str(x) for x in out["decided"]][:20]
        if out.get("review_error"):
            v["review_error"] = str(out["review_error"])[:200]
        for b in v.get("buttons") or []:
            if b.get("arguments", {}).get("step") == "dry_run" and v["open"]:
                b["primary"] = False                  # secondary until each decision is answered or skipped
                b["why"] = "Next leaves the open decision open."
    return v


def _schema_choices(v: dict) -> None:
    """AP2b (finding 2): the schema choices with the Model editor's rules (W1: workload_api.system_schema and
    krusgraph_schema, the words of sourceWords.ts): system schemas left out, the source schemas first, Krusgraph's own
    after them, labelled and never suggested. A combined chip ("dbo+gold+krusgraph+silver") that mixes Krusgraph's own
    output with sources is not offered; the source schemas together are, under the start tool's own rule for that chip
    (SM5: two to four schemas with tables, server._start_options). A schema is still planned by name if typed."""
    from .multi_schema import SEP, parts
    from .workload_api import OWN_SCHEMA_WORDS, krusgraph_schema, system_schema
    src, own, combos = [], [], []
    for ch in v["choices"]:
        names = parts(ch["arguments"].get("schema") or ch["label"])
        if not names or any(system_schema(n) for n in names):
            continue
        kinds = [krusgraph_schema(n) for n in names]
        if len(names) > 1:
            if not any(kinds):
                combos.append(ch)
            continue
        if kinds[0]:
            ch = {k: x for k, x in ch.items() if k != "selected"}
            ch["hint"] = ", ".join(x for x in (ch.get("hint"), OWN_SCHEMA_WORDS[kinds[0]]) if x)
            ch["own"] = kinds[0]
            own.append(ch)
        else:
            src.append(ch)
    full = [ch for ch in src if not ch.get("disabled")]
    if own and not combos and 2 <= len(full) <= 4:
        c = v.get("chosen") or {}
        n = sum(int(w[0]) for w in (str(ch.get("hint") or "").split() for ch in full) if w and w[0].isdigit())
        combos.append({"label": SEP.join(ch["label"] for ch in full), "hint": f"{n} tables, one plan",
                       "arguments": {"workspace": c.get("workspace"), "source": c.get("source"),
                                     "schema": SEP.join(ch["label"] for ch in full), "step": "check"}})
    if own and len(full) == 1 and not any(ch.get("selected") for ch in src):
        full[0]["selected"] = True                     # the one source schema with tables, suggested as the editor does
        full[0]["hint"] = ", ".join(x for x in (full[0].get("hint"), "suggested") if x)
    dropped = {str(b.get("arguments", {}).get("schema")) for b in own}
    if any(str(b.get("arguments", {}).get("schema")) in dropped for b in v.get("buttons") or []):
        v["buttons"] = [b for b in v["buttons"] if str(b.get("arguments", {}).get("schema")) not in dropped]
        c = v.get("chosen") or {}
        v["say"] = f"Which schema in {c.get('source')} shall I read?"        # not "I picked it": Krusgraph's own output
    v["choices"] = src + combos + own
    if own:
        v["own_line"] = ("Listed last, as Krusgraph's own output: " + ", ".join(ch["label"] for ch in own)
                         + ". Read one only to see what Krusgraph wrote.")


def _table_count(v: dict) -> None:
    """AP2b (finding 3): the check's tile said "13 tables read" while the map said 17: the start tool counts the tables
    with a key (one review item each), the map lists every table read. The tiles and the sentence now count every
    table the map has, and one line names the tables without a key and why."""
    tables = (v.get("map") or {}).get("tables") or []
    counts = v.get("counts") or {}
    keyed = counts.get("tables")
    if not tables or not isinstance(keyed, int) or len(tables) <= keyed:
        return
    total = len(tables)
    bare = [str(t.get("name")) for t in tables if not t.get("key")]
    counts["tables"], counts["keyed"] = total, keyed
    head = f"{keyed} tables, "
    if v.get("say", "").startswith(head):
        v["say"] = f"{total} tables, " + v["say"][len(head):]
    shown = ", ".join(bare[:8]) + (f" and {len(bare) - 8} more" if len(bare) > 8 else "")
    n = len(bare) or total - keyed
    one = n == 1
    line = (f"{keyed} of the {total} tables have a key the rules could prove; {n} {'has' if one else 'have'} none"
            + (f" ({shown})" if bare else "") + f", so no link can point at {'it' if one else 'them'} and no key of {'its' if one else 'theirs'} is "
            "counted.")
    v["lines"] = [line] + list(v.get("lines") or [])


def closing_line(sid: str) -> str:
    """AP2b (finding 5): the Builder's closing words after the check: what this session wrote to Fabric, or nothing."""
    from .guided_build import BUILDS
    made = [i for i in ((BUILDS.get(sid) or {}).get("created") or []) if isinstance(i, dict)] if sid else []
    if not made:
        return NOTHING_WRITTEN
    names = ", ".join(str(i.get("name") or i.get("type") or "an item") for i in made[:6]) + (" and more" if len(made) > 6 else "")
    return (f"In this session Create wrote {len(made)} {'item' if len(made) == 1 else 'items'} to Fabric, after your "
            f"confirm: {names}. The check, Decide and the dry run only read.")


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
             "nothing": NOTHING_WRITTEN, "error": coach.LINE["error"], "names": coach.NAMES,
             "decide": coach.LINE["decide"], "build": coach.LINE["build"], "dry_run": coach.LINE["dry_run"]}
    who = f"Signed in as {html.escape(name[:80])}. " if name else "Signed in. "
    body = f"""<section class="wrap app-wrap" aria-labelledby="app-h">
  <div class="app-chat">
    <div class="app-head">
      <span class="app-fig" data-mascot="onto" data-pose="rest" data-label=""></span>
      <div class="app-title"><h1 id="app-h">Your data, step by step</h1>
        <p class="muted tiny">{who}{HEADER}</p></div>
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
        self.build_limit = Limiter(parse("120/minute,2400/hour"), [])        # per session; Create's progress is polled

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
            return answer({"error": "The dry run and Create have their own address on this page (/app/api/build).",
                           "kind": "wrong_step"}, 400)
        args = {k: str(data[k]).strip()[:NAME_MAX] for k in ("workspace", "source", "schema")
                if isinstance(data.get(k), str) and data[k].strip()}
        if step:
            args["step"] = step
        text = str(data.get("text") or "").strip()[:NAME_MAX]
        tokens = SessionTokens(self.obo, s["token"], s["tid"], s["who"])
        sid = _digest(request.cookies.get(SESSION_COOKIE) or "")
        out = self.run(tokens, args)
        remember(sid, out)
        tap = data.get("decide")
        if step == "decide" and tap is not None:              # AP2: one tap on a decision card
            if (not isinstance(tap, dict) or not isinstance(tap.get("item"), str) or len(tap["item"]) > 400
                    or tap.get("review") not in REVIEWS):
                return answer({"error": "The decision is not readable.", "kind": "bad_request"}, 400)
            from .guided_build import decide_action
            again = decide_action(out, tap["item"], tap["review"])
            if again is None:
                return answer({**view(out), "match": {"text": "", "candidates": [],
                                                      "say": "That choice is not offered here now. Here is the step again."}})
            out = self.run(tokens, again)                     # the start card's own button: recorded as a tap
            log("decided", review=tap["review"])
        if text:
            out = self._typed(tokens, args, out, text, sid)
            remember(sid, out)
        v = view(out) if not out.get("match") else {**view(out), "match": out["match"]}
        if v.get("decisions"):
            from .guided_build import remember_rules
            remember_rules(sid, v["decisions"])
        if v.get("stage") == "check":
            v["closing"] = closing_line(sid)
        return answer(v)

    def build(self, request, body: bytes):
        """POST /app/api/build {action, ...} (AP2, guided_build.py), with the step endpoint's locks: this site's Origin,
        JSON, a session of an allowed tenant, a rate limit per session. Actions:
          places                                   the workspaces to build in
          lakehouses {workspace}                   the lakehouses of one of them
          dry_run {workspace, source, schema, target?: {workspace, lakehouse?}, update?: [kind]}
          confirm {token, names}                   the confirm dialog's yes: the dry run's token and exactly its names
          create {run, kind}                       one confirmed item, as a background operation
          state {operation_id}                     how that item is going; its card once done
          verify                                   verify_build's rules on what this session created"""
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
        if self._limited(self.build_limit, _digest(s["token"])[:24]):
            return answer({"error": "Too many requests at once. Wait a minute.", "kind": "rate_limited"}, 429)
        try:
            data = json.loads(body[:MAX_BODY]) if len(body) <= MAX_BODY else None
        except ValueError:
            data = None
        if not isinstance(data, dict) or data.get("action") not in BUILD_ACTIONS:
            return answer({"error": "The request is not readable.", "kind": "bad_request"}, 400)
        from . import guided_build as B
        from .errors import explain
        sid = _digest(request.cookies.get(SESSION_COOKIE) or "")
        tokens = SessionTokens(self.obo, s["token"], s["tid"], s["who"])
        owner = "app-" + s["who"]
        act = data["action"]
        try:
            if act == "places":
                return answer(B.places(tokens))
            if act == "lakehouses":
                return answer(B.lakehouses(tokens, str(data.get("workspace") or "")[:64]))
            if act == "dry_run":
                c = B.chosen(data)
                if c is None:
                    return answer({"error": "Choose the workspace, the source and the schema first.", "kind": "bad_request"}, 400)
                update = data.get("update") or []
                if not isinstance(update, list) or any(u not in dict(B.OUTPUTS) for u in update):
                    return answer({"error": "The update list is not readable.", "kind": "bad_request"}, 400)
                try:
                    target = B.target_of(tokens, c, data.get("target"))
                except ValueError as e:
                    return answer({"error": str(e), "kind": "bad_request"}, 400)
                return answer(B.dry_run(tokens, sid, c, target, list(update)))
            if act == "confirm":
                names = data.get("names")
                return answer(B.confirm(tokens, sid, str(data.get("token") or "")[:80],
                                        names if isinstance(names, list) and len(names) <= 20 else []))
            if act == "create":
                return answer(B.create_item(tokens, sid, str(data.get("run") or "")[:64], str(data.get("kind") or "")[:40], owner))
            if act == "state":
                return answer(B.item_state(tokens, sid, str(data.get("operation_id") or "")[:64], owner))
            return answer(B.verify(tokens, sid))
        except Exception as exc:                                    # noqa: BLE001 — explained, never leaked
            got = explain(exc, f"/app {act}")
            log("build_failed", action=act, error=type(exc).__name__, kind=got.get("kind"))
            return answer({k: str(got[k])[:400] for k in ("error", "kind", "hint") if got.get(k)})

    def _typed(self, tokens, args: dict, out: dict, text: str, sid: str = "") -> dict:
        """A typed name for the choice on screen: matched by fixed rules against the names start offered; one match
        is taken like a tap on it, otherwise the same step comes back with what matched. AP2b: when nothing here
        matches, the names this session saw elsewhere are searched by the same rules, and where it is is said, with a
        chip to go there (no Fabric read for it)."""
        offered = [a for a in out.get("actions") or [] if isinstance(a, dict) and a.get("kind") == "choose" and not a.get("disabled")]
        name, candidates = match_choice(text, [str(a.get("label") or "") for a in offered])
        if name is None:
            go: list = []
            if candidates:
                say = f"More than one name matches “{text}”: {', '.join(candidates)}. Tap the one you mean."
            else:
                hits = elsewhere(sid, text, _place(out))
                say, go = elsewhere_words(text, hits) if hits else (
                    f"No name here matches “{text}”. Tap one of the names, or type part of it.", [])
            return {**out, "match": {"text": text, "candidates": candidates, "say": say, **({"go": go} if go else {})}}
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
                route(STEP, "POST", self.step, threaded=True, body=True),
                route(BUILD, "POST", self.build, threaded=True, body=True)]


def routes(cfg, validator, obo, entra_post=None, run=None) -> list:
    """The /app routes (server.build_app adds them in Entra mode). Each answers 404 while KRUSGRAPH_APP_TENANTS is empty."""
    return App(cfg, validator, obo, entra_post, run).routes()
