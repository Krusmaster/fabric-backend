"""The /use-cases page: three synthetic examples drawn as maps, the tasks a visitor starts from, and ten industries
told as the customer's problem (n59: the page was 5 800 words with ten industry sketches; reviewers found it too long,
and the sketches' labels read as if the links were missing; n68: the industries are back as problems, not tables).

Each map is the engine's own run on the example, the same events /check draws (`browser_check.analyze`), embedded in
the page as JSON and drawn by `static/map.js`, the renderer /check uses. Nothing on the page is typed by hand about a
key or a link: the finding buttons under a map are the engine's findings.

Text fields use `backticks` for code; everything is HTML-escaped when rendered.
"""
from __future__ import annotations

import html
import json
import re
from functools import lru_cache

from .tool_status import create_api_status, phrase, task_status

FOOTNOTE = "The examples are synthetic: invented tables and rows, not customer projects."
WORD_CAP = 2200          # tests/test_use_cases.py keeps the page's main text under this (n68: 1 000 plus the ten industries at up to 120 words each)

# (example on /check, anchor, heading, one or two sentences, button)
EXAMPLES = [
    ("sample", "try-retail", "Retail and e-commerce",
     "A shop: customers, orders, lines, products. Summed over its lines the order total comes out twice, and "
     "`orders.ship_to_id` names no table, so the engine suggests a target for you to decide on.",
     "Open the shop example in /check"),
    ("sap", "try-sap", "Manufacturing and sales with SAP",
     "Sales orders, deliveries and billing documents from two SAP clients. The links come from public SAP knowledge "
     "(the SAP pack), with the client (MANDT) in every key.",
     "Open the SAP sales tables in /check"),
    ("crm", "try-crm", "Sales and CRM",
     "Accounts in Salesforce, customers in the ERP. No column name joins the two systems; the engine finds the link in "
     "the values and shows it as a suggestion.",
     "Open Salesforce + ERP in /check"),
]

# n68: the ten industries are back (they went in n59), told as the problem a customer brings rather than as table
# sketches: a heading, the question in the customer's words, what they get, and the nearest runnable example on /check.
# No "typical tables" and no map here: the maps are the three examples above. Each entry stays under
# INDUSTRY_WORD_CAP words on the page (tests/test_use_cases.py). No logistics, warehouse or supply-chain theme.
INDUSTRY_WORD_CAP = 120
# n224 (S1 section 3.2): no dataset stands behind the ten cards, so each says so, on the page and in the Markdown
ILLUSTRATIVE = "Illustrative, not run on customer data"
INDUSTRIES: list[dict] = [
    {"slug": "retail", "name": "Retail and e-commerce", "example": "sample",
     "problem": "Our order total in the sales report is twice what finance has, and a return never finds its order line.",
     "get": "A map of customers, orders, lines, products and returns with the reason for every link; the order amount counted "
            "once per order, not once per line; a return tied to the exact order line. What stays open is marked for you to decide."},
    {"slug": "manufacturing", "name": "Manufacturing", "example": "sap",
     "problem": "A work order points at an item, the bill of materials points at the same item twice, and nobody is sure which column means the parent.",
     "get": "Each link with its reason, the two roles kept apart and marked for your check, and the orders, deliveries and invoices "
            "that do not match counted before anyone builds a report on them."},
    {"slug": "saas", "name": "SaaS and subscriptions", "example": "crm",
     "problem": "Which account uses the service and which one pays? Our revenue per customer changes depending on who answers.",
     "get": "The using account and the paying account as two links with their reasons, invoices and their lines counted once, "
            "and a plan you can show finance before the model is built."},
    {"slug": "professional-services", "name": "Professional services", "example": "sample",
     "problem": "Which hours are still unbilled? Hours and invoices live in two tables and the join between them is a guess.",
     "get": "Hours linked to their project and invoice with the reason, the hours with no invoice counted, and the invoice total "
            "summed once, not once per time entry."},
    {"slug": "aml", "name": "Financial services: AML", "example": "crm",
     "problem": "Trace a transaction through its account holders when the same customer appears under two numbers in two systems.",
     "get": "One map across customers, accounts, holders, transactions and alerts with each link explained; a link found in the "
            "values rather than in the names is shown as a suggestion to confirm, never assumed."},
    {"slug": "financial-crime", "name": "Financial crime prevention", "example": "crm",
     "problem": "Fraud, sanctions and KYC keep separate cases for the same customer, and bringing them into one view is manual work every time.",
     "get": "The customer at the centre with cases, alerts, screening hits and logins linked and explained; a reference that matches "
            "no row is counted before the view is trusted."},
    {"slug": "pharma-research", "name": "Pharmaceutical research", "example": "sap",
     "problem": "A visit number repeats per subject, so results joined on it alone come out wrong.",
     "get": "A key that needs two columns is named as such, the duplicates a single column would give are counted, and coded "
            "columns are listed as open questions rather than linked by guess."},
    {"slug": "environment", "name": "Environment and sustainability", "example": "sample",
     "problem": "Which emission factor did this activity actually use? The report cannot show it.",
     "get": "Each activity linked to the factor row behind it, meters to their site, purchases to supplier and site, every link "
            "with its reason; a match by date range rather than by key is pointed out as work for a view, not hidden."},
    {"slug": "property", "name": "Property and real estate", "example": "sample",
     "problem": "Which unit does this maintenance request belong to, and who is the tenant right now?",
     "get": "Property, unit, lease, tenant and request on one map with the reason for each link; the column that names a role "
            "(reported by) marked as the weaker link and left for your check; nothing created until you ask."},
    {"slug": "education", "name": "Education", "example": "sap",
     "problem": "A student takes the same course twice, and the grade report counts one of them or both, depending on the join.",
     "get": "The enrolment key that needs student, course and term together, the duplicates a shorter key would give counted in "
            "your rows, and a plan the registrar can read before any dashboard."},
]

# The three tasks a visitor starts from (the website brief of 26 October 2026): what they say, what they get and the
# tools; each tool's status comes from tool_status. Worded as tasks, not as claims about customers.
TASKS = [
    {"slug": "inherited", "quote": "I inherited a lakehouse nobody has documented.",
     "shows": "An overview: the central tables, how they relate, and the questions you still need to clear up.",
     "tools": ["analyze_schema", "plan_backend", "data_dictionary"],
     "example": ("try-retail", "the shop example on this page")},
    {"slug": "join", "quote": "I need to check how these tables should join.",
     "shows": "A suggested join with its reason, a check against the rows, and what stays uncertain.",
     "tools": ["join_path", "validate_plan", "suggest_relationships"],
     "example": ("try-crm", "Salesforce and the ERP, joined by values")},
    {"slug": "app", "quote": "I want to build an app on this data.",
     "shows": "The reviewed plan, an API created from it in your workspace, and the setup steps the app still needs.",
     "tools": ["create_backend", "app_starter"],
     "example": ("try-sap", "the SAP order-to-cash tables")},
]

OUTPUTS = [   # (what, for what, status in the docs' words, from tool_status; "planned" draws the chip dashed)
    ("GraphQL API", "an API for GraphQL item in your workspace, for an app or for questions in Claude",
     f"{create_api_status()[0].lower() + create_api_status()[1:]}; querying an existing one: {phrase('query_graphql')}"),
    ("SQL views", "wide T-SQL views over the plan's joins on the SQL analytics endpoint", phrase("create_views")),
    ("Fabric IQ ontology draft", "entity types, keys and relationships (preview)", phrase("ontology_draft")),
    ("Semantic model", "a Power BI model in TMDL from the same keys",
     f"the draft: {phrase('semantic_model_draft')}; the item: {phrase('create_semantic_model')}"),
    ("Data agent", "a Fabric data agent with the plan as instructions", phrase("create_data_agent")),
]



# ------------------------------------------------------------------ engine -----------------------------------------

@lru_cache(maxsize=None)
def example_map(kind: str) -> dict:
    """The engine's run on one /check example, cut to what the map draws: its step events and up to three findings."""
    from .browser_check import analyze
    events: list[dict] = []
    r = analyze(kind, emit=events.append)
    keep = {"keys": ("tables",), "relationships": ("relationships",), "validate": ("orphans",), "suggest": ("suggested",)}
    steps = [{"step": e["step"], **{k: e.get(k) or [] for k in keep[e["step"]]}} for e in events if e["step"] in keep]
    for e in steps:
        for t in e.get("tables", []):
            t.pop("columns", None)
    picked = r["findings"][:2] + r["suggestions"][:1]
    picked += [f for f in r["findings"] + r["suggestions"] if f not in picked][:3 - len(picked)]
    return {"steps": steps, "findings": [{"title": f["title"], "link": f["link"], "amount": f["amount"], "table": f["table"]} for f in picked],
            "tables": len(r["tables"]), "relationships": len(r["relationships"])}


# ------------------------------------------------------------------ html -------------------------------------------

def _inline(s: str) -> str:
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", html.escape(s, quote=False))


def _json(data) -> str:
    """JSON safe inside <script type="application/json">: no "</" can close the element."""
    return json.dumps(data, separators=(",", ":")).replace("</", "<\\/")


def examples_html() -> str:
    e = html.escape
    out = []
    for kind, anchor, title, text, button in EXAMPLES:
        m = example_map(kind)
        finds = "".join(f'<li><button type="button" class="check-finding-link" data-finding="{i}" aria-pressed="false">{e(f["title"])}</button></li>'
                        for i, f in enumerate(m["findings"]))
        out.append(f"""<li class="card uc-ex" id="{anchor}"><span class="pill demo">Synthetic data</span>
  <h3>{e(title)}</h3>
  <p>{_inline(text)}</p>
  <figure class="uc-map" data-map="{kind}">
    <div class="check-map" id="map-{kind}" tabindex="0" role="region" aria-label="Map of the {e(title)} example"><noscript><p class="muted tiny">The map needs JavaScript; /check lists every table and relationship.</p></noscript></div>
    <figcaption class="muted tiny">{m["tables"]} tables, {m["relationships"]} relationships. Each line carries its rule; a suggestion is dashed.</figcaption>
    <script type="application/json" class="uc-map-data">{_json(m)}</script>
  </figure>
  <p class="tiny uc-ex-h">Mark a finding on the map:</p>
  <ul class="uc-ex-finds">{finds}</ul>
  <a class="btn primary small" href="/check?example={kind}" data-try="{kind}">{e(button)}</a></li>""")
    return "".join(out)


def _example_title(kind: str) -> str:
    return next(title for k, _a, title, _t, _b in EXAMPLES if k == kind)


def industries_html() -> str:
    """One card per industry: the heading, the problem in the customer's words, what they get, and the button to the
    nearest runnable example on /check (synthetic data)."""
    e = html.escape
    return "".join(
        f'<li class="card soft uc-ind" id="{e(i["slug"])}"><h3>{e(i["name"])}</h3>'
        f'<p class="uc-ind-tag"><span class="chip chip-planned">{e(ILLUSTRATIVE)}</span></p>'
        f'<p class="uc-task-q">“{e(i["problem"])}”</p>'
        f'<p><strong>What you get.</strong> {e(i["get"])}</p>'
        f'<p class="uc-ind-go"><a class="btn secondary small" href="/check?example={e(i["example"])}" data-try-like="{e(i["example"])}">Try a similar example</a>'
        f'<span class="muted tiny">{e(_example_title(i["example"]))}, synthetic data</span></p></li>'
        for i in INDUSTRIES)


def industry_words(ind: dict) -> int:
    """The words one industry puts on the page (heading, problem, what you get, the button and its note)."""
    text = re.sub(r"<[^>]+>", " ", industries_html().split(f'id="{ind["slug"]}"', 1)[1].split("</li>", 1)[0])
    return len(html.unescape(text).split())


def outputs_html() -> str:
    e = html.escape
    return "".join(f'<li{" class=planned" if tag == "planned" else ""}><strong>{e(name)}</strong><span>{e(what)}</span>'
                   f'{f"<em>{e(tag)}</em>" if tag else ""}</li>' for name, what, tag in OUTPUTS)


def _tools(task: dict) -> str:
    return ", ".join(f"`{n}`" for n in task["tools"])


def tasks_html() -> str:
    e = html.escape
    return "".join(
        f'<li class="uc-task" id="task-{e(t["slug"])}"><p class="uc-task-q">“{e(t["quote"])}”</p><p>{_inline(t["shows"])}</p>'
        f'<p class="muted tiny">Tools: {_inline(_tools(t))}. Status: {_inline(task_status(t["tools"]))}.</p>'
        f'<p class="tiny">For example: <a href="#{e(t["example"][0])}">{e(t["example"][1])}</a>.</p></li>'
        for t in TASKS)


def page_vars() -> dict[str, str]:
    return {"UC_PROBLEMS": problems_html(), "UC_TASKS": tasks_html(), "UC_EXAMPLES": examples_html(), "UC_INDUSTRIES": industries_html(),
            "UC_OUTPUTS": outputs_html(), "UC_FOOTNOTE": html.escape(FOOTNOTE),
            "UC_CONSULTANCY": html.escape(CONSULTANCY_TEXT.format(product="{{PRODUCT}}")),
            "UC_INTRO": html.escape(INTRO.format(product="{{PRODUCT}}"))}


# ------------------------------------------------------------------ markdown ---------------------------------------

def markdown(product: str, origin: str, contact: str) -> str:
    out = [f"# Use cases: what do you need to understand about your data?\n",
           INTRO.format(product=product) + "\n",
           f"*{FOOTNOTE}*\n",
           "## Three examples you can run\n"]
    for kind, _a, title, text, _b in EXAMPLES:
        m = example_map(kind)
        out.append(f"- **{title}**: {text} {m['tables']} tables, {m['relationships']} relationships. "
                   f"Run it: [{origin}/check?example={kind}]({origin}/check?example={kind})")
    out.append("\n## Start from your task\n")
    out += [f"- **“{t['quote']}”** {t['shows']} Tools: {_tools(t)}. Status: {task_status(t['tools'])}." for t in TASKS]
    out.append("\n## Problems we see in first reports\n")
    for p in PROBLEMS:
        out += [f"### {p['title']}\n", f"**“{p['question']}”**\n", f"- **Why it matters.** {p['why']}",
                f"- **How {product} shows it.** {p['how']}", f"- **What we do not know.** {p['unknown']}",
                f"- Run it on your laptop: [{origin}/local]({origin}/local). Tools: {_tools(p)}. Status: {task_status(p['tools'])}.\n"]
    out.append("## What comes out\n")
    out += [f"- **{n}**: {w}{' (' + t + ')' if t else ''}" for n, w, t in OUTPUTS]
    out.append("\n## Industries: the problem a customer brings\n")
    for i in INDUSTRIES:
        out += [f"### {i['name']}\n", f"*{ILLUSTRATIVE}.*\n", f"**“{i['problem']}”**\n", f"- **What you get.** {i['get']}",
                f"- Try a similar example ({_example_title(i['example'])}, synthetic data): [{origin}/check?example={i['example']}]({origin}/check?example={i['example']})\n"]
    out.append(f"\nThe rules behind every key and relationship: [{origin}/docs#how-relationships-are-inferred]({origin}/docs#how-relationships-are-inferred). "
               f"What each tool builds from a plan: [{origin}/use-cases/build]({origin}/use-cases/build).")
    out.append(f"\n## For Fabric consultancies\n\n{CONSULTANCY_TEXT.format(product=product)} "
               f"Start at [{origin}/start]({origin}/start), read [{origin}/docs]({origin}/docs), and email "
               f"Gustav at {contact} to discuss a pilot.\n")
    return "\n".join(out).replace("\n\n\n", "\n\n").replace("{{PRODUCT}}", product)


# Problem cards: one report error each, told the way a customer asks about it (Gustav's brief of 28 October 2026).
PROBLEMS = [
    {"slug": "total-doubles", "title": "The total that doubles",
     "question": "Why is our order total twice what finance says?",
     "why": "An amount on the order is joined to its lines and summed, so an order of 1 000 with two lines adds up to 2 000.",
     "how": "`validate_plan` points out header amounts and counts the lines per header; the semantic model draft puts the "
            "measure on the header. Order amount and line amount are different levels.",
     "unknown": "Which amount finance counts is not in the data: someone who knows the figures confirms it.",
     "tools": ["validate_plan", "semantic_model_draft"]},
]


def problems_html() -> str:
    e = html.escape
    out = []
    for p in PROBLEMS:
        out.append(f'<article class="uc-problem" id="problem-{e(p["slug"])}"><h3>{e(p["title"])}</h3>'
                   f'<p class="uc-task-q">“{e(p["question"])}”</p>'
                   f'<p><strong>Why it matters.</strong> {_inline(p["why"])}</p>'
                   f'<p><strong>How {{{{PRODUCT}}}} shows it.</strong> {_inline(p["how"])}</p>'
                   f'<p><strong>What we do not know.</strong> {_inline(p["unknown"])} <a href="/local#the-20-minute-demo">Run the demo on your laptop</a>.</p>'
                   f'<p class="muted tiny">Tools: {_inline(_tools(p))}. Status: {_inline(task_status(p["tools"]))}.</p></article>')
    return "".join(out)


CONSULTANCY_TEXT = ("Start a client conversation from their own schema instead of a slide. The plan lists every key and "
                    "relationship with the rule behind it, so a review with the client's data owners has something "
                    "concrete to check. The rules and the engine are open source.")

INTRO = ("Start with an unfamiliar lakehouse, a join you need to check or an app you want to build. These examples show "
         "where {product} helps and what still needs your judgement.")
