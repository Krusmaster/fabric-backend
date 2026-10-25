"""The public site — served by the MCP server itself, so one domain is enough.

    /                  start page           /explore            graph explorer (client-side demo, synthetic schema)
    /start             get started          /support            support
    /partners          partners             /partners/workspace illustrative partner workspace
    /docs              setup and usage      /privacy            privacy policy
    /lovable           using the created API with Lovable's Fabric connector
    /use-cases         industries, typical tables and what the engine finds in them (use_cases.py)
    /mascots           mascot review page (noindex, unlinked)
    /docs.md, /privacy.md, /start.md, /lovable.md, /use-cases.md   the same content as Markdown (for /llms.txt and agents)
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
                ".png": "image/png", ".woff2": "font/woff2", ".txt": "text/plain; charset=utf-8", ".json": "application/json"}

PAGES = {
    # path: (template, title, description, nav key)
    "/": ("home.html", "{{PRODUCT}} — Microsoft Fabric, connected",
          "Turn your Microsoft Fabric tables into an explainable graph, a GraphQL API and a Fabric IQ ontology draft. Every connection shows the rule that made it.", "product"),
    "/explore": ("explore.html", "Explore the demo graph — {{PRODUCT}}",
                 "An illustrative demo on a synthetic shop schema: tables, inferred connections and the rule behind each one.", "product"),
    "/start": ("start.html", "Get started — {{PRODUCT}}",
               "Connect your Microsoft account, choose a workspace and open {{PRODUCT}} in Claude. Small steps, useful connections.", "start"),
    "/support": ("support.html", "Support {{PRODUCT}}",
                 "Help good things keep happening: better examples, clearer docs and ongoing maintenance. Contributions open soon.", "support"),
    "/partners": ("partners.html", "Partners — {{PRODUCT}}",
                  "Better connections, built together. Preview an illustrative partner workspace.", "partners"),
    "/partners/workspace": ("workspace.html", "Partner workspace preview — {{PRODUCT}}",
                            "An illustrative partner workspace: Connect, Explore, Review, Build. No partner data connected.", "partners"),
    "/use-cases": ("use_cases.html", "Use cases — {{PRODUCT}}",
                   "Ten industries, one engine: typical tables, the keys and links {{PRODUCT}} finds in them with the rule behind each, what you build, and where the value is.", "usecases"),
    "/mascots": ("mascots.html", "Mascot review — {{PRODUCT}}",
                 "Review page for the three mascots: every pose and demo state.", ""),
}


def _vars() -> dict[str, str]:
    from urllib.parse import quote
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
        "MCP_URL": url,
        "CLIENT_ID": os.environ.get("ENTRA_CLIENT_ID", "<client id>"),
        "GITHUB": GITHUB,
        "ASSET_V": asset_version(),
        "PARTNER_SIGNIN": "1" if os.environ.get("PARTNER_SIGNIN", "").strip() in {"1", "true", "yes"} else "",
    }


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


MARKDOWN_TWINS = ("/docs", "/start", "/privacy", "/lovable", "/use-cases")       # pages that are also served as <path>.md


def _shell(title: str, description: str, body: str, page: str, nav: str, noindex: bool = False, head: str = "",
           path: str = "") -> str:
    v = _vars()
    links = [("product", "/", "Product"), ("usecases", "/use-cases", "Use cases"), ("docs", "/docs", "Docs"), ("support", "/support", "Support"), ("partners", "/partners", "Partners")]
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
      <p class="muted">{html.escape(v['PRODUCT'])} is made by Kruse Consulting AB, Sweden{html.escape(v['ORGNR_SUFFIX'])}. Open source under the MIT licence.</p>
      <p class="muted tiny">Microsoft Fabric and Fabric IQ are trademarks of Microsoft Corporation. {html.escape(v['PRODUCT'])} is an independent product and is not affiliated with, endorsed by or certified by Microsoft.</p>
    </div>
    <nav class="footer-links" aria-label="Footer">
      <a href="/explore">Demo</a><a href="/use-cases">Use cases</a><a href="/start">Get started</a><a href="/docs">Docs</a><a href="/lovable">Use with Lovable</a><a href="/privacy">Privacy</a><a href="/support">Support</a><a href="/partners">Partners</a>
      <a href="{GITHUB}" rel="noopener">GitHub</a><a href="mailto:{html.escape(v['CONTACT'])}">{html.escape(v['CONTACT'])}</a>
    </nav>
    <div class="footer-controls">
      <button type="button" class="btn ghost small" data-mascot-toggle aria-pressed="true">Mascots: on</button>
      <span class="muted tiny" id="mascot-toggle-note">Turns the figures off on every page. Saved in this browser.</span>
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
    keys = "".join(f'<li><strong>{html.escape(t["name"])}</strong>: ' + (f'key <code>{html.escape(" + ".join(t["key"]))}</code> by rule <code>{t["key_rule"]}</code> ({rules[t["key_rule"]]})'
                   if t["key"] else f'no key, rule <code>K3</code> ({rules["K3"]})') + f'; columns {html.escape(", ".join(c["name"] for c in t["columns"]))}</li>'
                   for t in d["tables"])
    rels = "".join(f'<li><code>{html.escape(r["source"] + "." + "+".join(r["source_cols"]))}</code> → <code>{html.escape(r["target"] + "." + "+".join(r["target_cols"]))}</code> '
                   f'by rule <code>{r["rule"]}</code> ({rules[r["rule"]]}); GraphQL fields <code>{html.escape(r["field"])}</code> and <code>{html.escape(r["reverse"])}</code></li>'
                   for r in d["relationships"])
    unlinked = "".join(f'<li><code>{html.escape(u["table"] + "." + u["column"])}</code>: {html.escape(u["note"])}</li>' for u in d["unlinked"]) or "<li>none</li>"
    text = (f'<p class="mono">{"<br>".join(html.escape(line) for line in d["summary"].splitlines())}</p><h3>Tables and keys</h3><ul>{keys}</ul>'
            f'<h3>Relationships</h3><ul>{rels}</ul><h3>Left unlinked</h3><ul>{unlinked}</ul>')
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
            "DEMO_CHECK": check, "DEMO_CHECK_SUMMARY": e(v["summary"])}


def render(path: str) -> str:
    template, title, description, nav = PAGES[path]
    v = _vars()
    body = _read(template)
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


PRIVACY_DESC = "How {{PRODUCT}} handles sign-in, metadata, query results and logs. Nothing is stored; tokens live in memory only."
DOCS_DESC = "Connect {{PRODUCT}} to Claude, what it can access, the eleven tools with an example each, checking a plan against the data, Fabric IQ ontology drafts, Snowflake and Databricks via mirroring, and the two portal steps that stay manual."
LOVABLE_DESC = "Create an API for GraphQL item in Microsoft Fabric with {{PRODUCT}}, then connect Lovable's Fabric connector to it."


def privacy_md() -> str:
    md = _read("PRIVACY.md")
    return _fill(re.sub(r"^\*Template\..*?\*\n", "", md, flags=re.S | re.M), escape=False)   # drop the template note


def docs_md() -> str:
    return _fill(_read("DOCS.md").replace("{{RULES_TABLE}}", _rules_table()), escape=False)


def lovable_md() -> str:
    return _fill(_read("LOVABLE.md"), escape=False)


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
    """A small 'on this page' list built from the h2 ids, placed after the first paragraph."""
    heads = re.findall(r'<h2 id="([^"]+)">(.*?)</h2>', rendered)
    if len(heads) < 3:
        return rendered
    toc = '<nav class="toc" aria-label="On this page"><ul>' + "".join(f'<li><a href="#{i}">{re.sub(r"<[^>]+>", "", t)}</a></li>' for i, t in heads) + "</ul></nav>"
    return rendered.replace("</p>", "</p>" + toc, 1)


def docs_html() -> str:
    body = f'<article class="wrap prose docs">{_with_toc(_md_to_html(docs_md()))}</article>'
    return _shell("{{PRODUCT}} — docs", DOCS_DESC, body, page="docs", nav="docs", path="/docs")


def lovable_html() -> str:
    body = f'<article class="wrap prose docs">{_md_to_html(lovable_md())}</article>'
    return _shell("Use {{PRODUCT}} with Lovable", LOVABLE_DESC, body, page="lovable", nav="docs", path="/lovable")


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
    s = re.sub(r"<pre><code>(.*?)</code></pre>", lambda m: "\n\n```\n" + m.group(1).strip() + "\n```\n\n", s, flags=re.S)
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


def json_ld() -> str:
    """Structured data for the home page: the application and the company. Facts only; no ratings or numbers."""
    import json
    v = _vars()
    origin = site_url()
    data = [
        {"@context": "https://schema.org", "@type": "SoftwareApplication", "name": v["PRODUCT"],
         "applicationCategory": "DeveloperApplication", "operatingSystem": "Web", "url": origin + "/",
         "description": _fill(PAGES["/"][2], escape=False), "license": "https://opensource.org/licenses/MIT",
         "offers": {"@type": "Offer", "price": "0", "priceCurrency": "SEK", "description": "MIT open source"},
         "sameAs": [GITHUB], "publisher": {"@type": "Organization", "name": "Kruse Consulting AB", "url": origin + "/"}},
        {"@context": "https://schema.org", "@type": "Organization", "name": "Kruse Consulting AB", "url": origin + "/",
         "email": v["CONTACT"], "sameAs": [GITHUB]},
        {"@context": "https://schema.org", "@type": "WebSite", "name": v["PRODUCT"], "url": origin + "/",
         "publisher": {"@type": "Organization", "name": "Kruse Consulting AB"}, "inLanguage": "en"},
    ]
    safe = lambda d: json.dumps(d, ensure_ascii=False).replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")   # inert inside <script>
    return "".join('<script type="application/ld+json">' + safe(d) + "</script>" for d in data)

