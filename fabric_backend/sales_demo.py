"""The first customer demonstration on the site: /example/sales-planning and its result JSON (the brief of 26 October
2026). A preview: served only when KRUSGRAPH_PREVIEW=1, noindex, out of the sitemap and the navigation, so a deploy
does not publish it; publishing is Gustav's separate decision.

The page asks the question, shows what the answer covers, lets the visitor decide the one uncertain product link,
then shows the weekly sales view, the tested forecast and a note for the planning meeting. Every number comes from
planning.result() over the synthetic lines in sales_example.py; the page state (decisions and filters) lives in the
URL, so a saved link reopens the same result.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache

from . import planning, sales_example

PREVIEW_ENV = "KRUSGRAPH_PREVIEW"
PATH = "/example/sales-planning"
QUESTION = "Show sales across our two companies and help me plan the next eight weeks."
TITLE = "Two companies, one sales view — {{PRODUCT}} example"
DESC = "An example with synthetic data: a combined weekly sales view of two companies and a tested eight-week forecast."


def enabled() -> bool:
    return os.environ.get(PREVIEW_ENV, "").strip() == "1"


@lru_cache(maxsize=1)
def dataset() -> dict:
    return {"companies": sales_example.COMPANIES, "registers": sales_example.registers(), "lines": sales_example.lines(),
            "group": sales_example.GROUP, "reference": sales_example.REFERENCE, "latest_week": sales_example.LATEST_WEEK,
            "version": f"synthetic-{sales_example.SEED}"}


def parse(params) -> tuple[dict[str, str], str, int]:
    """The page state from the query string: d=B-7003:A-103 (one per decision, comma separated), company, weeks."""
    decisions = {}
    for part in filter(None, (params.get("d") or "").split(",")):
        product, _, choice = part.partition(":")
        if not product or not choice:
            raise planning.PlanningInputError(f"a decision reads product:choice, not {part!r}")
        decisions[product.strip()] = choice.strip()
    try:
        weeks = int(params.get("weeks") or 26)
    except ValueError:
        raise planning.PlanningInputError("weeks must be a number") from None
    return decisions, (params.get("company") or "all"), weeks


@lru_cache(maxsize=64)
def _result(decisions: tuple, company: str, weeks: int) -> str:
    r = planning.result(dataset(), dict(decisions), company, weeks)
    r["question"] = QUESTION
    return json.dumps(r, ensure_ascii=False, separators=(",", ":"))


def result_json(decisions: dict[str, str], company: str, weeks: int) -> str:
    return _result(tuple(sorted(decisions.items())), company, weeks)


def page_html(params) -> str:
    """The page with the result for the URL's state embedded, so a reopened link shows its numbers at once."""
    import html
    from . import pages
    try:
        decisions, company, weeks = parse(params)
        data = result_json(decisions, company, weeks)
    except planning.PlanningInputError:
        data = result_json({}, "all", 26)                       # a broken link opens the example from the start
    body = pages._fill(pages._read("sales_planning.html"))
    body = (body.replace("{{SP_QUESTION}}", html.escape(QUESTION)).replace("{{SP_JSON_PATH}}", PATH + "/result.json")
                .replace("{{SP_DATA}}", data.replace("</", "<\\/")))
    head = f'<script src="/static/sales.js?v={pages._vars()["ASSET_V"]}" defer></script>'
    return pages._shell(TITLE, DESC, body, page="sales-planning", nav="", noindex=True, head=head, path=PATH)
