"""n88, point 3: lineage's own answer said "Tested end to end on 27 October 2026" while docs/LIVE-TEST.md records a run on
2 November 2026. A tool's note now names its latest recorded live run, and that run is in docs/LIVE-TEST.md."""
import json
from pathlib import Path

from fabric_backend import tool_status
from fabric_backend import server
from tests.test_golden import SRC, fabric  # noqa: F401  (fabric: fixture)

LIVE = (Path(__file__).resolve().parents[1] / "docs" / "LIVE-TEST.md").read_text(encoding="utf-8")


def test_lineage_names_the_run_of_2_november(fabric):
    note = json.loads(server.lineage(**SRC))["note"]
    assert "2 November 2026" in note and "7 tables and 7 objects, none skipped" in note
    assert "7 tables and 7 objects, none skipped" in LIVE


def test_every_latest_run_a_note_names_is_recorded():
    for tool, said in tool_status.LATEST_LIVE.items():
        assert "2 November 2026" in tool_status.answer_note(tool), tool
        assert said["evidence"] in LIVE, (tool, said["evidence"])
