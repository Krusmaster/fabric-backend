"""Each hosted tool's status as data, so one tool cannot carry two statuses on two pages (the website brief of
26 October 2026, /docs: "a shared status source with separate fields for availability, what the tool changes, test
level and latest verification").

`label()` turns the fields into the site's status words (Tested end to end, Experimental, Draft only, Available when
enabled by the operator, Planned); the docs' tool table, its test status list, llms.txt, the use-case tasks, the
home page's test line, the start page's hub (`SOURCES`, `BUILDS`, `build_word()`, `clients_working()`), the server's
instructions and the notes in the tools' own answers (`answer_note()`) render from here. "Draft only" says what a tool changes (nothing), "Tested end to end" how far it has been run: a draft that
ran live is "Tested end to end (a draft; creates nothing)", and a creating tool whose dry run ran live says "tested end
to end as a dry run" while creating keeps its status.
"""
from __future__ import annotations

from dataclasses import dataclass

HOSTED, OPERATOR = "hosted", "operator"          # operator: needs a permission the hosted app does not ask for today
READS, DRAFT, CREATES = "reads", "draft", "creates"

# The run that counts as tested end to end: from Claude through the hosted connector and Microsoft sign-in, against
# the demo workspace (a Fabric workspace with synthetic data: demo / demo_lh / shop), read-only, as drafts or as dry
# runs, and then, with the maintainer's approval, one creating call: create_backend updated shop_api in place (docs,
# Test status; the checklist is docs/LIVE-TEST.md).
LIVE_RUN_DATE = "27 October 2026"
LIVE_RUN_BUILD = "src-df29c45febaec4b0 (main 5adace8)"
# the tools of that run: read, then drafted, then the dry runs
LIVE_RUN = ("list_workspaces", "list_sources", "list_tables", "sample_rows", "plan_backend", "validate_plan",
            "suggest_relationships", "analyze_schema", "join_path", "describe_backend", "query_graphql", "answer_query_draft",
            "app_readiness", "app_starter", "plan_drift", "lineage", "review_plan", "compare_semantic_model",
            "dbt_schema", "data_dictionary", "semantic_model_draft", "ontology_draft", "rayfin_connector", "silver_notebook_draft",
            "gold_views_draft", "drift_monitor_draft", "export_item_definitions",
            "create_views", "create_semantic_model", "create_data_agent", "create_backend")
# a tool that ran only part of the way, with how far
LIVE_RUN_PARTLY = {"compare_semantic_model": "as far as the model lookup, which answered not_found: the demo workspace has no model",
                   "create_backend": "as an update in place of shop_api with confirmed; no new item was created"}
# The first such run, kept for the record: 14 steps, 16 tools, no creating call.
FIRST_RUN_DATE, FIRST_RUN_STEPS = "26 October 2026", 14
FIRST_RUN = ("list_workspaces", "list_sources", "sample_rows", "plan_backend", "validate_plan", "suggest_relationships",
             "analyze_schema", "join_path", "describe_backend", "query_graphql", "semantic_model_draft", "data_dictionary",
             "dbt_schema", "create_views", "plan_drift", "app_starter")
# What a sentence about the run says it covered (the home page's test line).
LIVE_RUN_SUMMARY = ("from Claude to a Fabric workspace with synthetic data: sign-in, plan, check, query, the drafts, three dry "
                    "runs and an update in place of an existing API; no new item was created")


@dataclass(frozen=True)
class ToolStatus:
    available: str             # HOSTED or OPERATOR
    kind: str                  # READS, DRAFT or CREATES
    changes: str               # what it changes in Fabric, in plain words
    tested: str                # how it is tested beyond the live run
    dry_run_only: bool = False  # in the live run, only as a dry run
    note: str = ""             # a qualifier after the status word, with its leading punctuation
    name: str = ""

    @property
    def live(self) -> bool:
        """Ran in the live run of LIVE_RUN_DATE (for a creating tool: its dry run)."""
        return self.name in LIVE_RUN


_NO = "nothing"
_ITEM = "creates/updates one item; never deletes"
_RAW = {
    "list_workspaces": (HOSTED, READS, _NO, "unit tests"),
    "list_sources": (HOSTED, READS, _NO, "unit tests"),
    "list_tables": (HOSTED, READS, _NO, "unit tests"),
    "plan_backend": (HOSTED, READS, _NO, "unit tests"),
    "validate_plan": (HOSTED, READS, "nothing (counting queries)", "unit tests"),
    "sample_rows": (HOSTED, READS, _NO, "unit tests; the masking live since 27 October 2026"),
    "create_backend": (HOSTED, CREATES, _ITEM, "unit tests; live as an update in place, a new item by unit tests only", False,
                       " (27 October 2026: update in place of shop_api with confirmed)"),
    "describe_backend": (HOSTED, READS, _NO, "unit tests"),
    "query_graphql": (HOSTED, READS, _NO, "unit tests; with `question` live since 27 October 2026"),
    "rayfin_connector": (HOSTED, DRAFT, _NO, "unit tests"),
    "ontology_draft": (HOSTED, DRAFT, _NO, "unit tests"),
    "semantic_model_draft": (HOSTED, DRAFT, _NO, "unit tests"),
    "join_path": (HOSTED, READS, _NO, "unit tests"),
    "data_dictionary": (HOSTED, DRAFT, _NO, "unit tests"),
    "dbt_schema": (HOSTED, DRAFT, _NO, "unit tests"),
    "sap_pack_draft": (HOSTED, DRAFT, _NO, "unit tests (synthetic SAP schema; no SAP system)"),
    "plan_drift": (HOSTED, READS, _NO, "unit tests"),
    "create_semantic_model": (OPERATOR, CREATES, _ITEM, "unit tests; creating by unit tests only", True),
    "create_views": (HOSTED, CREATES, "creates/alters views in that schema only; never drops",
                     "unit tests; creating by unit tests only", True, "; creating them: Experimental"),
    "create_data_agent": (OPERATOR, CREATES, "creates/updates one item and its staging config; never deletes",
                          "unit tests; creating by unit tests only", True),
    "create_ontology": (OPERATOR, CREATES, _ITEM, "unit tests", False, "; unit-tested, not yet run live"),
    "app_starter": (HOSTED, DRAFT, _NO, "unit tests"),
    "app_readiness": (HOSTED, READS, "nothing (one introspection query)", "unit tests"),
    "analyze_schema": (HOSTED, READS, _NO, "unit tests"),
    "lineage": (HOSTED, READS, _NO, "unit tests"),
    "silver_notebook_draft": (HOSTED, DRAFT, _NO, "unit tests and a local PySpark 4.0.1", False,
                              "; the notebook ran on a local PySpark 4.0.1, not yet in Fabric"),
    "create_silver_notebook": (OPERATOR, CREATES, _ITEM, "unit tests", False, "; unit-tested"),
    "drift_monitor_draft": (HOSTED, DRAFT, _NO, "unit tests; the notebook ran two nights on a local PySpark", False,
                            "; the notebook ran two nights on a local PySpark, not yet in Fabric"),
    "create_drift_monitor": (OPERATOR, CREATES, "creates/updates two items and a schedule; never deletes", "unit tests", False,
                             "; unit-tested"),
    "answer_query_draft": (HOSTED, DRAFT, _NO, "unit tests on the shop schema"),
    "suggest_relationships": (HOSTED, READS, "nothing (counting queries)", "unit tests"),
    "compare_semantic_model": (OPERATOR, READS, _NO, "unit tests; live only as far as the model lookup", False,
                               "; with `tmdl`: Experimental; live on 27 October 2026 only as far as the model lookup (no model in the demo workspace)"),
    "gold_views_draft": (HOSTED, DRAFT, _NO, "unit tests; the SQL on SQLite and a local PySpark 4.0.1", False,
                         "; the SQL ran on SQLite and a local PySpark 4.0.1, not yet in Fabric"),
    "create_gold_views": (OPERATOR, CREATES, "creates/updates one notebook; never deletes", "unit tests", False, "; unit-tested"),
    "export_item_definitions": (HOSTED, DRAFT, _NO, "unit tests"),
    "review_plan": (HOSTED, READS, "nothing (counting queries with validate=true)", "unit tests; reading a file back by unit tests only",
                    False, "; reading a file back is unit-tested"),
}
STATUS: dict[str, ToolStatus] = {name: ToolStatus(*v, name=name) for name, v in _RAW.items()}


DRY_RUN = "tested end to end as a dry run"


def word(name: str) -> str:
    """The status word with its fixed qualifier: availability first, then whether it ran live, then what it changes."""
    s = STATUS[name]
    if s.available == OPERATOR:
        return "Available when enabled by the operator" + (f"; {DRY_RUN}" if s.live and s.dry_run_only else "")
    if s.live:
        if s.dry_run_only:
            return DRY_RUN[0].upper() + DRY_RUN[1:]
        return "Tested end to end (a draft; creates nothing)" if s.kind == DRAFT else "Tested end to end"
    return "Draft only" if s.kind == DRAFT else "Experimental"


def label(name: str) -> str:
    return word(name) + STATUS[name].note


WORDS = ("Tested end to end", "Experimental", "Draft only", "Available when enabled by the operator", "Planned")


def phrase(name: str) -> str:
    """The label inside a sentence: the status words in lower case."""
    text = label(name)
    for w in WORDS:
        text = text.replace(w, w[0].lower() + w[1:])
    return text


def _listed(names) -> str:
    names = list(names)
    return ", ".join(names[:-1]) + " and " + names[-1] if len(names) > 1 else "".join(names)


def live_run_list() -> str:
    """The live run's tools as the docs list them: in run order, the dry runs and partial runs marked."""
    def one(t: str) -> str:
        if STATUS[t].dry_run_only:
            return f"`{t}` (dry run only; nothing was created)"
        return f"`{t}` ({LIVE_RUN_PARTLY[t]})" if t in LIVE_RUN_PARTLY else f"`{t}`"
    return _listed(one(t) for t in LIVE_RUN)


def not_run_list() -> str:
    """The hosted tools that did not run in the live run, not even as a dry run."""
    return _listed(f"`{t}`" for t in STATUS if not STATUS[t].live)


def answer_note(name: str) -> str:
    """One sentence for a tool's own answer: how far it has run against a live workspace, from the same fields."""
    s, where = STATUS[name], "against a Fabric workspace with synthetic data"
    if not s.live:
        return "Not yet run against a live workspace."
    if name in LIVE_RUN_PARTLY:
        return f"Run live on {LIVE_RUN_DATE} {where} only {LIVE_RUN_PARTLY[name]}; the rest is unit-tested."
    if s.dry_run_only:
        return f"The dry run was tested end to end on {LIVE_RUN_DATE} {where}; creating has not run against a live workspace."
    if s.kind == DRAFT:
        return f"Tested end to end on {LIVE_RUN_DATE} {where} as a draft; it creates nothing."
    return f"Tested end to end on {LIVE_RUN_DATE} {where}."


def instructions_sentence() -> str:
    """The test status in the server's instructions."""
    creating = [t for t in STATUS if STATUS[t].kind == CREATES]
    dry = [t for t in creating if STATUS[t].live and STATUS[t].dry_run_only]
    partly = "; ".join(f"{t} only {why.split(',')[0].split(';')[0]}" for t, why in LIVE_RUN_PARTLY.items())
    return (f"Test status: on {LIVE_RUN_DATE} every tool but {not_run_list().replace('`', '')} ran from Claude against a Fabric workspace "
            f"with synthetic data, read-only or as a draft, and {_listed(dry)} as dry runs" + (f" ({partly})" if partly else "")
            + "; no new item was created, so creating a new one is unit-tested only (status per tool: /docs#test-status).")


def create_api_status() -> str:
    """create_backend in a sentence for the pages that offer creating the API: what ran live and what did not."""
    s = STATUS["create_backend"]
    if s.live and "create_backend" in LIVE_RUN_PARTLY:
        return f"Creating a new API is experimental; updating one in place was tested end to end on {LIVE_RUN_DATE}"
    return "Creating the API is " + phrase("create_backend")


def task_status(tools: list[str]) -> str:
    """One line for a group of tools: the live date when all ran live, otherwise each tool with its word."""
    if all(STATUS[t].live and not STATUS[t].dry_run_only and not STATUS[t].note.startswith(";") for t in tools):
        return f"tested end to end on {LIVE_RUN_DATE}"
    return "; ".join(f"`{t}`: {phrase(t)}" for t in tools)


# ------------------------------------------------------------------ the start page's hub --------------------------------
# Gustav's brief of 27 October 2026: what Krusgraph reads in Fabric, what it builds there from one plan, and where people
# build, each part with its status from the fields above, so the hub follows when another part is tested live.

# Sources, by whether one has been read end to end on the hosted service (the docs' Sources section says the same).
SOURCES = (("Lakehouse", True), ("Warehouse", False), ("SQL database", False))

# What is built in Fabric, by the creating tool that builds it.
BUILDS = (("GraphQL API", "create_backend"), ("Power BI semantic model", "create_semantic_model"),
          ("Fabric IQ ontology", "create_ontology"), ("views", "create_views"), ("data agent", "create_data_agent"),
          ("silver notebooks", "create_silver_notebook"))

# The clients, one row each (Gustav's brief of 28 October 2026): where each one reaches Krusgraph and its status word.
# Client registration at /mcp/connect is switched on at krusgraph.com since 27 October 2026; VS Code and Glama reached
# the approval page there, but a full sign-in is not yet confirmed, so those clients are Experimental. A client is named
# as working (the hub, the docs' sentence) only when its status here is Tested end to end.
@dataclass(frozen=True)
class ClientStatus:
    name: str
    where: str                 # how it connects, in words
    path: str                  # /mcp, /mcp/connect, or "" for a client that does not use MCP
    status: str                # one of WORDS
    since: str = ""            # the date behind a Tested end to end
    note: str = ""


CONNECT_NOTE = ("client registration is switched on at krusgraph.com since 27 October 2026; VS Code and Glama reached the "
                "approval page, a full sign-in is not yet confirmed")
CLIENTS = (
    ClientStatus("Claude", "hosted, via /mcp (the connector)", "/mcp", "Tested end to end", "26 October 2026",
                 "the live runs of 26 and 27 October 2026"),
    ClientStatus("VS Code", "hosted, via /mcp/connect", "/mcp/connect", "Experimental", note=CONNECT_NOTE),
    ClientStatus("Claude Code", "hosted, via /mcp/connect", "/mcp/connect", "Experimental", note=CONNECT_NOTE),
    ClientStatus("Cursor", "hosted, via /mcp/connect", "/mcp/connect", "Experimental", note=CONNECT_NOTE),
    ClientStatus("Lovable", "via the GraphQL API that create_backend makes (not an MCP client of Krusgraph)", "", "Experimental",
                 note="Lovable's own Microsoft Fabric connector reads the API; the chain is in docs/LOVABLE-END-TO-END.md"),
)
# derived, for the hub and the docs' sentence: only what has signed in and run tools end to end
CLIENTS_TESTED = {c.name: (c.path, c.since) for c in CLIENTS if c.status == "Tested end to end" and c.path}
WHERE_YOU_BUILD = ("Claude", "VS Code", "Cursor")       # the MCP clients the hub names, in this order; Lovable comes last


def source_word(tested: bool) -> str:
    return "tested end to end" if tested else "experimental"


def build_word(tool: str) -> str:
    """"creates" only for what has been created or updated live on the hosted service; "draft" for the rest, whose
    tools ran live only as drafts or dry runs, or not yet."""
    s = STATUS[tool]
    return "creates" if s.kind == CREATES and s.live and not s.dry_run_only else "draft"


def clients_tested_at(path: str) -> list[tuple[str, str]]:
    """(client, date) for the clients recorded at one address, the hub's clients first, in its order, then the others."""
    rank = {c: i for i, c in enumerate(WHERE_YOU_BUILD)}
    names = sorted((c for c, (where, _) in CLIENTS_TESTED.items() if where == path), key=lambda c: (rank.get(c, len(rank)), c))
    return [(c, CLIENTS_TESTED[c][1]) for c in names]


def clients_working(registration_on: bool) -> list[str]:
    """The MCP clients the site names as working with the hosted service, in WHERE_YOU_BUILD order."""
    return [c for c in WHERE_YOU_BUILD if c in CLIENTS_TESTED and (CLIENTS_TESTED[c][0] == "/mcp" or registration_on)]


def connect_sentence() -> str:
    """What the site says about /mcp/connect: the tested clients there, or the status of the experimental ones."""
    seen = clients_tested_at("/mcp/connect")
    if seen:
        dates = list(dict.fromkeys(d for _, d in seen))
        return f"Tested on {_listed(dates)} with {_listed([n for n, _ in seen])}"
    names = [c.name for c in CLIENTS if c.path == "/mcp/connect"]
    return f"Experimental: {CONNECT_NOTE} ({_listed(names)})"


# ------------------------------------------------------------------ the overview of tools, functions and clients -------
# One table on /docs, /docs.md and llms-full.txt (Gustav's brief of 28 October 2026), rendered from here: every hosted
# tool with its status and where it runs, the functions outside the hosted tools, and one row per client.

# the hosted tools the local stdio server (fabric_backend/mcp_server.py) has too; tests/test_capabilities.py locks it
LOCAL_TOOLS = ("list_tables", "plan_backend", "validate_plan", "sample_rows", "join_path", "data_dictionary", "dbt_schema",
               "analyze_schema", "suggest_relationships", "rayfin_connector", "create_views", "answer_query_draft",
               "semantic_model_draft", "ontology_draft", "silver_notebook_draft", "review_plan", "create_backend")

# what is not a hosted tool: (name, status word, where, what it is)
FUNCTIONS = (
    ("`validate_plan` → `amount_levels`", "Experimental", "hosted, local demo, library",
     "the total that doubles: header amounts a join with their line rows would repeat, with the line rows per header counted; "
     "unit-tested, and run on 28 October 2026 against SQL Server 2022 in a container with synthetic data"),
    ("`plan_sql_server`", "Experimental", "library",
     "`from fabric_backend import plan_sql_server`: plan, validate, data dictionary and dbt schema over ODBC from your own Python; "
     "run on 28 October 2026 against SQL Server 2022 in a container, not yet on Windows"),
    ("`fabric-backend demo`", "Experimental", "local demo",
     "the 20-minute demo on 127.0.0.1: SQL Server over ODBC, a folder of CSV / Excel files, a columns list (file or pasted), "
     "or the synthetic shop; step 1 ends with one of five answers; over ODBC run on 28 October 2026 against SQL Server 2022 in a container"),
    ("`fabric-backend-mcp`", "Experimental", "local",
     "the local stdio MCP server over one ODBC connection string; its tools run on 28 October 2026 against SQL Server 2022 in a "
     "container; Claude Desktop starting it is not yet tried"),
    ("`plan_from` / `create`", "Experimental", "library", "the engine in a Fabric notebook (Spark catalog) or over any execute(sql)"),
    ("Claude plugin", "Planned", "—", "the connector with a skill and `/krusgraph` commands, built in the repository (`plugin/krusgraph`), not published; see *For agents*"),
    ("Databricks adapter", "Draft only", "library, local",
     "Unity Catalog metadata, informational constraints, and the `databricks_*` tools of the local server; see docs/DATABRICKS.md"),
)


def where(name: str) -> str:
    return "hosted, local" if name in LOCAL_TOOLS else "hosted"


def overview_md(registration_on: bool = True) -> str:
    """The table, as Markdown. With client registration off (a server hosted elsewhere), the clients that would use
    /mcp/connect cannot sign in, and the table says so."""
    rows = ["| Tool, function or client | Status | Where |", "| --- | --- | --- |"]
    rows += [f"| `{t}` | {label(t)} | {where(t)} |" for t in STATUS]
    rows += [f"| {n} | {w}: {what} | {at} |" for n, w, at, what in FUNCTIONS]
    for c in CLIENTS:
        status = c.status + (f" (since {c.since})" if c.since else "") + (f"; {c.note}" if c.note else "")
        at = c.where
        if c.path == "/mcp/connect" and not registration_on:
            status, at = c.status + "; cannot sign in to this server: client registration is not switched on here", "hosted elsewhere"
        rows.append(f"| {c.name} (client) | {status} | {at} |")
    return "\n".join(rows)


def overview_words() -> set[str]:
    """The status words the table uses: always from WORDS."""
    used = {word(t) for t in STATUS} | {w for _, w, _, _ in FUNCTIONS} | {c.status for c in CLIENTS}
    return {next(w for w in WORDS if u.startswith(w) or u.lower().startswith(w.lower())) for u in used}
