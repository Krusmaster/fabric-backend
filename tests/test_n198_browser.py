"""Round n198: the Data product page in Chromium (tests/n198_browser.js), at 375 and 1280 px, light and dark, by keyboard.

The pages are DataProductView.tsx rendered in every state from a fake outputs.json (productPage.fixture.ts) by the
workload job's dataProductPage.test.ts, which fails when tests/fixtures/n198/ is stale. Checked here: no horizontal
scroll and nothing wider than the page; every item says its state in words (the mark is hidden from screen readers and
colour is never the only signal) with a contrast of at least 4.5:1, and every text at least 4.5:1; buttons at least
24 px high; every enabled button and field is reached by Tab with a visible outline and nothing disabled is; Delete is
off until the data product's name is typed. Screenshots go to N198_SHOTS when it is set (never committed)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PAGES = ROOT / "tests" / "fixtures" / "n198"
STATES = {"built": "Built", "pending": "Pending", "failed": "Failed", "changed_outside": "Changed outside Krusgraph",
          "missing": "Missing", "removed": "Removed"}


def _browser() -> bool:
    return bool(shutil.which("node")) and subprocess.run(["node", "-e", "require('playwright')"], capture_output=True).returncode == 0


@pytest.fixture(scope="module")
def runs():
    if not _browser():
        pytest.skip("node + playwright not available")
    cmd = ["node", str(ROOT / "tests" / "n198_browser.js"), str(PAGES)] + ([os.environ["N198_SHOTS"]] if os.environ.get("N198_SHOTS") else [])
    run = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    assert run.returncode == 0, run.stderr[-3000:]
    out = json.loads(run.stdout.strip().splitlines()[-1])
    assert out["errors"] == []
    return out["runs"]


def test_every_state_is_rendered():
    assert {p.stem for p in PAGES.glob("*.html")} == {"states", "fresh", "update", "soft", "delete-dry-run", "delete-typed", "deleted",
                                                      "leftovers", "leftovers-unread"}
    html = (PAGES / "states.html").read_text()
    for state in STATES:
        assert f'data-state="{state}"' in html


def test_no_horizontal_scroll_at_375_and_1280_light_and_dark(runs):
    assert {(r["width"], r["scheme"]) for r in runs} == {(375, "light"), (375, "dark"), (1280, "light"), (1280, "dark")}
    for r in runs:
        assert r["scroll"] <= 0, (r["file"], r["width"], r["scheme"], r["scroll"])
        assert r["wide"] == [], (r["file"], r["width"], r["wide"])


def test_states_in_words_with_enough_contrast(runs):
    for r in runs:
        for s in r["states"]:
            assert s["words"] == STATES[s["state"]], (r["file"], s)
            assert s["markHidden"]
            assert s["contrast"] >= 4.5, (r["file"], r["width"], r["scheme"], s)
        assert r["minText"] >= 4.5, (r["file"], r["scheme"], r["minText"])
        assert r["minButton"] >= 24


def test_the_keyboard_reaches_every_control_with_a_visible_focus(runs):
    for r in runs:
        assert r["tabbed"] == r["focusable"], (r["file"], r["width"], r["scheme"], r["tabbed"], r["focusable"], r["order"])
        assert r["focusVisible"], (r["file"], r["scheme"])
        assert not r["reachedDisabled"]


def test_delete_waits_for_the_typed_name(runs):
    by = {(r["file"], r["width"], r["scheme"]): r for r in runs}
    wrong, right = by[("delete-dry-run.html", 1280, "light")], by[("delete-typed.html", 1280, "light")]
    assert wrong["disabledDelete"] == [True] and right["disabledDelete"] == [False]
    assert not any(t.startswith("Delete 4 item") for t in wrong["order"])
    assert any(t.startswith("Delete 4 item") for t in right["order"])
