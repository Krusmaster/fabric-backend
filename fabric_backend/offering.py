"""The product offering: the four Krusgraph products, as data, and what the site draws from it (round n177).

The founder, 9 November 2026: put the workload on the site, with docs and how to choose it; an analysis of which
Krusgraph to choose when (MCP in Claude, MCP in other agents, run it yourself, the Fabric workload); "make a nice
diagram and put it on the product offering on the website".

One engine, four products. Everything the site says about them comes from WAYS: the diagram (`diagram_html`, on the home
page and on /choose), the comparison table and the decision guide on /choose, the short version on /start and the home
page (`short_html`), and the Markdown twin (/choose.md). Status lines are built from tool_status (CLIENTS, the local
server's note) and say no more than it and docs/LIVE-TEST.md; prices say only what /pricing says. The workload uses no
AI model: it is said plainly, here and in the docs.

The founder, 9 November 2026 (evening): four products, named Krusgraph for Fabric (the Krusgraph Model item), Krusgraph
for Claude (the MCP connector, which works in other MCP clients too), Krusgraph for Lovable and Krusgraph Open Source;
one Krusgraph logo everywhere, no product logos and no mascot per product. The chat on krusgraph.com and /check are ways
to try it, not products; the drift monitor, the SAP pack and the dbt export are features; Marketplace is where you buy.
Partner names (Fabric, Claude, Lovable) are plain text only: no Microsoft, Anthropic or Lovable logo, and never one
next to the mascots or our logo. The footer carries the trademark line.
"""
from __future__ import annotations

import html

# Where the docs of each product are. /docs/krusgraph-for-fabric is the DOCS.md group "Krusgraph for Fabric".
FABRIC_DOCS = "/docs/krusgraph-for-fabric"
PILOT_PAGE = "/pilot/fabric"           # n176: what a pilot organisation's administrator does
CHOOSE = "/choose"


def _mcp_clients() -> list[str]:
    """The MCP clients besides Claude the hosted service signs in today (tool_status.clients_working); none while client
    registration is off (then only Claude can sign in)."""
    from . import tool_status as ts
    from .pages import _registration_on
    return [c for c in ts.clients_working(_registration_on()) if c != "Claude"]


def _lovable_on() -> bool:
    from .pages import _registration_on
    return _registration_on()                     # Lovable signs in at /mcp/connect, through client registration


def _claude_who() -> str:
    names = _mcp_clients()
    if names:
        return (f"People who use Claude, or another MCP client ({', '.join(names)}, through /mcp/connect), and want to ask "
                "about their Fabric tables in a chat.")
    return ("People who use Claude and want to ask about their Fabric tables in a chat. Other MCP clients cannot sign in "
            "to the hosted service today; they work when you host Krusgraph yourself (not tested).")


def _status_claude() -> str:
    from . import tool_status as ts
    c = next(x for x in ts.CLIENTS if x.name == "Claude")
    out = f"Claude: {c.status} since {c.works_since} (docs/LIVE-TEST.md)."
    names = set(_mcp_clients())
    tested = [(x.name, x.works_since) for x in ts.CLIENTS
              if x.path == "/mcp/connect" and x.status == "Tested end to end" and x.works_since and x.name in names]
    if tested:
        out += " Other MCP clients, tested end to end: " + ", ".join(f"{n} (since {d})" for n, d in tested) + "."
    other = [x.name for x in ts.CLIENTS if x.path == "/mcp/connect" and x.status != "Tested end to end"]
    if names and other:
        out += f" Experimental: {' and '.join(other)}."
    return out + " GitHub Copilot has no row of its own in the test status."


def _status_lovable() -> str:
    from . import tool_status as ts
    rows = [x for x in ts.CLIENTS if x.name == "Lovable"]
    mcp = next((x for x in rows if x.path == "/mcp/connect"), None)
    api = next((x for x in rows if not x.path), None)
    out = []
    if mcp and _lovable_on():
        out.append(f"In Lovable's chat (MCP): {mcp.status} since {mcp.works_since}.")
    elif mcp:
        out.append("In Lovable's chat (MCP): not supported on this service today, because client registration is off.")
    if api:
        out.append(f"An app reading the API for GraphQL with Lovable's own Fabric connector: {api.status} "
                   "(docs/LOVABLE-END-TO-END.md).")
    return " ".join(out)


def _status_self() -> str:
    from . import tool_status as ts
    tools = ts.LOCAL_TRIED_TOOLS
    return (f"Local server: Tried live for {', '.join(tools[:-1])} and {tools[-1]} ({ts.LOCAL_TRIED_NOTE}); its other "
            "tools are Experimental. In your own Azure: the same deploy script the hosted service is deployed with "
            "(deploy/krusgraph.sh).")


def _status_fabric() -> str:
    return ("A pilot, on request, for up to 20 selected organisations. Not yet among the runs docs/LIVE-TEST.md records. "
            "Workload Hub listing: planned, not available.")


# The four products, in the founder's order. `colour` is a site token (the mascots' colours and mustard), used for a
# border only: no product logo. `data` says where the data passes.
WAYS = (
    {"key": "fabric", "name": "Krusgraph for Fabric", "short": "The Krusgraph Model item in Fabric", "colour": "sage",
     "docs": FABRIC_DOCS,
     "who": "Teams that work in Microsoft Fabric and do not want an AI chat.",
     "needs": ["A Fabric workspace on a capacity (Power BI Pro alone is not enough)",
               "Your organisation in the pilot, and the tenant setting for workloads not validated by Microsoft",
               "Your Entra admin's consent for the workload app, once"],
     "how": "The Krusgraph Model item, which you click through in Fabric: choose a lakehouse and a schema, review the keys "
            "and links, check them against the rows, choose outputs, see the dry run, then Create. No AI.",
     "builds": "Silver notebook, gold views, pipeline, semantic model, report, API for GraphQL, ontology and data agent, "
               "with a data product over them and the data flow drawn.",
     "data": "Krusgraph's engine (Azure, Sweden Central) and your Fabric. It uses no AI model, so nothing goes to an AI "
             "provider.",
     "data_short": "Krusgraph (Sweden Central) only; no AI",
     "price": "Not on /pricing yet: the pilot is on request.",
     "status": lambda: _status_fabric(),
     "lacks": ["No questions in your own words: there is no chat",
               "Pilot only; not in Fabric's Workload Hub",
               "Does not run or schedule the notebooks or the pipeline it creates"]},
    {"key": "claude", "name": "Krusgraph for Claude", "short": "The MCP connector, in Claude and other MCP clients",
     "colour": "coral", "docs": "/start",
     "who": _claude_who,
     "needs": ["Claude with a custom connector, or another MCP client that signs in with OAuth",
               "A Microsoft work account and a Fabric workspace on a capacity",
               "Your Entra admin's consent for the Krusgraph app, once"],
     "how": "Chat. In Claude the answers come as text, and as cards with the map and buttons (MCP Apps) where the service "
            "has them turned on; in other MCP clients as text.",
     "builds": "Plans and checks, and every item the tools create on request after a dry run: API for GraphQL, semantic "
               "model, report, ontology, views, data agent, notebooks and a pipeline; drafts such as a dbt project and a "
               "data dictionary.",
     "data": "Krusgraph's service (Azure, Sweden Central), then your client and its AI provider (Anthropic for Claude): "
             "names, counts and the rows you ask for.",
     "data_short": "Krusgraph (Sweden Central) and your client's AI provider",
     "price": "Free; open source (MIT), as /pricing says.",
     "status": _status_claude,
     "lacks": ["Needs an AI chat licence and your admin's consent",
               "Cannot run or schedule a notebook or pipeline on the hosted service"]},
    {"key": "lovable", "name": "Krusgraph for Lovable", "short": "Plan and build an app's API from Lovable", "colour": "lav",
     "docs": "/lovable",
     "who": "People who build an app in Lovable on their Fabric data.",
     "needs": ["Lovable, with Krusgraph added as a custom MCP connector",
               "A Microsoft work account and a Fabric workspace on a capacity",
               "Your Entra admin's consent for the Krusgraph app, once"],
     "how": "In Lovable's chat Krusgraph plans, checks and creates the API for GraphQL; after three settings in Entra and "
            "the Fabric portal, Lovable's own Microsoft Fabric connector reads that API from your app.",
     "builds": "The API for GraphQL your app reads, and the same plans, checks and items as Krusgraph for Claude.",
     "data": "Krusgraph's service (Azure, Sweden Central), then Lovable and its AI provider; your app reads the API in "
             "Fabric.",
     "data_short": "Krusgraph (Sweden Central) and Lovable's AI provider",
     "price": "/pricing names the connector in Claude as free; Lovable reaches the same hosted service.",
     "status": _status_lovable,
     "lacks": ["No cards: text answers in Lovable's chat",
               "Three settings in Entra and the Fabric portal stay manual (introspection and permissions have no API)"]},
    {"key": "self", "name": "Krusgraph Open Source", "short": "The code under MIT, run by you", "colour": "mustard",
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
               "Krusgraph for Fabric is not part of it"]},
)

# What is built in Fabric, the diagram's right-hand column.
BUILT = ("Semantic model", "Report", "Ontology", "API for GraphQL", "Pipeline and notebooks", "Data agent", "Data product")

NO_AI = ("Krusgraph for Fabric (the Krusgraph Model item) uses no AI model: the keys and links come from the engine's named rules and "
         "the checks count your rows. A data agent it creates is Fabric's own item, and Fabric's AI answers there when "
         "someone asks it.")

# The decision guide, in the founder's words (9 November 2026), each to a product. "Code in VS Code" goes to Krusgraph for
# Claude: the connector works in other MCP clients too (the founder, 9 November 2026, evening).
DECIDE = (("I already use Claude", "claude"),
          ("We work in Fabric and do not want an AI chat", "fabric"),
          ("We build an app in Lovable", "lovable"),
          ("We code in VS Code", "claude"),
          ("Nothing may leave our Azure", "self"))

# Not products: how to try it, the features, and where to buy (the founder, 9 November 2026, evening).
NOT_PRODUCTS = ("The chat demo on this site and Check my tables (/check) are ways to try Krusgraph, not products. The drift "
                "monitor, the SAP pack and the dbt export are features of the products. Buying through Microsoft "
                "Marketplace is planned (/pricing).")


def val(w: dict, key: str):
    """A way's field; the ones that depend on today's status are functions."""
    return w[key]() if callable(w[key]) else w[key]


def way(key: str) -> dict:
    return next(w for w in WAYS if w["key"] == key)


def _e(s: str) -> str:
    return html.escape(s, quote=True)


# ------------------------------------------------------------------ the diagram ---------------------------------------

def _logo() -> str:
    """The one Krusgraph logo, the site's own (pages._LOGO): the engine wears it; the products have none of their own."""
    from .pages import _LOGO
    return _LOGO


def _arrow(cls: str, ends: int, fan_in: bool) -> str:
    """A connector between the columns: on a wide screen a fan of lines (the four products into the engine, the engine out to
    what is built), stretched to the column's height; on a phone a single arrow down (CSS shows one or the other)."""
    ys = [100 * (i + .5) / ends for i in range(ends)]
    lines = "".join(f'<path d="M0 {y:.1f} C20 {y:.1f} 20 50 40 50"/>' if fan_in else f'<path d="M0 50 C20 50 20 {y:.1f} 40 {y:.1f}"/>'
                    for y in ys)
    return (f'<div class="off-arrow {cls}" aria-hidden="true">'
            f'<svg class="off-fan" viewBox="0 0 40 100" preserveAspectRatio="none" focusable="false">{lines}</svg>'
            '<svg class="off-down" viewBox="0 0 24 32" focusable="false"><path d="M12 2v26M5 21l7 7 7-7"/></svg></div>')


def diagram_html(heading: str = "One engine, four products", level: int = 2, hid: str = "offering-h") -> str:
    """The product offering: the four products on the left, the one engine in the middle, what is built in Fabric on the right.
    Each way is a link to its docs (keyboard focus, a visible ring). The list under it says the same in words."""
    ways = "".join(
        f'<li class="off-way {w["colour"]}" data-way="{w["key"]}"><a href="{val(w, "docs")}" class="off-way-a">'
        f'<span class="off-way-h"><span class="off-way-n">{_e(w["name"])}</span></span>'
        f'<span class="off-way-who">{_e(val(w, "who"))}</span>'
        f'<span class="off-way-data"><span class="off-k">Data passes:</span> {_e(w["data_short"])}</span></a></li>'
        for w in WAYS)
    built = "".join(f"<li>{_e(b)}</li>" for b in BUILT)
    words = "".join(
        f'<li><a href="{val(w, "docs")}">{_e(w["name"])}</a>: for {_e(val(w, "who")[0].lower() + val(w, "who")[1:])} '
        f'Data passes: {_e(w["data_short"])}.</li>' for w in WAYS)
    return f"""<section class="wrap offering" id="offering" aria-labelledby="{hid}">
  <h{level} id="{hid}">{_e(heading)}</h{level}>
  <p class="intro">The same Krusgraph engine reads your tables, proposes keys and links with the rule behind each, and checks them against your rows. It comes as four products; each builds the same items in Fabric.</p>
  <figure class="off-fig" aria-describedby="offering-words-h">
    <div class="off-grid">
      <ul class="off-ways" aria-label="The four products">{ways}</ul>
      {_arrow("off-a1", len(WAYS), True)}
      <div class="off-engine"><div class="off-engine-box">{_logo()}<p class="off-engine-n">One Krusgraph engine</p><p class="off-engine-s">Keys, links and the rule behind each, checked against your rows</p></div></div>
      {_arrow("off-a2", len(BUILT), False)}
      <div class="off-built"><p class="off-built-h">Built in Microsoft Fabric</p><ul>{built}</ul></div>
    </div>
  </figure>
  <div class="off-words">
    <h{level + 1} id="offering-words-h" class="off-words-h">The diagram in words</h{level + 1}>
    <ul class="off-words-l">{words}</ul>
    <p class="muted tiny">All four use the same engine. What it builds in Fabric: {_e(", ".join(b.lower() if b != "API for GraphQL" else b for b in BUILT))}. Krusgraph for Fabric uses no AI model. <a href="{CHOOSE}">Which Krusgraph should I use?</a></p>
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
            f'<p class="muted tiny">{_e(NO_AI)} <a href="{CHOOSE}">Compare the four products</a>.</p></section>')


def choose_vars() -> dict[str, str]:
    return {"CHOOSE_DIAGRAM": diagram_html("The products: one engine, four ways in", 2, "choose-offering-h"),
            "CHOOSE_NOT_PRODUCTS": _e(NOT_PRODUCTS),
            "CHOOSE_COMPARE": compare_html(), "CHOOSE_DECIDE": decide_html(), "CHOOSE_NO_AI": _e(NO_AI),
            "CHOOSE_SHORT_START": short_html("start")}


def choose_md() -> str:
    """/choose.md: the same facts as Markdown."""
    out = ["# Which Krusgraph should I use?", "",
           "One Krusgraph engine, four products: " + ", ".join(w["name"] for w in WAYS) + ". Each builds the same items in "
           "Microsoft Fabric.", "",
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
    out += ["## Built in Microsoft Fabric", "", ", ".join(BUILT) + ".", "", NOT_PRODUCTS, ""]
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
