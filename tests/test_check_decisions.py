"""Round n85: /check's evidence report carries the decisions taken on the page (the guided demo's Accept and Reject):
what, the decision, the browser's time and "by: not recorded", the latest choice when it changes, nothing sent or
stored, and an accepted relationship still not checked. Without a decision the report is the worker's, unchanged.
Also the four example buttons: each description on at most two lines at 375 px, at 1280 px and at the narrowest width
where the four sit in one row. In a browser (tests/check_decisions_browser.js), skipped where there is none."""
from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from fabric_backend import browser_check as bc
from fabric_backend.platforms.local import sample_source
from test_browser import CHROMIUM, _playwright_available, site  # noqa: F401  the same local server fixture

ROOT = Path(__file__).resolve().parents[1]
WHAT = "suggested relationship orders.ship_to_id -> addresses"
pytestmark = pytest.mark.skipif(not _playwright_available(), reason="node + playwright not available")


@pytest.fixture(scope="module")
def run(site):  # noqa: F811
    out = subprocess.run(["node", str(ROOT / "tests" / "check_decisions_browser.js"), site] + ([CHROMIUM] if CHROMIUM else []),
                         capture_output=True, text=True, timeout=300)
    assert out.returncode == 0, out.stderr[-2000:]
    return json.loads(out.stdout.strip().splitlines()[-1])


def _decisions(md: str) -> list[list[str]]:
    part = md.split("\n## Decisions\n", 1)[1].split("\n## ", 1)[0]
    return [[c.strip() for c in line.strip("|").split(" | ")] for line in part.splitlines() if line.startswith("| ") and not line.startswith(("| What ", "| --- "))]


def _without_decisions(md: str) -> str:
    """The report as it would be without the Decisions table: what the worker wrote."""
    head, rest = md.split("\n## Decisions\n", 1)
    rest = rest.split("\n## ", 1)[1]
    head = re.sub(r"^(- \d+ open question\(s\), )\d+ decision\(s\)", r"\g<1>0 decision(s)", head, flags=re.M)
    return head + "\n## Decisions\n\nNone recorded.\n\n## " + rest


def _at(row: list[str], r: dict) -> datetime:
    at = datetime.strptime(row[3], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    assert r["before"] // 1000 - 1 <= at.timestamp() <= r["after"] / 1000 + 1, (row, r["before"], r["after"])   # the browser's clock
    return at


@pytest.mark.parametrize("width", [375, 1280])
def test_the_report_carries_each_decision_taken_on_the_page(run, width):
    r = run[f"guide@{width}"]
    assert run["errors"] == []
    d = r["downloads"]
    assert {x["name"] for x in d.values()} == {"shop_evidence_report.md"} and r["step"] == "A suggestion to decide on"
    # accepted: what, the decision, the browser's time, by: not recorded; and not checked by being accepted
    acc = _decisions(d["accepted"]["text"])
    assert len(acc) == 1 and acc[0][:3] == [WHAT, "accepted, not checked in the rows", "not recorded"], acc
    _at(acc[0], r)
    md = d["accepted"]["text"]
    assert "- 2 open question(s), 1 decision(s), 0 created object(s)" in md
    assert "An accepted relationship is not checked: accepting it counts nothing in the rows" in md
    rels, checks = md.split("## Relationships", 1)[1].split("## Checks against the rows", 1)
    assert "ship_to_id" not in rels and "ship_to_id" not in checks.split("## Open questions")[0]   # neither a relationship nor a check
    assert "- 13 checks: 13 counted in the rows, 0 not checked" in md                               # accepting counted nothing
    # changed after that download: the next download has the latest choice, once
    rej = _decisions(d["rejected"]["text"])
    assert len(rej) == 1 and rej[0][:3] == [WHAT, "rejected, the column stays unlinked", "not recorded"], rej
    assert _at(rej[0], r) >= _at(acc[0], r) and "An accepted relationship" not in d["rejected"]["text"]
    assert d["again"]["text"] == d["rejected"]["text"] and r["saidAfterBack"] == r["saidRejected"]   # back on the step: kept
    assert "Accepted on this page" in r["saidAccepted"] and "not checked" in r["saidAccepted"] and "Rejected on this page" in r["saidRejected"]
    # without a decision: the worker's report as it is, and with the table taken out each later one is that report
    assert "## Decisions\n\nNone recorded." in d["none"]["text"] and "0 decision(s)" in d["none"]["text"]
    assert _without_decisions(d["accepted"]["text"]) == d["none"]["text"] == _without_decisions(d["rejected"]["text"])
    gen = re.compile(r"^Status: \*\*Draft\*\*\. Generated .*$", re.M)
    assert gen.sub("", d["none"]["text"]) == gen.sub("", bc.analyze("sample")["evidence_report"]["markdown"])
    # nothing sent or stored: no request after the run, no request with a body, nothing in storage or cookies
    assert r["requestsAfter"] == [] and r["requestBodies"] == [] and r["storage"] == {"local": "{}", "session": "{}", "cookie": ""}
    # on the screen at both widths
    lay = r["layout"]
    assert lay["scrollWidth"] <= width and 0 <= lay["said"]["left"] and lay["said"]["right"] <= width, lay
    assert all(0 <= left and right <= width for left, right in lay["buttons"]), lay


def test_a_new_run_starts_without_the_last_runs_decisions(run):
    d = run["guide@1280"]["downloads"]
    assert "## Decisions\n\nNone recorded." in d["newRun"]["text"] and "0 decision(s)" in d["newRun"]["text"]


def test_no_row_value_is_in_a_report_with_decisions(run):
    src = sample_source()
    try:
        values = set()
        for t in src.schema:
            for row in src.execute(f"SELECT * FROM shop.[{t.name}]"):
                values |= {str(v) for v in row.values() if isinstance(v, str) and len(v) >= 4}
    finally:
        src.close()
    assert len(values) > 50
    for w in (375, 1280):
        for name, f in run[f"guide@{w}"]["downloads"].items():
            assert not [x for x in values if x in f["text"]], (w, name)


def test_the_example_descriptions_fit_on_two_lines(run):
    ex = {e["width"]: e for e in run["examples"]}
    row = [w for w, e in ex.items() if e["inRow"] and w != 1280]
    assert len(row) == 1 and not ex[row[0] - 1]["inRow"] and ex[1280]["inRow"] and not ex[375]["inRow"], {w: e["inRow"] for w, e in ex.items()}
    for w in (375, row[0], 1280):
        assert len(ex[w]["buttons"]) == 4 and all(1 <= b["lines"] <= 2 for b in ex[w]["buttons"]), (w, ex[w]["buttons"])
    billing = next(b for b in ex[375]["buttons"] if b["id"] == "check-billing")
    assert billing["title"] == "Subscription billing" and billing["text"] == "Younium + Salesforce invoices"
