"""The two public pages the Claude directory requires — served by the MCP server itself, so one domain is enough.

    /privacy   the privacy policy (fabric_backend/page_templates/PRIVACY.md, rendered)
    /docs      setup and usage: what it does, admin consent, the tools, the two manual portal steps

Filled from environment: PRODUCT_NAME, CONTACT_EMAIL, COMPANY_ORGNR, MCP_PUBLIC_URL, ENTRA_CLIENT_ID, POLICY_DATE.
"""
from __future__ import annotations

import html
import os
import re
from importlib import resources
from pathlib import Path


def _vars() -> dict[str, str]:
    url = os.environ.get("MCP_PUBLIC_URL", "https://example.com/mcp")
    domain = url.split("/")[2]
    return {
        "PRODUCT": os.environ.get("PRODUCT_NAME", "fabric-backend"),
        "DOMAIN": domain,
        "CONTACT": os.environ.get("CONTACT_EMAIL", "contact@" + domain),
        "ORGNR": os.environ.get("COMPANY_ORGNR", "—"),
        "DATE": os.environ.get("POLICY_DATE", "2026-10-22"),
        "MCP_URL": url,
        "CLIENT_ID": os.environ.get("ENTRA_CLIENT_ID", "<client id>"),
    } | {"PRODUCT_LOWER": os.environ.get("PRODUCT_NAME", "fabric-backend").lower(),
         "ORGNR_SUFFIX": (", org. nr " + os.environ["COMPANY_ORGNR"]) if os.environ.get("COMPANY_ORGNR") else ""}


def _fill(text: str) -> str:
    v = _vars()
    return re.sub(r"\{\{(\w+)\}\}", lambda m: v.get(m.group(1), m.group(0)), text)


def _md_to_html(md: str) -> str:
    """Just enough Markdown for these two pages: headings, paragraphs, bold/italic, code, links, lists, pipe tables."""
    def inline(s: str) -> str:
        s = html.escape(s, quote=False)
        s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
        s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", s)
        s = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<a href="\2">\1</a>', s)
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
            flush(); n = len(m.group(1)); out.append(f"<h{n}>{inline(m.group(2))}</h{n}>"); i += 1; continue
        if ln.startswith("|"):
            flush(); rows = []
            while i < len(lines) and lines[i].startswith("|"):
                if not re.match(r"^\|[\s\-|:]+\|$", lines[i]):
                    rows.append([c.strip() for c in lines[i].strip("|").split("|")])
                i += 1
            t = "<table><thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in rows[0]) + "</tr></thead><tbody>"
            t += "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in rows[1:]) + "</tbody></table>"
            out.append(t); continue
        if re.match(r"^(\d+\.|-) ", ln):
            flush(); tag = "ol" if ln[0].isdigit() else "ul"; items = []
            while i < len(lines) and re.match(r"^(\d+\.|-) ", lines[i]):
                items.append(re.sub(r"^(\d+\.|-) ", "", lines[i])); i += 1
                while i < len(lines) and lines[i].startswith("   ") and lines[i].strip():   # continuation line
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


_STYLE = """
:root{--bg:#fff;--fg:#1d1d1f;--muted:#6b7280;--line:#e5e7eb;--accent:#2563eb;--code:#f4f4f5}
@media (prefers-color-scheme:dark){:root{--bg:#121212;--fg:#ececec;--muted:#9ca3af;--line:#2a2a2a;--accent:#7aa2ff;--code:#1e1e1e}}
body{background:var(--bg);color:var(--fg);font:16px/1.6 -apple-system,Segoe UI,Inter,sans-serif;margin:0}
main{max-width:760px;margin:0 auto;padding:40px 16px 80px}
h1{font-size:28px;margin:0 0 8px}h2{font-size:20px;margin:32px 0 8px}h3{font-size:17px}
a{color:var(--accent);overflow-wrap:anywhere}code{background:var(--code);padding:1px 5px;border-radius:4px;font-size:14px}
pre{background:var(--code);padding:12px 14px;border-radius:8px;overflow-x:auto}pre code{padding:0;background:none}
table{border-collapse:collapse;width:100%;margin:12px 0;font-size:14px;display:block;overflow-x:auto}
th,td{border-bottom:1px solid var(--line);padding:8px 10px;text-align:left;vertical-align:top}
.btn{display:inline-block;background:var(--accent);color:#fff;padding:6px 12px;border-radius:6px;text-decoration:none}
footer{color:var(--muted);font-size:13px;margin-top:48px;border-top:1px solid var(--line);padding-top:12px}
"""


def _page(title: str, body_md: str) -> str:
    v = _vars()
    return (f"<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<title>{html.escape(title)}</title><style>{_STYLE}</style></head><body><main>{_md_to_html(_fill(body_md))}"
            f"<footer>{html.escape(v['PRODUCT'])} · Kruse Consulting AB · <a href='/docs'>Docs</a> · <a href='/privacy'>Privacy</a> · "
            f"<a href='mailto:{html.escape(v['CONTACT'])}'>{html.escape(v['CONTACT'])}</a></footer></main></body></html>")


def _read(name: str) -> str:
    here = Path(__file__).resolve().parent
    for p in (here / "page_templates" / name, here.parent / "deploy" / name):
        if p.exists():
            return p.read_text(encoding="utf-8")
    return resources.files("fabric_backend").joinpath("page_templates", name).read_text(encoding="utf-8")


def privacy_html() -> str:
    md = _read("PRIVACY.md")
    md = re.sub(r"^\*Template\..*?\*\n", "", md, flags=re.S | re.M)       # drop the template note
    return _page(f"Privacy policy — {_vars()['PRODUCT']}", md)


def docs_html() -> str:
    return _page(f"{_vars()['PRODUCT']} — docs", _read("DOCS.md"))


def landing_html() -> str:
    return _fill(_read("landing.html"))
