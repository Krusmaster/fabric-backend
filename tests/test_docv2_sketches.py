"""DOCV2 (Gustav, 21 November 2026: "Gärna"): two more hand-drawn sketches on the docs page "Where Krusgraph is
heading", drawn by DOCV1's pen (fabric_backend/heading_sketch.py): what Krusgraph builds in your Fabric, and how it
keeps itself up to date.

Both are static inline SVGs with an accessible name and description, load nothing from another host, sit under
DOCV1's status line, say honestly what exists today and what is direction (naming only tools the server has), use none
of the forbidden words, and at 390 px the page does not scroll sideways (only each sketch's own box does)."""
import json
import re
import subprocess

import pytest

from fabric_backend import heading_sketch, server
from tests.test_docv1_heading_page import (FORBIDDEN, PATH, STATUS, TESTS, _article, _browser_ready, _text,
                                           client)  # noqa: F401  (client is a fixture)

HEADINGS = ("What Krusgraph builds in your Fabric", "How it keeps itself up to date")
SKETCH_TEXT = {
    "heading-sketch-fabric": ("Your Fabric tenant", "Sources", "SAP", "Salesforce", "Dynamics", "More sources …",
                              "mirroring · shortcuts", "Bronze", "lakehouse · raw", "Silver", "notebook · keys checked",
                              "Gold", "views · star schema", "Data products · domain: Sales", "Customer", "Product",
                              "Order", "key · owner · contract", "What people use", "Semantic model", "Ontology",
                              "Data agent", "Report", "GraphQL API", "Around it", "Pipeline", "dbt tests", "Catalog",
                              "Domains", "Alerts", "Fabric Git", "Same plan, same items · every change is a PR", "raw",
                              "refined", "data product", "what people use", "run and govern"),
    "heading-sketch-loop": ("It watches", "new column in a source", "new table", "key no longer unique",
                            "data not fresh", "broken relationship", "unused items", "cost running away", "Watch",
                            "every night + on change", "Compare", "desired vs actual = plan", "Classify",
                            "rules decide the risk", "Safe: done on its own", "catalog · tests", "a new column",
                            "Risky: draft PR", "a mascot explains", "you approve", "Rebuild + test",
                            "dbt tests · rows prove", "Learn from the decision", "the same choice becomes the default",
                            "round after round", "Today: watching and dry runs.", "Next: fixing on its own."),
}
IDS = {"heading-sketch": "hs", "heading-sketch-fabric": "hs2", "heading-sketch-loop": "hs3"}
# the tools the page says exist today; each must be a tool the server has
TOOLS = ("create_silver_notebook", "create_gold_views", "create_pipeline", "create_semantic_model", "create_ontology",
         "create_data_agent", "create_report", "create_backend", "create_drift_monitor", "publish_catalog", "dbt_schema",
         "domain_draft", "plan_drift", "verify_build")


@pytest.mark.parametrize("name", list(heading_sketch.SKETCHES))
def test_each_checked_in_sketch_is_what_the_module_draws(name):
    path, build, _title = heading_sketch.SKETCHES[name]
    assert path.read_text(encoding="utf-8") == build(), "run: python -m fabric_backend.heading_sketch"
    assert path.parent.name == "static"


def test_the_page_has_three_sketches_each_inline_and_described(client):
    h = client.get(PATH).text
    svgs = re.findall(r'<svg class="hs-svg".*?</svg>', h, re.S)
    assert len(svgs) == 3
    ids = []
    for svg in svgs:
        m = re.search(r'aria-labelledby="(\w+)-title \1-desc"', svg)
        assert m and 'role="img"' in svg, svg[:200]
        ids.append(m.group(1))
        assert f'<title id="{m.group(1)}-title">Sketch: ' in svg
        assert re.search(rf'<desc id="{m.group(1)}-desc">A hand-drawn sketch\b.{{200,}}</desc>', svg)
        assert "xmlns" not in svg                                   # inline in the page
    assert ids == list(IDS.values())                                # unique ids, in the page's order
    for name, words in SKETCH_TEXT.items():
        svg = svgs[list(IDS).index(name)]
        t = _text(svg)
        for s in words:
            assert s in t, (name, s)
    assert h.count("The sketch in words") == 3


def test_the_headings_follow_the_status_line_and_are_in_on_this_page(client):
    h = client.get(PATH).text
    body = _text(_article(h))
    assert body.index(STATUS) < body.index("Your Fabric tenant · your data stays here")      # DOCV1's line stays on top
    assert body.index(STATUS) < body.index(HEADINGS[0]) < body.index(HEADINGS[1]) < body.index("You can try today's version")
    for s in HEADINGS:
        slug = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
        assert f'<h2 id="{slug}">{s}</h2>' in h, s                  # #### becomes this page's h2
        assert f'<li><a href="#{slug}">{s}</a></li>' in h, s


def test_the_text_says_what_exists_today_and_what_is_direction(client):
    body = _text(_article(client.get(PATH).text))
    for s in ("and other sources", "What it builds today.", "What it does today.", "The direction:",
              "building all of it in one go from one plan", "with a dry run first",
              "does not create them", "Every change is a dry run until you confirm it.",
              "fixing safe changes on its own", "rules, not a model"):
        assert s in body, s
    for tool in TOOLS:
        assert tool in body, tool
        assert callable(getattr(server, tool, None)), f"{tool} is named on the page but is not a server tool"


def test_the_markdown_twin_has_both_parts(client):
    md = client.get("/docs.md").text
    for s in HEADINGS:
        assert f"#### {s}" in md


@pytest.mark.parametrize("where", [PATH, "/docs.md"])
def test_no_forbidden_words_and_no_names(client, where):
    h = client.get(where).text
    if where == PATH:
        h = _article(h)
    else:
        h = h[h.index("### Where Krusgraph is heading"):]
        h = h[:h.index("\n## ")]
    low = _text(h).lower()
    for s in FORBIDDEN + ("employer", "customer:", "replaces data engineer", "faster than", "guarantee"):
        assert not re.search(r"(?<![a-z])" + re.escape(s) + r"(?![a-z])", low), s


def test_the_new_sketches_load_nothing_from_elsewhere():
    for name in ("heading-sketch-fabric", "heading-sketch-loop"):
        svg = heading_sketch.svg(name).replace(f'xmlns="{heading_sketch.XMLNS}"', "")
        assert "http" not in svg and "<image" not in svg and "@import" not in svg and "<script" not in svg


def test_390_px_has_no_page_level_sideways_scroll_with_all_three(client, tmp_path):
    if not _browser_ready():
        pytest.skip("node with playwright and Chromium is not available here")
    h = client.get(PATH).text
    files = {"__page__": PATH, PATH: ["text/html", h]}
    for ref in re.findall(r'(?:href|src)="(/static/[^"?]+\.(?:css|js))(?:\?[^"]*)?"', h):
        r = client.get(ref)
        files[ref] = [r.headers["content-type"], r.text]
    (tmp_path / "files.json").write_text(json.dumps(files), encoding="utf-8")
    p = subprocess.run(["node", str(TESTS / "test_docv2_overflow.js"), str(tmp_path / "files.json")],
                       capture_output=True, text=True, cwd=TESTS.parent, timeout=120)
    assert p.returncode == 0, p.stderr
    runs = json.loads(p.stdout.strip().splitlines()[-1])
    for x in runs:
        assert x["page"] <= x["inner"], x
        assert len(x["boxes"]) == 3, x
        for b in x["boxes"]:
            assert b["right"] <= x["inner"], x
            assert b["font"] >= 12, x
        assert not x["external"], x
    dark = next(x for x in runs if x["scheme"] == "dark")
    light = next(x for x in runs if x["scheme"] == "light")
    assert dark["teal"] != light["teal"] and dark["halo"] != light["halo"]       # the new fills follow the theme
