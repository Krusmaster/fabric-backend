"""The product offering: the four ways to use Krusgraph, as data, and what the site draws from it (round n177).

The founder, 9 November 2026: put the workload on the site, with docs and how to choose it; an analysis of which
Krusgraph to choose when (MCP in Claude, MCP in other agents, run it yourself, the Fabric workload); "make a nice
diagram and put it on the product offering on the website".

One engine, four ways in. Everything the site says about them comes from WAYS: the diagram (`diagram_html`, on the home
page and on /choose), the comparison table and the decision guide on /choose, the short version on /start and the home
page (`short_html`), and the Markdown twin (/choose.md). Status lines are built from tool_status (CLIENTS, the local
server's note) and say no more than it and docs/LIVE-TEST.md; prices say only what /pricing says. The workload uses no
AI model: it is said plainly, here and in the docs.

No Microsoft logo and no Microsoft product icon: the diagram uses the site's own shapes and the mascots' colours, and
the footer carries the trademark line.
"""
from __future__ import annotations

import html

# Where the docs of each way are. /docs/krusgraph-in-fabric is the DOCS.md group "Krusgraph in Fabric".
FABRIC_DOCS = "/docs/krusgraph-in-fabric"
PILOT_PAGE = "/pilot/fabric"           # n176: what a pilot organisation's administrator does
CHOOSE = "/choose"


def _status_claude() -> str:
    from . import tool_status as ts
    c = next(x for x in ts.CLIENTS if x.name == "Claude")
    return f"{c.status} since {c.works_since} (docs/LIVE-TEST.md)."


def _agent_names() -> list[str]:
    """The agents the hosted service signs in today (tool_status.clients_working, Claude aside), and Lovable, which signs in
    at the same address; none while client registration is off (then only Claude can sign in)."""
    from . import tool_status as ts
    from .pages import _registration_on
    reg = _registration_on()
    names = [c for c in ts.clients_working(reg) if c != "Claude"]
    return names + (["Lovable"] if reg else [])


def _agents_who() -> str:
    names = _agent_names()
    if not names:
        return ("People who work in another AI agent. The hosted service signs in only Claude today; other agents work "
                "when you host Krusgraph yourself (not tested).")
    return "People who build an app or write code with an AI agent, in Lovable or an editor, and want the plan where they work."


def _status_agents() -> str:
    from . import tool_status as ts
    names = set(_agent_names())
    if not names:
        return "Not supported on the hosted service today: client registration is off, so only Claude can sign in."
    tested = [(c.name, c.works_since) for c in ts.CLIENTS
              if c.path == "/mcp/connect" and c.status == "Tested end to end" and c.works_since and c.name in names]
    other = [c.name for c in ts.CLIENTS if c.path == "/mcp/connect" and c.status != "Tested end to end"]
    out = "Tested end to end: " + ", ".join(f"{n} (since {d})" for n, d in tested) + "." if tested else ""
    if other:
        out += f" Experimental: {' and '.join(other)}."
    return (out + " GitHub Copilot has no row of its own in the test status.").strip()


def _status_self() -> str:
    from . import tool_status as ts
    tools = ts.LOCAL_TRIED_TOOLS
    return (f"Local server: Tried live for {', '.join(tools[:-1])} and {tools[-1]} ({ts.LOCAL_TRIED_NOTE}); its other "
            "tools are Experimental. In your own Azure: the same deploy script the hosted service is deployed with "
            "(deploy/krusgraph.sh).")


def _status_fabric() -> str:
    return ("A pilot, on request, for up to 20 selected organisations. Not yet among the runs docs/LIVE-TEST.md records. "
            "Workload Hub listing: planned, not available.")


# The four ways. `colour` is a site token (the mascots' colours and mustard); `data` says where the data passes.
WAYS = (
    {"key": "claude", "name": "Krusgraph in Claude", "short": "The connector in Claude", "colour": "coral",
     "docs": "/start",
     "who": "People who already use Claude and want to ask about their Fabric tables in a chat.",
     "needs": ["A Claude plan that lets you add a custom connector",
               "A Microsoft work account and a Fabric workspace on a capacity",
               "Your Entra admin's consent for the Krusgraph app, once"],
     "how": "Chat. Answers come as text, and as cards with the map and buttons (MCP Apps) where the service has them turned on.",
     "builds": "Plans and checks, and every item the tools create on request after a dry run: API for GraphQL, semantic "
               "model, report, ontology, views, data agent, notebooks and a pipeline; drafts such as a dbt project and a "
               "data dictionary.",
     "data": "Krusgraph's service (Azure, Sweden Central), then Claude and so Anthropic, Claude's AI provider: names, "
             "counts and the rows you ask for.",
     "data_short": "Krusgraph (Sweden Central) and Anthropic",
     "price": "Free; open source (MIT), as /pricing says.",
     "status": _status_claude,
     "lacks": ["Needs an AI chat licence and your admin's consent",
               "Cannot run or schedule a notebook or pipeline on the hosted service"],
     "choose_if": "I already use Claude"},
    {"key": "agents", "name": "Krusgraph in other agents", "short": "MCP in your agent", "colour": "lav",
     "docs": lambda: "/docs/get-started/other-mcp-clients" if _agent_names() else "/docs/get-started/connect",
     "who": _agents_who,
     "needs": ["An agent that supports remote MCP servers with sign-in",
               "A Microsoft work account and a Fabric workspace on a capacity",
               "Your Entra admin's consent for the Krusgraph app, once"],
     "how": "Chat in your agent. Answers come as text; the cards are drawn in Claude only.",
     "builds": "The same tools as in Claude; your agent decides when to call them.",
     "data": "Krusgraph's service (Azure, Sweden Central), then your agent and its AI provider.",
     "data_short": "Krusgraph (Sweden Central) and your agent's AI provider",
     "price": "/pricing names the connector in Claude as free; other agents reach the same hosted service.",
     "status": _status_agents,
     "lacks": ["No cards: text answers only",
               "How well the agent chooses the tools depends on the agent and its model"],
     "choose_if": "We build an app in Lovable or code in VS Code"},
    {"key": "self", "name": "Run Krusgraph yourself", "short": "Self-hosted, open source", "colour": "mustard",
     "docs": "/local",
     "who": "Teams whose data may not leave their own Azure or their own network.",
     "needs": ["Your own Azure subscription for the service, or a machine for the local server",
               "Someone to run and update it (the code is on GitHub)",
               "For the local server: an ODBC connection to SQL Server, Azure SQL or a Fabric SQL endpoint"],
     "how": "You run it: as your own hosted service in Azure, as a local MCP server, from the command line or from Python.",
     "builds": "In your own Azure: the same as the hosted service. Locally: plans, checks and drafts, and the API for "
               "GraphQL and views on request.",
     "data": "Only your environment: your Azure or your machine. An AI agent you connect still gets the answers; the "
             "command line and Python use no AI.",
     "data_short": "Only your environment, and the AI provider of an agent you connect",
     "price": "The code is free under the MIT licence; your Azure costs are yours. Help with running it is the Team offer on /pricing (contact us).",
     "status": _status_self,
     "lacks": ["You install, update and watch it yourself",
               "The Fabric workload is not part of it"],
     "choose_if": "Nothing may leave our Azure"},
    {"key": "fabric", "name": "Krusgraph in Fabric", "short": "The Krusgraph Model item", "colour": "sage",
     "docs": FABRIC_DOCS,
     "who": "Teams that work in Microsoft Fabric and do not want an AI chat.",
     "needs": ["A Fabric workspace on a capacity (Power BI Pro alone is not enough)",
               "Your organisation in the pilot, and the tenant setting for workloads not validated by Microsoft",
               "Your Entra admin's consent for the workload app, once"],
     "how": "An item you click through in Fabric: choose a lakehouse and a schema, review the keys and links, check them "
            "against the rows, choose outputs, see the dry run, then Create. No AI.",
     "builds": "Silver notebook, gold views, pipeline, semantic model, report, API for GraphQL, ontology and data agent, "
               "with a data product over them and the data flow drawn.",
     "data": "Krusgraph's engine (Azure, Sweden Central) and your Fabric. The workload uses no AI model, so nothing goes "
             "to an AI provider.",
     "data_short": "Krusgraph (Sweden Central) only; no AI",
     "price": "Not on /pricing yet: the pilot is on request.",
     "status": _status_fabric,
     "lacks": ["No questions in your own words: there is no chat",
               "Pilot only; not in Fabric's Workload Hub",
               "Does not run or schedule the notebooks or the pipeline it creates"],
     "choose_if": "We work in Fabric and do not want an AI chat"},
)

# What is built in Fabric, the diagram's right-hand column.
BUILT = ("Semantic model", "Report", "Ontology", "API for GraphQL", "Pipeline and notebooks", "Data agent", "Data product")

NO_AI = ("The Krusgraph Model item in Fabric uses no AI model: the keys and links come from the engine's named rules and "
         "the checks count your rows. A data agent it creates is Fabric's own item, and Fabric's AI answers there when "
         "someone asks it.")

# The decision guide, in the founder's words (9 November 2026), each to a way.
DECIDE = (("I already use Claude", "claude"),
          ("We work in Fabric and do not want an AI chat", "fabric"),
          ("We build an app in Lovable or code in VS Code", "agents"),
          ("Nothing may leave our Azure", "self"))


def val(w: dict, key: str):
    """A way's field; the ones that depend on today's status are functions."""
    return w[key]() if callable(w[key]) else w[key]


def way(key: str) -> dict:
    return next(w for w in WAYS if w["key"] == key)


def _e(s: str) -> str:
    return html.escape(s, quote=True)


# ------------------------------------------------------------------ the diagram ---------------------------------------

_ENGINE_SVG = ('<svg class="off-engine-g" viewBox="0 0 120 84" aria-hidden="true" focusable="false">'
               '<path d="M22 22 60 14 98 26M22 22 34 62 60 14M98 26 88 66 60 14M34 62 88 66" class="off-e-l"/>'
               '<circle cx="22" cy="22" r="8" class="off-e-n coral"/><circle cx="60" cy="14" r="9" class="off-e-n sage"/>'
               '<circle cx="98" cy="26" r="8" class="off-e-n lav"/><circle cx="34" cy="62" r="8" class="off-e-n mustard"/>'
               '<circle cx="88" cy="66" r="9" class="off-e-n sage"/></svg>')

_ICONS = {   # the site's own glyphs, 24 px, stroked
    "claude": '<path d="M5 6h14a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2h-8l-4 3v-3H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2z"/>',
    "agents": '<path d="M9 7 4 12l5 5M15 7l5 5-5 5"/>',
    "self": '<rect x="4" y="4" width="16" height="7" rx="2"/><rect x="4" y="13" width="16" height="7" rx="2"/><path d="M8 7.5h.01M8 16.5h.01"/>',
    "fabric": '<rect x="4" y="4" width="7" height="7" rx="2"/><rect x="13" y="4" width="7" height="7" rx="2"/><rect x="4" y="13" width="7" height="7" rx="2"/><path d="M16.5 13v7M13 16.5h7"/>',
}


def _icon(key: str) -> str:
    return f'<svg class="off-i" viewBox="0 0 24 24" aria-hidden="true" focusable="false">{_ICONS[key]}</svg>'


def _arrow(cls: str, ends: int, fan_in: bool) -> str:
    """A connector between the columns: on a wide screen a fan of lines (the four ways into the engine, the engine out to
    what is built), stretched to the column's height; on a phone a single arrow down (CSS shows one or the other)."""
    ys = [100 * (i + .5) / ends for i in range(ends)]
    lines = "".join(f'<path d="M0 {y:.1f} C20 {y:.1f} 20 50 40 50"/>' if fan_in else f'<path d="M0 50 C20 50 20 {y:.1f} 40 {y:.1f}"/>'
                    for y in ys)
    return (f'<div class="off-arrow {cls}" aria-hidden="true">'
            f'<svg class="off-fan" viewBox="0 0 40 100" preserveAspectRatio="none" focusable="false">{lines}</svg>'
            '<svg class="off-down" viewBox="0 0 24 32" focusable="false"><path d="M12 2v26M5 21l7 7 7-7"/></svg></div>')


def diagram_html(heading: str = "One engine, four ways to use it", level: int = 2, hid: str = "offering-h") -> str:
    """The product offering: the four ways on the left, the one engine in the middle, what is built in Fabric on the right.
    Each way is a link to its docs (keyboard focus, a visible ring). The list under it says the same in words."""
    ways = "".join(
        f'<li class="off-way {w["colour"]}" data-way="{w["key"]}"><a href="{val(w, "docs")}" class="off-way-a">'
        f'<span class="off-way-h">{_icon(w["key"])}<span class="off-way-n">{_e(w["name"])}</span></span>'
        f'<span class="off-way-who">{_e(val(w, "who"))}</span>'
        f'<span class="off-way-data"><span class="off-k">Data passes:</span> {_e(w["data_short"])}</span></a></li>'
        for w in WAYS)
    built = "".join(f"<li>{_e(b)}</li>" for b in BUILT)
    words = "".join(
        f'<li><a href="{val(w, "docs")}">{_e(w["name"])}</a>: for {_e(val(w, "who")[0].lower() + val(w, "who")[1:])} '
        f'Data passes: {_e(w["data_short"])}.</li>' for w in WAYS)
    return f"""<section class="wrap offering" id="offering" aria-labelledby="{hid}">
  <h{level} id="{hid}">{_e(heading)}</h{level}>
  <p class="intro">The same Krusgraph engine reads your tables, proposes keys and links with the rule behind each, and checks them against your rows. You reach it in one of four ways; each builds the same items in Fabric.</p>
  <figure class="off-fig" aria-describedby="offering-words-h">
    <div class="off-grid">
      <ul class="off-ways" aria-label="The four ways">{ways}</ul>
      {_arrow("off-a1", len(WAYS), True)}
      <div class="off-engine"><div class="off-engine-box">{_ENGINE_SVG}<p class="off-engine-n">One Krusgraph engine</p><p class="off-engine-s">Keys, links and the rule behind each, checked against your rows</p></div></div>
      {_arrow("off-a2", len(BUILT), False)}
      <div class="off-built"><p class="off-built-h">Built in Microsoft Fabric</p><ul>{built}</ul></div>
    </div>
  </figure>
  <div class="off-words">
    <h{level + 1} id="offering-words-h" class="off-words-h">The diagram in words</h{level + 1}>
    <ul class="off-words-l">{words}</ul>
    <p class="muted tiny">All four use the same engine. What it builds in Fabric: {_e(", ".join(b.lower() if b != "API for GraphQL" else b for b in BUILT))}. The Fabric item uses no AI model. <a href="{CHOOSE}">Which Krusgraph should I use?</a></p>
  </div>
</section>"""


# ------------------------------------------------------------------ /choose: the comparison and the decision guide ----

ROWS = (("who", "Who it is for"), ("needs", "What you need"), ("how", "How you work"), ("builds", "What it can build"),
        ("data", "Where data passes"), ("price", "Free or paid"), ("status", "Status"), ("lacks", "What it lacks today"))


def _cell(w: dict, key: str) -> str:
    v = val(w, key)
    if isinstance(v, (list, tuple)):
        return '<ul class="plain-list">' + "".join(f"<li>{_e(x)}</li>" for x in v) + "</ul>"
    return _e(v)


def compare_html() -> str:
    head = "".join(f'<th scope="col" class="cmp-{w["colour"]}"><a href="{val(w, "docs")}">{_e(w["name"])}</a></th>' for w in WAYS)
    body = "".join(f'<tr><th scope="row">{_e(label)}</th>' + "".join(f"<td>{_cell(w, key)}</td>" for w in WAYS) + "</tr>"
                   for key, label in ROWS)
    return (f'<div class="table-wrap choose-table" tabindex="0" role="region" aria-labelledby="compare-h"><table>'
            f'<thead><tr><th scope="col"><span class="visually-hidden">Question</span></th>{head}</tr></thead>'
            f"<tbody>{body}</tbody></table></div>")


def decide_html() -> str:
    items = "".join(f'<li class="{way(k)["colour"]}"><span class="dec-if">“{_e(q)}”</span> <span aria-hidden="true">→</span> '
                    f'<a href="{val(way(k), "docs")}">{_e(way(k)["name"])}</a></li>' for q, k in DECIDE)
    return f'<ul class="decide">{items}</ul>'


def short_html(where: str) -> str:
    """The short version for /start and the home page: the decision guide in four lines and a link to /choose."""
    hid = f"choose-short-{where}"
    return (f'<section class="wrap choose-short" id="which" aria-labelledby="{hid}">'
            f'<h2 id="{hid}" class="h3">Which Krusgraph should I use?</h2>{decide_html()}'
            f'<p class="muted tiny">{_e(NO_AI)} <a href="{CHOOSE}">Compare the four ways</a>.</p></section>')


def choose_vars() -> dict[str, str]:
    return {"CHOOSE_DIAGRAM": diagram_html("The product: one engine, four ways in", 2, "choose-offering-h"),
            "CHOOSE_COMPARE": compare_html(), "CHOOSE_DECIDE": decide_html(), "CHOOSE_NO_AI": _e(NO_AI),
            "CHOOSE_SHORT_START": short_html("start")}


def choose_md() -> str:
    """/choose.md: the same facts as Markdown."""
    out = ["# Which Krusgraph should I use?", "",
           "One Krusgraph engine, four ways to use it. Each builds the same items in Microsoft Fabric.", "",
           "## Decision guide", ""]
    from .pages import site_url
    o = site_url()
    out += [f"- \"{q}\" → [{way(k)['name']}]({o}{val(way(k), 'docs')})" for q, k in DECIDE]
    out += ["", NO_AI, ""]
    for w in WAYS:
        out += [f"## {w['name']}", ""]
        for key, label in ROWS:
            v = val(w, key)
            out.append(f"- **{label}:** " + ("; ".join(v) if isinstance(v, (list, tuple)) else v))
        out += [f"- **Docs:** {o}{val(w, 'docs')}", ""]
    out += ["## Built in Microsoft Fabric", "", ", ".join(BUILT) + ".", ""]
    return "\n".join(out)


# ------------------------------------------------------------------ the docs' figures ---------------------------------

def permissions_table(_rendered: str = "") -> str:
    """The workload's permissions per output, in plain words, from workload_api.KINDS (the editor shows the same)."""
    from .workload_api import KINDS
    rows = "".join(f"\n<tr><td>{_e(v['label'])}</td><td>{_e('; '.join(' or '.join(a) for a in v['needs']))}.</td></tr>"
                   for v in KINDS.values())                     # one row a line, each a sentence: its own statement
    return ('<div class="table-wrap" tabindex="0"><table><thead><tr><th>To build</th><th>The signed-in person’s token needs</th>'
            f"</tr></thead><tbody>{rows}</tbody></table></div>")


SHOTS = (("model-review", "The review: the proposed keys and links with the rule behind each, checked against the rows, and the map."),
         ("model-outputs", "Choose what to build: each output with its name and the permission it needs."),
         ("model-preview-cards", "The dry run: one card per output, saying what it would create. Nothing is written yet."),
         ("model-flow", "The data flow: source tables, silver, gold and what is built on them; a box opens to show its code."))


def shot(name: str) -> str:
    from .pages import STATIC_DIR
    cap = dict(SHOTS)[name]
    for ext in ("webp", "png"):
        if (STATIC_DIR / "workload-shots" / f"{name}.{ext}").exists():
            return (f'<figure class="shot"><img src="/static/workload-shots/{name}.{ext}" alt="{_e(cap)} Synthetic data." loading="lazy">'
                    f'<figcaption>{_e(cap)} <span class="shot-tag">Synthetic data</span> (the shop schema), rendered from the editor’s own components.</figcaption></figure>')
    return ""


def figures() -> dict:
    out = {"workload-permissions": permissions_table}
    out.update({f"shot-{n}": (lambda n: lambda _r: shot(n))(n) for n, _ in SHOTS})
    return out
