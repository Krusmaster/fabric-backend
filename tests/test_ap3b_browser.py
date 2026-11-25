"""Round AP3b: the caretaker's report in Chromium (tests/ap3b_app_browser.js) at a desktop width and at 390 px, light and
dark, in AP3's browser-test pattern (tests/test_ap3_care_browser.py: the hosted app on localhost, a test Entra app, the
synthetic SAP demo and an in-memory Fabric that holds a data product a Krusgraph Model built).

The founder's live run of 25 November 2026: in the red "What was built, read back" the list ran over the next section.
Here the verify section is made long (its real lines and ten long ones more, with an unbroken run of characters), and the
pipeline part is slow on the first read so it is "Not read in time". Checked: the busy line names the parts still being
read, with a tick for each part read; no section overlaps the next and no text runs out of its section or the card, on
screen and in print media; nothing scrolls sideways at 390 px; Read again reads the product again and the late part is
then read.

Screenshots: set AP3B_SHOTS to a folder to keep them."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import pytest

pytest.importorskip("jwt")
pytest.importorskip("uvicorn")

from test_ap3_care_browser import RUNS as AP3_RUNS, TESTS, served  # noqa: E402,F401
from fabric_backend import guided_care  # noqa: E402

RUNS = list(AP3_RUNS) + [("desktop", 1280, 900, "dark")]               # light and dark at both widths
LONG = ("demo_lh_model (semantic model): differs. Definition: 2 difference(s) from the dry run (8 tables, 6 relationships, "
        "6 active, 4 measures compared): Relationship sap_vbap.MANDT+VBELN -> sap_vbak.MANDT+VBELN is in Fabric and not in "
        "the dry run. And 1 more. " + "x" * 140 + " Figures: 3 verified.")


@pytest.fixture(scope="module", params=RUNS, ids=[f"{r[0]}-{r[3]}" for r in RUNS])
def run(request, served):
    name, w, h, scheme = request.param
    fabric, got = served["fresh"]()
    mp = pytest.MonkeyPatch()
    real = dict(guided_care.SECTIONS)
    first = {"slow": True}

    def pipeline(p):
        if first.pop("slow", False):
            time.sleep(guided_care.CARE_SECONDS + guided_care.GRACE + 2)
        return real["pipeline"](p)

    def verify(p):
        sec, sig = real["verify"](p)
        sec = dict(sec, lines=list(sec["lines"]) + [f"{i + 1}. {LONG}" for i in range(10)], state="bad")
        return sec, sig
    mp.setattr(guided_care, "CARE_SECONDS", 6.0)
    mp.setattr(guided_care, "GRACE", 1.0)
    mp.setattr(guided_care, "SECTIONS", (("pipeline", pipeline), ("health", real["health"]), ("verify", verify),
                                         ("drift", real["drift"])))
    shots = os.environ.get("AP3B_SHOTS", "")
    prefix = ""
    if shots:
        Path(shots).mkdir(parents=True, exist_ok=True)
        prefix = str(Path(shots) / f"ap3b-{name}-{scheme}")
    pdf = str(Path(tempfile.mkdtemp(prefix="ap3b-")) / "report.pdf")
    try:
        r = subprocess.run(["node", str(TESTS / "ap3b_app_browser.js"), served["origin"], str(w), str(h), scheme, prefix, pdf],
                           capture_output=True, text=True, timeout=300, cwd=TESTS.parent)
    finally:
        mp.undo()
    assert r.returncode == 0, r.stderr[-4000:]
    out = json.loads(r.stdout)
    out.update(width=w, pdf=pdf)
    if shots:
        shutil.copy(pdf, prefix + "-report.pdf")
    return out


def words_overlapping(pdf: str) -> list[tuple[int, str, str]]:
    """Words of the printed page that are drawn over each other (pdftotext -bbox), per page."""
    got = subprocess.run(["pdftotext", "-bbox", pdf, "-"], capture_output=True, text=True, timeout=60).stdout
    out = []
    for n, page in enumerate(got.split("<page ")[1:], start=1):
        ws = [(float(a), float(b), float(c), float(d), x) for a, b, c, d, x in
              re.findall(r'xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">([^<]*)<', page)]
        for i, a in enumerate(ws):
            for b in ws[i + 1:]:
                if min(a[2], b[2]) - max(a[0], b[0]) > 1 and min(a[3], b[3]) - max(a[1], b[1]) > 2:
                    out.append((n, a[4], b[4]))
    return out


def test_the_busy_line_names_the_parts_still_read_and_ticks_the_ones_done(run):
    assert run["errors"] == []
    assert run["busy"].startswith("Reading Sales orders: pipeline runs")
    assert len(run["ticks"]) == 4 and any(t.endswith("(read)") for t in run["ticks"])
    assert run["ticks"][0] == "… pipeline runs"                               # the slow part is still being read


def test_no_section_overlaps_the_next_on_screen_or_in_print(run):
    assert run["first"] >= 4
    assert all(bad == [] for _, bad in run["overlaps"]), run["overlaps"]
    assert all(o <= 0 for _, o in run["overflow"]), run["overflow"]
    assert "10. demo_lh_model (semantic model)" in run["verify"]
    # printed: block flow, not the nested grid Chromium fragmented across pages in the live run
    assert run["printDisplay"] == ["block", "block", "block"]


def test_printed_on_letter_landscape_no_text_is_drawn_over_other_text(run):
    """The live run's page was printed on US Letter, landscape: the section crossing a page break was drawn under the
    next one. Read back from the PDF itself with poppler's pdftotext where it is installed."""
    if not shutil.which("pdftotext"):
        pytest.skip("pdftotext (poppler) is not installed here; the print-media layout test above still runs")
    assert Path(run["pdf"]).stat().st_size > 1000
    assert words_overlapping(run["pdf"]) == []


def test_a_part_not_read_in_time_says_so_and_read_again_reads_it(run):
    assert run["late"].startswith("Pipeline runs")
    assert "Not read in time: the report's time budget of 6 s ran out before pipeline runs were read." in run["late"]
    assert "Read again" in run["late"]
    assert run["lateAfter"] == 0 and "Latest run of demo_lh_pipeline" in run["again"]
    assert "Read the report again" in run["buttons"]
