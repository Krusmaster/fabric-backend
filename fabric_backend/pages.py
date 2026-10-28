"""The public site — served by the MCP server itself, so one domain is enough.

    /                  start page           /explore            graph explorer (client-side demo, synthetic schema)
    /demo              the guided demo: one order followed to its delivery address (demo.home_guide)
    /start             get started          /support            support
    /partners          partners             /partners/workspace illustrative partner workspace
    /docs              setup and usage      /privacy            privacy policy
    /lovable           using the created API with Lovable's Fabric connector
    /local             the local server over ODBC, and exactly what leaves the machine
    /use-cases         industries, typical tables and what the engine finds in them (use_cases.py)
    /mascots           mascot review page (noindex, unlinked)
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
import os
import re
from importlib import resources
from pathlib import Path

GITHUB = "https://github.com/Krusmaster/fabric-backend"
HERE = Path(__file__).resolve().parent
STATIC_DIR = HERE / "static"

STATIC_TYPES = {".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".svg": "image/svg+xml",
                ".png": "image/png", ".woff2": "font/woff2", ".txt": "text/plain; charset=utf-8", ".json": "application/json",
                ".ico": "image/x-icon"}

PAGES = {
    # path: (template, title, description, nav key)
    "/": ("home.html", "{{PRODUCT}} | Understand your Microsoft Fabric tables",
          "Explore keys and relationships in Microsoft Fabric, check them against your data, and review the plan in Claude before building on it.", "product"),
    "/demo": ("demo.html", "Guided demo: where should each order be delivered? — {{PRODUCT}}",
              "Follow one order to its delivery address on a synthetic shop schema: what the engine suggests, what the data shows, your decision and what you can explain afterwards. No account needed.", "product"),
    "/explore": ("explore.html", "Explore the demo graph — {{PRODUCT}}",
                 "A demo on a synthetic shop schema: select a table to inspect its key, or a line to see why two tables were linked.", "product"),
    "/start": ("start.html", "Connect to Claude — {{PRODUCT}}",
               "What you need, admin approval in Microsoft Entra, and how to add {{PRODUCT}} as a custom connector in Claude.", "start"),
    "/support": ("support.html", "Get help with {{PRODUCT}}",
                 "How to get help with {{PRODUCT}}: email with the error, kind and hint from the tool's answer, report a bug or a plan that came out wrong on GitHub Issues, and the most common first errors.", "support"),
    "/partners": ("partners.html", "Try a pilot — {{PRODUCT}}",
                  "Bring one schema and one question: a {{PRODUCT}} pilot reviews the relationships with you and builds one chosen result. Kruse Consulting AB; not affiliated with Microsoft.", "partners"),
    "/partners/workspace": ("workspace.html", "A sample pilot — {{PRODUCT}}",
                            "A sample {{PRODUCT}} pilot on a synthetic shop schema: Connect, Explore, Review, Build. No customer workspace is connected.", "partners"),
    "/use-cases": ("use_cases.html", "Use cases — {{PRODUCT}}",
                   "Start from an undocumented lakehouse, a join to check or an app to build. Ten illustrative schemas show what {{PRODUCT}} proposes, where it can go wrong and what still needs your judgement.", "usecases"),
    "/mascots": ("mascots.html", "Mascot review — {{PRODUCT}}",
                 "Review page for the three mascots: every pose and demo state.", ""),
}


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
        "CLIENT_ID": os.environ.get("ENTRA_CLIENT_ID", "<client id>"),
        "GITHUB": GITHUB,
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
        "REGISTRATION_WHERE": ("the server's memory (lost when it restarts)"
                               if os.environ.get("KRUSGRAPH_REGISTRATION_STORE", "").strip().lower() == "memory"
                               else "an Azure Table Storage table of ours in the service's Azure region"),
        # the test status, from tool_status: the live run's date and what it covered, and each tool's status in a sentence
        "LIVE_RUN_DATE": ts.LIVE_RUN_DATE, "LIVE_RUN_SUMMARY": ts.LIVE_RUN_SUMMARY, "CREATE_API_STATUS": ts.create_api_status(),
        **{f"STATUS_{name.upper()}": ts.phrase(name) for name in ts.STATUS},
        # the sources with their status, as the hub and the docs' "Why" section give it (tool_status.SOURCES)
        "SOURCES_STATUS": _listed([f"a {n[0].lower() + n[1:] if n != 'SQL database' else n} ({ts.source_word(t)})"
                                    for n, t in ts.SOURCES]).replace(" and a ", " or a "),
    }


def _registration_on() -> bool:
    from .registration import enabled
    return enabled()


def _listed(names: list[str]) -> str:
    return ", ".join(names[:-1]) + " and " + names[-1] if len(names) > 1 else "".join(names)


def _clients_sentence() -> str:
    """"Claude", or "Claude (and, Experimental, VS Code and Cursor)" once client registration is on
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


def hub_html() -> str:
    """The start page's hub under the hero (Gustav's brief of 27 October 2026): your data in Fabric and what {{PRODUCT}}
    builds there on the left, {{PRODUCT}} in the middle, where you build on the right, joined by lines as in the graph.
    Every status comes from tool_status: "creates" only for what has been created live on the hosted service, "updates"
    for what has only been updated in place there, "draft" for the rest; sources not yet read live are marked experimental; an MCP client is named only once it has signed
    in to the hosted service (Cursor and VS Code through client registration). Text names only, no third-party logos;
    the visual is hidden from screen readers, which get the same as one paragraph."""
    from . import tool_status as ts
    v = _vars()
    p, low = html.escape(v["PRODUCT"]), html.escape(v["PRODUCT_LOWER"])
    clients = ts.clients_working(_registration_on())

    def tag(word: str) -> str:
        return f'<span class="hub-tag hub-{word.split()[0]}">{word}</span>'
    sources = "".join(f"<li><b>{n}</b>{'' if tested else tag('experimental')}</li>" for n, tested in ts.SOURCES)
    builds = "".join(f"<li><b>{n}</b>{tag(ts.build_word(tool))}</li>" for n, tool in ts.BUILDS)
    status = {c.name: c.status for c in ts.CLIENTS}
    exp = lambda c: "" if status[c] == "Tested end to end" else tag("experimental")
    where = "".join(f'<li><b>{html.escape(c)}</b><span class="hub-via">via MCP</span>{exp(c)}</li>' for c in clients)
    where += f'<li><b>Lovable</b><span class="hub-via">via the GraphQL API</span>{exp("Lovable")}</li>'

    exp_word = lambda c: "" if status[c] == "Tested end to end" else " (experimental)"
    created = [n for n, tool in ts.BUILDS if ts.build_word(tool) == "creates"]
    updated = [n for n, tool in ts.BUILDS if ts.build_word(tool) == "updates"]
    drafted = [n for n, tool in ts.BUILDS if ts.build_word(tool) == "draft"]
    said = (f"Your data in Fabric: " + _listed([f"{n} ({ts.source_word(t)})" for n, t in ts.SOURCES]) + ". "
            f"In the middle, {p}: one plan, with the rule behind every relationship. "
            f"What {p} builds in Fabric from that plan: " + "; ".join(
                ([f"it creates the {_listed(created)}"] if created else [])
                + ([f"it updates an existing {_listed(updated)} (creating a new one is experimental)"] if updated else [])
                + ([f"{_listed(drafted)} {'is a draft' if len(drafted) == 1 else 'are drafts'} so far"] if drafted else [])) + ". "
            f"Where you build: {_listed([c + exp_word(c) for c in clients])} "
            f"{'connects' if len(clients) == 1 else 'connect'} to {p} through MCP, and "
            f"Lovable{exp_word('Lovable')} uses the GraphQL API {p} creates in Fabric rather than {p} itself.")
    makers = ["Microsoft", "Anthropic"] + (["Anysphere"] if "Cursor" in clients else []) + ["Lovable"]
    return f"""<section class="wrap connects" aria-label="What {p} connects">
  <p class="visually-hidden">{said}</p>
  <div class="hub" aria-hidden="true">
    <div class="hub-group hub-src c-coral"><p class="hub-h">Your data in Fabric</p><ul>{sources}</ul></div>
    <span class="hub-link hub-link-src"></span>
    <div class="hub-group hub-build c-sage"><p class="hub-h">What {p} builds in Fabric</p><ul>{builds}</ul></div>
    <span class="hub-link hub-link-build"></span>
    <div class="hub-mid"><span class="hub-node"><span class="c-hub">{low}</span><i class="hub-end"></i></span><span class="hub-sub">one plan, the rule behind every relationship</span></div>
    <div class="hub-group hub-where c-mustard"><p class="hub-h">Where you build</p><ul>{where}</ul></div>
  </div>
  <p class="muted tiny connects-note">Independent product. Not affiliated with or endorsed by {_listed(makers).replace(" and ", " or ")}.</p>
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


def _md_to_html(md: str) -> str:
    """Just enough Markdown for these pages: headings (with ids), paragraphs, bold/italic, code, links, lists, pipe tables."""
    def inline(s: str) -> str:
        s = html.escape(s, quote=False)
        s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
        s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", s)
        s = re.sub(r"\[([^\]]+)\]\(((?:https?://|/|mailto:)[^)]+)\)", lambda m: f'<a href="{m.group(2).replace(chr(34), "&quot;")}">{m.group(1)}</a>', s)
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


MARKDOWN_TWINS = ("/docs", "/start", "/privacy", "/lovable", "/local", "/use-cases")       # pages that are also served as <path>.md


def _shell(title: str, description: str, body: str, page: str, nav: str, noindex: bool = False, head: str = "",
           path: str = "") -> str:
    v = _vars()
    links = [("product", "/", "Product"), ("usecases", "/use-cases", "Use cases"), ("docs", "/docs", "Docs"), ("support", "/support", "Support"), ("partners", "/partners", "Try a pilot")]
    nav_html = "".join(f'<a href="{href}"{" aria-current=page" if key == nav else ""}>{label}</a>' for key, href, label in links)
    robots = '<meta name="robots" content="noindex,nofollow">' if noindex else ""
    t, d = _fill(title), _fill(description)                       # _fill escapes
    canonical = html.escape(site_url() + (path or "/"), quote=True)
    og_image = html.escape(f"https://{v['DOMAIN']}/static/og.png", quote=True)
    md_alternate = (f'<link rel="alternate" type="text/markdown" href="{path}.md" title="Markdown version">'
                    if path in MARKDOWN_TWINS else "")                       # agents and crawlers get the text form in one hop
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{t}</title>
<meta name="description" content="{d}">
{robots}
{"" if noindex else f'<link rel="canonical" href="{canonical}">'}
<meta property="og:type" content="website">
<meta property="og:site_name" content="{html.escape(v['PRODUCT'])}">
<meta property="og:url" content="{canonical}">
<meta property="og:title" content="{t}">
<meta property="og:description" content="{d}">
<meta property="og:image" content="{og_image}">
<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta property="og:image:alt" content="{html.escape(v['PRODUCT'])}: Microsoft Fabric, connected.">
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
      <span class="brand-text"><span class="wordmark">{html.escape(v['PRODUCT_LOWER'])}</span><span class="tagline">Microsoft Fabric, connected.</span></span>
    </a>
    <button class="nav-toggle" type="button" aria-expanded="false" aria-controls="site-nav" aria-label="Menu"><span></span><span></span><span></span></button>
    <nav id="site-nav" class="site-nav" aria-label="Main">
      {nav_html}
      <a class="icon-link" href="{GITHUB}" aria-label="Source on GitHub" rel="noopener">{_GITHUB_ICON}</a>
    </nav>
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
      <p class="muted tiny">Microsoft Fabric and Fabric IQ are trademarks of Microsoft Corporation. {html.escape(v['PRODUCT'])} is an independent product and is not affiliated with, endorsed by or certified by Microsoft.</p>
    </div>
    <nav class="footer-links" aria-label="Footer">
      <a href="/demo">Guided demo</a><a href="/explore">Demo graph</a><a href="/use-cases">Use cases</a><a href="/start">Get started</a><a href="/docs">Docs</a><a href="/lovable">Use with Lovable</a><a href="/privacy">Privacy</a><a href="/support">Support</a><a href="/partners">Try a pilot</a>
      <a href="{GITHUB}" rel="noopener">GitHub</a><a href="mailto:{html.escape(v['CONTACT'])}">{html.escape(v['CONTACT'])}</a>
    </nav>
    <div class="footer-controls">
      <button type="button" class="btn ghost small" data-mascot-toggle aria-pressed="true">Mascots: on</button>
      <span class="muted tiny" id="mascot-toggle-note">Your choice applies across the site and is saved in this browser.</span>
    </div>
  </div>
</footer>
<script src="/static/mascots.js?v={v['ASSET_V']}" defer></script>
<script src="/static/site.js?v={v['ASSET_V']}" defer></script>
</body>
</html>"""


def _demo_vars() -> dict[str, str]:
    """Server-rendered fallbacks for the demo pages, so the table list exists before (or without) JavaScript."""
    from .demo import demo_plan
    d = demo_plan()
    order = ["customers", "orders", "order_items", "products", "categories", "addresses", "audit_log"]
    colors = ["coral", "sage", "lav", "mustard"]
    icon = ('<svg class="g-ico" viewBox="0 0 16 16" aria-hidden="true" focusable="false"><rect x="1.5" y="2.5" width="13" height="11" rx="2.6" '
            'fill="currentColor" fill-opacity=".22" stroke="currentColor" stroke-width="1.5"/><path d="M1.5 6.5h13M6.2 6.5v7" stroke="currentColor" stroke-width="1.5"/></svg>')

    def row(i: int, t: dict) -> str:
        color = colors[(order.index(t["name"]) if t["name"] in order else i) % len(colors)]
        code = t["key_rule"] if t["key"] else "K3"
        label = "no key" if not t["key"] else "composite key" if len(t["key"]) > 1 else "key"
        tip = html.escape(f'Rule {code}: {d["rules"].get(code, "").replace("`", "")}')
        return (f'<li><button type="button" data-table="{html.escape(t["name"])}"><span class="t-ico c-{color}">{icon}</span>'
                f'<span class="nm">{html.escape(t["name"])}</span><span class="rule" title="{tip}">{label}</span></button></li>')
    items = "".join(row(i, t) for i, t in enumerate(d["tables"]))
    rules = {k: re.sub(r"`([^`]+)`", r"<code>\1</code>", html.escape(t)) for k, t in d["rules"].items()}
    used = [t["key_rule"] if t["key"] else "K3" for t in d["tables"]] + [r["rule"] for r in d["relationships"]]
    used = [k for k in d["rules"] if k in used]                              # each rule explained once, in the engine's order
    legend = "".join(f'<div><dt><code>{k}</code></dt><dd>{rules[k]}</dd></div>' for k in used)
    keys = "".join(f'<li><strong>{html.escape(t["name"])}</strong>: ' + (f'key <code>{html.escape(" + ".join(t["key"]))}</code>, <code>{t["key_rule"]}</code>'
                   if t["key"] else 'no key, <code>K3</code>') + f'; columns {html.escape(", ".join(c["name"] for c in t["columns"]))}</li>'
                   for t in d["tables"])
    rels = "".join(f'<li><code>{html.escape(r["source"] + "." + "+".join(r["source_cols"]))}</code> → <code>{html.escape(r["target"] + "." + "+".join(r["target_cols"]))}</code>, '
                   f'<code>{r["rule"]}</code>; GraphQL fields <code>{html.escape(r["field"])}</code> and <code>{html.escape(r["reverse"])}</code></li>'
                   for r in d["relationships"])
    unlinked = "".join(f'<li><code>{html.escape(u["table"] + "." + u["column"])}</code>: {html.escape(u["note"])}</li>' for u in d["unlinked"]) or "<li>none</li>"
    text = (f'<p class="mono">{"<br>".join(html.escape(line) for line in d["summary"].splitlines())}</p><h3>The rules used</h3><dl class="rule-list">{legend}</dl>'
            f'<h3>Tables and keys</h3><ul>{keys}</ul><h3>Relationships</h3><ul>{rels}</ul><h3>Left unlinked</h3><ul>{unlinked}</ul>')
    from .demo import demo_validation
    v = demo_validation()
    e = html.escape
    krows = "".join(f'<tr><td><code>{e(k["table"])}</code></td><td><code>{e(" + ".join(k["columns"]))}</code> <span class="muted">{e(k["rule"])}</span></td>'
                    f'<td>{k["rows"]}</td><td>{k["distinct"]}</td><td>{k["nulls"]}</td><td>{e(k["verdict"])}</td></tr>' for k in v["keys"])
    rrows = "".join(f'<tr><td><code>{e(r["source"] + "." + "+".join(r["columns"]))}</code> → <code>{e(r["target"] + "." + "+".join(r["target_columns"]))}</code> '
                    f'<span class="muted">{e(r["rule"])}</span></td><td>{r["rows_with_value"]}</td><td>{r["orphans"]}</td><td>{e(r["verdict"])}</td></tr>'
                    for r in v["relationships"])
    sugg = "".join(f'<li><code>{e(x["table"])}</code>: <code>{e(" + ".join(x["columns"]))}</code> — {e(x["why"])}</li>' for x in v["suggested_keys"]) or "<li>none</li>"
    check = (f'<p class="mono">{e(v["summary"])}</p>'
             f'<h3>Keys</h3><div class="table-wrap"><table class="check"><thead><tr><th>Table</th><th>Key (rule)</th><th>Rows</th><th>Distinct</th><th>NULLs</th><th>Verdict</th></tr></thead><tbody>{krows}</tbody></table></div>'
             f'<h3>Relationships</h3><div class="table-wrap"><table class="check"><thead><tr><th>Reference (rule)</th><th>Rows with a value</th><th>Orphans</th><th>Verdict</th></tr></thead><tbody>{rrows}</tbody></table></div>'
             f'<h3>Composite keys the plan suggests before any override</h3><ul>{sugg}</ul>')
    return {"DEMO_TABLE_LIST": items, "DEMO_SUMMARY": html.escape(d["summary"].splitlines()[0]), "DEMO_PLAN_TEXT": text,
            "DEMO_CHECK": check, "DEMO_CHECK_SUMMARY": e(v["summary"]), "DEMO_BUILD": build_html(), "DEMO_PATH": build_path_html()}


# The docs section each card of "What you can build automatically from this plan" links to, by heading (slugged as _md_to_html does).
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
         "you": "You ask for each part. All but create_backend show what they would create first, and create when you say so."},
    ]


def build_path_html() -> str:
    """The row of steps above the cards, with the counts from the path, the demo plan and the 20-minute demo's budget."""
    from .demo import demo_plan
    from .demo_app import STEPS
    from .tool_status import label
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
            f'<p class="muted tiny">Status of creating: {"; ".join(f"<code>{e(t)}</code> {e(label(t))}" for t in path[-1]["tools"])}.</p>')


def build_html() -> str:
    """The four cards of /explore's last section, from demo.build_cards()."""
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
               + (f' ({e(", ".join(f"{x['header']}.{c}" for x in m["header_amounts"] for c in x["amount_columns"]))})' if m["header_amounts"] else "")
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


def _home_vars() -> dict[str, str]:
    """The guided demo's example (/demo): the detail of the default relationship, server-rendered so it reads without JavaScript,
    every detail as JSON for the page's script, and the relationships as links (demo.home_details)."""
    import json
    from .demo import HOME_DEFAULT, home_details, home_guide, home_relationship_list
    details = home_details()
    safe = json.dumps(details, ensure_ascii=False).replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    return {"HOME_DETAIL": details[HOME_DEFAULT], "HOME_DETAILS_JSON": safe, "HOME_REL_LIST": home_relationship_list(),
            "HOME_GUIDE": home_guide(), "HOME_HUB": hub_html()}


def render(path: str) -> str:
    template, title, description, nav = PAGES[path]
    v = _vars()
    body = _read(template)
    if "{{HOME_" in body:
        hv = _home_vars()
        body = re.sub(r"\{\{(HOME_\w+)\}\}", lambda m: hv.get(m.group(1), ""), body)
    if "{{DEMO_" in body:
        dv = _demo_vars()
        body = re.sub(r"\{\{(DEMO_\w+)\}\}", lambda m: dv.get(m.group(1), ""), body)
    if "{{UC_" in body:
        from .use_cases import page_vars
        uv = page_vars()
        body = re.sub(r"\{\{(UC_\w+)\}\}", lambda m: uv.get(m.group(1), ""), body)
    body = _fill(_conditional(body, v))
    head = json_ld() if path == "/" else ""
    return _shell(title, description, body, page=template.split(".")[0], nav=nav, noindex=(path == "/mascots"), head=head, path=path)


PRIVACY_DESC = "How {{PRODUCT}} handles your Microsoft sign-in, access tokens, metadata, sample rows, query results, usage records and technical logs."
DOCS_DESC = "Connect {{PRODUCT}} to Claude, explore and check a plan against your data, keep the review, build from it, and the status of each tool: what it changes and how far it has been tested."
LOVABLE_DESC = "Prepare a GraphQL API in Microsoft Fabric with {{PRODUCT}} in Claude, then connect Lovable's Microsoft Fabric connector to it."


def privacy_md() -> str:
    md = _conditional(_read("PRIVACY.md"), _vars())
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
    md = _conditional(_read("DOCS.md").replace("{{RULES_TABLE}}", _rules_table()), _vars())
    return _fill(_tool_statuses(md), escape=False)


def lovable_md() -> str:
    return _fill(_read("LOVABLE.md"), escape=False)


LOCAL_DESC = "Run {{PRODUCT}} on your own machine against SQL Server or a Fabric SQL endpoint over ODBC: the same rules, no account with us, and exactly what leaves the machine."


def local_md() -> str:
    return _fill(_read("LOCAL.md"), escape=False)


def local_html() -> str:
    body = f'<article class="wrap prose docs">{_md_to_html(local_md())}</article>'
    return _shell("Run {{PRODUCT}} locally", LOCAL_DESC, body, page="local", nav="docs", path="/local")


def use_cases_md() -> str:
    from .use_cases import markdown
    v = _vars()
    return markdown(v["PRODUCT"], site_url(), v["CONTACT"])


def not_found_html(path: str) -> str:
    body = f"""<section class="wrap hero"><div class="hero-grid"><div>
<span class="kicker">404</span><h1>Nothing connects here.</h1>
<p class="lede">There is no page at <code>{html.escape(path[:120])}</code>.</p>
<div class="ctas"><a class="btn primary" href="/">Start page</a><a class="btn secondary" href="/explore">Explore the demo</a><a class="btn ghost" href="/docs">Docs</a></div>
</div><div class="hero-figure" aria-hidden="true"><span data-mascot="onto" data-pose="aside" data-label=""></span></div></div></section>"""
    return _shell("Page not found — {{PRODUCT}}", "There is no page at this address.", body, page="notfound", nav="", noindex=True)


def privacy_html() -> str:
    body = f'<article class="wrap prose">{_md_to_html(privacy_md())}</article>'
    return _shell("Privacy policy — {{PRODUCT}}", PRIVACY_DESC, body, page="privacy", nav="", path="/privacy")


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


def docs_html() -> str:
    body = f'<article class="wrap prose docs">{_with_toc(_md_to_html(docs_md()))}</article>'
    return _shell("{{PRODUCT}} — docs", DOCS_DESC, body, page="docs", nav="docs", path="/docs")


def lovable_html() -> str:
    body = f'<article class="wrap prose docs">{_md_to_html(lovable_md())}</article>'
    return _shell("Build a Lovable app on your Fabric tables — {{PRODUCT}}", LOVABLE_DESC, body, page="lovable", nav="docs", path="/lovable")


def start_md() -> str:
    """The get-started page as Markdown, converted from the same template the HTML page uses."""
    v = _vars()
    return _html_to_md(_fill(_conditional(_read("start.html"), v)), "https://" + v["DOMAIN"])


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

