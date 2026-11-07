"""What the hosted Entra app is granted, what each permission is used for, and what the service keeps of a sign-in:
one source for /start, /it, /privacy, llms.txt and docs/SCOPES.md (round n146, after the outside review of 7 November
2026 found the pages naming different permissions and different token lifetimes).

Read from the code, not typed per page:
  - the permissions are the ones `deploy/azure_containerapp.py` REQUIRED_SCOPES makes the deploy check demand
    (tests/test_n146_one_source.py keeps GRANTED equal to it); the server asks Microsoft for `<resource>/.default`
    (fabric_backend/entra.py FABRIC_SCOPE, SQL_SCOPE), so a token carries what the app registration has, nothing more;
  - which tool uses which permission comes from the Fabric REST operation each tool calls (docs/SCOPES.md, "What each
    tool needs", from the `Required Delegated Scopes` of microsoft/fabric-rest-api-specs, read 25 October 2026);
  - the token lifetimes are the constants in registration.py (TXN_TTL, CODE_TTL, FAMILY_TTL), registration_flow.py
    (REFRESH_OVERLAP), registration_store.py (PURGE_EVERY) and entra.py (an exchanged token is reused until 120 seconds
    before it expires).
"""
from __future__ import annotations

import html
from dataclasses import dataclass

# The date this table was last read against the code that requests the permissions.
AS_OF = "7 November 2026"
ADDED = "28 October 2026"          # Notebook.ReadWrite.All, DataPipeline.ReadWrite.All, Item.ReadWrite.All (docs/SCOPES.md)

GRAPH, FABRIC, SQL = "Microsoft Graph", "Fabric", "Azure SQL Database"
RESOURCE_IDS = {GRAPH: "00000003-0000-0000-c000-000000000000", FABRIC: "00000009-0000-0000-c000-000000000000",
                SQL: "022907d3-0f1b-48f7-badc-1ba6abab6d66"}


@dataclass(frozen=True)
class Grant:
    resource: str
    scope: str
    since: str          # "" = on the app before the three write permissions were added (ADDED; docs/SCOPES.md)
    tools: str          # which tools use it, and for what
    runs: str           # whether anything runs or is scheduled with it


GRANTED = (
    Grant(GRAPH, "User.Read", "", "sign-in only; nothing else is read from Microsoft Graph", "no"),
    Grant(FABRIC, "Workspace.Read.All", "", "`list_workspaces`, and finding a workspace by name for the tools that take a workspace",
          "no"),
    Grant(FABRIC, "Item.Read.All", "",
          "`list_sources` and item lookups; `lineage` with `runs` reads a pipeline's or notebook's latest runs", "no"),
    Grant(FABRIC, "GraphQLApi.ReadWrite.All", "",
          "`create_backend` creates or updates the one API for GraphQL item named in the call (never deletes); reading an "
          "existing API's definition (`describe_backend`, `plan_drift`, `app_starter`, `app_readiness`, `lineage`, "
          "`answer_query_draft` with `api`), for which Fabric has no read-only permission", "no"),
    Grant(FABRIC, "GraphQLApi.Execute.All", "",
          "`query_graphql` runs the read-only queries you ask for (mutations are refused); `app_readiness` sends one "
          "introspection query", "yes: the GraphQL queries you ask for, during the call; nothing is scheduled"),
    Grant(FABRIC, "Notebook.ReadWrite.All", ADDED,
          "`create_silver_notebook`, `create_gold_views`, `create_drift_monitor` and `create_pipeline` create or update "
          "notebook definitions, only with `dry_run=false`",
          "no: a notebook runs only when someone runs it in Fabric"),
    Grant(FABRIC, "DataPipeline.ReadWrite.All", ADDED,
          "`create_drift_monitor` and `create_pipeline` create or update a pipeline definition, only with `dry_run=false`; "
          "`lineage` with `runs` reads a pipeline's activities",
          "no: a pipeline runs only when someone runs or schedules it in Fabric; adding a schedule needs "
          "`DataPipeline.Execute.All`, which the app does not request, so `create_drift_monitor` needs `schedule=false`"),
    Grant(FABRIC, "Item.ReadWrite.All", ADDED,
          "`create_semantic_model`, `create_ontology` and `create_data_agent` create or update one item, `create_report` "
          "creates one report, only with `dry_run=false`; `compare_semantic_model` and `lineage` read semantic model "
          "definitions", "no: no model is refreshed and no item is run"),
    Grant(SQL, "user_impersonation", "",
          "reading table and column names from the SQL analytics endpoint; the counting queries of planning (rule R5) and of "
          "the checks (`validate_plan`, `suggest_relationships`, `data_dictionary` with `validate=true`); `sample_rows`; "
          "`create_views` creates a schema and views, only with `dry_run=false`",
          "yes: SQL queries during the call (counts, up to 20 sample rows, and with `create_views` CREATE SCHEMA and "
          "CREATE OR ALTER VIEW); nothing is scheduled"),
)

# Asked about, not requested (docs/SCOPES.md): what the app cannot do because of that.
NOT_REQUESTED = (
    ("DataPipeline.Execute.All", "Item.Execute.All", "running or scheduling pipelines and notebooks"),
    ("Workspace.ReadWrite.All", "", "changing workspaces"),
    ("SensitivityLabel.Read", "", "reading a sensitivity label's name from Microsoft Graph (the label's id comes with the item)"),
)


def scopes(resource: str | None = None) -> list[str]:
    return [g.scope for g in GRANTED if resource is None or g.resource == resource]


def _since(g: Grant) -> str:
    return f"since {g.since}" if g.since else f"before {ADDED}"


def _md(text: str) -> str:
    return text


def _html(text: str) -> str:
    out, parts = [], text.split("`")
    for i, part in enumerate(parts):
        out.append(f"<code>{html.escape(part)}</code>" if i % 2 else html.escape(part))
    return "".join(out)


def not_requested_sentence() -> str:
    return ("Not requested: " + "; ".join(
        (f"`{a}` or `{b}`" if b else f"`{a}`") + f" ({why})" for a, b, why in NOT_REQUESTED)
        + ". The app has no application permissions: every call runs as the signed-in person.")


def table_md() -> str:
    rows = [f"Delegated permissions of the hosted app, read from the code on {AS_OF}.", "",
            "| Permission | Granted | What the tools use it for | Runs or schedules anything? |", "| --- | --- | --- | --- |"]
    rows += [f"| `{g.scope}` ({g.resource}) | {_since(g)} | {g.tools} | {g.runs} |" for g in GRANTED]
    return "\n".join(rows) + "\n\n" + not_requested_sentence()


def table_html() -> str:
    rows = "".join(f"<tr><td><code>{g.scope}</code> ({g.resource})</td><td>{_since(g)}</td><td>{_html(g.tools)}</td>"
                   f"<td>{_html(g.runs)}</td></tr>" for g in GRANTED)
    return (f'<p class="muted tiny">Delegated permissions of the hosted app, read from the code on {AS_OF}.</p>'
            '<div class="table-wrap" tabindex="0"><table class="it-scopes"><thead><tr><th>Permission</th><th>Granted</th>'
            '<th>What the tools use it for</th><th>Runs or schedules anything?</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></div><p class="muted tiny">{_html(not_requested_sentence())}</p>')


def sentence() -> str:
    """The permissions in one sentence, for llms.txt and the docs' summaries."""
    by = {}
    for g in GRANTED:
        by.setdefault(g.resource, []).append(f"`{g.scope}`")
    listed = "; ".join(f"{r}: {', '.join(s)}" for r, s in by.items())
    return (f"The hosted Entra app has these delegated permissions ({AS_OF}): {listed}. The three write permissions "
            f"`Notebook.ReadWrite.All`, `DataPipeline.ReadWrite.All` and `Item.ReadWrite.All` were added on {ADDED}; the "
            "creating tools use them only on a call with `dry_run=false`. Nothing is run or scheduled with them: "
            "`DataPipeline.Execute.All` and `Item.Execute.All` are not requested.")


# ------------------------------------------------------------------ what is kept of a sign-in -------------------------

def _minutes(seconds: int) -> str:
    return f"{seconds // 60} minutes" if seconds % 60 == 0 and seconds >= 120 else f"{seconds} seconds"


def token_rows(registration_on: bool, where: str) -> list[tuple[str, str, str, str]]:
    """(client, what, where, how long) for every token the service holds, from the constants in the code."""
    from . import registration as reg
    from .registration_flow import REFRESH_OVERLAP
    from .registration_store import PURGE_EVERY
    rows = [
        ("Claude (/mcp)", "Your Microsoft access token, sent by Claude with each request", "memory, during the request",
         "not kept: validated and exchanged, then dropped with the request"),
        ("Claude (/mcp)", "The Fabric and SQL access tokens obtained for you (on-behalf-of)", "memory only; never disk or logs",
         "reused until 120 seconds before the expiry Microsoft gives them, then exchanged again; lost when the server restarts"),
        ("Claude (/mcp)", "Refresh tokens", "none: Claude renews its sign-in with Microsoft itself", "not held by the service"),
    ]
    if registration_on:
        days = reg.FAMILY_TTL // 86400
        rows += [
            ("Other MCP clients (/mcp/connect)", "A sign-in in progress (the client's request, no tokens)", where,
             f"{_minutes(reg.TXN_TTL)}, deleted when Microsoft sends the browser back"),
            ("Other MCP clients (/mcp/connect)", "Microsoft's access and refresh token of a finished sign-in, encrypted", where,
             f"{_minutes(reg.CODE_TTL)}, deleted when the client collects them"),
            ("Other MCP clients (/mcp/connect)", "Microsoft's refresh token, encrypted; never given to the client", where,
             f"as long as the client keeps renewing, at most {days} days from the first sign-in; deleted when an old "
             "refresh token comes back or Microsoft refuses a renewal"),
            ("Other MCP clients (/mcp/connect)", "The answer to the last renewal (a Microsoft access token and the next "
             "refresh token), encrypted", where,
             f"reused for at most {_minutes(REFRESH_OVERLAP)} to answer a client that asks again; after that it is never "
             f"opened, and it stays encrypted until the next renewal overwrites it or the sign-in ends (at most {days} days)"),
            ("Other MCP clients (/mcp/connect)", "The access token the client then sends with each request", "as for Claude",
             "as for Claude: exchanged in memory, never written"),
        ]
        rows.append(("Other MCP clients (/mcp/connect)", "Expired records", where,
                     "never handed out once expired; deleted by a sweep that runs at most once every "
                     f"{_minutes(PURGE_EVERY)} per server (Table Storage), or when the store grows large (memory)"))
    return rows


def tokens_md(registration_on: bool, where: str) -> str:
    rows = ["| Client | Token | Where | How long |", "| --- | --- | --- | --- |"]
    rows += [f"| {a} | {b} | {c} | {d} |" for a, b, c, d in token_rows(registration_on, where)]
    return "\n".join(rows)


def tokens_html(registration_on: bool, where: str) -> str:
    rows = "".join(f"<tr><td>{html.escape(a)}</td><td>{html.escape(b)}</td><td>{html.escape(c)}</td><td>{html.escape(d)}</td></tr>"
                   for a, b, c, d in token_rows(registration_on, where))
    return ('<div class="table-wrap" tabindex="0"><table class="it-tokens"><thead><tr><th>Client</th><th>Token</th>'
            f'<th>Where</th><th>How long</th></tr></thead><tbody>{rows}</tbody></table></div>')


# ------------------------------------------------------------------ where the tools' answers go -----------------------

def flows_md(product: str, domain: str) -> str:
    return (f"- **Hosted ({domain}):** Fabric → {product} on Azure, Sweden Central, in memory during the call → your MCP "
            "client → the client's AI provider (for Claude, Anthropic). The AI client receives the tools' answers: names, "
            "counts, the sample rows and query results you ask for.\n"
            f"- **Self-hosted (your Azure):** Fabric → {product} in your tenant and region → your MCP client → the client's AI "
            "provider. Nothing passes through Kruse Consulting, but the AI client still receives the same answers, under "
            "your organisation's agreement with that provider.")


def flows_html(product: str, domain: str) -> str:
    out = []
    for line in flows_md(product, domain).splitlines():
        text = line[2:]
        head, _, rest = text.partition(":** ")
        out.append(f"<li><strong>{html.escape(head.strip('*'))}:</strong> {html.escape(rest)}</li>")
    return '<ul class="data-flows">' + "".join(out) + "</ul>"


# ------------------------------------------------------------------ what planning reads, and what the checks cover -----

def planning_sentence(R5_SAMPLE: int, R5_MAX_QUERIES: int, VALIDATE_MAX_ITEMS: int) -> str:
    """Planning: metadata, and the bounded counting queries of rule R5 (server.py R5_SAMPLE, R5_MAX_QUERIES)."""
    return ("Planning reads schema metadata (workspace, item, table and column names and types) and may run bounded "
            "counting queries that return counts only: rule R5 checks the code and role columns the names left unlinked, "
            f"with at most {R5_MAX_QUERIES} counting queries per call, each over at most the first {R5_SAMPLE} distinct "
            "values of one column. No row values come back, and nothing from the counts is kept between calls.")


def checks_sentence(R5_SAMPLE: int, R5_MAX_QUERIES: int, VALIDATE_MAX_ITEMS: int) -> str:
    """What is checked against the rows, and what stays unchecked (server.py validate_plan's max_items, create_backend)."""
    return ("Every proposed key and relationship shows its basis: the rule or the source behind it. The checks you run show "
            "their results: `validate_plan` counts duplicate and empty key values and references with no matching row, "
            f"for up to {VALIDATE_MAX_ITEMS} keys and relationships per call by default (`max_items`, at most 200), and says "
            "when it checked fewer than the plan has. What stays unchecked: anything you have not run a check on (planning "
            "does not run `validate_plan`, and neither does `create_backend`); the keys and relationships past that cap; "
            "R5's proposals, which the rows did not support and which are never applied; and whether a relationship "
            "means what your business means, which is yours to decide.")


def inline_html(text: str) -> str:
    """A sentence with `code` spans, as HTML."""
    return _html(text)
