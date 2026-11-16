"""B3 (16 November 2026, backlog X-23): the SBOM covers Python, the editor's npm packages and the image, and reaches a
release only when the maintainer has made one. The workflow file is read here; the tag path has not run."""
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
TEXT = (ROOT / ".github" / "workflows" / "sbom.yml").read_text(encoding="utf-8")
WF = yaml.safe_load(TEXT)
FILES = ["sbom.cdx.json", "sbom-editor.cdx.json", "sbom-image.cdx.json"]


def steps(job):
    return WF["jobs"][job]["steps"]


def test_three_sboms_are_built_and_kept_together():
    runs = "\n".join(str(s.get("run", "")) for s in steps("sbom"))
    assert "cyclonedx-py requirements deploy/constraints.txt" in runs and "-o sbom.cdx.json" in runs
    npm = next(s for s in steps("sbom") if "cyclonedx-npm" in str(s.get("run", "")))
    assert npm["working-directory"] == "workload/Workload" and (ROOT / "workload/Workload/package-lock.json").is_file()
    assert re.search(r'"@cyclonedx/cyclonedx-npm@\d+\.\d+\.\d+" --package-lock-only', npm["run"])       # an exact version; nothing installed
    assert "sbom-editor.cdx.json" in npm["run"] and "if" not in npm                                    # on every push
    image = next(s for s in steps("sbom") if "anchore/sbom-action@" in str(s.get("uses", "")))
    assert image["with"] == {"image": "krusgraph-sbom:${{ github.sha }}", "format": "cyclonedx-json",
                             "output-file": "sbom-image.cdx.json", "upload-artifact": False, "upload-release-assets": False}
    build = next(s for s in steps("sbom") if str(s.get("run", "")).startswith("docker build"))
    assert build["if"] == image["if"] == "github.ref_type == 'tag' || github.event_name == 'workflow_dispatch'"
    assert "push" not in build["run"]                                                                  # built, never pushed
    upload = next(s for s in steps("sbom") if "upload-artifact@" in str(s.get("uses", "")))
    assert upload["with"]["path"].split() == FILES + ["release-notes.md"]


def test_only_the_release_job_can_write_and_it_never_creates_a_release():
    assert WF["permissions"] == {"contents": "read"} and "permissions" not in WF["jobs"]["sbom"]
    rel = WF["jobs"]["release"]
    assert rel["permissions"] == {"contents": "write"} and rel["if"] == "github.ref_type == 'tag'" and rel["needs"] == "sbom"
    assert [("uses" in s and s["uses"].split("@")[0]) or "run" for s in rel["steps"]] == ["actions/download-artifact", "run"]
    run = rel["steps"][1]["run"]
    assert 'if gh release view "$GITHUB_REF_NAME"' in run
    assert f'gh release upload "$GITHUB_REF_NAME" {" ".join(FILES)} --clobber' in run
    for word in ("release create", "release edit", "release delete", "git push", "git tag", "npx", "pip", "docker"):
        assert word not in run and word not in str(rel["steps"][0]), word
    assert "gh release" not in "\n".join(str(s.get("run", "")) for s in steps("sbom"))
    assert rel["steps"][0]["with"]["name"] == next(s for s in steps("sbom") if "upload-artifact@" in str(s.get("uses", "")))["with"]["name"]


def test_the_runbook_says_how_the_files_reach_a_release_and_what_has_not_run():
    ops = " ".join((ROOT / "docs" / "OPERATIONS.md").read_text(encoding="utf-8").split())
    for f in FILES:
        assert f"`{f}`" in ops and f in TEXT
    assert "it creates no release itself" in ops and "The tag path has not run yet" in ops and "The image is not signed" in ops
