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
DESCRIPTION = "See how your business tables really connect, with the proof behind every link."   # ≤ 100 characters
# n39: the promise, the same on the home page, /docs, llms.txt and the README (tests/test_site.py keeps them in step)
USP = ("See how your business tables really connect – with the proof behind every link – so your reports, apps and agents "
       "get the numbers right.")
USP_POINTS = (
    "The proof: every key and link comes with the rule or source behind it, and is checked against your data.",
    "The errors before anyone sees them: the total that doubles, keys that are not unique, references with no matching row.",
    "SAP knowledge from public sources: keys with MANDT and the order-to-cash links for VBAK, VBAP and their neighbours, each with its source.",
    "One plan for what you build: the same reviewed plan drafts a GraphQL API, a Power BI model, a Fabric IQ ontology and a data agent.",
)

# The public pages, in sitemap order. /mascots is a review page and stays out (noindex, disallowed).
PUBLIC_PAGES = ["/", "/demo", "/check", "/explore", "/start", "/docs", "/lovable", "/local", "/use-cases", "/privacy", "/support", "/partners", "/partners/workspace"]


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
    rules = "User-agent: *\nDisallow: /mascots\nDisallow: /example/\nDisallow: /mcp\nAllow: /mcp/server-card\n"
    for bot in AI_CRAWLERS:
        rules += f"\nUser-agent: {bot}\nAllow: /\nDisallow: /mascots\nDisallow: /example/\nDisallow: /mcp\nAllow: /mcp/server-card\n"
    return rules + f"\nSitemap: {site_url()}/sitemap.xml\n"


def llms_full_txt(parts: list[tuple[str, str]]) -> str:
    """One document with every Markdown page, for agents that want the whole thing in one fetch."""
    o = site_url()
    out = [f"# {_vars()['PRODUCT']}: full documentation\n\nSame content as the pages linked from {o}/llms.txt, in one file.\n"]
    for path, md in parts:
        out.append(f"\n\n---\n\n<!-- {o}{path} -->\n\n{md.strip()}\n")
    return "".join(out)


def llms_txt() -> str:
    from . import tool_status as ts
    v, o = _vars(), site_url()
    p = v["PRODUCT"]
    if v["CLIENT_REGISTRATION"]:              # client registration on: VS Code, Cursor and others sign in at /mcp/connect
        clients_said = (f"The hosted service works with Claude at that address; at {v['CONNECT_URL']}, MCP clients that "
                        f"register themselves can sign in ({v['CONNECT_TESTED'][0].lower() + v['CONNECT_TESTED'][1:]}).")
        connect_lines = (
            f"- Claude Code: `claude mcp add --transport http {v['PRODUCT_LOWER']} {v['CONNECT_URL']}` (sign-in through client registration; not tried yet).\n"
            f"- VS Code, Cursor and other MCP clients that register themselves: streamable HTTP at `{v['CONNECT_URL']}`, OAuth discovery at "
            f"{o}/.well-known/oauth-protected-resource/mcp/connect: client ID metadata documents or dynamic registration, {p}'s own "
            f"approval page per client, then Microsoft sign-in. {v['CONNECT_TESTED']}. Set-up per client: {o}/docs.md#other-mcp-clients")
    else:
        clients_said = (f"The hosted service supports Claude, the client it has been tested with. Other MCP clients should work when "
                        f"you host {p} yourself (not tested yet).")
        connect_lines = (
            f"- Claude Code: `claude mcp add --transport http {v['PRODUCT_LOWER']} {v['MCP_URL']}` takes the same URL, but its local sign-in "
            f"redirect is not registered on the Entra app yet, so it cannot sign in to {v['DOMAIN']} today.\n"
            f"- Other MCP clients: streamable HTTP at `{v['MCP_URL']}`, OAuth discovery at {o}/.well-known/oauth-protected-resource. Only "
            f"Claude's sign-in redirect is registered on the hosted app, so Cursor and other local clients cannot sign in to it today. Other "
            f"MCP clients should work when you host {p} yourself (not tested yet).")
    usp = "\n".join("- " + x for x in USP_POINTS)
    return f"""# {p}

> {USP} {p} turns the tables in a Microsoft Fabric lakehouse, warehouse or SQL database into an explainable graph and an API for GraphQL item. It is a remote MCP server at {v['MCP_URL']}: you add it to Claude as a custom connector and sign in with a Microsoft Entra work account, and every call runs with that account's own Fabric permissions. {clients_said}

{usp}

It reads table and column names, infers keys and relationships from names (declared keys and foreign keys win), and shows the rule behind each one (K0–K5 for keys, R0–R4 for relationships). Ambiguous columns are reported, never guessed. Sources: lakehouses (tested end to end), and, experimental until a live run, warehouses, Fabric SQL databases, Snowflake database items, mirrored databases (Snowflake, Azure SQL, Cosmos DB, SAP), mirrored Azure Databricks catalogs and mirrored catalogs; Snowflake and Databricks schemas can also be planned where they are with the open-source library, CLI or local stdio server. Thirty-six tools: `list_workspaces`, `list_sources`, `list_tables`, `plan_backend` (nothing is deployed; also suggests composite keys), `sample_rows` (a few rows of one table), `validate_plan` (checks every key for uniqueness and NULLs and every relationship for orphans against the rows; returns counts), `create_backend` (creates or updates one API for GraphQL item; never deletes; no dry run, and it does not run `validate_plan`), `describe_backend` (types, fields and relationships of an existing API, read from its definition), `query_graphql` (read-only; mutations are refused), `rayfin_connector`, `ontology_draft` (the plan as a Fabric IQ ontology (preview) draft; nothing deployed); from the same plan without creating anything: `semantic_model_draft` (Power BI model in TMDL, Direct Lake), `join_path` (how two tables connect, with T-SQL), `data_dictionary` (hand-over Markdown), `dbt_schema` (dbt sources with tests), `plan_drift` (plan against an existing API), `analyze_schema` (table roles, central tables, subject areas, cycles) and `suggest_relationships` (missing links checked against the data); creating with a dry run first, all from the same plan: `create_semantic_model`, `create_ontology` (a Fabric IQ ontology item), `create_views` (wide T-SQL views in a schema of their own) and `create_data_agent`, of which only `create_views` can create with the permissions the hosted app has today; `app_starter` and `app_readiness` for an app on a created API; `lineage` for which APIs, semantic models, views and data agents build on a source's tables; from understanding to building: `silver_notebook_draft` and `create_silver_notebook` (a PySpark notebook that writes de-duplicated silver tables with every reference checked and a quarantine table, never over the source), `drift_monitor_draft` and `create_drift_monitor` (a nightly notebook and pipeline that compare the plan with the last one and message a webhook), and `answer_query_draft` (a question in Swedish or English as T-SQL over the safest join path, or as GraphQL for an existing API; `query_graphql` with `question` runs it); further down the lakehouse, `gold_views_draft` and `create_gold_views` (materialized lake views over the silver tables with the plan's keys and relationships as data quality rules); `compare_semantic_model` (an existing Power BI semantic model checked against the plan); `export_item_definitions` (what the creating tools would create, as files in Fabric's Git format for your own repository); and `review_plan` (the plan with your decisions and its checks as a file for your own repository; passed back later, it applies the decisions again and marks checks on changed tables stale). For SAP tables (VBAK, VBAP, LIKP, VBRK… with or without a prefix), keys with MANDT and the order-to-cash relationships come from the SAP pack, each with its public source (rule "SAP pack"), and `sap_pack_draft` shows what the pack recognises and what is missing, with exports for Data API builder, dbt and extraction tools. Columns that look like personal data by name are masked in sample rows and left out of drafted queries unless asked for. It is meant to sit beside Microsoft's own Fabric MCP servers, which manage workspaces and items and query models; it is not affiliated with Microsoft. Test status: on {ts.LIVE_RUN_DATE}, {len(ts.LIVE_RUN)} tools were run from Claude against a Fabric workspace with synthetic data, read-only, as drafts or as dry runs, and one creating call that updated an existing API in place: {ts.live_run_list()}; the rest ({ts.not_run_list()}), and creating a new item with any tool, is unit-tested. Creating semantic models, ontologies, data agents, notebooks and pipelines needs permissions the hosted app does not ask for today (available when enabled by the operator); their dry runs work. The status per tool is in the docs. Two steps stay manual in the Fabric portal because Fabric has no API for them yet: turning on introspection on the GraphQL item, and granting permissions on it to other apps or service principals. Metadata, the sample rows and query results you ask for pass through the server and are not kept after the request; tokens are held in memory only; each tool call leaves an anonymous usage record, and the privacy policy describes the technical logs. Published in the official MCP Registry as com.krusgraph/krusgraph (https://registry.modelcontextprotocol.io/v0.1/servers?search=com.krusgraph%2Fkrusgraph; verified 26 October 2026). Open source under the MIT licence, made by Kruse Consulting AB.

## Docs

- [Docs]({o}/docs.md): connecting, what it reads and passes through, reviewing and checking a plan, the thirty-six tools with what each changes and its test status, {p} beside Microsoft's Fabric MCP servers, how relationships are inferred, Fabric IQ ontology drafts, sources, cold start, the two manual steps
- [Get started]({o}/start.md): admin consent, choosing a workspace, adding the connector in Claude
- [Use with Lovable]({o}/lovable.md): create the API for GraphQL item with {p}, then connect Lovable's Fabric connector to it
- [Run it locally]({o}/local.md): the same engine on your own machine over ODBC (SQL Server with Windows sign-in, or a Fabric SQL endpoint), and exactly what leaves the machine
- [Use cases]({o}/use-cases.md): three tasks to start from (an undocumented lakehouse, a join to check, an app to build), then ten illustrative schemas from different industries (retail, manufacturing, SaaS, professional services, AML, financial crime prevention, pharmaceutical research, environment and sustainability, property, education): typical tables, the keys and links found in them with their rules, what you build
- [Privacy policy]({o}/privacy.md): sign-in, metadata, sample rows and query results, access tokens, usage records and technical logs

## Connect

- Claude (web, desktop, mobile): Settings → Connectors → Add custom connector → URL `{v['MCP_URL']}` → sign in with a Microsoft work account. An Entra admin of the organisation grants consent once: {o}/docs.md#connect
{connect_lines}
- First calls: `list_workspaces`, then `list_sources` with the workspace name, `plan_backend` (nothing is deployed), `validate_plan` to check the plan against the rows (a step to ask for; `create_backend` does not run it), `create_backend`, then `describe_backend` before `query_graphql`.

## Demo

- [Guided demo]({o}/demo): one order followed to its delivery address in four steps, on the synthetic shop schema: what the engine suggests (`suggest_relationships` for `orders.ship_to_id`), what the data check shows, the visitor's decision and a summary of the result; nothing is changed in Fabric
- [Check your files]({o}/check): drop CSV or Excel exports, or paste a list of columns, and see the map of the tables (keys and relationships with their rules) and what is wrong or unclear; the same engine runs in the browser (Pyodide), and the files are read there and never uploaded; the page sends only two anonymous events (the engine has loaded, a check is done), with no file contents, file names or table names
- [Demo graph]({o}/explore): every table and relationship of the same schema, with the rule behind each one and the checks on its rows
- [Demo plan]({o}/demo/plan.json): the real planning engine's output on a synthetic shop schema (JSON, with a Mermaid ER diagram)
- [Demo validation]({o}/demo/validation.json): what validate_plan answers for that plan, computed on the synthetic rows

## Optional

- [Full documentation in one file]({o}/llms-full.txt): every page above, concatenated
- [MCP Server Card]({v['MCP_URL'].rstrip('/')}/server-card): name, version and transport for MCP clients
- [Source code]({GITHUB}): the engine, the inference rules and the server
"""


# Glama (glama.ai/mcp/connectors/com.krusgraph/krusgraph) lists the server and asks its owner to confirm the listing with
# this file at the domain. The claim is the maintainer's and is made to be public; it is served only when the public host
# (MCP_PUBLIC_URL) is krusgraph.com, so a self-hosted copy never claims the listing of someone else's domain.
GLAMA_HOST = "krusgraph.com"
GLAMA_CLAIM = {"$schema": "https://glama.ai/mcp/schemas/connector.json", "claim": "glama_claim_nlxchmx_fb4bANK8J8zGgfTdUrOH6Wq1"}


def glama_json() -> bytes | None:
    """The body of /.well-known/glama.json, or None (a 404) when the public host is not GLAMA_HOST or MCP_PUBLIC_URL is unset."""
    from urllib.parse import urlsplit
    host = (urlsplit(os.environ.get("MCP_PUBLIC_URL", "").strip()).hostname or "").lower()
    return json.dumps(GLAMA_CLAIM).encode("utf-8") if host == GLAMA_HOST else None


def card_json(doc: dict) -> bytes:
    return (json.dumps(doc, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
