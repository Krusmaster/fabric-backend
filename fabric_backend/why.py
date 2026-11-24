"""W8 (the founder, 24 November 2026): why Krusgraph, in eight points, each one line and a link to its evidence.

One source for the home page's compact section (home_html, {{HOME_WHY}}) and the docs page /docs/why-krusgraph
({{WHY_POINTS}} in DOCS.md, markdown()), so the two cannot say different things. Every line has to be true today and
backed by a page the site already has; tests/test_w8_why.py checks that each link answers and each anchor exists, that no
price and no ruled-out sales word appears, and that the rule names follow infer.RULES.

What the points leave out on purpose (W8): no speed or cost figure (none is measured), no "follows Microsoft's
guidance" (the repository cites Microsoft Learn for Direct Lake, not for the medallion pattern), no price, and no
company in Switzerland: the place line is the footer's agreed wording (pages.BEHIND)."""
from __future__ import annotations

import html
import re

DIRECT_LAKE = "https://learn.microsoft.com/en-us/fabric/fundamentals/direct-lake-overview"   # cited in semantic_model.py
PAGE = "/docs/why-krusgraph"
GITHUB = "https://github.com/Krusmaster/fabric-backend"


def _rule_names() -> str:
    """'K0–K6 for keys, R0–R6 for relationships', read from the engine's own rule table."""
    from .infer import RULES
    def span(prefix: str) -> str:
        n = sorted(int(k[1:]) for k in RULES if re.fullmatch(prefix + r"\d+", k))
        return f"{prefix}{n[0]}–{prefix}{n[-1]}"
    return f"{span('K')} for keys, {span('R')} for relationships"


def points() -> list[dict]:
    """The eight points in the founder's order: title, a short line (the home page), the line (the docs page), and the
    evidence links (href, text)."""
    return [
        dict(id="no-guessing", title="Nothing is guessed",
             short=("No AI model decides: keys and links come from named rules, the check counts them in your rows, and "
                   "an unclear column is reported."),
             line=(f"No AI model decides a key or a relationship: each comes from a named, fixed rule ({_rule_names()}, "
                   "or the SAP pack), the check counts it against your rows, and a column that could mean two things is "
                   "reported, not guessed."),
             links=[("/docs/explore-and-check/how-relationships-are-inferred", "How relationships are inferred"),
                    (GITHUB + "/blob/main/fabric_backend/infer.py", "the rules in the code")]),
        dict(id="a-person-decides", title="A person decides, and owns the result",
             short=("Each link shows its rule and, once checked, its counts; a person settles the open questions, and a data "
                   "product gets the owner you name."),
             line=("Every key and relationship shows its rule, and its counts once you run the check; open questions wait "
                   "for a person, the review keeps each decision with its reason, and a data product gets the owner you "
                   "name."),
             links=[("/docs/explore-and-check/keep-your-review", "Keep your review"),
                    ("/docs/concepts/data-products", "Data products")]),
        dict(id="fabric-building-blocks", title="Built from Fabric's own pieces",
             short=("Raw tables stay as they are; silver, gold, a pipeline and a Direct Lake semantic model are written from "
                   "one reviewed plan."),
             line=("The raw tables stay as they are (bronze); from the reviewed plan, {{PRODUCT}} writes a silver notebook "
                   "that removes duplicates and checks every reference, gold views on top, a pipeline that runs them in order, and a Power BI semantic "
                   "model in Direct Lake mode."),
             links=[("/docs/build-from-a-plan/one-plan-five-fabric-pieces", "One plan, five Fabric pieces"),
                    (DIRECT_LAKE, "Microsoft Learn: Direct Lake overview")]),
        dict(id="light-on-resources", title="No tokens of its own",
             short="No language model inside, so no AI tokens of its own; the checks are SQL counts in your own Fabric capacity.",
             line=("{{PRODUCT}} calls no language model, so it spends no AI tokens itself; the checks run as counting SQL "
                   "queries in your own Fabric capacity, with your own sign-in, and return counts, not rows."),
             links=[("/docs/concepts/where-it-runs", "Where it runs"),
                    ("/docs/hosting-and-permissions/what-it-accesses", "What it accesses")]),
        dict(id="run-it-yourself", title="Runs on your own machines too",
             short="Open source (MIT): a local server, your own Azure subscription, or the browser check, where files are not uploaded.",
             line=("Open source under the MIT licence: run the local server or the command line on your own machine "
                   "(experimental), host the whole service in your own Azure subscription with `deploy/krusgraph.sh`, or "
                   "check exports in the browser, where the files are not uploaded."),
             links=[("/local", "Run it locally"), ("/it#open-source", "For your IT department"),
                    ("/trust", "Security and data")]),
        dict(id="free-and-workload", title="Free to try; the Fabric workload is a pilot",
             short=("Check my tables and the connector for Claude are free; Krusgraph for Fabric is a pilot (preview), and "
                   "Marketplace is planned."),
             line=("Check my tables, the connector for Claude and the open-source code are free today; Krusgraph for "
                   "Fabric, the packaged workload, is a pilot (preview) for selected organisations, and a Workload Hub "
                   "listing and buying through Microsoft Marketplace are planned, not available yet."),
             links=[("/choose", "Which Krusgraph should I use?"), ("/check", "Check my tables")]),
        dict(id="who-makes-it", title="Who makes it",
             short="Made by Kruse Consulting AB. Based in Uppsala, Sweden, and Bern, Switzerland.",
             line="Made by Kruse Consulting AB. Based in Uppsala, Sweden, and Bern, Switzerland.",
             links=[("/it#who", "Who stands behind it")]),
        dict(id="not-one-platform", title="Not tied to one platform",
             short=("Built for Microsoft Fabric; the open-source engine also plans Snowflake and Databricks schemas "
                   "(Databricks: draft only)."),
             line=("The hosted product is built for Microsoft Fabric, where it also reads mirrored databases "
                   "(experimental) and SAP tables; the open-source library, command line and local server also plan "
                   "Snowflake and Databricks schemas where they are (Databricks: draft only)."),
             links=[("/docs/explore-and-check/sources", "Sources"), ("/sap", "SAP tables"),
                    ("/docs/build-from-a-plan/databricks-draft-only", "Databricks")]),
    ]


def _md_links(links) -> str:
    return " · ".join(f"[{t}]({h})" for h, t in links)


def markdown() -> str:
    """The numbered list for DOCS.md's "Why choose Krusgraph"."""
    return "\n".join(f"{i}. **{p['title']}.** {p['line']} Evidence: {_md_links(p['links'])}."
                     for i, p in enumerate(points(), 1))


def _inline(s: str) -> str:
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", html.escape(s, quote=False))


def home_html() -> str:
    """The home page's compact section: the eight titles and lines, one evidence link each, and the way to the page."""
    items = []
    for p in points():
        href, text = p["links"][0]
        ext = ' rel="noopener"' if href.startswith("http") else ""
        items.append(f'<li id="why-{p["id"]}"><h3>{html.escape(p["title"])}</h3><p>{_inline(p["short"])}</p>'
                     f'<p class="why-ev tiny"><a href="{html.escape(href, quote=True)}"{ext}>{html.escape(text)}</a></p></li>')
    return (f'<section class="wrap why" id="why" aria-labelledby="why-h" style="padding-top:0">\n'
            f'  <h2 id="why-h">Why {{{{PRODUCT}}}}</h2>\n'
            f'  <p class="muted why-lede">Eight points, each with the page that backs it.</p>\n'
            f'  <ol class="why-list">{"".join(items)}</ol>\n'
            f'  <p class="why-more"><a href="{PAGE}">All eight, with the evidence →</a></p>\n'
            f'</section>')
