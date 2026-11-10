"""What the site claims Krusgraph builds, and how far each claim is proven: one source for every page (round n190).

The outside UX review the founder pasted on 9 November 2026 found that the home page said Krusgraph creates semantic
models and ontologies while the set-up guide said some things lack permissions on the hosted service, and asked that
what is demonstrated, what is technically possible and what is available to customers be unambiguous. Every page that
names an output (the home page's grid, /start, /choose, /pricing, the docs) renders it from OUTPUTS with the chip
`status()` gives, and tests/test_n190_site.py checks each page's chips against this module.

The chips (CHIPS) are derived, never typed per page:
  Tested live   the hosted service created the item in a live Fabric workspace with synthetic data, as tool_status and
                docs/LIVE-TEST.md record it (tool_status.build_word == "creates", or the item was run there: RAN_LIVE);
  Preview       available, but only in Krusgraph for Fabric (the Krusgraph Model item, a pilot not yet among the runs
                docs/LIVE-TEST.md records), or a Fabric item type that is itself in preview;
  Experimental  the tool exists and is unit-tested; creating it has no recorded live run;
  Planned       not available yet.
"""
from __future__ import annotations

import html

CHIPS = ("Tested live", "Preview", "Experimental", "Planned")
CHIP_MEANING = {
    "Tested live": "created by the hosted service in a live Fabric workspace with synthetic data, as the test record says",
    "Preview": "available in Krusgraph for Fabric (a pilot) or as a Fabric preview item; not yet in the recorded live runs",
    "Experimental": "built and unit-tested; creating it has no recorded live run",
    "Planned": "not available yet",
}
CHIP_CLASS = {"Tested live": "chip-live", "Preview": "chip-preview", "Experimental": "chip-exp", "Planned": "chip-planned"}
STATUS_LINK = "/docs#test-status"

# The one promise (docs/WEBSITE_COPY_REWRITE.md says why this headline): the hero, the page title and llms.txt.
HEADLINE = "Your data already has connections. Krusgraph finds them."
SUPPORT = ("Discover how your tables connect, catch data issues before anyone sees them, and build trusted Power BI models, "
           "APIs and AI-ready data products in Microsoft Fabric.")
STORY = ("Krusgraph understands how your business data connects, checks that the relationships hold against your rows, "
         "and gets the data ready for reports, apps and AI agents.")

# The outputs in the order the home page's grid shows them: (key, name, tool behind it, what it is, where to read more).
# `tool` None: not an MCP tool of the hosted service (only the Krusgraph Model item builds it).
OUTPUTS = (
    ("semantic_model", "Power BI semantic model", "create_semantic_model",
     "Tables, checked relationships, measures and a date table, in Direct Lake.", "/docs#tools"),
    ("report", "Power BI report", "create_report", "A first report page bound to that model.", "/docs#tools"),
    ("ontology", "Fabric IQ ontology", "create_ontology",
     "Entity types, keys and relationship types; needs the tenant setting for Ontology (preview).", "/docs/concepts/ontologies"),
    ("pipeline", "Notebooks and a pipeline", "create_pipeline",
     "Silver and gold notebooks and the pipeline that runs them, from the plan you reviewed.", "/docs#tools"),
    ("graphql", "API for GraphQL", "create_backend", "An API your app or agent reads, with the plan's links.", "/lovable"),
    ("data_agent", "Data agent", "create_data_agent",
     "A Fabric data agent with the plan as its instructions; Fabric's own AI answers in it.", "/docs#tools"),
    ("app", "App (Rayfin)", None, "Key figures, lists and charts over the data product; made by Krusgraph for Fabric only.",
     "/docs/krusgraph-for-fabric"),
)
# What is said about running, once: the hosted service creates, but neither runs nor schedules.
RUNS = ("Krusgraph creates an item only when you ask, after a dry run, with your own Fabric permissions. Running or "
        "scheduling the pipeline is a separate, opt-in step that needs DataPipeline.Execute.All: Krusgraph for Fabric "
        "offers it (Run once, Schedule) when your admin grants it; the hosted connector does not request it, so in Claude "
        "the pipeline is run in Fabric by you.")
CHECK_LINE = ("On /check, in your browser and without an account, the same engine gives drafts: a Power BI project, an app "
              "preview, the ontology as RDF/XML and an evidence report. Nothing is created in Fabric from there.")


def status(key: str) -> str:
    """The chip for one output, derived from tool_status (see the module's docstring)."""
    from . import tool_status as ts
    tool = next(t for k, _n, t, _w, _l in OUTPUTS if k == key)
    if tool is None:
        return "Preview"
    s = ts.STATUS[tool]
    if s.available == ts.OPERATOR:
        return "Planned"
    return "Tested live" if ts.build_word(tool) == "creates" or tool in ts.RAN_LIVE else "Experimental"


def note(key: str) -> str:
    """What the chip leaves out, in one short clause (empty when nothing)."""
    from . import tool_status as ts
    if key == "graphql" and ts.build_word("create_backend") == "updates":
        return "Updating an existing API in place: tested live."
    if key == "ontology":
        return "Fabric's Ontology item is itself a preview."
    return ""


def table() -> list[dict]:
    return [{"key": k, "name": n, "tool": t, "what": w, "link": link, "status": status(k), "note": note(k)}
            for k, n, t, w, link in OUTPUTS]


def chip_html(key: str) -> str:
    s = status(key)
    return (f'<a class="chip {CHIP_CLASS[s]}" href="{STATUS_LINK}" data-claim="{key}" data-status="{s}" '
            f'title="{html.escape(CHIP_MEANING[s], quote=True)}">{s}</a>')


def legend_html() -> str:
    return ('<p class="muted tiny chip-legend">' + " · ".join(
        f'<span class="chip {CHIP_CLASS[c]}" aria-hidden="true">{c}</span> {html.escape(CHIP_MEANING[c])}' for c in CHIPS[:3])
        + f'. <a href="{STATUS_LINK}">Status per tool</a>.</p>')


def grid_html() -> str:
    """The home page's 'What you can build' grid: each output, its chip and a link."""
    e = html.escape
    cards = "".join(
        f'<li class="out-tile"><div class="out-tile-head"><h3>{e(r["name"])}</h3>{chip_html(r["key"])}</div>'
        f'<p>{e(r["what"])}{(" " + e(r["note"])) if r["note"] else ""}</p><a class="out-tile-more" href="{r["link"]}">'
        f'More<span class="visually-hidden"> about the {e(r["name"])}</span> →</a></li>' for r in table())
    return f'<ul class="out-grid" role="list">{cards}</ul>'


def line_html() -> str:
    """The short form for /start, /choose and /pricing: every output with its chip, in one line."""
    e = html.escape
    return ('<p class="claims-line">What Krusgraph builds in Fabric: '
            + ", ".join(f'{e(r["name"])} {chip_html(r["key"])}' for r in table()) + f'. <span class="muted">{e(RUNS)}</span></p>')


def markdown() -> str:
    """The docs' table: the same rows as Markdown."""
    rows = "\n".join(f'| {r["name"]} | {r["status"]} | {r["what"]}{(" " + r["note"]) if r["note"] else ""} |' for r in table())
    meaning = "\n".join(f"- **{c}**: {CHIP_MEANING[c]}." for c in CHIPS)
    return (f"| Output | Status | What it is |\n| --- | --- | --- |\n{rows}\n\n{meaning}\n\n{RUNS}\n\n{CHECK_LINE}")
