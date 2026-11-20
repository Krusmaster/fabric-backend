"""WP1 (18 November 2026): the workload package is built by CI when the manifest changes; Gustav only uploads it.

Checked here, with no network, no Fabric and no GitHub:
- .github/workflows/workload-package.yml: its triggers and paths, least-privilege permissions, pinned actions, no
  secrets, the variable fallback, no upload or portal call, and that deploy.yml and deploy/ are not part of it;
- tools/workload_package_ci.py: which issue is updated or closed, what the package is compared with, the issue body;
- the versions: unique and growing across runs, never below 1.0.1396 (1.0.1395 is active in Fabric);
- the Cloud Shell fix: a missing module stops with the exact install command, and the server-dependent tests are named
  as run in CI when the server extras are absent.
"""
from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WF_PATH = ROOT / ".github" / "workflows" / "workload-package.yml"
WF_TEXT = WF_PATH.read_text(encoding="utf-8")
WF = yaml.safe_load(WF_TEXT)
APP = "853a0cf0-7d35-42b7-b384-26178755a72a"
PORTAL = "https://app.fabric.microsoft.com/onelake/govern/org-config/workloads/publish?experience=fabric-developer"


def _load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / file)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


sys.path.insert(0, str(ROOT / "tools"))
wp = _load("workload_package", "workload_package.py")
ci = _load("wp1_workload_package_ci", "workload_package_ci.py")


# ------------------------------------------------------------------ the workflow

def _on():
    return WF.get("on", WF.get(True))              # PyYAML reads the key `on` as True


def test_triggers_are_a_manifest_change_on_main_and_a_manual_run():
    on = _on()
    assert set(on) == {"push", "workflow_dispatch"}
    assert on["push"]["branches"] == ["main"]
    paths = on["push"]["paths"]
    assert "workload/Workload/Manifest/**" in paths
    for p in ("workload/scripts/build_package.py", "tools/workload_package.py", "tools/workload_package_ci.py",
              "tools/workload-package.sh", ".github/workflows/workload-package.yml"):
        assert p in paths, p
    assert not any(p.startswith(("deploy", "fabric_backend")) for p in paths)
    assert "pull_request" not in on and "pull_request_target" not in on and "schedule" not in on


def test_permissions_are_least_privilege():
    assert WF["permissions"] == {}
    assert WF["jobs"]["no-variable"]["permissions"] == {}
    assert WF["jobs"]["package"]["permissions"] == {"contents": "write", "issues": "write"}
    assert "id-token" not in WF_TEXT and "pull-requests:" not in WF_TEXT
    assert WF["concurrency"]["group"] == "workload-package" and WF["concurrency"]["cancel-in-progress"] is False


def test_actions_are_pinned_by_commit_like_the_other_workflows():
    uses = re.findall(r"uses:\s*(\S+)(.*)", WF_TEXT)
    assert uses
    for ref, rest in uses:
        assert re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", ref), ref
        assert re.fullmatch(r"\s*#\s*v\d+\.\d+\.\d+\s*", rest), rest
    others = "".join(p.read_text() for p in (ROOT / ".github" / "workflows").glob("*.yml") if p != WF_PATH)
    for ref, _ in uses:                                         # the same commits the other workflows use
        assert ref in others, ref


def test_no_secret_no_upload_no_portal_call():
    assert "secrets." not in WF_TEXT
    assert "${{ vars.KRUSGRAPH_WORKLOAD_APP_ID }}" in WF_TEXT
    for bad in ("--upload", "curl ", "wget ", "Invoke-RestMethod", "api.fabric.microsoft.com", "app.fabric.microsoft.com",
                "powerbi.com", "playwright", "azure/login", "az ", "deploy.yml", "deploy/krusgraph"):
        assert bad not in WF_TEXT, bad
    assert "--full-tests" in WF_TEXT and "--summary-json" in WF_TEXT


def test_without_the_variable_it_only_says_so():
    skip = WF["jobs"]["no-variable"]
    assert skip["if"] == "vars.KRUSGRAPH_WORKLOAD_APP_ID == ''"
    assert WF["jobs"]["package"]["if"] == "vars.KRUSGRAPH_WORKLOAD_APP_ID != ''"
    run = skip["steps"][0]["run"]
    assert "Skipped" in run and "KRUSGRAPH_WORKLOAD_APP_ID" in run and "GITHUB_STEP_SUMMARY" in run
    assert "uses" not in skip["steps"][0]


def test_the_artifact_keeps_the_package_and_the_diff_for_30_days():
    steps = WF["jobs"]["package"]["steps"]
    art = next(s for s in steps if "upload-artifact" in s.get("uses", ""))
    assert art["with"]["retention-days"] == 30 and art["with"]["if-no-files-found"] == "error"
    assert "diff.txt" in art["with"]["path"] and "steps.build.outputs.file" in art["with"]["path"]
    checkout = next(s for s in steps if "actions/checkout" in s.get("uses", ""))
    assert checkout["with"]["fetch-depth"] == 0 and checkout["with"]["fetch-tags"] is True


def test_one_issue_is_updated_not_duplicated_and_a_version_is_tagged_once():
    offer = next(s for s in WF["jobs"]["package"]["steps"] if s.get("name", "").startswith("Tag the version"))
    run = offer["run"]
    assert 'gh issue edit "$ISSUE"' in run and "gh issue create" in run and 'if [ -n "$ISSUE" ]' in run
    assert run.index("git push origin") < run.index("gh issue")         # a taken version stops before the issue
    assert "--force" not in run and "git push -f" not in run and "--delete" not in run
    assert offer["if"] == "steps.build.outputs.changed == 'true' || env.OFFER_UNCHANGED == 'true'"


def test_this_round_does_not_change_deploy():
    changed = subprocess.run(["git", "diff", "--name-only", "origin/main...HEAD"], cwd=ROOT, capture_output=True,
                             text=True)
    if changed.returncode:
        pytest.skip("no origin/main here")
    names = changed.stdout.split()
    if ".github/workflows/workload-package.yml" not in names:
        pytest.skip("not on the WP1 branch")
    assert ".github/workflows/deploy.yml" not in names
    assert not [n for n in names if n.startswith("deploy/")]


# ------------------------------------------------------------------ the issue

def _bot(number, body, title="New workload package ready: Org.Krusgraph 1.0.1432", login="app/github-actions"):
    return {"number": number, "title": title, "body": body, "author": {"login": login, "is_bot": True}}


SUMMARY = {"name": "Org.Krusgraph", "version": "1.0.1432", "file": "Org.Krusgraph.1.0.1432.nupkg",
           "diff": ["Version: 3610190 -> 1.0.1432", "translations.json Workload_Hub_Slogan: \"a\" -> \"b\""],
           "identity": False, "changed": True, "tests_skipped": False}
RUN = "https://github.com/Krusmaster/fabric-backend/actions/runs/1"
ART = "https://github.com/Krusmaster/fabric-backend/actions/runs/1/artifacts/2"


def _body(summary=SUMMARY, ref="3610190", note=ci.INITIAL_NOTE):
    return ci.body(summary, artifact_url=ART, run_url=RUN, previous_ref=ref, baseline_note=note)


def test_the_issue_body_has_the_diff_the_link_the_portal_and_the_steps():
    b = _body()
    assert ci.title(SUMMARY) == "New workload package ready: Org.Krusgraph 1.0.1432"
    assert ci.MARKER in b and "<!-- workload-package baseline: 3610190 -->" in b
    assert "Workload_Hub_Slogan" in b and "Version: 3610190 -> 1.0.1432" in b
    assert f"]({ART})" in b and RUN in b and PORTAL in b
    steps = [b.index(s) for s in ("**Upload workload**", "must name **Org.Krusgraph**", "Open **Krusgraph (preview)**",
                                  "version **1.0.1432**", "**Activate**", "activate the previous version")]
    assert steps == sorted(steps)
    assert "- [ ] uploaded" in b and "Nothing was uploaded" in b
    assert "WARNING" not in b


def test_a_name_or_item_type_change_is_flagged():
    b = _body({**SUMMARY, "identity": True, "diff": ["ModelItem.xml Item type: Org.Krusgraph.Model -> Org.Krusgraph.X"]})
    assert "[!WARNING]" in b and "workload name or an item type changes" in b and "Org.Krusgraph.X" in b


def test_a_diff_line_cannot_break_out_of_the_code_block():
    b = _body({**SUMMARY, "diff": ["x ``` y"]})
    assert b.count("```") == 2


def test_no_issue_and_no_tag_compare_with_the_hand_uploaded_1_0_1395():
    got = ci.baseline([], [])
    assert got == {"previous_ref": "3610190", "baseline_note": ci.INITIAL_NOTE, "issue": "", "close_issue": ""}
    count = subprocess.run(["git", "rev-list", "--count", ci.INITIAL_REF], cwd=ROOT, capture_output=True, text=True)
    if count.returncode == 0 and subprocess.run(["git", "rev-parse", "--is-shallow-repository"], cwd=ROOT,
                                                capture_output=True, text=True).stdout.strip() == "false":
        assert count.stdout.strip() == "1395"


def test_without_an_open_issue_the_last_tag_is_the_baseline():
    got = ci.baseline([], [("1.0.1432", "workload-pkg/1.0.1432"), ("1.0.1440", "workload-pkg/1.0.1440")])
    assert got["previous_ref"] == "workload-pkg/1.0.1440" and got["issue"] == "" and got["close_issue"] == ""


def test_an_open_issue_not_uploaded_is_updated_with_its_own_baseline():
    issue = _bot(26, _body())
    got = ci.baseline([issue], [("1.0.1432", "workload-pkg/1.0.1432")])
    assert got["issue"] == "26" and got["close_issue"] == ""
    assert got["previous_ref"] == "3610190" and got["baseline_note"] == ci.INITIAL_NOTE


def test_a_ticked_issue_is_closed_and_the_next_compares_with_the_last_tag():
    body = _body().replace("- [ ] uploaded", "- [x] uploaded")
    got = ci.baseline([_bot(30, body)], [("1.0.1432", "workload-pkg/1.0.1432")])
    assert got == {"previous_ref": "workload-pkg/1.0.1432",
                   "baseline_note": "workload-pkg/1.0.1432 (the last package this workflow offered)",
                   "issue": "", "close_issue": "30"}


def test_only_the_workflow_s_own_issue_counts_and_a_bad_ref_is_ignored():
    body = _body()
    assert ci.baseline([_bot(5, body, login="someone")], [])["issue"] == ""
    assert ci.baseline([_bot(5, body, title="Other")], [])["issue"] == ""
    assert ci.baseline([_bot(5, "no marker")], [])["issue"] == ""
    evil = body.replace("baseline: 3610190", "baseline: main;rm${IFS}-rf")
    got = ci.baseline([_bot(7, evil)], [])
    assert got["issue"] == "7" and got["previous_ref"] == "3610190"
    assert ci.baseline([_bot(9, body), _bot(8, body)], [])["issue"] == "8"


def test_the_cli_writes_github_outputs(tmp_path):
    issues = tmp_path / "issues.json"
    issues.write_text(json.dumps([_bot(12, _body())]))
    lines = []
    assert ci.main(["baseline", "--issues", str(issues)], tags=lambda: [], out=lines.append) == 0
    assert "issue=12" in lines and "previous_ref=3610190" in lines
    summary = tmp_path / "s.json"
    summary.write_text(json.dumps(SUMMARY))
    lines = []
    assert ci.main(["outputs", "--summary", str(summary)], out=lines.append) == 0
    assert lines == ["name=Org.Krusgraph", "version=1.0.1432", "file=Org.Krusgraph.1.0.1432.nupkg", "changed=true"]
    lines = []
    assert ci.main(["body", "--summary", str(summary), "--artifact-url", ART, "--run-url", RUN, "--previous-ref",
                    "3610190", "--baseline-note", "x"], out=lines.append) == 0
    assert PORTAL in lines[0]
    summary.write_text(json.dumps({**SUMMARY, "version": "1.0.1432; rm"}))
    assert ci.main(["title", "--summary", str(summary)], out=lines.append) == 1


# ------------------------------------------------------------------ the versions

def test_versions_never_go_below_1_0_1396():
    assert wp.MIN_VERSION == "1.0.1396"
    assert wp.version_floor("1.0.1300", [], wp.MIN_VERSION) == "1.0.1396"
    assert wp.version_floor("1.0.1431", [], wp.MIN_VERSION) == "1.0.1431"
    assert wp.next_version(None, "patch", wp.version_floor(None, [], wp.MIN_VERSION)) == "1.0.1396"


def test_versions_grow_across_runs_even_on_the_same_commit():
    tags: list[tuple[str, str]] = []
    seen = []
    for commits in (1431, 1431, 1431, 1435, 1435, 1500):        # a manual re-run reuses a commit count
        v = wp.next_version(None, "patch", wp.version_floor(f"1.0.{commits}", tags, wp.MIN_VERSION))
        seen.append(v)
        tags = sorted(tags + [(v, f"workload-pkg/{v}")], key=lambda t: wp.parse_version(t[0]))
    assert seen == ["1.0.1431", "1.0.1432", "1.0.1433", "1.0.1435", "1.0.1436", "1.0.1500"]
    assert len(set(seen)) == len(seen)
    assert [wp.parse_version(v) for v in seen] == sorted(wp.parse_version(v) for v in seen)


def test_tags_are_read_in_version_order_and_others_ignored():
    out = "workload-pkg/1.0.1440\nworkload-pkg/1.0.999\nworkload-pkg/latest\nv1.2.3\nworkload-pkg/1.0.1500\n"
    got = wp.tag_versions(lambda cmd: out)
    assert got == [("1.0.999", "workload-pkg/1.0.999"), ("1.0.1440", "workload-pkg/1.0.1440"),
                   ("1.0.1500", "workload-pkg/1.0.1500")]

    def no_git(cmd):
        raise OSError("no git")
    assert wp.tag_versions(no_git) == []


def _main(args, tmp_path, *, tags=(), floor="1.0.1431", find=None, probe=lambda: ""):
    b = wp.load_build()
    b.default_version = lambda root=None: floor
    lines, calls = [], []

    def runner(cmd):
        calls.append(cmd)
        return 0
    code = wp.main(["--frontend-app-id", APP, "--out", str(tmp_path), *args], build=b, test_runner=runner,
                   test_find=find or (lambda m: object()), test_probe=probe, tags=list(tags), out=lines.append)
    return code, "\n".join(lines), calls


def test_the_tool_builds_above_the_last_tag_and_refuses_a_lower_version(tmp_path):
    code, out, _ = _main([], tmp_path, tags=[("1.0.1440", "workload-pkg/1.0.1440")])
    assert code == 0 and (tmp_path / "Org.Krusgraph.1.0.1441.nupkg").exists(), out
    code, out, _ = _main(["--version", "1.0.1440"], tmp_path / "b", tags=[("1.0.1440", "workload-pkg/1.0.1440")])
    assert code == 1 and "below 1.0.1441" in out and "workload-pkg/1.0.1440" in out
    code, out, _ = _main(["--version", "1.0.1395"], tmp_path / "c", floor="1.0.12")
    assert code == 1 and "below 1.0.1396" in out
    code, out, _ = _main([], tmp_path / "d", floor="1.0.12")
    assert code == 0 and (tmp_path / "d" / "Org.Krusgraph.1.0.1396.nupkg").exists()


def test_the_summary_json_is_what_the_workflow_reads(tmp_path):
    s = tmp_path / "s.json"
    code, out, _ = _main(["--previous-ref", "HEAD", "--summary-json", str(s)], tmp_path / "p")
    if code and "git could not read" in out:
        pytest.skip("no git checkout")
    assert code == 0, out
    got = json.loads(s.read_text())
    assert got["name"] == "Org.Krusgraph" and got["version"] == "1.0.1431" and got["file"] == "Org.Krusgraph.1.0.1431.nupkg"
    assert got["changed"] is False and got["identity"] is False and got["tests_skipped"] is False
    assert got["diff"][0] == "Version: HEAD -> 1.0.1431"


def test_manifest_changed_ignores_a_version_only_diff():
    assert not wp.manifest_changed(wp.Diff(lines=["Version: a -> b", "Nothing else changed in the manifest: x"]))
    assert wp.manifest_changed(wp.Diff(lines=["Version: a -> b", "Image added: images/x.png"]))
    assert wp.manifest_changed(wp.Diff(lines=["No last package to compare with"]))


# ------------------------------------------------------------------ the Cloud Shell fix (17 November 2026)

def test_a_missing_module_stops_with_the_exact_install_command(tmp_path):
    def find(mod):
        return None if mod == "PIL" else object()
    code, out, calls = _main([], tmp_path, find=find)
    assert code == 1 and not calls
    assert "STOP: The manifest tests need pillow, which is not installed here." in out
    assert "`python3 -m pip install --user pytest pillow`" in out and "--skip-tests" in out
    assert not list(tmp_path.glob("*.nupkg"))


def test_without_the_server_extras_the_light_tests_run_and_the_rest_are_named(tmp_path):
    code, out, calls = _main([], tmp_path, probe=lambda: "starlette")
    assert code == 0, out
    assert len(calls) == 1 and "--noconftest" in calls[0]
    assert set(wp.MANIFEST_TESTS) <= set(calls[0]) and not set(wp.SERVER_TESTS) & set(calls[0])
    assert "Not run here: the server-dependent workload tests" in out and "(starlette is missing)" in out
    assert "CI runs them" in out and "`python3 -m pip install --user -e '.[server,test]'`" in out


def test_full_tests_require_the_server_extras(tmp_path):
    code, out, calls = _main(["--full-tests"], tmp_path, probe=lambda: "starlette")
    assert code == 1 and not calls
    assert "--full-tests" in out and "cannot import starlette" in out
    assert "`python3 -m pip install --user -e '.[server,test]'`" in out
    assert not list(tmp_path.glob("*.nupkg"))
    code, out, calls = _main(["--full-tests"], tmp_path / "ok")
    assert code == 0 and len(calls) == 2 and set(wp.SERVER_TESTS) <= set(calls[1]) and "--noconftest" not in calls[1]


def test_the_probe_names_a_module_that_is_really_missing(tmp_path):
    """A real import in a separate Python, with a stand-in package that fails like a missing starlette."""
    fake = tmp_path / "site"
    (fake / "starlette").mkdir(parents=True)
    (fake / "starlette" / "__init__.py").write_text("raise ModuleNotFoundError(\"No module named 'starlette'\", name='starlette')\n")

    def probe():
        code = ("import importlib, sys\nsys.path.insert(0, %r)\n" % str(fake) +
                "try:\n    importlib.import_module('starlette.testclient')\n"
                "except ImportError as e:\n    print(e.name)\n")
        return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True).stdout.strip()
    assert wp.server_import_problem(probe) == "starlette"
    assert wp.server_import_problem(lambda: "") is None


def test_the_manifest_tests_need_no_server():
    """The light group imports nothing that needs the server extras, so a clean Cloud Shell can run it."""
    heavy = ("starlette", "fabric_backend.server", "from fabric_backend import server", "httpx", "mcp", "jwt")
    for t in wp.MANIFEST_TESTS:
        src = (ROOT / t).read_text(encoding="utf-8")
        for word in heavy:
            assert not re.search(rf"^\s*(import|from)\s+{re.escape(word)}\b", src, re.M), (t, word)
        assert "server." not in src, t


def test_the_doc_has_the_automatic_build_and_the_cloud_shell_steps():
    doc = (ROOT / "docs" / "WORKLOAD-PACKAGE-UPDATES.md").read_text(encoding="utf-8")
    auto = doc.split("## Automatic build")[1]
    for word in ("KRUSGRAPH_WORKLOAD_APP_ID", "Settings", "Secrets and variables", "Actions", "Variables",
                 "New repository variable", "1.0.1396", "workload-pkg/", PORTAL, "uploaded", "Krusgraph (preview)"):
        assert word in auto, word
    assert "python3 -m pip install --user pytest pillow" in doc
    assert "python3 -m pip install --user -e '.[server,test]'" in doc
