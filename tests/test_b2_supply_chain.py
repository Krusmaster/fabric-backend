"""B2 (15 November 2026): the supply chain in CI (backlog X-22, part).

- every action in .github/workflows is pinned by a full commit SHA, with its version in a comment;
- Dependabot covers the editor's npm packages (workload/Workload) next to pip and the Actions;
- the vendored Pyodide files match the SHA-256 sums written in fabric_backend/static/pyodide/README.txt, and no file is
  there that README.txt does not name;
- the container image is scanned by a pinned scanner (.github/workflows/image-scan.yml).
"""
import hashlib
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
PYODIDE = ROOT / "fabric_backend" / "static" / "pyodide"
USES = re.compile(r"^\s*(?:-\s*)?uses:\s*(\S+)(.*)$")


def _uses():
    for wf in WORKFLOWS:
        for n, line in enumerate(wf.read_text().splitlines(), 1):
            m = USES.match(line)
            if m:
                yield wf.name, n, m.group(1), m.group(2)


def test_workflows_exist_and_use_actions():
    assert len(WORKFLOWS) >= 5
    assert len(list(_uses())) >= 20


def test_every_action_is_pinned_by_commit_with_its_version_in_a_comment():
    bad = []
    for name, n, ref, rest in _uses():
        if ref.startswith("./") or ref.startswith("docker://"):
            continue
        action, _, sha = ref.partition("@")
        if not re.fullmatch(r"[0-9a-f]{40}", sha) or not re.fullmatch(r"\s*#\s*v\d+\.\d+\.\d+\s*", rest):
            bad.append(f"{name}:{n} {ref}{rest}")
    assert not bad, "not pinned by commit with '# vX.Y.Z': " + "; ".join(bad)


def test_one_commit_per_action_version():
    """The same action at the same version is the same commit everywhere, so an update cannot leave one file behind."""
    seen: dict[str, set[str]] = {}
    for _, _, ref, rest in _uses():
        action, _, sha = ref.partition("@")
        seen.setdefault(action, set()).add(sha + rest.strip())
    assert {a: s for a, s in seen.items() if len(s) > 1} == {}


def test_dependabot_covers_pip_actions_and_the_editors_npm_packages():
    cfg = yaml.safe_load((ROOT / ".github" / "dependabot.yml").read_text())
    got = {(u["package-ecosystem"], u["directory"]) for u in cfg["updates"]}
    assert got >= {("pip", "/"), ("pip", "/deploy"), ("github-actions", "/"), ("npm", "/workload/Workload")}
    assert (ROOT / "workload" / "Workload" / "package-lock.json").is_file()
    for u in cfg["updates"]:
        assert u["schedule"]["interval"] == "monthly" and u["groups"]["all"]["patterns"] == ["*"]


def _readme_sums() -> dict[str, str]:
    sums = {}
    for line in (PYODIDE / "README.txt").read_text().splitlines():
        m = re.fullmatch(r"([0-9a-f]{64})\s+(\S+)", line.strip())
        if m:
            sums[m.group(2)] = m.group(1)
    return sums


def test_pyodide_files_match_the_sums_in_readme():
    sums = _readme_sums()
    files = {p.name for p in PYODIDE.iterdir() if p.is_file() and p.name != "README.txt"}
    assert files and files <= set(sums), f"not named in README.txt: {sorted(files - set(sums))}"
    for name in sorted(files):
        assert hashlib.sha256((PYODIDE / name).read_bytes()).hexdigest() == sums[name], name


def test_pyodide_has_the_files_check_downloads():
    from fabric_backend import pages

    assert set(pages.CHECK_DOWNLOAD) <= set(_readme_sums())


def test_image_scan_builds_the_dockerfile_and_fails_on_fixable_criticals():
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "image-scan.yml").read_text())
    steps = wf["jobs"]["scan"]["steps"]
    assert any(s.get("run", "").startswith("docker build ") for s in steps)
    scan = next(s for s in steps if s.get("uses", "").startswith("anchore/scan-action@"))
    w = scan["with"]
    assert w["fail-build"] is True and w["severity-cutoff"] == "critical" and w["only-fixed"] is True
    assert wf["permissions"] == {"contents": "read"}
    on = wf[True] if True in wf else wf["on"]  # YAML 1.1 reads the key `on` as True
    assert "Dockerfile" in on["push"]["paths"] and "schedule" in on
