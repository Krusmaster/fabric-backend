"""CD1 (16 November 2026): tools/path_guard.py, the check behind CONTRIBUTING.md's "Merging and deploying" rule that a
round never merges a protected change on its own (.github/workflows/path-guard.yml)."""
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("path_guard", ROOT / "tools" / "path_guard.py")
pg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pg)


@pytest.mark.parametrize("path, word", [
    ("social/2026-11-16-linkedin.png", "social"),
    ("docs/marketing/taglines.md", "marketing"),
    ("docs/PRICING-2027.md", "pricing"),
    ("fabric_backend/page_templates/pricing.html", "pricing"),
    ("fabric_backend/page_templates/PRIVACY.md", "legal"),
    ("fabric_backend/page_templates/terms.html", "legal"),
    ("fabric_backend/legal.py", "legal"),
    ("workload/Workload/Manifest/Product.json", "workload name"),
    ("workload/Workload/Manifest/items/Model/ModelItem.xml", "workload name"),
    ("workload/scripts/build_package.py", "workload name"),
    (".github/workflows/ci.yml", "secrets"),
    ("deploy/azure_containerapp.py", "secrets"),
    ("fabric_backend/entra.py", "secrets"),
    ("fabric_backend/registration_store.py", "user data"),
    ("CONTRIBUTING.md", "merge policy"),
    ("tools/path_guard.py", "merge policy"),
])
def test_protected_paths(path, word):
    hits = pg.protected([path])
    assert len(hits) == 1 and word in hits[0][1], (path, hits)


@pytest.mark.parametrize("path", [
    "fabric_backend/csn.py", "fabric_backend/infer.py", "tests/test_cds2_csn.py", "tests/fixtures/csn/README.md",
    "docs/SAP-CSN.md", "README.md", "fabric_backend/page_templates/sap.html", "THIRD_PARTY_NOTICES.md",
    "docs/DEMO-SALES-PLANNING.md", "fabric_backend/page_templates/sales_planning.html",
    "workload/Workload/app/items/ModelItem/ModelItemEditor.tsx", "deploy/constraints.txt",
])
def test_code_tests_and_public_docs_are_not_protected(path):
    assert pg.protected([path]) == []


def test_pr_33_would_have_passed_without_the_label():
    """The SAP CSN reader merged in CD1 step 5: code, tests, public docs and Apache-2.0 sample fixtures only."""
    files = ["THIRD_PARTY_NOTICES.md", "docs/SAP-CSN.md", "fabric_backend/amounts.py", "fabric_backend/cli.py",
             "fabric_backend/csn.py", "fabric_backend/csn_demo.py", "fabric_backend/infer.py", "fabric_backend/mcp_server.py",
             "fabric_backend/schema.py", "tests/fixtures/csn/README.md", "tests/test_cds2_csn.py", "tools/third_party_notices.py"]
    ok, lines = pg.evaluate(files, [])
    assert ok and "may merge" in lines[0]


def test_label_turns_a_protected_change_into_a_pass_that_names_the_reasons():
    ok, lines = pg.evaluate(["social/post.png", "fabric_backend/csn.py"], [])
    assert not ok and "needs-gustav" in lines[0] and any("social/post.png" in line for line in lines)
    ok, lines = pg.evaluate(["social/post.png"], ["bug", " needs-gustav "])
    assert ok and "maintainer merges" in lines[0] and "social/post.png" in lines[1]


def test_major_bumps_pip():
    old = "fastapi==0.115.2\nuvicorn==0.32.0\nrequests==2.32.3\nmcp==1.9.0\n"
    new = "fastapi==0.116.0\nuvicorn==0.32.1\nrequests==3.0.0\nmcp==1.12.4\nnewpkg==5.0.0\n"
    assert pg.major_bumps(old, new, "pip") == ["fastapi 0.115 -> 0.116", "requests 2.32 -> 3.0"]


def test_major_bumps_pyproject_lists():
    old = '[project]\ndependencies = [\n  "httpx>=0.27",\n  "PyYAML>=6.0",\n]\n'
    new = '[project]\ndependencies = [\n  "httpx>=0.27",\n  "pyyaml>=7.0",\n]\n'
    assert pg.major_bumps(old, new, "pip") == ["pyyaml 6.0 -> 7.0"]


def test_major_bumps_npm():
    old = json.dumps({"dependencies": {"react": "^18.3.1", "x": "~1.2.0"}, "devDependencies": {"typescript": "5.6.2"}})
    new = json.dumps({"dependencies": {"react": "^19.0.0", "x": "~1.3.0"}, "devDependencies": {"typescript": "5.7.0"}})
    assert pg.major_bumps(old, new, "npm") == ["dependencies:react 18.3 -> 19.0"]
    assert pg.major_bumps("not json", new, "npm") == []


def test_evaluate_reads_dependency_files_at_base_and_head():
    texts = {("base", "deploy/constraints.txt"): "starlette==0.47.0\n", ("head", "deploy/constraints.txt"): "starlette==1.0.0\n"}
    ok, lines = pg.evaluate(["deploy/constraints.txt"], [], lambda rev, path: texts.get((rev, path), ""))
    assert not ok and any("starlette 0.47 -> 1.0" in line for line in lines)
    texts[("head", "deploy/constraints.txt")] = "starlette==0.47.3\n"
    ok, _ = pg.evaluate(["deploy/constraints.txt"], [], lambda rev, path: texts.get((rev, path), ""))
    assert ok


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
                          check=True, capture_output=True, text=True).stdout.strip()


def test_main_against_a_real_git_history(tmp_path, monkeypatch, capsys):
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / "fabric_backend").mkdir()
    (repo / "fabric_backend" / "csn.py").write_text("x = 1\n")
    (repo / "social").mkdir()
    (repo / "social" / "old.png").write_text("png")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    (repo / "fabric_backend" / "csn.py").write_text("x = 2\n")
    _git(repo, "commit", "-q", "-am", "code only")
    code_only = _git(repo, "rev-parse", "HEAD")
    _git(repo, "mv", "social/old.png", "renamed.png")        # a move out of social/ is a change to social/ too
    _git(repo, "commit", "-q", "-m", "move")
    moved = _git(repo, "rev-parse", "HEAD")
    monkeypatch.chdir(repo)
    assert pg.changed_paths(base, code_only) == ["fabric_backend/csn.py"]
    assert "social/old.png" in pg.changed_paths(base, moved)
    assert pg.main(["--base", base, "--head", code_only, "--labels", ""]) == 0
    assert pg.main(["--base", base, "--head", moved, "--labels", "x"]) == 1
    assert "social/old.png" in capsys.readouterr().out
    assert pg.main(["--base", base, "--head", moved, "--labels", "x,needs-gustav"]) == 0


def test_the_workflow_runs_the_base_branchs_rules_on_every_label_change():
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "path-guard.yml").read_text())
    on = wf[True] if True in wf else wf["on"]
    assert {"opened", "synchronize", "labeled", "unlabeled"} <= set(on["pull_request"]["types"])
    assert "pull_request_target" not in on
    assert wf["permissions"] == {"contents": "read"}
    script = wf["jobs"]["path-guard"]["steps"][-1]["run"]
    assert 'git show "$BASE:tools/path_guard.py"' in script and "PIPESTATUS" in script
    assert "${{" not in script                    # event values reach the shell as environment variables only


def test_contributing_states_the_policy_and_the_label():
    text = (ROOT / "CONTRIBUTING.md").read_text()
    section = text.split("## Merging and deploying", 1)[1].split("\n## ", 1)[0]
    for phrase in ("needs-gustav", "tools/path_guard.py", "every CI job", "major", "demo tenant", "docs/AUTO-DEPLOY.md"):
        assert phrase in section, phrase
