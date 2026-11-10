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
one Krusgraph logo everywhere, no product logos. n183 (the founder's decision, 9 November 2026): each product card has
its mascot hugging a symbol we draw ourselves (PICTURES); still no product logo and no partner logo. The chat on krusgraph.com and /check are ways
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


# The four products, in the founder's order. `colour` is a site token (n183: the colour of the product's mascot, mustard
# for Open Source), used for a border only: no product logo. `data` says where the data passes.
WAYS = (
    {"key": "fabric", "name": "Krusgraph for Fabric", "short": "The Krusgraph Model item in Fabric", "colour": "sage",
     "docs": FABRIC_DOCS,
     "who": "Teams that work in Microsoft Fabric and do not want an AI chat.",
     "needs": ["A Fabric workspace on a capacity (Power BI Pro alone is not enough)",
               "Your organisation in the pilot, and the tenant setting for workloads not validated by Microsoft",
               "Your Entra admin's consent for the workload app, once"],
     "how": "The Krusgraph Model item, which you click through in Fabric: choose a lakehouse and a schema, review the keys "
            "and links, check them against the rows, choose outputs, see the dry run, then Create. No AI.",
     "builds": "Silver notebook, gold views, pipeline, semantic model, report, API for GraphQL, ontology, data agent and an "
               "App (Rayfin, preview), with a data product over them and the data flow drawn.",
     "data": "Krusgraph's engine (Azure, Sweden Central) and your Fabric. It uses no AI model, so nothing goes to an AI "
             "provider.",
     "data_short": "Krusgraph (Sweden Central) only; no AI",
     "price": "Not on /pricing yet: the pilot is on request.",
     "status": lambda: _status_fabric(),
     "lacks": ["No questions in your own words: there is no chat",
               "Pilot only; not in Fabric's Workload Hub",
               "Runs or schedules the pipeline only when you tick Run once or Schedule and your admin has granted "
               "DataPipeline.Execute.All (n185)"]},
    {"key": "claude", "name": "Krusgraph for Claude", "short": "The MCP connector, in Claude and other MCP clients",
     "colour": "lav", "docs": "/start",
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
    {"key": "lovable", "name": "Krusgraph for Lovable", "short": "Plan and build an app's API from Lovable", "colour": "coral",
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

# What is built in Fabric, the diagram's right-hand column. n183: the App (Rayfin, preview), which only the Krusgraph Model
# item creates (APP_NOTE; docs/RAYFIN-APP.md).
BUILT = ("Semantic model", "Report", "Ontology", "API for GraphQL", "Pipeline and notebooks", "Data agent", "App (Rayfin, preview)",
         "Data product")
APP_NOTE = ("The App (Rayfin, preview) is built by Krusgraph for Fabric only: Create makes the empty App item, and its pages "
            "and read-only connector come as a package you publish (no App item definition is documented).")

NO_AI = ("Krusgraph for Fabric (the Krusgraph Model item) uses no AI model: the keys and links come from the engine's named rules and "
         "the checks count your rows. A data agent it creates is Fabric's own item, and Fabric's AI answers there when "
         "someone asks it.")

# The decision guide, in the founder's words (9 November 2026), each to a product. "Code in VS Code" goes to Krusgraph for
# Claude: the connector works in other MCP clients too (the founder, 9 November 2026, evening). n183: the row reads "We code
# in VS Code or Cursor" -> "Krusgraph for Claude (any MCP client)" (decide_suffix).
DECIDE = (("I already use Claude", "claude"),
          ("We work in Fabric and do not want an AI chat", "fabric"),
          ("We build an app in Lovable", "lovable"),
          ("We code in VS Code or Cursor", "claude"),
          ("Nothing may leave our Azure", "self"))


def decide_suffix(q: str) -> str:
    """What follows the product's name in a row of the guide. VS Code and Cursor sign in to the hosted service only through
    client registration (/mcp/connect), so the row says so, or that the hosted service cannot sign them in today."""
    if q != "We code in VS Code or Cursor":
        return ""
    if _lovable_on():                                  # client registration on
        return " (any MCP client, through /mcp/connect)"
    return " (any MCP client, though the hosted service cannot sign VS Code or Cursor in today: host your own Krusgraph)"

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
# n183 (the founder, 9 November 2026): the diagram is a data flow, left to right: your tables in Fabric -> one Krusgraph
# engine -> what is built in Fabric, with the four products above the engine as the ways to drive it. On a phone it stacks
# in the same order as the HTML: the ways in, the tables, the engine, what is built.

def _logo() -> str:
    """The one Krusgraph logo, the site's own (pages._LOGO): the engine wears it; the products have none of their own."""
    from .pages import _LOGO
    return _LOGO


def _arrow(cls: str, down_only: bool = False) -> str:
    """A connector: on a wide screen an arrow to the right (or down, for the ways in above the engine), on a phone an arrow
    down (CSS shows one or the other)."""
    right = ('' if down_only else '<svg class="off-right" viewBox="0 0 44 24" focusable="false"><path d="M3 12h36M32 5l7 7-7 7"/></svg>')
    return (f'<div class="off-arrow {cls}" aria-hidden="true">{right}'
            '<svg class="off-down" viewBox="0 0 24 32" focusable="false"><path d="M12 2v26M5 21l7 7 7-7"/></svg></div>')


# ---- the mascot pictures (n183, the founder's decision of 9 November 2026) -------------------------------------------
# Each product card has a mascot hugging a symbol we draw ourselves, in Krusgraph's style: a data table for Fabric, a
# speech bubble for Claude, an app screen for Lovable, code brackets for Open Source, with "for ..." under it. The figures
# are the site's own (static/mascots.js KINDS, read by mcp_apps_mascots), drawn flat, in the heart pose's hug (the arms
# turned inwards), with no gradient ids, so four on a page never clash. No partner logo is drawn or referenced: partner
# names are plain text. The pictures are decoration with alt text; the site's mascot switch hides them (mascot-only).

INK = "#3A3340"
SYMBOLS = {      # the symbol in a 40 x 28 box
    "table": (f'<rect x="1" y="1" width="38" height="26" rx="4" fill="#fff" stroke="{INK}" stroke-width="1.6"/>'
              '<path d="M1 5a4 4 0 0 1 4-4h30a4 4 0 0 1 4 4v3H1z" fill="#E3A93B"/>'
              f'<path d="M1 8h38M1 14.5h38M1 21h38M14 8v19M27 8v19" stroke="{INK}" stroke-width="1.1" opacity=".55"/>'
              f'<rect x="1" y="1" width="38" height="26" rx="4" fill="none" stroke="{INK}" stroke-width="1.6"/>'),
    "bubble": (f'<path d="M8 1h24a7 7 0 0 1 7 7v8a7 7 0 0 1-7 7H16l-8 5 1.5-5.2A7 7 0 0 1 1 16V8a7 7 0 0 1 7-7z" fill="#fff" '
               f'stroke="{INK}" stroke-width="1.6" stroke-linejoin="round"/>'
               '<circle cx="12" cy="12" r="3" fill="#F2735C"/><circle cx="20" cy="12" r="3" fill="#9DB8A0"/>'
               '<circle cx="28" cy="12" r="3" fill="#A99AD8"/>'),
    "screen": (f'<rect x="1" y="1" width="38" height="26" rx="4" fill="#fff" stroke="{INK}" stroke-width="1.6"/>'
               f'<path d="M1 7h38" stroke="{INK}" stroke-width="1.1" opacity=".55"/>'
               '<circle cx="5.5" cy="4" r="1.3" fill="#F2735C"/><circle cx="9.5" cy="4" r="1.3" fill="#E3A93B"/>'
               '<circle cx="13.5" cy="4" r="1.3" fill="#9DB8A0"/>'
               '<rect x="5" y="11" width="12" height="12" rx="2.5" fill="#CDDFCD"/>'
               f'<path d="M21 13h14M21 17.5h10M21 22h12" stroke="{INK}" stroke-width="1.6" stroke-linecap="round" opacity=".7"/>'),
    "code": (f'<rect x="1" y="1" width="38" height="26" rx="6" fill="#fff" stroke="{INK}" stroke-width="1.6"/>'
             f'<path d="M14 8l-6 6 6 6M26 8l6 6-6 6" fill="none" stroke="{INK}" stroke-width="2.6" stroke-linecap="round" '
             'stroke-linejoin="round"/><path d="M22.5 6l-5 16" stroke="#F2735C" stroke-width="2.6" stroke-linecap="round"/>'),
}
# product -> (figure, symbol, what the symbol is, "for ...")
PICTURES = {"fabric": ("onto", "table", "a data table", "for Fabric"),
            "claude": ("thinker", "bubble", "a speech bubble", "for Claude"),
            "lovable": ("builder", "screen", "an app screen", "for Lovable"),
            "self": ("onto", "code", "code brackets", "Open Source")}
# where the symbol sits on each figure (x, y, width, height in the figure's 120 x 120 box): below the eyes, between the arms
_HUG = {"onto": (30, 77, 60, 30), "thinker": (35, 70, 50, 34), "builder": (35, 66, 50, 36)}
_HUG_TURN = 44                  # degrees each arm turns inwards (the heart pose turns 38)


def picture_svg(key: str) -> str:
    """One product's picture: the mascot hugging its symbol, flat inline SVG with alt text (role="img")."""
    from . import mcp_apps_mascots as M
    kind, sym, what, _for = PICTURES[key]
    k = M.kinds()[kind]
    n = M._n
    eyes = "".join(f'<circle cx="{n(x)}" cy="{n(y)}" r="{n(k["eyeR"])}" fill="#1B1B1F"/>'
                   f'<circle cx="{n(x + 1.2)}" cy="{n(y - 1.3)}" r="1.15" fill="#fff"/>' for x, y in k["eyes"])
    blush = "".join(f'<ellipse cx="{n(x)}" cy="{n(y)}" rx="5" ry="2.8" fill="{k["cheek"]}" opacity=".6"/>' for x, y in k["blush"])
    hx, hy, hrx, hry, hrot = k["hl"]
    sx, sy, srx, sry = k["shadow"]
    bx, by, bw, bh = _HUG[kind]
    scale = min(bw / 40, bh / 28)
    tx, ty = bx + (bw - 40 * scale) / 2, by + (bh - 28 * scale) / 2

    def arm(a: list, turn: float) -> str:
        x, y, angle = a
        rx, ry = k["armRX"], k["armRY"]
        return (f'<g transform="rotate({n(angle + turn)} {n(x)} {n(y)})">'
                f'<ellipse cx="{n(x)}" cy="{n(y + ry - 3)}" rx="{n(rx)}" ry="{n(ry)}" fill="{k["fill"]}" stroke="{k["dark"]}" '
                f'stroke-width="1.1" stroke-opacity=".7"/>'
                f'<ellipse cx="{n(x - 1.5)}" cy="{n(y + 2)}" rx="2.4" ry="4" fill="#fff" opacity=".22"/></g>')
    label = f'{M.NAMES[kind]}, the Krusgraph mascot, hugging {what}: Krusgraph {_for}'
    return (f'<svg class="off-pic-svg" viewBox="8 16 104 98" role="img" aria-label="{_e(label)}" focusable="false">'
            f'<ellipse cx="{n(sx)}" cy="{n(sy)}" rx="{n(srx)}" ry="{n(sry)}" fill="{k["dark"]}" opacity=".35"/>'
            f'<path d="{k["body"]}" fill="{k["fill"]}" stroke="{k["dark"]}" stroke-width="1.2" stroke-opacity=".6"/>'
            f'<ellipse cx="{n(hx)}" cy="{n(hy)}" rx="{n(hrx)}" ry="{n(hry)}" fill="{k["light"]}" opacity=".85" '
            f'transform="rotate({n(hrot)} {n(hx)} {n(hy)})"/>{blush}{eyes}'
            f'<g transform="translate({tx:.2f} {ty:.2f}) scale({scale:.3f})">{SYMBOLS[sym]}</g>'
            + arm(k["armL"], -_HUG_TURN) + arm(k["armR"], _HUG_TURN) + "</svg>")


def picture_html(key: str) -> str:
    _kind, _sym, _what, label = PICTURES[key]
    return (f'<span class="off-pic mascot-only">{picture_svg(key)}'
            f'<span class="off-pic-for" aria-hidden="true">{_e(label)}</span></span>')


SOURCES = ("Lakehouse", "Warehouse", "Mirrored databases")
ENGINE_SUB = "Keys and links, checked against your rows"


def diagram_html(heading: str = "One engine, four products", level: int = 2, hid: str = "offering-h") -> str:
    """The product offering as a data flow: your tables in Fabric -> one Krusgraph engine -> built in Fabric, the four
    products above the engine as the ways to drive it. Each product is a link to its docs (keyboard focus, a visible ring).
    The words under it, in a collapsed <details>, say the same for screen readers and anyone who prefers text."""
    ways = "".join(
        f'<li class="off-way {w["colour"]}" data-way="{w["key"]}"><a href="{val(w, "docs")}" class="off-way-a">'
        f'{picture_html(w["key"])}'
        f'<span class="off-way-h"><span class="off-way-n">{_e(w["name"])}</span></span>'
        f'<span class="off-way-who">{_e(val(w, "who"))}</span>'
        f'<span class="off-way-data"><span class="off-k">Data passes:</span> {_e(w["data_short"])}</span></a></li>'
        for w in WAYS)
    built = "".join(f"<li>{_e(b)}</li>" for b in BUILT)
    sources = "".join(f"<li>{_e(s)}</li>" for s in SOURCES)
    words = "".join(
        f'<li><a href="{val(w, "docs")}">{_e(w["name"])}</a>: for {_e(val(w, "who")[0].lower() + val(w, "who")[1:])} '
        f'Data passes: {_e(w["data_short"])}.</li>' for w in WAYS)
    built_words = ", ".join(b if b.startswith(("API", "App")) else b.lower() for b in BUILT)
    return f"""<section class="wrap offering" id="offering" aria-labelledby="{hid}">
  <h{level} id="{hid}">{_e(heading)}</h{level}>
  <p class="intro">Your tables in Fabric go into one Krusgraph engine, which proposes keys and links with the rule behind each and checks them against your rows. What it builds lands in Fabric. Four products are the ways to drive it.</p>
  <figure class="off-fig" aria-describedby="offering-words">
    <div class="off-flow">
      <div class="off-in"><p class="off-in-h">Choose how you work</p>
        <ul class="off-ways" aria-label="The four products: the ways to drive the engine">{ways}</ul></div>
      {_arrow("off-a0", down_only=True)}
      <div class="off-src"><p class="off-col-h">Your tables in Fabric</p><ul>{sources}</ul></div>
      {_arrow("off-a1")}
      <div class="off-engine"><div class="off-engine-box">{_logo()}<p class="off-engine-n">One Krusgraph engine</p><p class="off-engine-s">{_e(ENGINE_SUB)}</p></div></div>
      {_arrow("off-a2")}
      <div class="off-built"><p class="off-col-h off-built-h">Built in Fabric</p><ul>{built}</ul></div>
    </div>
  </figure>
  <details class="off-words">
    <summary id="offering-words-h" class="off-words-h">The diagram in words</summary>
    <div id="offering-words">
    <p>Your tables in Fabric ({_e(", ".join(s.lower() for s in SOURCES))}) go into one Krusgraph engine, which proposes keys and links and checks them against your rows. What it builds lands in Fabric: {_e(built_words)}. The four products are the ways to drive the engine:</p>
    <ul class="off-words-l">{words}</ul>
    <p class="muted tiny">{_e(APP_NOTE)} Krusgraph for Fabric uses no AI model. <a href="{CHOOSE}">Which Krusgraph should I use?</a></p>
    </div>
  </details>
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
                    f'<a href="{val(way(k), "docs")}">{_e(way(k)["name"])}</a>{_e(decide_suffix(q))}</li>' for q, k in DECIDE)
    return f'<ul class="decide">{items}</ul>'


def decide_md() -> str:
    """n188: the decision guide in Markdown, first on the docs start page (DOCS.md's {{WHICH_KRUSGRAPH}}), site-relative links."""
    rows = "\n".join(f"- “{q}” → [{way(k)['name']}]({val(way(k), 'docs')}){decide_suffix(q)}" for q, k in DECIDE)
    return f"**Which Krusgraph should I use?**\n\n{rows}\n\n[Compare the four products]({CHOOSE})."


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
    out += [f"- \"{q}\" → [{way(k)['name']}]({o}{val(way(k), 'docs')}){decide_suffix(q)}" for q, k in DECIDE]
    out += ["", NO_AI, ""]
    for w in WAYS:
        out += [f"## {w['name']}", ""]
        for key, label in ROWS:
            v = val(w, key)
            out.append(f"- **{label}:** " + ("; ".join(v) if isinstance(v, (list, tuple)) else v))
        out += [f"- **Docs:** {o}{val(w, 'docs')}", ""]
    out += ["## Built in Microsoft Fabric", "", ", ".join(BUILT) + ".", "", APP_NOTE, "", NOT_PRODUCTS, ""]
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
