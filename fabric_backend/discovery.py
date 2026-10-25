"""Discovery documents for search engines and agents. All public, all derived from the same settings as the site.

    /robots.txt                     crawl rules + sitemap
    /sitemap.xml                    the public pages (not /mascots)
    /llms.txt                       llmstxt.org summary with links to the Markdown versions of the pages
    /mcp/server-card                MCP Server Card (SEP-2127), application/mcp-server-card+json
    /.well-known/ai-catalog.json    AI Catalog pointing at the Server Card, application/ai-catalog+json

The Server Card describes identity and transport only; tools are listed at runtime by the protocol itself.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

from .pages import GITHUB, _vars, site_url

SERVER_CARD_SCHEMA = "https://static.modelcontextprotocol.io/schemas/v1/server-card.schema.json"
SERVER_CARD_TYPE = "application/mcp-server-card+json"
AI_CATALOG_TYPE = "application/ai-catalog+json"
DESCRIPTION = "Turn Microsoft Fabric tables into an explainable graph and a GraphQL API."   # ≤ 100 characters

# The public pages, in sitemap order. /mascots is a review page and stays out (noindex, disallowed).
PUBLIC_PAGES = ["/", "/explore", "/start", "/docs", "/lovable", "/privacy", "/support", "/partners", "/partners/workspace"]


def package_version() -> str:
    try:
        from importlib.metadata import version
        return version("fabric-backend")
    except Exception:                                                    # running from a checkout without install
        t = (Path(__file__).resolve().parent.parent / "pyproject.toml")
        m = re.search(r'^version\s*=\s*"([^"]+)"', t.read_text(encoding="utf-8"), re.M) if t.exists() else None
        return m.group(1) if m else "0.0.0"


def server_name() -> str:
    """Reverse-DNS name, e.g. com.krusgraph/krusgraph — the same name server.json uses for the MCP Registry."""
    v = _vars()
    return ".".join(reversed(v["DOMAIN"].split("."))) + "/" + re.sub(r"[^a-z0-9._-]", "-", v["PRODUCT_LOWER"])


def protocol_versions() -> list[str]:
    """The MCP protocol versions the installed SDK accepts on the streamable-HTTP endpoint."""
    try:
        from mcp_types.version import HANDSHAKE_PROTOCOL_VERSIONS, MODERN_PROTOCOL_VERSIONS
        return sorted(set(HANDSHAKE_PROTOCOL_VERSIONS) | set(MODERN_PROTOCOL_VERSIONS))
    except Exception:
        try:
            from mcp.types import LATEST_PROTOCOL_VERSION
            return [LATEST_PROTOCOL_VERSION]
        except Exception:
            return []


def server_card() -> dict:
    v = _vars()
    remote = {"type": "streamable-http", "url": v["MCP_URL"]}
    pv = protocol_versions()
    if pv:
        remote["supportedProtocolVersions"] = pv
    return {
        "$schema": SERVER_CARD_SCHEMA,
        "name": server_name(),
        "version": package_version(),
        "title": v["PRODUCT"],
        "description": DESCRIPTION,
        "websiteUrl": site_url() + "/",
        "repository": {"url": GITHUB, "source": "github"},
        "icons": [{"src": site_url() + "/static/favicon.png", "mimeType": "image/png", "sizes": ["64x64"]},
                  {"src": site_url() + "/static/favicon.svg", "mimeType": "image/svg+xml", "sizes": ["any"]}],
        "remotes": [remote],
    }


def ai_catalog() -> dict:
    v = _vars()
    product = re.sub(r"[^a-z0-9._-]", "-", v["PRODUCT_LOWER"])
    return {"specVersion": "1.0", "entries": [{
        "identifier": f"urn:air:{v['DOMAIN']}:mcp:{product}",
        "type": SERVER_CARD_TYPE,
        "url": v["MCP_URL"].rstrip("/") + "/server-card",
    }]}


def etag(body: bytes) -> str:
    return '"' + hashlib.sha256(body).hexdigest()[:16] + '"'


def lastmod() -> str:
    return os.environ.get("SITE_LASTMOD", "2026-10-25")


def sitemap_xml() -> str:
    origin, d = site_url(), lastmod()
    urls = "".join(f"  <url><loc>{origin}{p}</loc><lastmod>{d}</lastmod></url>\n" for p in PUBLIC_PAGES)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{urls}</urlset>\n'


def robots_txt() -> str:
    return f"User-agent: *\nDisallow: /mascots\nDisallow: /mcp\nAllow: /mcp/server-card\n\nSitemap: {site_url()}/sitemap.xml\n"


def llms_txt() -> str:
    v, o = _vars(), site_url()
    p = v["PRODUCT"]
    return f"""# {p}

> {p} turns the tables in a Microsoft Fabric lakehouse, warehouse or SQL database into an explainable graph and an API for GraphQL item. It is a remote MCP server at {v['MCP_URL']}: you add it to Claude (or Claude Code, Cursor) as a custom connector and sign in with a Microsoft Entra work account, and every call runs with that account's own Fabric permissions.

It reads table and column names, infers keys and relationships from names (declared keys and foreign keys win), and shows the rule behind each one (K0–K3 for keys, R0–R3 for relationships). Ambiguous columns are reported, never guessed. Six tools: `list_sources`, `list_tables`, `plan_backend` (nothing is deployed), `create_backend` (creates or updates one API for GraphQL item; never deletes), `rayfin_connector` and `query_graphql` (read-only; mutations are refused). Two steps stay manual in the Fabric portal because Fabric has no API for them yet: turning on introspection on the GraphQL item, and granting permissions on it to other apps or service principals. The server stores nothing; tokens are held in memory only. Open source under the MIT licence, made by Kruse Consulting AB, Sweden.

## Docs

- [Docs]({o}/docs.md): connecting, what it accesses, the six tools, how relationships are inferred, the two manual steps
- [Get started]({o}/start.md): admin consent, choosing a workspace, adding the connector in Claude
- [Use with Lovable]({o}/lovable.md): create the API for GraphQL item with {p}, then connect Lovable's Fabric connector to it
- [Privacy policy]({o}/privacy.md): sign-in, the data path, logs, what is stored (nothing)

## Demo

- [Demo plan]({o}/demo/plan.json): the real planning engine's output on a synthetic shop schema (JSON, with a Mermaid ER diagram)

## Optional

- [MCP Server Card]({v['MCP_URL'].rstrip('/')}/server-card): name, version and transport for MCP clients
- [Source code]({GITHUB}): the engine, the inference rules and the server
"""


def card_json(doc: dict) -> bytes:
    return (json.dumps(doc, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
