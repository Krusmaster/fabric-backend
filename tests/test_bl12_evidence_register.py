"""Round BL12, 21 November 2026 (backlog C-24): the evidence register is complete, checked and up to date."""
from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import evidence_register as er  # noqa: E402

TOOL = ROOT / "tools" / "evidence_register.py"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True, cwd=ROOT)


def test_check_passes_on_this_checkout():
    r = _run("--check")
    assert r.returncode == 0, r.stderr
    assert f"ok: {len(er.REGISTER)} claims" in r.stdout


def test_the_doc_is_up_to_date():
    assert (ROOT / er.DOC).read_text(encoding="utf-8") == er.render(), "run python tools/evidence_register.py"


def test_at_least_twenty_claims_with_unique_ids_and_known_classes():
    assert len(er.REGISTER) >= 20
    assert len({c.id for c in er.REGISTER}) == len(er.REGISTER)
    assert {c.cls for c in er.REGISTER} <= set(er.CLASSES)


def test_seeded_from_the_four_sources():
    files = {c.file for c in er.REGISTER}
    assert {"README.md", "docs/TRUST.md", "fabric_backend/claims.py", "docs/MISSING-EVIDENCE.md"} <= files


def test_no_customer_row_yet_and_the_doc_says_so():
    assert not [c for c in er.REGISTER if c.cls == "C"]
    assert "No class C row exists yet" in er.render()


def test_a_planted_missing_test_fails():
    bad = replace(er.REGISTER[0], test="tests/test_bl3_counts.py::test_this_test_does_not_exist")
    found = er.problems((bad, *er.REGISTER[1:]))
    assert found == [f"{bad.id}: the test test_this_test_does_not_exist is missing from tests/test_bl3_counts.py"]


@pytest.mark.parametrize("field, value, words", [
    ("file", "docs/NO-SUCH-FILE.md", "is missing"),
    ("anchor", "a sentence no file has ever said", "no longer says"),
    ("test", "tests/test_no_such_file.py::test_x", "the test file"),
    ("live_row", "| 999 | `no_such_tool` |", "has no row"),
    ("cls", "X", "unknown class"),
])
def test_each_kind_of_gap_is_reported(field, value, words):
    bad = replace(er.REGISTER[1], **{field: value})
    found = er.problems((bad,))
    assert len(found) == 1 and words in found[0], found


def test_the_cli_fails_on_a_planted_missing_test_in_a_copy(tmp_path):
    """--check on a copy of the repository where one registered test function was renamed."""
    for c in er.REGISTER:
        for rel in {c.file, c.test.partition("::")[0], str(er.LIVE_TEST), str(er.DOC)} - {""}:
            dst = tmp_path / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / rel, dst)
    victim = next(c for c in er.REGISTER if "::" in c.test)
    path, _, name = victim.test.partition("::")
    t = tmp_path / path
    t.write_text(t.read_text(encoding="utf-8").replace(f"def {name}(", f"def renamed_{name}("), encoding="utf-8")
    r = _run("--check", "--root", str(tmp_path))
    assert r.returncode == 1
    assert f"the test {name} is missing" in r.stderr


def test_a_stale_doc_fails(tmp_path):
    for c in er.REGISTER:
        for rel in {c.file, c.test.partition("::")[0], str(er.LIVE_TEST)} - {""}:
            dst = tmp_path / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / rel, dst)
    (tmp_path / er.DOC).write_text("# old\n", encoding="utf-8")
    r = _run("--check", "--root", str(tmp_path))
    assert r.returncode == 1 and "is stale" in r.stderr


def test_no_model_call_and_no_network_in_the_tool():
    src = TOOL.read_text(encoding="utf-8")
    for word in ("import requests", "import httpx", "urllib", "anthropic", "openai", "socket"):
        assert word not in src
