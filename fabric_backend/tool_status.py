"""Each hosted tool's status as data, so one tool cannot carry two statuses on two pages (the website brief of
26 October 2026, /docs: "a shared status source with separate fields for availability, what the tool changes, test
level and latest verification").

`label()` turns the fields into the site's status words (Tested end to end, Experimental, Draft only, Available when
enabled by the operator, Planned); the docs' tool table, its test status list, llms.txt and the use-case tasks render
from here. "Draft only" says what a tool changes (nothing), "Tested end to end" how far it has been run; a draft tool
that ran live is therefore "Tested end to end", and the changes column says it creates nothing.
"""
from __future__ import annotations

from dataclasses import dataclass

HOSTED, OPERATOR = "hosted", "operator"          # operator: needs a permission the hosted app does not ask for today
READS, DRAFT, CREATES = "reads", "draft", "creates"

# The run that counts as tested end to end: from Claude as a custom connector, through Microsoft sign-in, against a
# Fabric workspace with synthetic data, without any creating call (docs, Test status).
LIVE_RUN_DATE = "26 October 2026"
LIVE_RUN_STEPS = 14
# the tools of that run, in the order they ran
LIVE_RUN = ("list_workspaces", "list_sources", "sample_rows", "plan_backend", "validate_plan", "suggest_relationships",
            "analyze_schema", "join_path", "describe_backend", "query_graphql", "semantic_model_draft", "data_dictionary",
            "dbt_schema", "create_views", "plan_drift", "app_starter")


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
        """Ran in the live run of LIVE_RUN_DATE."""
        return self.name in LIVE_RUN


_NO = "nothing"
_ITEM = "creates/updates one item; never deletes"
_RAW = {
    "list_workspaces": (HOSTED, READS, _NO, "unit tests"),
    "list_sources": (HOSTED, READS, _NO, "unit tests"),
    "list_tables": (HOSTED, READS, _NO, "unit tests; not run live as a tool of its own"),
    "plan_backend": (HOSTED, READS, _NO, "unit tests"),
    "validate_plan": (HOSTED, READS, "nothing (counting queries)", "unit tests"),
    "sample_rows": (HOSTED, READS, _NO, "unit tests; the masking by unit tests only", False, "; masking: Experimental"),
    "create_backend": (HOSTED, CREATES, _ITEM, "unit tests; not run live"),
    "describe_backend": (HOSTED, READS, _NO, "unit tests"),
    "query_graphql": (HOSTED, READS, _NO, "unit tests; with `question` by unit tests only", False, "; with `question`: Experimental"),
    "rayfin_connector": (HOSTED, DRAFT, _NO, "unit tests"),
    "ontology_draft": (HOSTED, DRAFT, _NO, "unit tests"),
    "semantic_model_draft": (HOSTED, DRAFT, _NO, "unit tests", False, " (a draft; creates nothing)"),
    "join_path": (HOSTED, READS, _NO, "unit tests"),
    "data_dictionary": (HOSTED, READS, _NO, "unit tests"),
    "dbt_schema": (HOSTED, DRAFT, _NO, "unit tests"),
    "plan_drift": (HOSTED, READS, _NO, "unit tests"),
    "create_semantic_model": (OPERATOR, CREATES, _ITEM, "unit tests"),
    "create_views": (HOSTED, CREATES, "creates/alters views in that schema only; never drops",
                     "unit tests; creating and the header views by unit tests only", True,
                     "; creating and the header views are unit-tested"),
    "create_data_agent": (OPERATOR, CREATES, "creates/updates one item and its staging config; never deletes", "unit tests"),
    "create_ontology": (OPERATOR, CREATES, _ITEM, "unit tests", False, "; unit-tested, not yet run live"),
    "app_starter": (HOSTED, DRAFT, _NO, "unit tests; the backend part by unit tests only", False,
                    " (prompt and queries); the backend part is unit-tested"),
    "app_readiness": (HOSTED, READS, "nothing (one introspection query)", "unit tests"),
    "analyze_schema": (HOSTED, READS, _NO, "unit tests"),
    "lineage": (HOSTED, READS, _NO, "unit tests"),
    "silver_notebook_draft": (HOSTED, DRAFT, _NO, "unit tests and a local PySpark 4.0.1", False,
                              "; unit-tested and run on a local PySpark 4.0.1, not yet in Fabric"),
    "create_silver_notebook": (OPERATOR, CREATES, _ITEM, "unit tests", False, "; unit-tested"),
    "drift_monitor_draft": (HOSTED, DRAFT, _NO, "unit tests; the notebook ran two nights on a local PySpark", False,
                            "; unit-tested, the notebook ran two nights on a local PySpark"),
    "create_drift_monitor": (OPERATOR, CREATES, "creates/updates two items and a schedule; never deletes", "unit tests", False,
                             "; unit-tested"),
    "answer_query_draft": (HOSTED, DRAFT, _NO, "unit tests on the shop schema", False, "; unit-tested on the shop schema"),
    "suggest_relationships": (HOSTED, READS, "nothing (counting queries)", "unit tests"),
    "compare_semantic_model": (OPERATOR, READS, _NO, "unit tests", False, "; with `tmdl`: Experimental"),
    "gold_views_draft": (HOSTED, DRAFT, _NO, "unit tests; the SQL on SQLite and a local PySpark 4.0.1", False,
                         "; unit-tested, the SQL run on SQLite and a local PySpark 4.0.1"),
    "create_gold_views": (OPERATOR, CREATES, "creates/updates one notebook; never deletes", "unit tests", False, "; unit-tested"),
    "export_item_definitions": (HOSTED, DRAFT, _NO, "unit tests", False, "; unit-tested"),
}
STATUS: dict[str, ToolStatus] = {name: ToolStatus(*v, name=name) for name, v in _RAW.items()}


def word(name: str) -> str:
    """The status word alone: availability first, then whether it ran live, then what it changes."""
    s = STATUS[name]
    if s.available == OPERATOR:
        return "Available when enabled by the operator"
    if s.live:
        return "Tested end to end (dry run)" if s.dry_run_only else "Tested end to end"
    return "Draft only" if s.kind == DRAFT else "Experimental"


def label(name: str) -> str:
    return word(name) + STATUS[name].note


def live_run_list() -> str:
    """The live run's tools as the docs list them: in run order, the dry runs marked."""
    names = [f"`{t}`" + (" (dry run only; nothing was created)" if STATUS[t].dry_run_only else "") for t in LIVE_RUN]
    return ", ".join(names[:-1]) + " and " + names[-1]


def task_status(tools: list[str]) -> str:
    """One line for a group of tools: the live date when all ran live, otherwise each tool with its word."""
    if all(STATUS[t].live and not STATUS[t].dry_run_only and not STATUS[t].note.startswith(";") for t in tools):
        return f"tested end to end on {LIVE_RUN_DATE}"
    return "; ".join(f"`{t}`: {label(t)[0].lower() + label(t)[1:]}" for t in tools)
