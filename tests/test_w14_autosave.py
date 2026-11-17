"""W14: autosave in the Model editor (the founder's "B: Ja", 17 November 2026).

W13 found that review decisions were lost when the item was closed before Save. The behaviour is tested in TypeScript
(workload/Workload/app/items/ModelItem/autosave.test.ts and autosave.editor.test.tsx, `npm test`) and in Chromium by
the W13 end-to-end flows 18 and 19 (workload/scripts/e2e/run.js). These checks keep the pieces wired together for the
Python suite: the editor uses the autosave, the definition keeps the revision, and the end-to-end harness clears the
drafts on a fresh run and has the two flows.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ITEM = ROOT / "workload/Workload/app/items/ModelItem"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_editor_uses_the_autosave():
    editor = _read(ITEM / "ModelItemEditor.tsx")
    for needle in ("from \"./autosave\"", "<SaveIndicator", "AUTOSAVE_DELAY_MS", "writeDraft(", "readDraft(", "recover(",
                   "resolve(", "stamp(", "\"pagehide\"", "\"visibilitychange\""):
        assert needle in editor, needle


def test_the_revision_is_kept_and_cleaned():
    definition = _read(ITEM / "ModelItemDefinition.ts")
    assert "saved?: SavedMark" in definition
    assert "cleanSaved(def.item?.saved)" in definition


def test_the_indicator_is_a_live_region_with_a_mark_that_is_not_a_colour():
    indicator = _read(ITEM / "SaveIndicator.tsx")
    assert 'role="status"' in indicator and 'aria-live="polite"' in indicator
    assert 'aria-hidden="true"' in indicator      # the mark (✓ … ✕ •) is decoration; the words say it
    words = _read(ITEM / "autosave.ts")
    for mark in ("✓", "…", "✕", "•"):
        assert f'mark: "{mark}"' in words


def test_the_draft_holds_no_secret():
    src = _read(ITEM / "autosave.ts")
    body = src.split("export function writeDraft", 1)[1].split("\n}\n", 1)[0]
    assert "token" not in body.lower() and "secret" not in body.lower()


def test_the_e2e_flows_cover_autosave():
    harness = _read(ROOT / "workload/scripts/e2e/harness.tsx")
    assert "DRAFT_PREFIX" in harness and "slowsave" in harness
    run = _read(ROOT / "workload/scripts/e2e/run.js")
    assert "18 Autosave: a decision is saved without Save" in run
    assert "19 Closed before the save: the decision comes back on reopening" in run
