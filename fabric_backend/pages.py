"""The public site — served by the MCP server itself, so one domain is enough.

    /                  start page           /check              the engine in the browser; ?example=sample&guide=1 is the guided demo
    /demo, /explore    redirects to /check (n55)
    /start             get started          /support            support
    /partners          partners             /partners/workspace illustrative partner workspace
    /docs              setup and usage      /privacy            privacy policy
    /lovable           using the created API with Lovable's Fabric connector
    /local             the local server over ODBC, and exactly what leaves the machine
    /use-cases         industries, typical tables and what the engine finds in them (use_cases.py)
    /mascots           mascot review page (noindex, unlinked)
    /consent/done      where Microsoft sends the admin after the consent link on /start (noindex; consent_done_html)
    /docs.md, /privacy.md, /start.md, /lovable.md, /local.md, /use-cases.md   the same content as Markdown (for /llms.txt and agents)
    /static/...        css, js, fonts, icons (self-hosted; no external resources at runtime)
    /demo/plan.json    the real `plan()` on the synthetic shop schema

Filled from environment: PRODUCT_NAME, CONTACT_EMAIL, COMPANY_ORGNR (optional — the org. nr line is shown only when
set), MCP_PUBLIC_URL, ENTRA_CLIENT_ID, PARTNER_SIGNIN (set to 1 to show the not-yet-wired
"Continue with Microsoft" button on /partners).
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
from importlib import resources
from pathlib import Path

GITHUB = "https://github.com/Krusmaster/fabric-backend"
HERE = Path(__file__).resolve().parent
STATIC_DIR = HERE / "static"

STATIC_TYPES = {".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".svg": "image/svg+xml",
                ".png": "image/png", ".woff2": "font/woff2", ".txt": "text/plain; charset=utf-8", ".json": "application/json",
                ".ico": "image/x-icon", ".mjs": "text/javascript; charset=utf-8", ".wasm": "application/wasm",
                ".zip": "application/zip", ".whl": "application/zip",
                ".mp4": "video/mp4", ".webp": "image/webp", ".vtt": "text/vtt; charset=utf-8"}   # n157: the overview film

PAGES = {
    # path: (template, title, description, nav key)
    "/": ("home.html", "{{PRODUCT}} | Understand your Microsoft Fabric tables",
          "Explore keys and relationships in Microsoft Fabric, check them against your data, and review the plan in Claude before building on it.", "product"),
    "/check": ("check.html", "Check your files in the browser — {{PRODUCT}}",
               "Drop CSV or Excel exports, or paste a list of columns: see how the tables connect and what is wrong, with the rule behind each item. The files are read in your browser and never uploaded.", "check"),
    "/start": ("start.html", "Connect {{PRODUCT}} — the set-up guide",
               "What you need, admin approval in Microsoft Entra, and how to add {{PRODUCT}} as a custom connector in Claude.", "start"),
    "/support": ("support.html", "Get help with {{PRODUCT}}",
                 "How to get help with {{PRODUCT}}: email with the error, kind and hint from the tool's answer, report a bug or a plan that came out wrong on GitHub Issues, and the most common first errors.", "support"),
    "/partners": ("partners.html", "Try a pilot — {{PRODUCT}}",
                  "Bring one number your team cannot agree on: a first assessment says what it would take, a {{PRODUCT}} pilot explains the number with the counts behind it and leaves a reviewed model. Kruse Consulting AB; not affiliated with Microsoft.", "partners"),
    "/partners/workspace": ("workspace.html", "A sample pilot — {{PRODUCT}}",
                            "A sample {{PRODUCT}} pilot on a synthetic shop schema: Connect, Explore, Review, Build. No customer workspace is connected.", "partners"),
    "/use-cases": ("use_cases.html", "Use cases — {{PRODUCT}}",
                   "Start from an undocumented lakehouse, a join to check or an app to build. Three synthetic examples drawn as maps show what {{PRODUCT}} proposes and what still needs your judgement.", "usecases"),
    "/use-cases/build": ("use_cases_build.html", "What you can build from a plan — {{PRODUCT}}",
                         "What each {{PRODUCT}} tool returns for the synthetic shop plan: the API, views, ontology, semantic model and data agent, with each tool's test status.", "usecases"),
    "/it": ("it.html", "For your IT department — {{PRODUCT}}",
            "For a BI lead to forward to IT: the delegated permissions the {{PRODUCT}} Entra app asks for and why, what is stored where and for how long, how to revoke access, and who stands behind it.", ""),
    "/pricing": ("pricing.html", "Pricing — {{PRODUCT}}",
                 "Check and the connector in Claude are free and open source (MIT); a pilot with named deliveries and ongoing work for a team are on request and invoiced. What is stored, permissions and how to buy.", "pricing"),
    "/terms": ("terms.html", "Preview terms — {{PRODUCT}}",
               "Preview terms for {{PRODUCT}}: a preview service, code under the MIT licence, nothing created in Fabric unless you ask for it (a dry run first for every creating tool) and only with your own permissions.", ""),
    "/mascots": ("mascots.html", "Mascot review — {{PRODUCT}}",
                 "Review page for the three mascots: every pose and demo state.", ""),
}


# n53: who stands behind the product, in the maintainer's words (29 October 2026), and what is true of it and checkable.
# Only these phrasings: tests/test_site.py keeps "partner", "certified", "endorsed" and "offices" off the site otherwise.
BEHIND = ("Member of the Microsoft AI Cloud Partner Program", "Based in Uppsala, Sweden, and Bern, Switzerland")
# n58: the date on /terms, changed by hand with the text
TERMS_UPDATED = "30 October 2026"
BUILT = ("Built for Microsoft Fabric", "Sign in with Microsoft Entra ID", "Hosted in Azure, Sweden Central")


def _vars() -> dict[str, str]:
    from urllib.parse import quote
    from . import tool_status as ts
    url = os.environ.get("MCP_PUBLIC_URL", "https://example.com/mcp")
    domain = url.split("/")[2]
    product = os.environ.get("PRODUCT_NAME", "fabric-backend")
    orgnr = os.environ.get("COMPANY_ORGNR", "").strip()
    return {
        "PRODUCT": product, "PRODUCT_LOWER": product.lower(), "PRODUCT_URL": quote(product),
        "DOMAIN": domain,
        "CONTACT": os.environ.get("CONTACT_EMAIL", "contact@" + domain),
        "ORGNR_SUFFIX": (", org. nr " + orgnr) if orgnr else "",
        "ORGNR_PAREN": (" (org. nr " + orgnr + ")") if orgnr else "",
        "ORGNR_DOT": (" · Org. no. " + orgnr) if orgnr else "",
        "MCP_URL": url,
        "BEHIND": " · ".join(BEHIND), "BUILT": " · ".join(BUILT),
        "CLIENT_ID": os.environ.get("ENTRA_CLIENT_ID", "<client id>"),
        "GITHUB": GITHUB,
        "TERMS_UPDATED": TERMS_UPDATED,
        "LABEL_CHECK": CHECK_LABEL, "LABEL_CONNECT": CONNECT_LABEL,          # n149: the two ways in, one label each
        # n75: how much the hosted tools count, read from server.py (R5's sample and query budget, validate_plan's default)
        **_counting_limits(),
        "ASSET_V": asset_version(),
        "PARTNER_SIGNIN": "1" if os.environ.get("PARTNER_SIGNIN", "").strip() in {"1", "true", "yes"} else "",
        # the privacy page states what this deployment keeps: console logs in Log Analytics or nowhere, org hashes or none
        "LOGS_KEPT_DAYS": _days(os.environ.get("KRUSGRAPH_LOG_RETENTION_DAYS", "")),
        "LOGS_NOT_KEPT": "" if _days(os.environ.get("KRUSGRAPH_LOG_RETENTION_DAYS", "")) else "1",
        "USAGE_ORG": "1" if os.environ.get("KRUSGRAPH_USAGE_SALT", "").strip() else "",
        "RATE_LIMITS": "" if os.environ.get("KRUSGRAPH_RATE_LIMITS", "1").strip().lower() in {"0", "off", "false", "no"} else "1",
        # client registration for MCP clients other than Claude (registration.py) keeps a few sign-in records; the page says which
        "CLIENT_REGISTRATION": "1" if _registration_on() else "", "NO_CLIENT_REGISTRATION": "" if _registration_on() else "1",
        # the MCP clients the site names as working with the hosted service, and the address for those that register
        "MCP_CLIENTS": _clients_sentence(), "CONNECT_URL": url.split("/mcp")[0] + "/mcp/connect", "CONNECT_TESTED": _connect_tested(),
        "CONNECT_URL_OAUTH": url.split("/mcp")[0] + "/oauth",
        # n146: one instruction for Claude Code on every page that gives one (llms.txt, and {{CLAUDE_CODE_CONNECT}} for /docs)
        "CLAUDE_CODE_CONNECT": _claude_code_connect(product.lower(), url, domain),
        # n73: Lovable's two rows in tool_status.CLIENTS (as an MCP client, and reading the API), for /lovable
        "LOVABLE_MCP_STATUS": _client_status("Lovable", "via MCP"), "LOVABLE_API_STATUS": _client_status("Lovable", "via the GraphQL API"),
        # n68: where Microsoft sends the admin after the consent on /start (CONSENT_PATH); the encoded form goes in the link
        "CONSENT_URL": "https://" + domain + CONSENT_PATH, "CONSENT_URL_ENC": quote("https://" + domain + CONSENT_PATH, safe=""),
        "REGISTRATION_WHERE": ("the server's memory (lost when it restarts)"
                               if os.environ.get("KRUSGRAPH_REGISTRATION_STORE", "").strip().lower() == "memory"
                               else "an Azure Table Storage table of ours in the service's Azure region"),
        # the test status, from tool_status: the live run's date and what it covered, and each tool's status in a sentence
        "LIVE_RUN_DATE": ts.LIVE_RUN_DATE, "LIVE_RUN_SUMMARY": ts.LIVE_RUN_SUMMARY, "CREATE_API_STATUS": ts.create_api_status(), "CREATE_API_WORD": ts.create_api_word(),
        **{f"STATUS_{name.upper()}": ts.phrase(name) for name in ts.STATUS},
        # the short form next to an offer on the home page; the long form, with its history, is on /docs#test-status
        **{f"SHORT_{name.upper()}": ts.short(name) for name in ts.STATUS},
        # the sources with their status, as the hub and the docs' "Why" section give it (tool_status.SOURCES)
        "SOURCES_STATUS": _listed([f"a {n[0].lower() + n[1:] if n != 'SQL database' else n} ({ts.source_word(t)})"
                                    for n, t in ts.SOURCES]).replace(" and a ", " or a "),
    }


def _claude_code_connect(low: str, url: str, domain: str) -> str:
    """How Claude Code connects to this server, from tool_status.CLIENTS and whether client registration is on."""
    from .tool_status import CLIENTS
    c = next(c for c in CLIENTS if c.name == "Claude Code")
    if _registration_on():
        connect = url.split("/mcp")[0] + "/mcp/connect"
        return (f"`claude mcp add --transport http {low} {connect}`: Claude Code registers itself at /mcp/connect and signs in "
                f"with Microsoft. {c.status} (not tried yet).")
    return (f"`claude mcp add --transport http {low} {url}` takes the URL, but Claude Code's local sign-in redirect is not "
            f"registered on the Entra app, and client registration is off on this server, so it cannot sign in "
            f"to {domain} today.")


def _counting_limits() -> dict[str, str]:
    """plan_backend's R5 reads the first R5_SAMPLE distinct values of a candidate column with at most R5_MAX_QUERIES
    counting queries; validate_plan checks up to max_items keys and relationships (its default). From server.py, so the
    docs cannot drift from the code: the loaded module when the server runs, else its source (importing server.py
    needs the Entra settings, and the pages also render on the local demo and in tests without them)."""
    import ast
    import inspect
    import sys
    server = sys.modules.get("fabric_backend.server")
    if server is not None:
        return {"R5_SAMPLE": str(server.R5_SAMPLE), "R5_MAX_QUERIES": str(server.R5_MAX_QUERIES),
                "VALIDATE_MAX_ITEMS": str(inspect.signature(server.validate_plan).parameters["max_items"].default)}
    tree = ast.parse((HERE / "server.py").read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Tuple):      # R5_SAMPLE, R5_MAX_QUERIES = 200, 20
            for name, value in zip(node.targets[0].elts, node.value.elts):
                if name.id in ("R5_SAMPLE", "R5_MAX_QUERIES"):
                    out[name.id] = str(ast.literal_eval(value))
        if isinstance(node, ast.FunctionDef) and node.name == "validate_plan":
            args = node.args
            defaults = dict(zip([a.arg for a in args.args][len(args.args) - len(args.defaults):], args.defaults))
            out["VALIDATE_MAX_ITEMS"] = str(ast.literal_eval(defaults["max_items"]))
    assert set(out) == {"R5_SAMPLE", "R5_MAX_QUERIES", "VALIDATE_MAX_ITEMS"}, out
    return out


def _client_status(name: str, where: str) -> str:
    """One client row of tool_status.CLIENTS as a sentence: its status word, since when it works, and its note."""
    from .tool_status import CLIENTS
    c = next(c for c in CLIENTS if c.name == name and c.where.startswith(where))
    return c.status + (f" (works since {c.works_since})" if c.works_since else "") + (f"; {c.note}" if c.note else "")


def _registration_on() -> bool:
    from .registration import effective
    return effective()                                  # review L17: not the flag alone; a layer that refused is off


def _listed(names: list[str]) -> str:
    return ", ".join(names[:-1]) + " and " + names[-1] if len(names) > 1 else "".join(names)


def _clients_sentence() -> str:
    """"Claude", or "Claude, VS Code and Cursor" once client registration is on (n82; "(and, Experimental, ...)" for a
    client whose row is Experimental)
    (tool_status.clients_working); a client not tested end to end is never named as plainly as Claude (n30)."""
    from .tool_status import CLIENTS, clients_working
    status = {c.name: c.status for c in CLIENTS}
    names = clients_working(_registration_on())
    tested = [c for c in names if status[c] == "Tested end to end"]
    other = [c for c in names if c not in tested]
    return _listed(tested) + (f" (and, Experimental, {_listed(other)})" if other else "")


def _connect_tested() -> str:
    """"Tested on 27 October 2026 with VS Code, Cursor and Glama": the clients recorded as signed in at /mcp/connect."""
    from .tool_status import connect_sentence
    return connect_sentence()


# n68: one click per client. The deep links follow the clients' documented install links: VS Code's
# `vscode:mcp/install?<url-encoded JSON {name,type,url}>` (and `vscode-insiders:` for Insiders), Cursor's
# `cursor://anysphere.cursor-deeplink/mcp/install?name=<name>&config=<base64 JSON {url}>`; Claude and Lovable take the
# address pasted in their own settings. Formats as written in the VS Code docs (Copilot: MCP servers, "URL handler") and
# the Cursor docs (MCP: install links); they could not be re-read from this build (the docs hosts are not reachable from
# it), so a check against those pages is part of the first live try. The clients that register themselves are offered
# only when client registration is on (/mcp/connect exists then) and, for VS Code and Cursor, once tool_status records
# them as signed in there (the hub's rule); Claude always.
def connect_links() -> dict[str, str]:
    import base64
    import json
    from urllib.parse import quote
    v = _vars()
    install = lambda scheme: scheme + ":mcp/install?" + quote(json.dumps({"name": v["PRODUCT"], "type": "http", "url": v["CONNECT_URL"]}, separators=(",", ":")), safe="")
    return {"vscode": install("vscode"), "vscode_insiders": install("vscode-insiders"),
            "cursor": "cursor://anysphere.cursor-deeplink/mcp/install?name=" + quote(v["PRODUCT"], safe="") + "&config="
                      + base64.b64encode(json.dumps({"url": v["CONNECT_URL"]}, separators=(",", ":")).encode()).decode(),
            "claude": "https://claude.ai/customize/connectors"}


# n80: the first question the Connect menu offers to copy: read-only, and it needs no workspace name (list_workspaces
# takes no arguments, and the server's instructions start there); the tools it leads to are FIRST_QUESTION_TOOLS, all of
# them reading (tests/test_site.py checks both against server.py and tool_status).
FIRST_QUESTION = ("List my Fabric workspaces, then map how the tables in the lakehouse I choose connect, and check the "
                  "links against the rows.")
FIRST_QUESTION_TOOLS = ("list_workspaces", "list_sources", "plan_backend", "validate_plan")


def consent_link() -> str:
    """The admin consent link of /start's step 1, with /consent/done as where Microsoft brings the admin back."""
    v = _vars()
    return ("https://login.microsoftonline.com/organizations/adminconsent?client_id=" + v["CLIENT_ID"]
            + "&redirect_uri=" + v["CONSENT_URL_ENC"])


def admin_note() -> str:
    """n80: the note a person copies to their admin (the Connect menu, and the page after a sign-in that stopped for want
    of admin consent): the consent link, what is approved, and /it. Copying sends nothing."""
    v = _vars()
    p = v["PRODUCT"]
    return (f"Hi, could you approve {p} for our Microsoft Entra tenant? It connects Claude and other AI clients to Microsoft "
            f"Fabric, so we can map and check our lakehouse tables.\n\n"
            f"Admin consent link (sign in with an administrator account): {consent_link()}\n\n"
            f"What you approve: delegated Fabric permissions only. Every call runs as the signed-in person, with that "
            f"person's own Fabric rights; the app asks for no application permissions.\n\n"
            f"Each permission and why, what is stored, and how to revoke it: {site_url()}/it")


def connect_menu_html(where: str) -> str:
    """The Connect button and its chooser: `where` is "start" (n149: step 3 of /start, "Choose your client"; the home
    page's hero has a plain link to /start instead) or "pop" (the panel opens over the page; n91: the hub's
    inline chooser is gone, the hub's node links to /start instead). A <details>, so it works without JavaScript; the copy buttons
    need it (site.js). n80, Gustav's brief of 2 November 2026: Claude first and open (its connectors page, the address
    to copy, a first question to copy), Lovable under it, the other clients folded at the bottom (VS Code, then Cursor),
    and the admin line last, with a note to copy for the admin. No address is printed: each copy button holds the one
    its client needs."""
    v = _vars()
    e = lambda x: html.escape(x, quote=True)
    p, links = e(v["PRODUCT"]), connect_links()
    mcp, connect = e(v["MCP_URL"]), e(v["CONNECT_URL"])
    from .tool_status import CLIENTS, clients_working
    reg = _registration_on()
    working = clients_working(reg)                 # VS Code and Cursor only once the hosted service has signed them in, as in the hub
    # n82: "Experimental: " only before a client whose MCP row in tool_status.CLIENTS says so (Gustav's decision of
    # 2 November 2026: VS Code, Cursor and Lovable are Tested end to end)
    word = {c.name: c.status for c in CLIENTS if c.path}
    exp = lambda c: "" if word.get(c) == "Tested end to end" else "Experimental: "
    cap = lambda c, text: exp(c) + (text if exp(c) else text[0].upper() + text[1:])
    items = [f'<div class="connect-item connect-claude"><strong>Claude</strong>'
             f'<span class="connect-row"><a class="btn primary connect-main" href="{e(links["claude"])}" rel="noopener">Open Claude’s connectors</a>'
             f'<button type="button" class="btn secondary small" data-copy-text="{mcp}">Copy URL</button></span>'
             f'<span class="muted tiny">Add → Add custom connector, paste the URL and sign in with Microsoft.</span>'
             f'<span class="connect-row"><button type="button" class="btn ghost small" data-copy-text="{e(FIRST_QUESTION)}">Copy a first question</button></span>'
             f'<span class="muted tiny">Paste it in a new chat; it only reads.</span></div>']
    if reg:
        items.append(f'<div class="connect-item"><strong>Lovable</strong><span class="connect-row"><button type="button" class="btn secondary small" data-copy-text="{connect}">Copy URL</button></span>'
                     f'<span class="muted tiny">{cap("Lovable", "paste it under Connectors → Custom MCP, then Add &amp; authorize and sign in with Microsoft.")}</span></div>')
    other = []
    if "VS Code" in working:
        other.append(f'<div class="connect-item"><strong>VS Code</strong><span class="connect-row"><a class="btn primary small" href="{e(links["vscode"])}">Add to VS Code</a><a class="connect-alt" href="{e(links["vscode_insiders"])}">Insiders</a></span>'
                     f'<span class="muted tiny">{cap("VS Code", "opens VS Code, which asks before it adds the server; then you sign in with Microsoft.")}</span></div>')
    if "Cursor" in working:
        other.append(f'<div class="connect-item"><strong>Cursor</strong><span class="connect-row"><a class="btn primary small" href="{e(links["cursor"])}">Add to Cursor</a></span>'
                     f'<span class="muted tiny">{cap("Cursor", "opens Cursor’s install dialog; then you sign in with Microsoft.")}</span></div>')
    if other:
        items.append(f'<details class="connect-other"><summary>Other clients<span class="connect-caret" aria-hidden="true"></span></summary>{"".join(other)}</details>')
    guide = "" if where == "start" else '<span>Step by step: <a href="/start">the set-up guide</a>.</span>'
    label = "Choose your client" if where == "start" else "Connect"
    return (f'<details class="connect connect-{where}" data-connect id="connect">\n'
            f'<summary class="btn secondary">{label}<span class="connect-caret" aria-hidden="true"></span></summary>\n'
            f'<div class="connect-panel" role="group" aria-label="Add {p} to your client">\n<p class="connect-h">Add {p} to</p>\n{"".join(items)}\n'
            f'<p class="tiny connect-foot">Your admin approves {p} once; every call runs with your own Fabric permissions.'
            f'<span class="connect-row"><button type="button" class="btn ghost small connect-admin" data-copy-text="{e(admin_note())}">Copy a note to your admin</button>'
            f'{guide}</span></p>\n'
            f'</div>\n</details>')


HUB_LINK = "Connect {p} to Claude: the guide"     # n91: the name of the hub's node, a link to /start


def hub_status_note(clients: list[str]) -> str:
    """n95: the one line under the hub that keeps the statuses the hub no longer marks, all from tool_status: which
    sources are tested end to end and which are experimental, any client named there that is not tested end to end, and
    that some items need a permission the hosted service does not ask for today (tool_status.OPERATOR)."""
    from . import tool_status as ts
    tested = [n for n, t in ts.SOURCES if t]
    other = [n for n, t in ts.SOURCES if not t]
    parts = []
    if tested:
        parts.append(f"{_listed(tested)} {'is' if len(tested) == 1 else 'are'} tested end to end")
    if other:
        parts.append(f"{_listed(other)} {'is' if len(other) == 1 else 'are'} experimental")
    named = list(clients) + ["Lovable"]
    shown = {c.name: c.status for c in ts.CLIENTS if c.path}                 # an MCP client, at its address
    shown.update({c.name: c.status for c in ts.CLIENTS if not c.path})      # Lovable's row: the app builder over the API
    untested = [c for c in named if shown.get(c) and shown[c] != "Tested end to end"]
    if untested:
        parts.append(f"{_listed(untested)} {'is' if len(untested) == 1 else 'are'} experimental as {'a client' if len(untested) == 1 else 'clients'}")
    out = "; ".join(parts)
    out = out[:1].upper() + out[1:] + "." if out else ""
    if any(ts.STATUS[tool].available == ts.OPERATOR for _, tool in ts.BUILDS):
        out += " Some items need a permission the hosted service does not ask for today."
    return out.strip()


def hub_html() -> str:
    """The start page's hub under the hero (Gustav's brief of 27 October 2026): your data in Fabric and what {{PRODUCT}}
    builds there on the left, {{PRODUCT}} in the middle, where you build on the right, joined by lines as in the graph.
    n95: the cards carry names only, no status tags; the statuses are said once, in a muted line under the hub built from
    tool_status (hub_status_note), with a link to /docs#test-status; an MCP client is named only once it has signed
    in to the hosted service (Cursor and VS Code through client registration). Text names only, no third-party logos;
    the visual is hidden from screen readers, which get the same as one paragraph. n68: the middle node is the logo (the
    mark and the wordmark; the mark alone under 720 px) in the same faint coral frame. n91 (Gustav's decision of 2 November
    2026): no Connect chooser in the "Your data in Fabric" card (the hero's stays); the node in the middle is a link to
    /start, the set-up guide, and the one part of the visual screen readers and the keyboard get, named for where it leads."""
    from . import tool_status as ts
    v = _vars()
    p, low = html.escape(v["PRODUCT"]), html.escape(v["PRODUCT_LOWER"])
    clients = ts.clients_working(_registration_on())

    sources = "".join(f"<li><b>{n}</b></li>" for n, _ in ts.SOURCES)
    builds = "".join(f"<li><b>{n}</b></li>" for n, _ in ts.BUILDS)
    where = "".join(f'<li><b>{html.escape(c)}</b><span class="hub-via">via MCP</span></li>' for c in clients)
    where += '<li><b>Lovable</b><span class="hub-via">via the GraphQL API</span></li>'
    note = hub_status_note(clients)
    said = (f"Your data in Fabric: " + _listed([n for n, _ in ts.SOURCES]) + ". " + note + " "
            f"In the middle, {p}: one plan, with the rule behind every relationship. "
            f"What {p} builds in Fabric from that plan: " + _listed([n for n, _ in ts.BUILDS]) + ". "
            f"Where you build: {_listed(clients)} {'connects' if len(clients) == 1 else 'connect'} to {p} through MCP, and "
            f"Lovable uses the GraphQL API {p} makes in Fabric rather than {p} itself.")
    makers = ["Microsoft", "Anthropic"] + (["Anysphere"] if "Cursor" in clients else []) + ["Lovable"]
    return f"""<section class="wrap connects" aria-label="What {p} connects">
  <p class="visually-hidden">{said}</p>
  <div class="hub">
    <div class="hub-group hub-src c-coral"><p class="hub-h" aria-hidden="true">Your data in Fabric</p><ul aria-hidden="true">{sources}</ul></div>
    <span class="hub-link hub-link-src" aria-hidden="true"></span>
    <div class="hub-group hub-build c-sage" aria-hidden="true"><p class="hub-h">What {p} builds in Fabric</p><ul>{builds}</ul></div>
    <span class="hub-link hub-link-build" aria-hidden="true"></span>
    <div class="hub-mid"><span class="hub-node"><a class="c-hub c-hub-logo hub-go" href="/start" aria-label="{HUB_LINK.format(p=p)}">{_LOGO}<span class="c-hub-word" aria-hidden="true">{low}</span></a><i class="hub-end" aria-hidden="true"></i></span><span class="hub-sub" aria-hidden="true">one plan, the rule behind every relationship</span></div>
    <div class="hub-group hub-where c-mustard" aria-hidden="true"><p class="hub-h">Where you build</p><ul>{where}</ul></div>
  </div>

  <p class="muted tiny connects-status"><span aria-hidden="true">{html.escape(note)}</span> <a href="/docs#test-status">Status per tool</a></p>
  <p class="muted tiny connects-note">Independent product, not made by {_listed(makers).replace(" and ", " or ")}.</p>
</section>"""


def _days(value: str) -> str:
    value = value.strip()
    return value if value.isdigit() and int(value) > 0 else ""


def _fill(text: str, escape: bool = True) -> str:
    """{{VAR}} → value. HTML-escaped by default (templates); the Markdown pages escape during rendering instead."""
    v = _vars()
    return re.sub(r"\{\{(\w+)\}\}", lambda m: (html.escape(v[m.group(1)], quote=True) if escape else v[m.group(1)]) if m.group(1) in v else m.group(0), text)


def _conditional(text: str, v: dict[str, str]) -> str:
    """{{#IF NAME}}…{{/IF}} blocks: kept when the variable is non-empty, removed otherwise."""
    return re.sub(r"\{\{#IF (\w+)\}\}(.*?)\{\{/IF\}\}", lambda m: m.group(2) if v.get(m.group(1)) else "", text, flags=re.S)


# ------------------------------------------------------------------ markdown (docs, privacy) --------------------

def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", re.sub(r"<[^>]+>", "", s).lower()).strip("-")


_FIGURE = re.compile(r"^<!-- figure:([a-z0-9-]+) -->$")


DEMO_APP_URL = "https://demo.krusgraph.com"   # n147: the live Shop Desk example opens in a new tab
NEW_TAB = ' target="_blank" rel="noopener"'


# n157: the overview film. One element, used on the home page (after the hero) and at the top of /docs; the files are
# the compressed web version in static/media (the masters stay out of the repository). Nothing loads before play.
FILM_MP4 = "/static/media/krusgraph-overview-web.mp4"
FILM_MP4_4X5 = "/static/media/krusgraph-overview-web-4x5.mp4"   # n161: phones get the 4:5 version (same narration, same captions)
FILM_PHONE = "(max-width: 640px)"                                 # the same breakpoint as site.css's rule for the frame
FILM_POSTER = "/static/media/krusgraph-overview-poster.webp"
FILM_VTT = "/static/media/krusgraph-overview.en.vtt"
# n160: no visible note under the heading; the film's end card carries the disclosure, and the video says it to
# assistive technology through its aria-label.
FILM_LABEL = "Krusgraph overview film, synthetic demo data, AI-generated voice"


def film_html(heading: bool = True) -> str:
    """The overview film: a native <video> with controls, preload="none", a poster and an English captions track."""
    video = (f'<figure class="film-frame">\n'
             f'    <video controls preload="none" playsinline width="1920" height="1080" poster="{FILM_POSTER}" aria-label="{FILM_LABEL}">\n'
             f'      <source media="{FILM_PHONE}" src="{FILM_MP4_4X5}" type="video/mp4">\n'
             f'      <source src="{FILM_MP4}" type="video/mp4">\n'
             f'      <track kind="captions" srclang="en" label="English" src="{FILM_VTT}" default>\n'
             f'      <p>Your browser cannot play this film. <a href="{FILM_MP4}">Download it as MP4</a>.</p>\n'
             f'    </video>\n  </figure>')
    if heading:
        return (f'<section class="wrap film" id="film" aria-labelledby="film-h">\n  <h2 id="film-h">See how it works</h2>\n'
                f'  {video}\n</section>')
    return f'<div class="film film-docs" id="film">\n  {video}\n</div>'


def _md_to_html(md: str, figures: dict | None = None) -> str:
    """Just enough Markdown for these pages: headings (with ids), paragraphs, bold/italic, code, links, lists, pipe tables.
    n86b: the Markdown between `<!-- figure:NAME -->` and `<!-- /figure -->` is rendered as usual and handed to
    figures[NAME], which returns the HTML for that place (the Concepts pages' HTML and SVG); without it, as usual."""
    def inline(s: str) -> str:
        s = html.escape(s, quote=False)
        s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
        s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", s)
        s = re.sub(r"\[([^\]]+)\]\(((?:https?://|/|mailto:|#)[^)]+)\)", lambda m: f'<a href="{m.group(2).replace(chr(34), "&quot;")}"{NEW_TAB if m.group(2).startswith(DEMO_APP_URL) else ""}>{m.group(1)}</a>', s)
        s = re.sub(r"(?<![\"'>])(https://[^\s<]+[^\s<.,)])", r'<a href="\1">\1</a>', s)
        return s

    out, para, i = [], [], 0
    lines = md.splitlines()

    def flush():
        if para:
            out.append("<p>" + inline(" ".join(para)) + "</p>")
            para.clear()

    while i < len(lines):
        ln = lines[i]
        if not ln.strip():
            flush(); i += 1; continue
        f = _FIGURE.match(ln.strip())
        if f or ln.strip() == "<!-- /figure -->":
            flush(); i += 1
            if not f:
                continue
            inner = []
            while i < len(lines) and lines[i].strip() != "<!-- /figure -->":
                inner.append(lines[i]); i += 1
            i += 1
            rendered = _md_to_html("\n".join(inner))
            out.append(figures[f.group(1)](rendered) if figures and f.group(1) in figures else rendered); continue
        m = re.match(r"^(#{1,3}) (.*)", ln)
        if m:
            flush(); n = len(m.group(1)); text = inline(m.group(2))
            out.append(f"<h{n} id=\"{_slug(m.group(2))}\">{text}</h{n}>" if n > 1 else f"<h1>{text}</h1>"); i += 1; continue
        if ln.startswith("|"):
            flush(); rows = []
            while i < len(lines) and lines[i].startswith("|"):
                if not re.match(r"^\|[\s\-|:]+\|$", lines[i]):
                    rows.append([c.strip() for c in lines[i].strip("|").split("|")])
                i += 1
            t = "<div class=\"table-wrap\" tabindex=\"0\"><table><thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in rows[0]) + "</tr></thead><tbody>"
            t += "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in rows[1:]) + "</tbody></table></div>"
            out.append(t); continue
        if re.match(r"^(\d+\.|-) ", ln):
            flush(); tag = "ol" if ln[0].isdigit() else "ul"; items = []
            while i < len(lines) and re.match(r"^(\d+\.|-) ", lines[i]):
                items.append(re.sub(r"^(\d+\.|-) ", "", lines[i])); i += 1
                while i < len(lines) and lines[i].startswith("  ") and lines[i].strip():   # continuation line
                    items[-1] += " " + lines[i].strip(); i += 1
            out.append(f"<{tag}>" + "".join(f"<li>{inline(x)}</li>" for x in items) + f"</{tag}>"); continue
        if ln.startswith("```"):
            flush(); i += 1; code = []
            while i < len(lines) and not lines[i].startswith("```"):
                code.append(lines[i]); i += 1
            i += 1
            out.append("<pre><code>" + html.escape("\n".join(code)) + "</code></pre>"); continue
        para.append(ln.strip()); i += 1
    flush()
    return "\n".join(out)


# ------------------------------------------------------------------ files -----------------------------------------

def _read(name: str) -> str:
    p = HERE / "page_templates" / name
    if p.exists():
        return p.read_text(encoding="utf-8")
    return resources.files("fabric_backend").joinpath("page_templates", name).read_text(encoding="utf-8")


def static_file(path: str) -> Path | None:
    """Resolve a /static/<path> request to a file inside the package's static dir, or None."""
    if not path or len(path) > 200 or path.startswith("/") or path.endswith("/") or ".." in path.split("/"):
        return None
    try:
        p = (STATIC_DIR / path).resolve()
        p.relative_to(STATIC_DIR.resolve())
        return p if p.is_file() and p.suffix in STATIC_TYPES else None
    except (ValueError, OSError):              # outside the static dir, a null byte, an over-long name
        return None


_ASSET_V: str | None = None


def asset_version() -> str:
    """Short hash of the css/js so cached assets roll over with each release."""
    global _ASSET_V
    if _ASSET_V is None:
        h = hashlib.sha256()
        for p in sorted(STATIC_DIR.glob("*.css")) + sorted(STATIC_DIR.glob("*.js")):
            h.update(p.name.encode() + p.read_bytes())
        _ASSET_V = h.hexdigest()[:10]
    return _ASSET_V


# ------------------------------------------------------------------ shell -----------------------------------------

_LOGO = """<svg class="logo-mark" viewBox="0 0 40 40" aria-hidden="true" focusable="false">
<path d="M20 9 L9 29 M20 9 L31 29 M9 29 H31" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" opacity=".55"/>
<circle cx="20" cy="9" r="5.2" fill="#F2735C"/><circle cx="9" cy="29" r="5.2" fill="#9DB8A0"/><circle cx="31" cy="29" r="5.2" fill="#A99AD8"/></svg>"""

_GITHUB_ICON = """<svg viewBox="0 0 16 16" width="20" height="20" aria-hidden="true" focusable="false"><path fill="currentColor" d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8z"/></svg>"""


def site_url() -> str:
    """The public origin, e.g. https://krusgraph.com, taken from MCP_PUBLIC_URL."""
    return "https://" + _vars()["DOMAIN"]


# n55: the theme choice from the header button, restored before the stylesheet loads so a page never flashes in the
# other theme. The only inline script on the site; the CSP allows exactly this text by its hash (server.py).
THEME_JS = ('(function(){var d=document.documentElement,t;try{t=localStorage.getItem("theme")}catch(e){}'
            'if(t==="light"||t==="dark"){d.dataset.theme=t;'
            'document.querySelectorAll("meta[name=theme-color]").forEach(function(m){m.content=t==="dark"?"#1F1B19":"#FBF8F5"})}})();')
THEME_HASH = "'sha256-" + __import__("base64").b64encode(hashlib.sha256(THEME_JS.encode()).digest()).decode() + "'"
_THEME_BUTTON = ('<button type="button" class="theme-toggle" data-theme-toggle aria-pressed="false" aria-label="Dark theme">'
                 '<svg class="t-moon" viewBox="0 0 24 24" aria-hidden="true"><path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z" fill="currentColor"/></svg>'
                 '<svg class="t-sun" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4.5" fill="currentColor"/>'
                 '<path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1 7 17M17 7l2.1-2.1" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>'
                 '</button>')


MARKDOWN_TWINS = ("/docs", "/start", "/privacy", "/lovable", "/local", "/use-cases")       # pages that are also served as <path>.md


# n55: one demo, on /check. The old addresses answer with a redirect so docs, the sitemap's old entries and shared
# links still land: /demo on the guided demo, /explore on the map of the same example.
REDIRECTS = {"/demo": "/check?example=sample&guide=1", "/explore": "/check?example=sample#check-map"}

MASCOT_PAGES_BY_SCRIPT = ()                 # pages whose mascots site.js draws without a placeholder in the HTML (none since n55)


def has_mascots(body: str, page: str) -> bool:
    return "data-mascot=" in body or page in MASCOT_PAGES_BY_SCRIPT


def before_after_html() -> str:
    """The total that doubles, before and after, from the synthetic rows in seed.AMOUNT_DEMO (one order, two lines): the
    order amount summed over the joined line rows, then once per order. The numbers are computed, not typed."""
    from .seed import AMOUNT_DEMO
    (order_id, _, amount), = AMOUNT_DEMO["orders"][1]
    lines = [r[2] for r in AMOUNT_DEMO["order_lines"][1] if r[0] == order_id]
    n = lambda x: f"{x:,.0f}".replace(",", "\u00a0")
    return f"""<section class="wrap before-after" id="example" aria-labelledby="example-h">
  <div class="card">
    <div class="ba-head"><div><p class="eyebrow">Before and after, on sample data</p>
    <h2 id="example-h">Why is the order total twice what finance says?</h2>
    <p>One order of {n(amount)} with {len(lines)} lines ({" and ".join(n(x) for x in lines)}). Join the order to its lines and sum the order amount, and every line repeats it.</p></div>
    <span class="ba-figure" aria-hidden="true"><span data-mascot="thinker" data-pose="look" data-label=""></span></span></div>
    <dl class="ba">
      <div class="ba-before"><dt>Before: summed over the joined lines</dt><dd>{n(amount * len(lines))}</dd></div>
      <div class="ba-after"><dt>After: once per order, as the plan says</dt><dd>{n(amount)}</dd></div>
    </dl>
    <p class="muted tiny"><code>validate_plan</code> points out the order amount as a header amount and counts the lines per order: order amount and line amount are different levels. <a href="/use-cases#problem-total-doubles">The total that doubles</a>.</p>
    <p class="ba-more"><a href="{BLOG_TOTALS}">Read the full walkthrough →</a></p>
  </div>
</section>"""


def _tips_json() -> str:
    """n86b: the two sentences the question mark next to "ontology" and "data products" opens (concepts.TIPS), read by
    site.js and never run as a script."""
    from . import concepts
    return ('\n<script type="application/json" id="kg-tips">'
            + json.dumps(concepts.tips(_vars()["PRODUCT"]), ensure_ascii=False).replace("<", "\\u003c") + "</script>")


def _shell(title: str, description: str, body: str, page: str, nav: str, noindex: bool = False, head: str = "",
           path: str = "", chat: bool = False, og_type: str = "website") -> str:
    v = _vars()
    links = [("product", "/", "Product"), ("check", "/check", CHECK_LABEL), ("usecases", "/use-cases", "Use cases"), ("docs", "/docs", "Docs"), ("blog", "/blog", "Blog"), ("support", "/support", "Get help"), ("partners", "/partners", "Try a pilot"), ("pricing", "/pricing", "Pricing")]
    nav_html = "".join(f'<a href="{href}"{" aria-current=page" if key == nav else ""}>{label}</a>' for key, href, label in links)
    robots = '<meta name="robots" content="noindex,nofollow">' if noindex else ""
    t, d = _fill(title), _fill(description)                       # _fill escapes
    canonical = html.escape(site_url() + (path or "/"), quote=True)
    og_image = html.escape(f"https://{v['DOMAIN']}/static/og.png", quote=True)
    md_alternate = (f'<link rel="alternate" type="text/markdown" href="{path}.md" title="Markdown version">'
                    if path in MARKDOWN_TWINS else "")                       # agents and crawlers get the text form in one hop
    # the mascot toggle only on a page that has mascots: a placeholder in the HTML, or the ones /demo's graph draws (n36:
    # the toggle said "Mascots: on" on pages with none, such as /docs); n93: the chat's button shows Onto, so every page
    # with it has the toggle too
    toggle = ('<button type="button" class="btn ghost small" data-mascot-toggle aria-pressed="true">Mascots: on</button>\n'
              '      <span class="muted tiny" id="mascot-toggle-note">Your choice applies across the site and is saved in this browser.</span>'
              if has_mascots(body, page) or chat else "")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{t}</title>
<meta name="description" content="{d}">
{robots}
{"" if noindex else f'<link rel="canonical" href="{canonical}">'}
<meta property="og:type" content="{og_type}">
<meta property="og:site_name" content="{html.escape(v['PRODUCT'])}">
<meta property="og:url" content="{canonical}">
<meta property="og:title" content="{t}">
<meta property="og:description" content="{d}">
<meta property="og:image" content="{og_image}">
<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta property="og:image:alt" content="{html.escape(v['PRODUCT'])}: For Microsoft Fabric.">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{t}">
<meta name="twitter:description" content="{d}">
<meta name="twitter:image" content="{og_image}">
<link rel="alternate" type="text/plain" href="/llms.txt" title="llms.txt">
{md_alternate}
{"" if noindex else '<meta name="robots" content="index,follow,max-snippet:-1,max-image-preview:large">'}
<meta name="theme-color" content="#FBF8F5" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#1F1B19" media="(prefers-color-scheme: dark)">
<link rel="icon" href="/static/favicon.svg" type="image/svg+xml">
<link rel="icon" href="/static/favicon.png" type="image/png" sizes="64x64">
<link rel="icon" href="/static/icon-512.png" type="image/png" sizes="512x512">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="preload" href="/static/fonts/fredoka-var.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="/static/fonts/nunito-var.woff2" as="font" type="font/woff2" crossorigin>
<script>{THEME_JS}</script>
<link rel="stylesheet" href="/static/site.css?v={v['ASSET_V']}">
{head}
</head>
<body class="page-{page}">
<a class="skip" href="#main">Skip to content</a>
<div class="deco deco-dots deco-tl" aria-hidden="true"></div>
<div class="deco deco-arc deco-br" aria-hidden="true"></div>
<header class="site-header">
  <div class="wrap header-row">
    <a class="brand" href="/" aria-label="{html.escape(v['PRODUCT'])} home">
      {_LOGO}
      <span class="brand-text"><span class="wordmark">{html.escape(v['PRODUCT_LOWER'])}</span><span class="tagline">For Microsoft Fabric.</span></span>
    </a>
    <nav id="site-nav" class="site-nav" aria-label="Main">
      {nav_html}
      <a class="icon-link" href="{GITHUB}" aria-label="Source on GitHub" rel="noopener">{_GITHUB_ICON}</a>
    </nav>
    <div class="header-tools">{_THEME_BUTTON}<button class="nav-toggle" type="button" aria-expanded="false" aria-controls="site-nav" aria-label="Menu"><span></span><span></span><span></span></button></div>
  </div>
</header>
<main id="main" tabindex="-1">
{body}
</main>
<footer class="site-footer">
  <div class="wrap footer-grid">
    <div>
      <div class="brand small">{_LOGO}<span class="wordmark">{html.escape(v['PRODUCT_LOWER'])}</span></div>
      <p class="muted">{html.escape(v['PRODUCT'])} by Kruse Consulting AB{html.escape(v['ORGNR_DOT'])} · Open source under the MIT licence.</p>
      <p class="muted tiny footer-facts">{html.escape(v['BEHIND'])}.<br>{html.escape(v['BUILT'])}. <a href="/it">For your IT department</a>.</p>
      <p class="muted tiny">Microsoft Fabric and Fabric IQ are trademarks of Microsoft Corporation. {html.escape(v['PRODUCT'])} is an independent product, not made by Microsoft.</p>
    </div>
    <nav class="footer-links" aria-label="Footer">
      <a href="/check?example=sample&amp;guide=1">Try the guided demo</a><a href="/check">{CHECK_LABEL}</a><a href="/use-cases">Use cases</a><a href="/start">{CONNECT_LABEL}</a><a href="/docs">Docs</a><a href="/blog">Blog</a><a href="/lovable">Use with Lovable</a><a href="/privacy">Privacy</a><a href="/support">Get help</a><a href="/partners">Try a pilot</a><a href="/pricing">Pricing</a><a href="/terms">Preview terms</a>
      <a href="{GITHUB}" rel="noopener">GitHub</a><a href="mailto:{html.escape(v['CONTACT'])}">{html.escape(v['CONTACT'])}</a>
    </nav>
    <div class="footer-controls">
      {toggle}
    </div>
  </div>
</footer>{chr(10) + chat_launch_html() if chat else ""}{_tips_json() if chat or page == "check" else ""}
<script src="/static/mascots.js?v={v['ASSET_V']}" defer></script>
<script src="/static/site.js?v={v['ASSET_V']}" defer></script>
</body>
</html>"""


BUILD_DOCS = {"join_path": "How {{PRODUCT}} uses graph theory", "semantic_model_draft": "One plan, five Fabric pieces",
              "rayfin_connector": "Tools", "app_starter": "Use with Lovable"}


def build_doc_anchor(tool: str) -> str:
    return "/docs#" + _slug(_fill(BUILD_DOCS[tool], escape=False))


def _bar_chart(chart: dict) -> str:
    """Horizontal bars as inline SVG, scaled to the largest value; the numbers are the query's."""
    e = html.escape
    bars = chart["bars"]
    top = max((b["value"] or 0) for b in bars) or 1
    row, label_w, width = 30, 110, 360
    h = row * len(bars) + 8
    out = []
    for i, b in enumerate(bars):
        y, w = 4 + i * row, max(2, round((width - label_w - 60) * (b["value"] or 0) / top))
        out.append(f'<text x="{label_w - 8}" y="{y + 17}" text-anchor="end" class="bar-label">{e(str(b["label"]))}</text>'
                   f'<rect x="{label_w}" y="{y + 4}" width="{w}" height="18" rx="3" class="bar"/>'
                   f'<text x="{label_w + w + 6}" y="{y + 17}" class="bar-value">{b["value"]:g}</text>')
    return (f'<svg class="bar-chart" viewBox="0 0 {width} {h}" role="img" aria-label="{e(chart["question"])}: '
            + e("; ".join(f'{b["label"]} {b["value"]:g}' for b in bars)) + f'">{"".join(out)}</svg>')


def _card(tool: str, title: str, body: str) -> str:
    from .tool_status import label
    e = html.escape
    return (f'<article class="build-card" data-tool="{e(tool)}"><header><h3>{e(title)}</h3>'
            f'<p class="build-meta"><code>{e(tool)}</code> · <span class="build-status">{e(label(tool))}</span> · '
            f'<a href="{build_doc_anchor(tool)}">docs</a></p></header>{body}</article>')


# The path from tables to Fabric items, as the hosted tools walk it (the server's instructions): each step with the tools
# that do it and what you do yourself. Counted, not typed: the calls come from these tuples and tool_status.BUILDS.
def build_path() -> list[dict]:
    from .tool_status import BUILDS
    creating = tuple(t for _, t in BUILDS)
    return [
        {"title": "Connect", "tools": ("list_workspaces", "list_sources"),
         "you": "You sign in with Microsoft and pick a workspace and a lakehouse."},
        {"title": "The plan is drawn up", "tools": ("plan_backend",),
         "you": "You read the keys and relationships; nothing is created."},
        {"title": "The plan is checked against the data", "tools": ("validate_plan",),
         "you": "You approve the plan, or correct a key first."},
        {"title": "The parts are created", "tools": creating,
         "you": "You ask for each part. Each shows what it would create first, and creates when you say so."},
    ]


def build_path_html() -> str:
    """The row of steps above the cards, with the counts from the path, the demo plan and the 20-minute demo's budget."""
    from .demo import demo_plan
    from .demo_app import STEPS
    from .tool_status import short
    e = html.escape
    path = build_path()
    before = sum(len(s["tools"]) for s in path[:-1])
    parts = len(path[-1]["tools"])
    d = demo_plan()
    keyed = sum(1 for t in d["tables"] if t["key"])
    items = "".join(
        f'<li><span class="path-n" aria-hidden="true">{i}</span><h3>{e(s["title"])}</h3>'
        f'<p class="path-tools">{", ".join(f"<code>{e(t)}</code>" for t in s["tools"])}</p><p>{e(s["you"])}</p></li>'
        for i, s in enumerate(path, 1))
    minutes = sum(s["minutes"] for s in STEPS)
    budget = ", ".join(f'{s["title"].lower()} {s["minutes"]} min' for s in STEPS)
    return (f'<ol class="path-steps" aria-label="From tables to Fabric items in {len(path)} steps">{items}</ol>'
            f'<p class="path-facts">{len(path)} steps. {before} tool calls take you from your tables to a checked plan; '
            f'then one call per part, {parts} parts in all. On the shop schema the plan has {len(d["tables"])} tables, '
            f'{keyed} with keys and {len(d["relationships"])} relationships, without anyone writing code or configuration.</p>'
            f'<p class="path-facts">From your tables to a checked plan in about {minutes} minutes; each part after that is one call '
            f'when you ask for it. The {minutes} minutes are the budget of the <a href="/local#the-20-minute-demo">20-minute demo</a> '
            f'({e(budget)}), which ends with the plan checked against the rows and the exports in your hands.</p>'
            f'<p class="muted tiny">Status of creating: {"; ".join(f"<code>{e(t)}</code> {e(short(t))}" for t in path[-1]["tools"])}. '
            f'The runs behind each: <a href="/docs#test-status">test status per tool</a>.</p>')


def build_html() -> str:
    """The four cards "What you can build automatically from a plan" on /use-cases, from demo.build_cards()."""
    from .demo import build_cards
    e = html.escape
    c = build_cards()
    cards = []
    ch = c["chart"]
    if ch:
        steps = "; ".join(f'{s["from"]} → {s["to"]} on {", ".join(s["on"])} ({s["rule"]}, {s["direction"]})' for s in ch["steps"])
        cards.append(_card("join_path", "A chart along the safest join path",
                           f'<figure class="build-chart">{_bar_chart(ch)}<figcaption>{e(ch["question"])}</figcaption></figure>'
                           f'<p class="muted tiny">Path: {e(steps)}; {e(ch["why"])}. Measure <code>{e(ch["expression"])}</code> from '
                           f'<code>semantic_model_draft</code>, summed over the synthetic seed rows.</p>'
                           f'<details class="tech"><summary>SQL</summary><pre class="build-pre">{e(ch["sql"])}</pre></details>'))
    m = c["model"]
    rels = "".join(f'<li><code>{e(r["from"])}</code> → <code>{e(r["to"])}</code>: many-to-one, {e(r["filter"])}'
                   + ("" if r["active"] else " (inactive)") + "</li>" for r in m["relationships"])
    meas = "".join(f'<li><code>{e(x["table"])}</code> · {e(x["name"])}: <code>{e(x["expression"])}</code></li>' for x in m["measures"])
    ad = m["amount_demo"]
    amounts = (f'<p><strong>Header-level amounts:</strong> {e(m["amount_check"])}'
               + (f' ({e(", ".join(f"{x['table']}.{x['column']}" for x in m["header_amounts"]))})' if m["header_amounts"] else "")
               + f'. {e(m["amount_rule"])} In the synthetic example <code>{e(ad["line"])}</code> → <code>{e(ad["header"])}</code>, '
               f'<code>SUM({e(ad["header"])}.{e(ad["column"])})</code> over the joined lines gives {ad["before"]:g}; summed on '
               f'<code>{e(ad["header"])}</code> it gives {ad["after"]:g}, and the lines add up to {ad["lines_total"]:g}.</p>')
    cards.append(_card("semantic_model_draft", "A Power BI semantic model draft",
                       f'<h4>Relationships</h4><ul class="build-list">{rels}</ul><h4>Suggested measures</h4><ul class="build-list">{meas}</ul>{amounts}'
                       f'<p class="muted tiny">{len(m["files"])} TMDL files; keyless: {e(", ".join(m["keyless"]) or "none")}.</p>'))
    r = c["rayfin"]
    ents = "".join(f'<li><code>{e(x["class"])}</code> ← <code>{e(x["table"])}</code>'
                   + (f', key <code>{e(", ".join(x["key"]))}</code>' if x["key"] else ", no key")
                   + ("; " + ", ".join(f'@{e(l["kind"])} <code>{e(l["to"])}</code>' for l in x["links"]) if x["links"] else "") + "</li>"
                   for x in r["entities"])
    cards.append(_card("rayfin_connector", "Rayfin connector entities",
                       f'<ul class="build-list">{ents}</ul><p class="muted tiny">{len(r["files"])} files, including <code>schema.ts</code>.</p>'))
    a = c["app"]
    cards.append(_card("app_starter", "An app starter prompt and a GraphQL query",
                       f'<h4>{e(a["query"]["title"])}</h4><pre class="build-pre">{e(a["query"]["query"])}</pre>'
                       f'<details class="tech"><summary>The prompt</summary><pre class="build-pre">{e(a["prompt"])}</pre></details>'
                       f'<p class="muted tiny">One of {a["queries"]} queries <code>app_starter</code> writes. The endpoint has placeholders: the demo has no workspace.</p>'))
    return "".join(cards)


def partners_vars() -> dict[str, str]:
    """n75: the illustrative delivery on /partners repeats the synthetic order of the demo (seed.AMOUNT_DEMO), read from
    the engine's own run of it: the order's amount, what a join over its lines counts it as, and how many lines it has."""
    from .amounts import demo
    from .demo_app import _amount
    d = demo()
    return {"DEMO_ORDER_AMOUNT": _amount(d["after"]), "DEMO_ORDER_DOUBLED": _amount(d["before"]),
            "DEMO_ORDER_LINES": str(d["finding"]["rows_per_header"]["max_lines"])}


def before_after_mini_html() -> str:
    """n149: the same before and after as before_after_html, as a small card under the hero's buttons, with a link down
    to the section that explains it. The numbers come from seed.AMOUNT_DEMO, as there."""
    from .seed import AMOUNT_DEMO
    (order_id, _, amount), = AMOUNT_DEMO["orders"][1]
    lines = [r[2] for r in AMOUNT_DEMO["order_lines"][1] if r[0] == order_id]
    n = lambda x: f"{x:,.0f}".replace(",", "\u00a0")
    return (f'    <p class="ba-mini"><span class="ba-mini-what">One order, {len(lines)} lines, sample data:</span> '
            f'<span class="ba-mini-before">{n(amount * len(lines))}</span> <span aria-hidden="true">→</span>'
            f'<span class="visually-hidden">becomes</span> <span class="ba-mini-after">{n(amount)}</span> '
            f'<a href="#example">why</a></p>')


# n92: the chat demo (on every ordinary page since n93). The three results it can show, with the tool that drafts them
# and the tool that creates them in Fabric; what the chat says about creating comes from tool_status, not from the chat's
# own text.
CHAT_RESULTS = (("model", "semantic_model_draft", "create_semantic_model"), ("ontology", "ontology_draft", "create_ontology"),
                ("domains", "domain_draft", ""))
# n93: the pages that never get the chat's button: /demo (a redirect to /check). n154: the button is on every other page,
# the home page and /check included (Gustav's decision of 8 November 2026, undoing n149's PILL_OFF). /check's policy says
# connect-src 'none', so the page carries the demo plan inline (chat_plan_html) and the chat fetches nothing there.
CHAT_OFF = ("/demo",)

# n149: the blog article on the total that doubles, linked from the start page's before and after and /check's example
BLOG_TOTALS = "/blog/fabric-totals-double-after-join"

# n149: the two ways in, with the same labels wherever they are offered (the hero, the middle of the start page, after a
# /check result, /pricing, the navigation and the footer): the primary to /check, the secondary to /start.
CHECK_LABEL = "Check my tables"
CONNECT_LABEL = "Connect to my Fabric"


def chat_status(tool: str) -> str:
    """A tool's status as the chat says it (n93): a short plain sentence without the tool's name, built from tool_status
    and saying no more than it: whether it created its item in a live Fabric workspace (build_word), whether that item
    was reviewed there (REVIEWED), how a tool that has not run live is tested, and whether creating needs a permission the
    hosted app does not ask for today (available == OPERATOR)."""
    from . import tool_status as ts
    s = ts.STATUS[tool]
    if s.kind == ts.CREATES:
        made = ts.build_word(tool)
        if made == "creates":
            out = "Created in a live Fabric workspace" + (" and reviewed there." if tool in ts.REVIEWED else ".")
        elif made == "updates":
            out = "Updated in place in a live Fabric workspace; a new one is not yet created there."
        else:
            out = "Not yet created in a live Fabric workspace."
    elif s.live:
        out = "Run against a live Fabric workspace" + (" as a draft." if s.kind == ts.DRAFT else ".")
    else:
        out = ("Tested with unit tests" if s.tested.startswith("unit tests") else "Tested") + ", not yet against a live Fabric workspace."
    if s.available == ts.OPERATOR:
        out += " Creating it needs a permission the hosted service does not ask for today."
    return out


def chat_does(create):
    """n94: data-does-* for a result. "creates" only when the creating tool creates live (build_word) and the hosted
    service asks for its permission (available is not OPERATOR); "drafts-gated" when such a tool exists but its
    permission is not asked for today; "drafts" when nothing creates it (data products)."""
    from . import tool_status as ts
    if not create:
        return "drafts"
    if ts.build_word(create) == "creates" and ts.STATUS[create].available != ts.OPERATOR:
        return "creates"
    return "drafts-gated"


def chat_launch_html() -> str:
    """The chat demo's button (n92, Gustav's decision of 4 November 2026; on every ordinary page since n93). Hidden
    without JavaScript; site.js shows it, and the first click (or a chat to restore, n93) loads chat-demo.css and
    chat-demo.js, which fetch /demo/plan.json and nothing else. Each result's status sentence and whether the agent
    creates it in Fabric (tool_status.build_word) ride along as data attributes."""
    from . import tool_status as ts
    v = _vars()
    e = lambda x: html.escape(x, quote=True)
    attrs = [f'data-product="{e(v["PRODUCT"])}"', f'data-css="/static/chat-demo.css?v={v["ASSET_V"]}"',
             f'data-js="/static/chat-demo.js?v={v["ASSET_V"]}"', 'data-fallback="/check?example=sample"',
             f'data-label-check="{e(CHECK_LABEL)}"', f'data-label-connect="{e(CONNECT_LABEL)}"']   # n158: the chat's two exits
    for key, draft, create in CHAT_RESULTS:
        tool = create or draft
        attrs += [f'data-status-{key}="{e(chat_status(tool))}"',
                  f'data-does-{key}="{chat_does(create)}"']
    return (f'<button class="kgc-launch" id="kgcLaunch" type="button" aria-expanded="false" hidden '
            f'{" ".join(attrs)}><span class="kgc-fig" aria-hidden="true"></span>Try a demo</button>')


_CHAT_BUTTON = re.compile(r'\n?<button class="kgc-launch" id="kgcLaunch"[^>]*>.*?</button>', re.S)


def strip_chat(page: str) -> str:
    """The page without the chat's button: for a page whose content security policy says connect-src 'none', where the
    chat could not fetch its plan (server.py), unless the page carries the plan itself (chat_plan_html)."""
    return page if 'id="kgcPlan"' in page else _CHAT_BUTTON.sub("", page)


def chat_plan_html() -> str:
    """n154: the demo plan as an inert JSON block, for /check, whose policy lets the page fetch nothing (connect-src
    'none'); chat-demo.js reads it instead of GET /demo/plan.json. The same bytes as /demo/plan.json, with "<" escaped so
    the block cannot end early."""
    from .demo import demo_plan_json
    return '<script type="application/json" id="kgcPlan">' + demo_plan_json().replace("<", "\\u003c") + "</script>"


def _home_vars() -> dict[str, str]:
    """The start page's server-rendered parts: the hub, the before/after example and the Connect menu."""
    return {"HOME_HUB": hub_html(), "HOME_BEFORE_AFTER": before_after_html(), "HOME_BEFORE_AFTER_MINI": before_after_mini_html(),
            "HOME_FILM": film_html()}                                             # n157

PYODIDE_DIR = STATIC_DIR / "pyodide"
CHECK_DOWNLOAD = ("pyodide.mjs", "pyodide.asm.js", "pyodide.asm.wasm", "python_stdlib.zip", "pyodide-lock.json",
                  "sqlite3-1.0.0-cp312-cp312-pyodide_2024_0_wasm32.whl")      # what /check's worker loads, besides the engine


def check_download_bytes() -> int:
    """What the first visit to /check downloads, uncompressed: Pyodide's files, the engine zip and the page's two scripts."""
    from .browser_check import engine_zip
    return (sum((PYODIDE_DIR / n).stat().st_size for n in CHECK_DOWNLOAD) + len(engine_zip())
            + sum((STATIC_DIR / n).stat().st_size for n in ("check.js", "check-worker.js")))


# measured with tests' Chromium and DevTools network throttling (40 ms latency) against a local server; see the n38 report
CHECK_TIMES = ("about 13.5 s the first time on a 5 Mbit/s line, 5.5 s on 20 Mbit/s, and 2.5 s once the engine is in the "
               "browser's cache")


def check_vars() -> dict[str, str]:
    from .browser_check import engine_zip
    v = hashlib.sha256(engine_zip()).hexdigest()[:10]
    # n49: the start page may fetch these ahead of a visit to /check, at exactly the URLs the worker asks for, so the
    # browser's cache answers the worker (site.js, checkPrefetch)
    urls = [f"/static/pyodide/{n}" for n in CHECK_DOWNLOAD] + [f"/check/engine.zip?v={v}"]
    return {"CHECK_MB": str(round(check_download_bytes() / 1e6)), "CHECK_TIMES": CHECK_TIMES, "CHECK_ENGINE_V": v, "CHECK_PREFETCH": " ".join(urls)}


def render(path: str) -> str:
    template, title, description, nav = PAGES[path]
    v = _vars()
    body = _read(template)
    if "{{HOME_" in body:
        hv = _home_vars()
        body = re.sub(r"\{\{(HOME_\w+)\}\}", lambda m: hv.get(m.group(1), ""), body)
    if "{{DEMO_" in body:                                                  # the build cards on /use-cases/build (n55; their own page since n59)
        dv = {"DEMO_BUILD": build_html(), "DEMO_PATH": build_path_html()} if "{{DEMO_BUILD" in body or "{{DEMO_PATH" in body else {}
        if "{{DEMO_ORDER_" in body:                                        # n75: the synthetic order on /partners
            dv.update(partners_vars())
        body = re.sub(r"\{\{(DEMO_\w+)\}\}", lambda m: dv.get(m.group(1), ""), body)
    if "{{START_CONNECT}}" in body:                                       # n149: the client chooser, on /start (it was the home page's)
        body = body.replace("{{START_CONNECT}}", connect_menu_html("start"))
    if "{{CHECK_" in body:
        cv = check_vars()
        body = re.sub(r"\{\{(CHECK_\w+)\}\}", lambda m: cv.get(m.group(1), ""), body)
    if "{{UC_" in body:
        from .use_cases import page_vars
        uv = page_vars()
        body = re.sub(r"\{\{(UC_\w+)\}\}", lambda m: uv.get(m.group(1), ""), body)
    body = _fill(_conditional(_access(body), v))
    if path == "/check":                                                   # n154: the chat's plan, inline (chat_plan_html)
        body += "\n" + chat_plan_html()
    head = json_ld() if path == "/" else ""
    out = _shell(title, description, body, page=template.split(".")[0], nav=nav, noindex=(path == "/mascots"), head=head, path=path,
                 chat=path not in CHAT_OFF)
    return out


PRIVACY_DESC = "How {{PRODUCT}} handles your Microsoft sign-in, access tokens, metadata, sample rows, query results, usage records and technical logs."
DOCS_DESC = "Connect {{PRODUCT}} to Claude, explore and check a plan against your data, keep the review, build from it, and the status of each tool: what it changes and how far it has been tested."
LOVABLE_DESC = "Plan and create a GraphQL API in Microsoft Fabric from Lovable's chat with {{PRODUCT}} as a custom MCP connector, finish the three portal steps, then connect Lovable's Microsoft Fabric connector to it: the path that ran on 30 October 2026."


def privacy_md() -> str:
    md = _conditional(_access(_read("PRIVACY.md"), markdown=True), _vars())
    return _fill(re.sub(r"^\*Template\..*?\*\n", "", md, flags=re.S | re.M), escape=False)   # drop the template note


def _tool_statuses(md: str) -> str:
    """The Status and What it changes cells of the tool table, and the live-run list, from tool_status."""
    from . import tool_status as ts
    seen = set()

    def row(m: re.Match) -> str:
        name = m.group(1)
        seen.add(name)
        return f"| `{name}` | {ts.label(name)} | {ts.STATUS[name].changes} | "
    md = re.sub(r"^\| `(\w+)` \| \{\{status\}\} \| \{\{changes\}\} \| ", row, md, flags=re.M)
    if seen != set(ts.STATUS):                                                # every tool once, no tool without a status
        raise ValueError(f"tool table and tool_status differ: {sorted(seen ^ set(ts.STATUS))}")
    return (md.replace("{{LIVE_RUN_BUILD}}", ts.LIVE_RUN_BUILD).replace("{{LIVE_RUN_LIST}}", ts.live_run_list())
              .replace("{{NOT_RUN_LIST}}", ts.not_run_list()).replace("{{FIRST_RUN_DATE}}", ts.FIRST_RUN_DATE)
              .replace("{{FIRST_RUN_STEPS}}", str(ts.FIRST_RUN_STEPS)).replace("{{OVERVIEW_TABLE}}", ts.overview_md(_registration_on())))


def docs_md() -> str:
    from . import concepts
    md = _conditional(_access(_read("DOCS.md"), markdown=True).replace("{{RULES_TABLE}}", _rules_table()), _vars())
    return _fill(concepts.fill(_tool_statuses(md)), escape=False)          # n86b: the Concepts pages' examples and statuses


def lovable_md() -> str:
    return _fill(_conditional(_read("LOVABLE.md"), _vars()), escape=False)      # n73: step 1 depends on client registration


LOCAL_DESC = "Run {{PRODUCT}} on your own machine against SQL Server or a Fabric SQL endpoint over ODBC: the same rules, no account with us, and exactly what leaves the machine."


def local_md() -> str:
    return _fill(_read("LOCAL.md"), escape=False)


def local_html() -> str:
    body = f'<article class="wrap prose docs">{_md_to_html(local_md())}</article>'
    return _shell("Run {{PRODUCT}} locally", LOCAL_DESC, body, page="local", nav="docs", path="/local", chat=True)


def use_cases_md() -> str:
    from .use_cases import markdown
    v = _vars()
    return markdown(v["PRODUCT"], site_url(), v["CONTACT"])


# n68: the admin consent link on /start names this page as its redirect_uri, so Microsoft brings the admin back here
# instead of to the OAuth callback (which answered "This sign-in cannot continue"). The page reads Microsoft's own
# query string: admin_consent=True&tenant=<id> on success, error=<code>&error_description=<text> otherwise. Nothing is
# stored; the values are shown escaped and cut short. The address must be registered as a Web redirect URI on the
# Entra app before it works (otherwise Entra answers AADSTS50011 and never reaches it).
CONSENT_PATH = "/consent/done"
_GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def consent_done_html(params) -> str:
    """The page after Microsoft's admin consent: granted, refused (with the code and the next step), or opened directly."""
    v = _vars()
    e = html.escape
    p = e(v["PRODUCT"])
    get = lambda k: str(params.get(k, "") or "")
    granted = get("admin_consent").strip().lower() == "true"
    code = re.sub(r"[^A-Za-z0-9_.-]", "", get("error"))[:60]
    desc = " ".join(get("error_description").split())[:400]
    tenant = get("tenant").strip()
    tenant_line = f'<p class="muted tiny">Tenant: <code>{e(tenant)}</code>.</p>' if _GUID.match(tenant) else ""
    if granted:
        title, kicker, h1 = "Admin consent granted — {{PRODUCT}}", "Admin consent", f"Admin consent granted for your organisation."
        q = e(FIRST_QUESTION)
        body = f"""<p class="lede">Nothing more to do: your colleagues can now connect.</p>
<h2 class="h3" id="next">Next step: connect, then ask a first question</h2>
<p>Add {p} to Claude (step 3 of the set-up guide) and sign in with your Microsoft work account. Then paste this question in a new chat; it only reads:</p>
<blockquote class="consent-question"><p>{q}</p></blockquote>
<div class="ctas"><a class="btn primary" href="/start#step-3">{CONNECT_LABEL}</a><button type="button" class="btn secondary" data-copy-text="{q}">Copy the question</button></div>
<p class="muted">Each person signs in with their own account, and every call runs with that person’s own Fabric permissions; {p} reaches nothing they cannot already reach. The steps are on <a href="/start#step-3">the set-up page</a>; the permissions and how to revoke them (Enterprise applications in Entra) are on <a href="/it">the page for your IT department</a>.</p>
{tenant_line}"""
        pose = "celebrate"
    elif code or desc:
        title, kicker, h1 = "Admin consent not granted — {{PRODUCT}}", "Admin consent", "Admin consent was not granted."
        why = {"access_denied": "The person who opened the link declined, or is not an administrator who may consent to applications for the organisation.",
               "invalid_client": f"Microsoft Entra did not recognise the {p} app in this tenant.",
               "invalid_request": "Microsoft Entra could not use the request as sent.",
               "interaction_required": "Microsoft Entra needs the administrator to sign in again, or with another account."}.get(code, "")
        body = (f'<p class="lede">Microsoft Entra answered <code>{e(code) or "an error"}</code>.</p>'
                + (f"<p>{e(desc)}</p>" if desc else "") + (f"<p>{why}</p>" if why else "") + f"""
<h2 class="h3">Next step</h2>
<ol>
<li>Send <a href="/it">the page for your IT department</a> to an administrator of your Microsoft Entra tenant: it lists each permission {p} asks for and why, what is stored, and how to revoke the approval.</li>
<li>The administrator opens <a href="/start#step-1">Grant admin consent in Entra</a> on the set-up page and signs in with the administrator account.</li>
<li>If it fails again, <a href="/support">get help</a> with the code above; nothing about this attempt is kept on our side.</li>
</ol>
{tenant_line}
<div class="ctas"><a class="btn primary" href="/it">For your IT department</a><a class="btn ghost" href="/start#step-1">The set-up guide</a></div>""")
        pose = "aside"
    else:
        title, kicker, h1 = "Admin consent — {{PRODUCT}}", "Admin consent", "Nothing to show yet."
        body = f"""<p class="lede">This is where Microsoft Entra sends an administrator after the admin consent for {p}. Opened directly, there is nothing to report.</p>
<p>The consent link, what it approves and the rest of the set-up are on <a href="/start#step-1">the set-up page</a>.</p>
<div class="ctas"><a class="btn primary" href="/start">{CONNECT_LABEL}</a><a class="btn ghost" href="/it">For your IT department</a></div>"""
        pose = "look"
    section = f"""<section class="wrap hero"><div class="hero-grid"><div>
<span class="kicker">{kicker}</span><h1>{h1}</h1>
{body}
</div><div class="hero-figure" aria-hidden="true"><span data-mascot="onto" data-pose="{pose}" data-label=""></span></div></div></section>"""
    return _shell(title, "What happened after the admin consent for {{PRODUCT}} in Microsoft Entra, and the next step.", section,
                  page="consent", nav="", noindex=True, chat=True)


def not_found_html(path: str) -> str:
    body = f"""<section class="wrap hero"><div class="hero-grid"><div>
<span class="kicker">404</span><h1>Nothing connects here.</h1>
<p class="lede">There is no page at <code>{html.escape(path[:120])}</code>.</p>
<div class="ctas"><a class="btn primary" href="/">Start page</a><a class="btn secondary" href="/check?example=sample#check-map">See the example’s map</a><a class="btn ghost" href="/docs">Docs</a></div>
</div><div class="hero-figure" aria-hidden="true"><span data-mascot="onto" data-pose="aside" data-label=""></span></div></div></section>"""
    return _shell("Page not found — {{PRODUCT}}", "There is no page at this address.", body, page="notfound", nav="", noindex=True, chat=True)


def privacy_html() -> str:
    body = f'<article class="wrap prose">{_md_to_html(privacy_md())}</article>'
    return _shell("Privacy policy — {{PRODUCT}}", PRIVACY_DESC, body, page="privacy", nav="", path="/privacy", chat=True)


def _rules_table() -> str:
    """The K/R rules as a Markdown table, straight from infer.RULES so the docs never drift from the engine."""
    from .infer import RULES
    rows = ["| Rule | Applies to | Means |", "| --- | --- | --- |"]
    for code, text in RULES.items():
        if code == "confirmed":
            continue
        rows.append(f"| {code} | {'keys' if code.startswith('K') else 'relationships'} | {text.replace('|', '/')} |")
    return "\n".join(rows)


def _with_toc(rendered: str) -> str:
    """A small 'on this page' list built from the h2 ids, each with its h3 sections under it, placed after the first
    paragraph."""
    heads = re.findall(r'<h([23]) id="([^"]+)">(.*?)</h\1>', rendered)
    if sum(1 for n, _i, _t in heads if n == "2") < 3:
        return rendered
    groups: list[tuple[str, str, list[str]]] = []
    for n, i, t in heads:
        link = f'<a href="#{i}">{re.sub(r"<[^>]+>", "", t)}</a>'
        if n == "2" or not groups:
            groups.append((i, link, []))
        else:
            groups[-1][2].append(f"<li>{link}</li>")
    toc = ('<nav class="toc" aria-label="On this page"><ul>'
           + "".join(f'<li>{link}' + (f'<ul>{"".join(sub)}</ul>' if sub else "") + "</li>" for _i, link, sub in groups)
           + "</ul></nav>")
    return rendered.replace("</p>", "</p>" + toc, 1)


# n86a: /docs in sub-pages with a menu. DOCS.md stays the only source: the pages are cut out of docs_md() when they are
# rendered, so every line of it is on exactly one page and /docs.md is the same text as before. The intro and "Why" are
# /docs itself (the overview); each other "##" section is a group page (its heading and the lines before its first "###")
# and each "###" a page under it. The menu labels of the groups are below; the rest of the menu is the headings.
DOCS_GROUPS = ["Overview", "Get started", "Concepts", "Explore and check", "Build from a plan", "Reference", "Hosting and permissions"]
DOCS_MORE = [("/start", "The set-up guide"), ("/it", "For your IT department"), ("/lovable", "Use with Lovable")]


def _md_plain(s: str) -> str:
    return re.sub(r"[`*]", "", s).strip()


def docs_pages() -> list[dict]:
    """The docs as pages in reading order: path, title, group, group path, depth (0 overview, 1 group, 2 page), md."""
    md = docs_md()
    chunks: list[list[str]] = [[]]
    kinds: list[str] = ["intro"]
    fence = False
    for ln in md.splitlines(keepends=True):
        if ln.startswith("```"):
            fence = not fence
        if not fence and (ln.startswith("## ") or ln.startswith("### ")):
            chunks.append([]); kinds.append(ln[:3].strip())
        chunks[-1].append(ln)
    pages: list[dict] = []
    gi, why = 0, False
    for kind, lines in zip(kinds, chunks):
        text = "".join(lines)
        head = _md_plain(lines[0].lstrip("#")) if lines else ""
        if kind == "intro":
            pages.append(dict(path="/docs", title=DOCS_GROUPS[0], group=DOCS_GROUPS[0], gpath="/docs", depth=0, md=text)); gi = 1
        elif kind == "##" and len(pages) == 1 and not why:
            pages[0]["md"] += text; why = True                      # "Why ..." belongs to the overview
        elif kind == "##":
            label = DOCS_GROUPS[gi]; gi += 1
            pages.append(dict(path="/docs/" + _slug(label), title=head, group=label, gpath="/docs/" + _slug(label), depth=1, md=text))
        else:
            parent = next(x for x in reversed(pages) if x["depth"] <= 1)
            if parent["depth"] == 0:
                raise ValueError("a ### before the first group in DOCS.md")
            pages.append(dict(path=parent["gpath"] + "/" + _slug(lines[0][4:]), title=head, group=parent["group"],
                              gpath=parent["gpath"], depth=2, md=text))
    if gi != len(DOCS_GROUPS):
        raise ValueError(f"DOCS.md has {gi} groups, the menu {len(DOCS_GROUPS)}")
    paths = [x["path"] for x in pages]
    if len(paths) != len(set(paths)):
        raise ValueError("two docs pages with the same address")
    for x in pages:
        x["ids"] = re.findall(r'<h[23] id="([^"]+)">', _md_to_html(x["md"]))
    return pages


def docs_anchors(pages: list[dict] | None = None) -> dict[str, str]:
    """Old /docs#anchor → the page that has that heading now (built from the headings, never by hand)."""
    return {i: x["path"] for x in (pages or docs_pages()) if x["depth"] for i in x["ids"]}


def _docs_tree(pages: list[dict], current: str) -> str:
    cur = lambda path: ' aria-current="page"' if path == current else ""
    out = []
    for x in pages:
        if x["depth"] <= 1:
            kids = [y for y in pages if y["depth"] == 2 and y["gpath"] == x["path"]]
            sub = "".join(f'<li><a href="{y["path"]}"{cur(y["path"])}>{html.escape(y["title"])}</a></li>' for y in kids)
            out.append(f'<li><a class="docs-group" href="{x["path"]}"{cur(x["path"])}>{html.escape(x["group"])}</a>'
                       + (f"<ul>{sub}</ul>" if sub else "") + "</li>")
    more = "".join(f'<li><a href="{h}">{html.escape(t)}</a></li>' for h, t in DOCS_MORE)
    return f'<ul class="docs-tree">{"".join(out)}</ul><ul class="docs-tree docs-more">{more}</ul>'


def docs_page_html(path: str) -> str:
    pages = docs_pages()
    idx = next(i for i, x in enumerate(pages) if x["path"] == path)
    pg = pages[idx]
    where = docs_anchors(pages)
    from . import concepts
    figs = concepts.figures()
    figs["overview-film"] = lambda _rendered: film_html(heading=False)        # n157: the overview film at the top of /docs
    body = _md_to_html(pg["md"], figs)
    # links between the parts of the old page go to the page that has the heading now
    body = re.sub(r'href="#([^"]+)"', lambda m: f'href="{where[m.group(1)]}#{m.group(1)}"' if where.get(m.group(1), path) != path
                  else m.group(0), body)
    if pg["depth"]:                                                         # the page's own heading is its h1
        body = re.sub(r'^<h([23]) id="([^"]+)">(.*?)</h\1>', r'<h1 id="\2">\3</h1>', body, count=1)
    own = [(i, t) for _n, i, t in re.findall(r'<h([23]) id="([^"]+)">(.*?)</h\1>', body)]
    otp = ("" if not own else '<aside class="docs-otp"><nav aria-label="On this page"><p class="docs-otp-h">On this page</p><ul>'
           + "".join(f'<li><a href="#{i}">{re.sub(r"<[^>]+>", "", t)}</a></li>' for i, t in own) + "</ul></nav></aside>")
    tree = _docs_tree(pages, path)
    crumbs = ['<li><a href="/docs">Docs</a></li>']
    if pg["depth"] == 2:
        crumbs.append(f'<li><a href="{pg["gpath"]}">{html.escape(pg["group"])}</a></li>')
    if pg["depth"]:
        crumbs.append(f'<li aria-current="page">{html.escape(pg["title"])}</li>')
    kids = ""
    if pg["depth"] == 0:
        kids = f'<nav class="docs-children" aria-label="All docs pages">{tree}</nav>'
    elif pg["depth"] == 1:
        kids = ('<nav class="docs-children" aria-label="Pages in this part"><ul>' + "".join(
            f'<li><a href="{y["path"]}">{html.escape(y["title"])}</a></li>' for y in pages if y["depth"] == 2 and y["gpath"] == path) + "</ul></nav>")
    pager = []
    if idx > 0:
        pager.append(f'<a class="docs-prev" href="{pages[idx-1]["path"]}" rel="prev"><span class="muted tiny">Previous</span> {html.escape(pages[idx-1]["title"])}</a>')
    if idx + 1 < len(pages):
        pager.append(f'<a class="docs-next" href="{pages[idx+1]["path"]}" rel="next"><span class="muted tiny">Next</span> {html.escape(pages[idx+1]["title"])}</a>')
    anchors = ""
    if pg["depth"] == 0:                                                    # read by /static/docs.js, never run as script
        data = json.dumps(where).replace("<", "\\u003c")
        anchors = f'<script type="application/json" id="docs-anchors">{data}</script>'
    main = f"""<div class="wrap docs-layout">
<details class="docs-menu-m"><summary>Docs menu</summary><nav aria-label="Docs">{tree}</nav></details>
<nav class="docs-menu" aria-label="Docs">{tree}</nav>
<article class="prose docs">
<nav class="crumbs" aria-label="Breadcrumb"><ol>{"".join(crumbs)}</ol></nav>
{body}
{kids}
<nav class="docs-pager" aria-label="Previous and next">{"".join(pager)}</nav>
</article>
{otp}
</div>{anchors}"""
    title = "{{PRODUCT}} — docs" if not pg["depth"] else f'{pg["title"]} — {{{{PRODUCT}}}} docs'
    first = re.search(r"<p>(.*?)</p>", body, flags=re.S)
    desc = re.sub(r"<[^>]+>", "", first.group(1)) if pg["depth"] and first else DOCS_DESC
    desc = html.unescape(desc) if len(desc) <= 220 else DOCS_DESC
    head = f'<script src="/static/docs.js?v={_vars()["ASSET_V"]}" defer></script>' if pg["depth"] == 0 else ""
    return _shell(title, desc, main, page="docs", nav="docs", path=path, chat=True, head=head)


def docs_html() -> str:
    return docs_page_html("/docs")


def lovable_html() -> str:
    html = _md_to_html(lovable_md()).replace(f'<a href="{DEMO_APP_URL}"{NEW_TAB}>See the live example →', f'<a class="btn primary" href="{DEMO_APP_URL}"{NEW_TAB}>See the live example →')
    body = f'<article class="wrap prose docs">{html}</article>'
    return _shell("Build a Lovable app on your Fabric tables — {{PRODUCT}}", LOVABLE_DESC, body, page="lovable", nav="docs", path="/lovable", chat=True)


# ------------------------------------------------------------------ n145: the blog -----------------------------------
# Each post is a Markdown file in page_templates (BLOG-<slug>.md), served unchanged at <path>.md and rendered the way the
# docs are. Its title, meta description and JSON-LD (Article, FAQPage) are read from the file, never written twice.

BLOG_AUTHOR = "Gustav Kruse"
BLOG_PUBLISHER = "Kruse Consulting AB"
BLOG_POSTS = [{"slug": "fabric-totals-double-after-join", "date": "2026-11-07"}]
BLOG_DESC = "Articles on keys, grain and relationships between Microsoft Fabric tables, by Gustav Kruse, Kruse Consulting AB."
BLOG_OWN_HOSTS = ("krusgraph.com",)


def _long_date(iso: str) -> str:
    y, m, d = (int(x) for x in iso.split("-"))
    return f"{d} {('January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December')[m - 1]} {y}"


def _md_inline_plain(s: str) -> str:
    """Markdown inline text as plain text: links become their text, code and emphasis marks go."""
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
    return re.sub(r"\s+", " ", s.replace("**", "").replace("`", "")).strip()


def blog_md(slug: str) -> str:
    return _read(f"BLOG-{slug}.md")


def blog_post(slug: str) -> dict:
    meta = next(x for x in BLOG_POSTS if x["slug"] == slug)
    md = blog_md(slug)
    lines = md.splitlines()
    title = _md_inline_plain(next(ln[2:] for ln in lines if ln.startswith("# ")))
    quick = _md_inline_plain(next(ln for ln in lines if ln.startswith("**Quick answer:**"))[len("**Quick answer:**"):])
    quick = quick[:1].upper() + quick[1:]
    if len(quick) >= 160:                                       # cut at a word, under 160 characters with the ellipsis
        quick = quick[:158].rsplit(" ", 1)[0].rstrip(",;:") + "…"
    faq, q, fence, in_faq = [], None, False, False
    for ln in lines:
        if ln.startswith("```"):
            fence = not fence
        if fence:
            continue
        if ln.startswith("## "):
            in_faq = ln.strip() == "## FAQ"; q = None; continue
        if in_faq and ln.startswith("### "):
            q = {"q": _md_inline_plain(ln[4:]), "a": []}; faq.append(q); continue
        if q is not None and ln.strip():
            q["a"].append(ln.strip())
    faq = [{"q": x["q"], "a": _md_inline_plain(" ".join(x["a"]))} for x in faq]
    return dict(meta, path="/blog/" + slug, md=md, title=title, description=quick, faq=faq,
                author=BLOG_AUTHOR, publisher=BLOG_PUBLISHER, date_text=_long_date(meta["date"]))


def blog_json_ld(post: dict) -> str:
    url = site_url() + post["path"]
    data = [
        {"@context": "https://schema.org", "@type": "Article", "headline": post["title"], "description": post["description"],
         "datePublished": post["date"], "inLanguage": "en", "url": url, "mainEntityOfPage": url,
         "author": {"@type": "Person", "name": post["author"], "worksFor": {"@type": "Organization", "name": post["publisher"]}},
         "publisher": {"@type": "Organization", "name": post["publisher"], "url": site_url() + "/"}},
        {"@context": "https://schema.org", "@type": "FAQPage", "url": url,
         "mainEntity": [{"@type": "Question", "name": x["q"], "acceptedAnswer": {"@type": "Answer", "text": x["a"]}} for x in post["faq"]]},
    ]
    safe = lambda d: json.dumps(d, ensure_ascii=False).replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    return "".join('<script type="application/ld+json">' + safe(d) + "</script>" for d in data)


def _offsite_noopener(body: str) -> str:
    """Links to other sites get rel="noopener", as the header's and footer's GitHub links do."""
    from urllib.parse import urlsplit
    own = set(BLOG_OWN_HOSTS) | {_vars()["DOMAIN"].lower()}

    def fix(m):
        host = (urlsplit(html.unescape(m.group(1))).hostname or "").lower()
        return m.group(0) if host in own else f'<a href="{m.group(1)}" rel="noopener">'
    return re.sub(r'<a href="(https?://[^"]+)">', fix, body)


def _byline(post: dict) -> str:
    return (f'<p class="blog-meta muted"><time datetime="{post["date"]}">{post["date_text"]}</time> · '
            f'{html.escape(post["author"])}, {html.escape(post["publisher"])}</p>')


def blog_post_html(slug: str) -> str:
    post = blog_post(slug)
    body = _offsite_noopener(_md_to_html(post["md"]))
    body = re.sub(r"^(<h1>.*?</h1>)", lambda m: m.group(1) + "\n" + _byline(post), body, count=1)
    main = f"""<article class="wrap prose docs blog">
<nav class="crumbs" aria-label="Breadcrumb"><ol><li><a href="/blog">Blog</a></li><li aria-current="page">{html.escape(post["title"])}</li></ol></nav>
{body}
<p class="blog-foot muted tiny"><a href="/blog">All articles</a> · <a href="{post["path"]}.md">This article as Markdown</a></p>
</article>"""
    md_link = f'<link rel="alternate" type="text/markdown" href="{post["path"]}.md" title="Markdown version">'
    return _shell(post["title"] + " — {{PRODUCT}} blog", post["description"], main, page="blog", nav="blog",
                  path=post["path"], head=md_link + blog_json_ld(post), og_type="article", chat=True)


def blog_index_html() -> str:
    items = []
    for meta in sorted(BLOG_POSTS, key=lambda x: x["date"], reverse=True):
        post = blog_post(meta["slug"])
        items.append(f'<li class="blog-item"><h2><a href="{post["path"]}">{html.escape(post["title"])}</a></h2>{_byline(post)}'
                     f'<p>{html.escape(post["description"])}</p></li>')
    main = f"""<article class="wrap prose docs blog">
<h1>Blog</h1>
<p class="lead">{html.escape(BLOG_DESC)}</p>
<ul class="blog-list">{"".join(items)}</ul>
</article>"""
    return _shell("Blog — {{PRODUCT}}", BLOG_DESC, main, page="blog", nav="blog", path="/blog", chat=True)


def start_md() -> str:
    """The get-started page as Markdown, converted from the same template the HTML page uses."""
    v = _vars()
    body = _read("start.html").replace("{{START_CONNECT}}", "")         # n149: the chooser's buttons need the page; the steps say the same
    return _html_to_md(_fill(_conditional(_access(body), v)), "https://" + v["DOMAIN"])


def access_vars(markdown: bool = False) -> dict[str, str]:
    """n146: the permissions, the tokens kept per client, the two data flows and the planning and checking sentences,
    from fabric_backend/access.py and server.py's limits: the same text on /start, /it, /privacy and llms.txt."""
    from . import access
    v = _vars()
    reg, where = _registration_on(), v["REGISTRATION_WHERE"]
    lim = {k: int(v[k]) for k in ("R5_SAMPLE", "R5_MAX_QUERIES", "VALIDATE_MAX_ITEMS")}
    if markdown:
        return {"ACCESS_SCOPES": access.table_md(), "ACCESS_TOKENS": access.tokens_md(reg, where),
                "ACCESS_FLOWS": access.flows_md(v["PRODUCT"], v["DOMAIN"]),
                "ACCESS_PLANNING": access.planning_sentence(**lim), "ACCESS_CHECKS": access.checks_sentence(**lim)}
    return {"ACCESS_SCOPES": access.table_html(), "ACCESS_TOKENS": access.tokens_html(reg, where),
            "ACCESS_FLOWS": access.flows_html(v["PRODUCT"], v["DOMAIN"]),
            "ACCESS_PLANNING": access.inline_html(access.planning_sentence(**lim)),
            "ACCESS_CHECKS": access.inline_html(access.checks_sentence(**lim))}


def _access(body: str, markdown: bool = False) -> str:
    """{{ACCESS_...}} → the generated tables and sentences (HTML, or Markdown for the Markdown pages)."""
    if "{{ACCESS_" not in body:
        return body
    av = access_vars(markdown)
    return re.sub(r"\{\{(ACCESS_\w+)\}\}", lambda m: av[m.group(1)], body)


def _html_to_md(src: str, origin: str) -> str:
    """Just enough HTML → Markdown for the site's own templates (headings, paragraphs, lists, links, code, tables)."""
    s = re.sub(r"<(svg|script|style|button)\b.*?</\1>", "", src, flags=re.S)
    s = re.sub(r'<span[^>]*data-mascot[^>]*></span>', "", s)
    s = re.sub(r'<span class="kicker">.*?</span>', "", s)
    s = re.sub(r"<summary>(.*?)</summary>", r"\n\n## \1\n\n", s, flags=re.S)
    s = re.sub(r"<pre><code[^>]*>(.*?)</code></pre>", lambda m: "\n\n```\n" + m.group(1).strip() + "\n```\n\n", s, flags=re.S)
    s = re.sub(r"<h1[^>]*>(.*?)</h1>", r"\n\n# \1\n\n", s, flags=re.S)
    s = re.sub(r"<h2[^>]*>(.*?)</h2>", r"\n\n## \1\n\n", s, flags=re.S)
    s = re.sub(r"<h3[^>]*>(.*?)</h3>", r"\n\n### \1\n\n", s, flags=re.S)
    s = re.sub(r"<tr>(.*?)</tr>", lambda m: "| " + " | ".join(c.strip() for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", m.group(1), flags=re.S)) + " |\n", s, flags=re.S)
    s = re.sub(r"(<thead>\s*)(\|.*?\|)\n", lambda m: m.group(2) + "\n" + "|" + " --- |" * m.group(2).count(" | ") + " --- |\n", s, flags=re.S)
    s = re.sub(r'<a href="(/[^"]*)"', lambda m: f'<a href="{origin}{m.group(1)}"', s)
    s = re.sub(r'<a href="([^"]+)"[^>]*>(.*?)</a>', r"[\2](\1)", s, flags=re.S)
    s = re.sub(r"</?(strong|b)>", "**", s)
    s = re.sub(r"</?em>", "*", s)
    s = re.sub(r"</?code>", "`", s)
    s = re.sub(r'<span class="step-n[^"]*">\d+</span>', "", s)
    s = re.sub(r"<li>", "\n- ", s)
    s = re.sub(r"<p[^>]*>", "\n\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    s = re.sub(r"[ \t]+\n", "\n", s)
    s = re.sub(r"\n[ \t]+", "\n", s)
    s = re.sub(r"^-\s*$", "", s, flags=re.M)                                  # list items that only held a heading
    s = re.sub(r"\n{3,}", "\n\n", s)
    s = re.sub(r"\|\n\n(?=\|)", "|\n", s)                                        # table rows stay together
    return s.strip() + "\n"


JSON_LD_DESC = ("Suggests keys and relationships between Microsoft Fabric tables, explains each one with the rule behind it and "
                "checks them against the data, from Claude.")


def json_ld() -> str:
    """Structured data for the home page: the application and the company. Facts only; no ratings or numbers."""
    import json
    v = _vars()
    origin = site_url()
    data = [
        {"@context": "https://schema.org", "@type": "SoftwareApplication", "name": v["PRODUCT"],
         "applicationCategory": "DeveloperApplication", "operatingSystem": "Web", "url": origin + "/",
         "description": _fill(JSON_LD_DESC, escape=False), "license": "https://opensource.org/licenses/MIT",
         "sameAs": [GITHUB], "publisher": {"@type": "Organization", "name": "Kruse Consulting AB", "url": origin + "/"}},
        {"@context": "https://schema.org", "@type": "Organization", "name": "Kruse Consulting AB", "url": origin + "/",
         "email": v["CONTACT"], "sameAs": [GITHUB]},
        {"@context": "https://schema.org", "@type": "WebSite", "name": v["PRODUCT"], "url": origin + "/",
         "publisher": {"@type": "Organization", "name": "Kruse Consulting AB"}, "inLanguage": "en"},
    ]
    safe = lambda d: json.dumps(d, ensure_ascii=False).replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")   # inert inside <script>
    return "".join('<script type="application/ld+json">' + safe(d) + "</script>" for d in data)

