"""Discovery documents for search engines and agents. All public, all derived from the same settings as the site.

    /robots.txt                     crawl rules + sitemap (AI crawlers spelled out)
    /llms-full.txt                  every Markdown page in one file
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

from .pages import GITHUB, _vars, site_url

SERVER_CARD_SCHEMA = "https://static.modelcontextprotocol.io/schemas/v1/server-card.schema.json"
SERVER_CARD_TYPE = "application/mcp-server-card+json"
AI_CATALOG_TYPE = "application/ai-catalog+json"
DESCRIPTION = "Turn Microsoft Fabric tables into an explainable graph and a GraphQL API."   # ≤ 100 characters

# The public pages, in sitemap order. /mascots is a review page and stays out (noindex, disallowed).
PUBLIC_PAGES = ["/", "/explore", "/start", "/docs", "/lovable", "/local", "/use-cases", "/privacy", "/support", "/partners", "/partners/workspace"]


def package_version() -> str:
    """The package's own version (fabric_backend.__version__, kept equal to pyproject.toml by the tests)."""
    from . import __version__
    return __version__


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
                  {"src": site_url() + "/static/favicon.svg", "mimeType": "image/svg+xml", "sizes": ["any"]},
                  {"src": site_url() + "/static/icon-512.png", "mimeType": "image/png", "sizes": ["512x512"]}],
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


AI_CRAWLERS = ("GPTBot", "OAI-SearchBot", "ChatGPT-User", "ClaudeBot", "Claude-SearchBot", "Claude-User", "PerplexityBot",
               "Google-Extended", "Applebot-Extended", "Bingbot", "DuckAssistBot", "CCBot")


def robots_txt() -> str:
    """Everyone may read the site, AI crawlers and answer engines spelled out so the policy is explicit; the mascot review
    page and the MCP endpoint itself stay out (the server card is the machine-readable entry)."""
    rules = "User-agent: *\nDisallow: /mascots\nDisallow: /mcp\nAllow: /mcp/server-card\n"
    for bot in AI_CRAWLERS:
        rules += f"\nUser-agent: {bot}\nAllow: /\nDisallow: /mascots\nDisallow: /mcp\nAllow: /mcp/server-card\n"
    return rules + f"\nSitemap: {site_url()}/sitemap.xml\n"


def llms_full_txt(parts: list[tuple[str, str]]) -> str:
    """One document with every Markdown page, for agents that want the whole thing in one fetch."""
    o = site_url()
    out = [f"# {_vars()['PRODUCT']}: full documentation\n\nSame content as the pages linked from {o}/llms.txt, in one file.\n"]
    for path, md in parts:
        out.append(f"\n\n---\n\n<!-- {o}{path} -->\n\n{md.strip()}\n")
    return "".join(out)


def llms_txt() -> str:
    v, o = _vars(), site_url()
    p = v["PRODUCT"]
    return f"""# {p}

> {p} turns the tables in a Microsoft Fabric lakehouse, warehouse or SQL database into an explainable graph and an API for GraphQL item. It is a remote MCP server at {v['MCP_URL']}: you add it to Claude as a custom connector and sign in with a Microsoft Entra work account, and every call runs with that account's own Fabric permissions. Claude is the client it is built and documented for; other MCP clients take the same URL once their sign-in redirect is registered on the Entra app.

It reads table and column names, infers keys and relationships from names (declared keys and foreign keys win), and shows the rule behind each one (K0–K5 for keys, R0–R4 for relationships). Ambiguous columns are reported, never guessed. Sources: lakehouses, warehouses, Fabric SQL databases, Snowflake database items, mirrored databases (Snowflake, Azure SQL, Cosmos DB, SAP), mirrored Azure Databricks catalogs and mirrored catalogs; Snowflake and Databricks schemas can also be planned where they are with the open-source library, CLI or local stdio server. Twenty-four tools: `list_workspaces`, `list_sources`, `list_tables`, `plan_backend` (nothing is deployed; also suggests composite keys), `sample_rows` (a few rows of one table), `validate_plan` (checks every key for uniqueness and NULLs and every relationship for orphans against the rows), `create_backend` (creates or updates one API for GraphQL item; never deletes), `describe_backend` (types, fields and relationships of an existing API, read from its definition), `query_graphql` (read-only; mutations are refused), `rayfin_connector`, `ontology_draft` (the plan as a Fabric IQ ontology (preview) draft; nothing deployed); from the same plan without creating anything: `semantic_model_draft` (Power BI model in TMDL, Direct Lake), `join_path` (how two tables connect, with T-SQL), `data_dictionary` (hand-over Markdown), `dbt_schema` (dbt sources with tests), `plan_drift` (plan against an existing API), `analyze_schema` (table roles, central tables, subject areas, cycles) and `suggest_relationships` (missing links checked against the data); creating with a dry run first: `create_semantic_model`, `create_views` (wide T-SQL views in a schema of their own) and `create_data_agent`; `app_starter` and `app_readiness` for an app on a created API; `lineage` for which APIs, semantic models, views and data agents build on a source's tables. Run end to end against a live Fabric workspace with synthetic data on 25 October 2026; the consultant, graph and dry-run tools answered from the same workspace on 26 October 2026 (nothing created by them yet). Two steps stay manual in the Fabric portal because Fabric has no API for them yet: turning on introspection on the GraphQL item, and granting permissions on it to other apps or service principals. The server stores nothing; tokens are held in memory only. Listed in the official MCP Registry as com.krusgraph/krusgraph (https://registry.modelcontextprotocol.io/v0.1/servers?search=com.krusgraph%2Fkrusgraph; verified 26 October 2026). Open source under the MIT licence, made by Kruse Consulting AB, Sweden.

## Docs

- [Docs]({o}/docs.md): connecting, what it accesses, the twenty-four tools with an example each, how relationships are inferred, checking a plan against the data, cold start, Fabric IQ ontology drafts, Snowflake and Databricks, the two manual steps
- [Get started]({o}/start.md): admin consent, choosing a workspace, adding the connector in Claude
- [Use with Lovable]({o}/lovable.md): create the API for GraphQL item with {p}, then connect Lovable's Fabric connector to it
- [Run it locally]({o}/local.md): the same engine on your own machine over ODBC (SQL Server with Windows sign-in, or a Fabric SQL endpoint); data stays with you
- [Use cases]({o}/use-cases.md): ten industries (retail, manufacturing, SaaS, professional services, AML, financial crime prevention, pharmaceutical research, environment and sustainability, property, education): typical tables, the keys and links found in them with their rules, what you build
- [Privacy policy]({o}/privacy.md): sign-in, the data path, logs, what is stored (nothing)

## Connect

- Claude (web, desktop, mobile): Settings → Connectors → Add custom connector → URL `{v['MCP_URL']}` → sign in with a Microsoft work account. An Entra admin of the organisation grants consent once: {o}/docs.md#connect
- Claude Code: `claude mcp add --transport http {v['PRODUCT_LOWER']} {v['MCP_URL']}` — same URL; its local sign-in redirect is not registered on the Entra app yet, so until it is, Claude is the tested client.
- Cursor and other MCP clients: streamable HTTP at `{v['MCP_URL']}`, OAuth discovery at {o}/.well-known/oauth-protected-resource; same redirect caveat.
- First calls: `list_workspaces`, then `list_sources` with the workspace name, `plan_backend` (nothing is deployed), `validate_plan` to check the plan against the rows, `create_backend`, then `describe_backend` before `query_graphql`.

## Demo

- [Demo plan]({o}/demo/plan.json): the real planning engine's output on a synthetic shop schema (JSON, with a Mermaid ER diagram)
- [Demo validation]({o}/demo/validation.json): what validate_plan answers for that plan, computed on the synthetic rows

## Optional

- [Full documentation in one file]({o}/llms-full.txt): every page above, concatenated
- [MCP Server Card]({v['MCP_URL'].rstrip('/')}/server-card): name, version and transport for MCP clients
- [Source code]({GITHUB}): the engine, the inference rules and the server
"""


def card_json(doc: dict) -> bytes:
    return (json.dumps(doc, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
