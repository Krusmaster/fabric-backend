"""The public site — served by the MCP server itself, so one domain is enough.

    /                  start page           /explore            graph explorer (client-side demo, synthetic schema)
    /start             get started          /support            support
    /partners          partners             /partners/workspace illustrative partner workspace
    /docs              setup and usage      /privacy            privacy policy
    /mascots           mascot review page (noindex, unlinked)
    /static/...        css, js, fonts, icons (self-hosted; no external resources at runtime)
    /demo/plan.json    the real `plan()` on the synthetic shop schema

Filled from environment: PRODUCT_NAME, CONTACT_EMAIL, COMPANY_ORGNR (optional — the org. nr line is shown only when
set), MCP_PUBLIC_URL, ENTRA_CLIENT_ID, POLICY_DATE, PARTNER_SIGNIN (set to 1 to show the not-yet-wired
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
                ".png": "image/png", ".woff2": "font/woff2", ".txt": "text/plain; charset=utf-8",
                ".json": "application/json", ".ico": "image/x-icon", ".webmanifest": "application/manifest+json"}

PAGES = {
    # path: (template, title, description, nav key)
    "/": ("home.html", "{{PRODUCT}} — Microsoft Fabric, connected",
          "Turn your Microsoft Fabric tables into an explainable graph and a GraphQL API. Every connection shows the rule that made it.", "product"),
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
    "/mascots": ("mascots.html", "Mascot review — {{PRODUCT}}",
                 "Review page for the three mascots: every pose and demo state.", ""),
}


def _vars() -> dict[str, str]:
    url = os.environ.get("MCP_PUBLIC_URL", "https://example.com/mcp")
    domain = url.split("/")[2]
    product = os.environ.get("PRODUCT_NAME", "fabric-backend")
    orgnr = os.environ.get("COMPANY_ORGNR", "").strip()
    return {
        "PRODUCT": product, "PRODUCT_LOWER": product.lower(),
        "DOMAIN": domain,
        "CONTACT": os.environ.get("CONTACT_EMAIL", "contact@" + domain),
        "ORGNR": orgnr,
        "ORGNR_SUFFIX": (", org. nr " + orgnr) if orgnr else "",
        "ORGNR_PAREN": (" (org. nr " + orgnr + ")") if orgnr else "",
        "DATE": os.environ.get("POLICY_DATE", "2026-10-25"),
        "MCP_URL": url,
        "CLIENT_ID": os.environ.get("ENTRA_CLIENT_ID", "<client id>"),
        "GITHUB": GITHUB,
        "ASSET_V": asset_version(),
        "PARTNER_SIGNIN": "1" if os.environ.get("PARTNER_SIGNIN", "").strip() in {"1", "true", "yes"} else "",
    }


def _fill(text: str) -> str:
    v = _vars()
    return re.sub(r"\{\{(\w+)\}\}", lambda m: v.get(m.group(1), m.group(0)), text)


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
        s = re.sub(r"\[([^\]]+)\]\(((?:https?://|/|mailto:)[^)]+)\)", r'<a href="\2">\1</a>', s)
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
            t = "<div class=\"table-wrap\"><table><thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in rows[0]) + "</tr></thead><tbody>"
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
    for p in (HERE / "page_templates" / name, HERE.parent / "deploy" / name):
        if p.exists():
            return p.read_text(encoding="utf-8")
    return resources.files("fabric_backend").joinpath("page_templates", name).read_text(encoding="utf-8")


def static_file(path: str) -> Path | None:
    """Resolve a /static/<path> request to a file inside the package's static dir, or None."""
    if not path or path.startswith("/") or ".." in path.split("/"):
        return None
    p = (STATIC_DIR / path).resolve()
    try:
        p.relative_to(STATIC_DIR.resolve())
    except ValueError:
        return None
    return p if p.is_file() and p.suffix in STATIC_TYPES else None


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


def _shell(title: str, description: str, body: str, page: str, nav: str, noindex: bool = False, head: str = "") -> str:
    v = _vars()
    links = [("product", "/", "Product"), ("docs", "/docs", "Docs"), ("support", "/support", "Support"), ("partners", "/partners", "Partners")]
    nav_html = "".join(f'<a href="{href}"{" aria-current=page" if key == nav else ""}>{label}</a>' for key, href, label in links)
    robots = '<meta name="robots" content="noindex,nofollow">' if noindex else ""
    t, d = html.escape(_fill(title)), html.escape(_fill(description), quote=True)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{t}</title>
<meta name="description" content="{d}">
{robots}
<meta property="og:type" content="website">
<meta property="og:title" content="{t}">
<meta property="og:description" content="{d}">
<meta property="og:image" content="https://{v['DOMAIN']}/static/og.png">
<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
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
      <p class="muted tiny">Microsoft Fabric is a trademark of Microsoft Corporation. {html.escape(v['PRODUCT'])} is an independent product and is not affiliated with, endorsed by or certified by Microsoft.</p>
    </div>
    <nav class="footer-links" aria-label="Footer">
      <a href="/explore">Demo</a><a href="/start">Get started</a><a href="/docs">Docs</a><a href="/privacy">Privacy</a><a href="/support">Support</a><a href="/partners">Partners</a>
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
    items = "".join(f'<li><button type="button" data-table="{html.escape(t["name"])}"><span>{html.escape(t["name"])}</span>'
                    f'<span class="rule">{t["key_rule"] if t["key"] else "K3"}</span></button></li>' for t in d["tables"])
    return {"DEMO_TABLE_LIST": items, "DEMO_SUMMARY": html.escape(d["summary"].splitlines()[0])}


def render(path: str) -> str:
    template, title, description, nav = PAGES[path]
    v = _vars()
    body = _read(template)
    if "{{DEMO_" in body:
        dv = _demo_vars()
        body = re.sub(r"\{\{(DEMO_\w+)\}\}", lambda m: dv.get(m.group(1), ""), body)
    body = _fill(_conditional(body, v))
    return _shell(title, description, body, page=template.split(".")[0], nav=nav, noindex=(path == "/mascots"))


def privacy_html() -> str:
    md = _read("PRIVACY.md")
    md = re.sub(r"^\*Template\..*?\*\n", "", md, flags=re.S | re.M)       # drop the template note
    body = f'<article class="wrap prose">{_md_to_html(_fill(md))}</article>'
    return _shell("Privacy policy — {{PRODUCT}}", "How {{PRODUCT}} handles sign-in, metadata, query results and logs. Nothing is stored; tokens live in memory only.",
                  body, page="privacy", nav="")


def docs_html() -> str:
    body = f'<article class="wrap prose docs">{_md_to_html(_fill(_read("DOCS.md")))}</article>'
    return _shell("{{PRODUCT}} — docs", "Connect {{PRODUCT}} to Claude, what it can access, the six tools, how relationships are inferred and the two portal steps that stay manual.",
                  body, page="docs", nav="docs")


def landing_html() -> str:
    return render("/")
