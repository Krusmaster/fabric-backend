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
for Claude (the MCP connector; other MCP clients sign in only where /mcp/connect is switched on), Krusgraph for Lovable and Krusgraph Open Source;
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


def _or(names: list[str]) -> str:
    return ", ".join(names[:-1]) + " or " + names[-1] if len(names) > 1 else "".join(names)


# n216: what the Claude card says about other MCP clients follows one fact, whether client registration (/mcp/connect)
# is switched on on this server (pages._registration_on, the same switch /start, /docs and tool_status read). Off: only
# Claude signs in to the hosted service. On: the clients tool_status records as tested there are named, and nothing is
# said about "any MCP client".
def _claude_who() -> str:
    names = _mcp_clients()
    if names:
        return (f"People who use Claude, or {_or(names)} (they sign in at /mcp/connect, which is switched on on this "
                "service), and want to ask about their Fabric tables in a chat.")
    return ("People who use Claude and want to ask about their Fabric tables in a chat. Other MCP clients cannot sign in "
            "to the hosted service today; they work when you host Krusgraph yourself (not tested).")


def _claude_short() -> str:
    names = _mcp_clients()
    return "The MCP connector, in Claude" + (f" and in {_or(names).replace(' or ', ' and ')}" if names else "")


def _claude_needs() -> list[str]:
    names = _mcp_clients()
    first = (f"Claude with a custom connector, or {_or(names)} signing in at /mcp/connect" if names else
             "Claude with a custom connector (other MCP clients cannot sign in to the hosted service today)")
    return [first, "A Microsoft work account and a Fabric workspace on a capacity",
            "Your Entra admin's consent for the Krusgraph app, once"]


def _claude_how() -> str:
    names = _mcp_clients()
    return ("Chat. In Claude the answers come as text, and as cards with the map and buttons (MCP Apps) where the service "
            "has them turned on" + (f"; in {_or(names).replace(' or ', ' and ')}, signed in at /mcp/connect, as text." if names else "."))


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
    {"key": "claude", "name": "Krusgraph for Claude", "short": _claude_short,
     "colour": "lav", "docs": "/start",
     "who": _claude_who,
     "needs": _claude_needs,
     "how": _claude_how,
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
# in VS Code or Cursor" -> "Krusgraph for Claude" with what is true today (decide_suffix; n216: no "any MCP client").
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
    names = [n for n in _mcp_clients() if n in ("VS Code", "Cursor")]
    if names:                                          # client registration on (n216: named, not "any MCP client")
        return f" ({' and '.join(names)} sign in at /mcp/connect)"
    return " (the hosted service cannot sign VS Code or Cursor in today: host your own Krusgraph)"

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


# ---- the mascot pictures (n183, the founder's decision of 9 November 2026; n216, 11 November 2026) --------------------
# Each product card has a mascot with a symbol we draw ourselves, in Krusgraph's style: a data table for Fabric, a speech
# bubble for Claude, an app screen for Lovable, code brackets for Open Source, with "for ..." under it. n216: the figure is
# the glossy 3D one from the overview film and the home page (static/mascots/<kind>.webp, cut from the film's closing
# frame by tools/mascot_renders.py, 112 px for a 56 px slot, so crisp at 2x), the same characters as the film and the
# sales deck; the film has no render of a mascot holding a prop, so the symbol is a small badge at the figure's side
# (docs/MASCOT-ART-NEEDED.md lists the renders that would let the figure hold it). No partner logo is drawn or
# referenced: partner names are plain text. The pictures are decoration with alt text; the site's mascot switch hides
# them (mascot-only).

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
MASCOT_RENDERS = "/static/mascots"
RENDER_PX = 112                 # the renders' size; shown at 56 CSS px


def render_src(kind: str, ext: str = "webp") -> str:
    """The 3D render of one figure (onto, thinker, builder), transparent ground."""
    return f"{MASCOT_RENDERS}/{kind}.{ext}"


def picture_label(key: str) -> str:
    from . import mcp_apps_mascots as M
    kind, _sym, what, _for = PICTURES[key]
    return f"{M.NAMES[kind]}, the Krusgraph mascot, with {what}: Krusgraph {_for}"


def picture_figure(key: str) -> str:
    """One product's picture: the 3D figure and its symbol as a badge, one image for assistive technology (role="img")."""
    kind, sym, _what, _for = PICTURES[key]
    return (f'<span class="off-pic-fig" role="img" aria-label="{_e(picture_label(key))}">'
            f'<img class="off-pic-img" src="{render_src(kind)}" width="56" height="56" alt="" decoding="async">'
            f'<svg class="off-pic-prop" viewBox="-2 -2 44 32" aria-hidden="true" focusable="false">{SYMBOLS[sym]}</svg></span>')


def picture_html(key: str) -> str:
    _kind, _sym, _what, label = PICTURES[key]
    return (f'<span class="off-pic mascot-only">{picture_figure(key)}'
            f'<span class="off-pic-for" aria-hidden="true">{_e(label)}</span></span>')


def sources() -> list[tuple[str, str]]:
    """n206: the diagram's "Your tables in Fabric", each with its status word, straight from tool_status.SOURCES (the
    status record the site uses): Lakehouse tested end to end, Warehouse and SQL database experimental. Mirrored
    databases are not listed until the record has them (planned, n201)."""
    from . import tool_status as ts
    return [(n, ts.source_word(t)) for n, t in ts.SOURCES]


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
    src = sources()
    source_items = "".join(f'<li>{_e(n)} <span class="off-src-st">{_e(w)}</span></li>' for n, w in src)
    source_words = ", ".join(f"{n[0].lower() + n[1:] if n != 'SQL database' else n} ({w})" for n, w in src)
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
      <div class="off-src"><p class="off-col-h">Your tables in Fabric</p><ul>{source_items}</ul></div>
      {_arrow("off-a1")}
      <div class="off-engine"><div class="off-engine-box">{_logo()}<p class="off-engine-n">One Krusgraph engine</p><p class="off-engine-s">{_e(ENGINE_SUB)}</p></div></div>
      {_arrow("off-a2")}
      <div class="off-built"><p class="off-col-h off-built-h">Built in Fabric</p><ul>{built}</ul></div>
    </div>
  </figure>
  <details class="off-words">
    <summary id="offering-words-h" class="off-words-h">The diagram in words</summary>
    <div id="offering-words">
    <p>Your tables in Fabric ({_e(source_words)}) go into one Krusgraph engine, which proposes keys and links and checks them against your rows. What it builds lands in Fabric: {_e(built_words)}. The four products are the ways to drive the engine:</p>
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
            "CHOOSE_SHORT_START": short_html("start"), "CHOOSE_ALTERNATIVES": alternatives_html()}


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
    out += alternatives_md()
    out += ["## Built in Microsoft Fabric", "", ", ".join(BUILT) + ".", "", APP_NOTE, "", NOT_PRODUCTS, "",
            f"Security, data and what is in place: {o}/trust.md", ""]
    return "\n".join(out)


# n205: "Why not just Microsoft's tools?", the short comparison on /choose (linked from /docs). Plain text names, no logos;
# each row says what the tool does in the words of its own pages as docs/COMPANION-MCP.md and docs/FAQ-COMPETITION.md
# quote them, and what Krusgraph adds; nothing about what they cannot do, no measurement (none exists), nothing non-public.
ALTERNATIVES_H = "Why not just Microsoft's tools?"
ALTERNATIVES_ID = "why-not-microsoft"
ALTERNATIVES_INTRO = ("Krusgraph works beside these tools, not instead of them. What it adds in each case is the same: keys and "
                      "relationships with the rule behind each, checked against your rows before anything is built.")
ALTERNATIVES = (
    ("Fabric API for GraphQL, set up by hand",
     "You create the API item in Fabric, pick the tables and define the relationships between them yourself.",
     "Proposes the keys and relationships with the rule for each, checks them against the rows (duplicate keys, references "
     "with no match), and creates or updates the API from the plan you reviewed, keeping its existing field names."),
    ("GraphQL MCP and Lovable's Fabric connector",
     "Let an AI agent or an app query an existing Fabric API for GraphQL.",
     "Builds the API they read, with relationships that were checked against the rows first; Lovable's connector reads an "
     "API Krusgraph made (a Lovable app read one live on 30 October 2026)."),
    ("Fabric MCP, Fabric IQ MCP and the Power BI Modeling MCP",
     "Give an AI agent access to Fabric's APIs, item definitions and OneLake, to questions in DAX on Power BI content, and to "
     "editing semantic models.",
     "Works out which tables relate and on what rule, with the counts, and builds the model, ontology or API from that plan; "
     "it can sit beside them in the same AI client."),
    ("Power BI's automatic relationships",
     "Power BI Desktop can detect relationships when data is loaded.",
     "Shows the rule behind each relationship and the counts from all rows: keys that are not unique, references with no "
     "matching row and the total that doubles after a join; the same plan then builds more than a Power BI model."),
    ("dbt tests",
     "unique, not_null and relationships tests run in your dbt project on the columns you name.",
     "Proposes which keys and relationships to test and writes the dbt sources file with those tests (dbt_schema); the "
     "check also runs without a dbt project."),
)


def alternatives_html() -> str:
    rows = "".join(f'<tr><th scope="row">{_e(n)}</th><td>{_e(d)}</td><td>{_e(a)}</td></tr>' for n, d, a in ALTERNATIVES)
    return (f'<section class="wrap choose-alternatives" id="{ALTERNATIVES_ID}" aria-labelledby="{ALTERNATIVES_ID}-h">'
            f'<h2 id="{ALTERNATIVES_ID}-h">{_e(ALTERNATIVES_H)}</h2><p class="intro">{_e(ALTERNATIVES_INTRO)}</p>'
            f'<div class="table-wrap" tabindex="0" role="region" aria-labelledby="{ALTERNATIVES_ID}-h"><table>'
            '<thead><tr><th scope="col">Tool</th><th scope="col">What it does</th><th scope="col">What Krusgraph adds</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></div>'
            '<p class="muted tiny">Krusgraph is independent and not made by Microsoft; the names are used descriptively. '
            'More: <a href="/docs/reference/with-microsoft-s-fabric-mcp-servers">With Microsoft\'s Fabric MCP servers</a> in the docs. '
            'Security, data and what is in place: <a href="/trust">Security and data</a>.</p></section>')


def alternatives_md() -> list[str]:
    out = [f"## {ALTERNATIVES_H}", "", ALTERNATIVES_INTRO, "", "| Tool | What it does | What Krusgraph adds |", "| --- | --- | --- |"]
    out += [f"| {n} | {d} | {a} |" for n, d, a in ALTERNATIVES]
    return out + [""]


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
