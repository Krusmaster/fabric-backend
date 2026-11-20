#!/usr/bin/env python3
"""WP1 (18 November 2026): the parts of .github/workflows/workload-package.yml that are worth testing.

When the workload manifest changes on main, the workflow builds the package with tools/workload_package.py (all tests),
keeps the .nupkg and the diff as the run's artifact, and opens one GitHub issue that tells Gustav what changes for
Fabric and how to upload it by hand. Microsoft documents no upload API (docs/WORKLOAD-PACKAGE-UPDATES.md), so nothing
here, and nothing in the workflow, calls Fabric or any portal endpoint.

    python tools/workload_package_ci.py baseline --issues <gh issue list JSON> [--tags-from-git]
        prints, for $GITHUB_OUTPUT: previous_ref (what the diff compares with), baseline_note (the same in words),
        issue (the number of the open package issue to update, or empty) and close_issue (an issue marked uploaded,
        to close before a new one is opened)
    python tools/workload_package_ci.py body --summary <the tool's --summary-json> --artifact-url <url> --run-url <url>
        --previous-ref <ref> --baseline-note <words>
        prints the issue's body (Markdown)
    python tools/workload_package_ci.py title --summary <file>
    python tools/workload_package_ci.py outputs --summary <file>     (name, version, file, changed, for $GITHUB_OUTPUT)

Standard library only.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import workload_package as wp  # noqa: E402

TITLE_PREFIX = "New workload package ready:"
MARKER = "<!-- workload-package-issue -->"
BASELINE_MARKER = re.compile(r"<!-- workload-package baseline: ([^ ]+) -->")
# A ref read back from an issue body is used only if it looks like one of ours: a commit id or a workload-pkg/ tag.
SAFE_REF = re.compile(r"^(?:[0-9a-f]{7,40}|workload-pkg/\d+\.\d+\.\d+)$")
UPLOADED_DONE = re.compile(r"^\s*-\s*\[[xX]\]\s*uploaded\b", re.M)
# Before the first package of this workflow: main at 3610190 (17 November 2026, 20:55 CET, the merge of PR #49) is the
# commit with 1395 commits, so `1.0.<commits>` there is 1.0.1395, the version Gustav uploaded and activated by hand that
# evening. Its manifest is the first baseline; the manifest has not changed between it and WP1.
INITIAL_REF = "3610190"
INITIAL_NOTE = ("the manifest at 3610190 (main on 17 November 2026 with 1395 commits, so most likely what 1.0.1395, "
                "the version active in Fabric, was built from)")


def _ours(issue: dict) -> bool:
    """An issue this workflow opened: the marker, the title, and written by GitHub Actions (not anyone's copy)."""
    login = str((issue.get("author") or {}).get("login", ""))
    return (MARKER in (issue.get("body") or "") and str(issue.get("title", "")).startswith(TITLE_PREFIX)
            and login in ("app/github-actions", "github-actions", "github-actions[bot]"))


def find_issue(issues: list[dict]) -> dict | None:
    """The open package issue (the lowest number if there were ever two)."""
    ours = sorted((i for i in issues if _ours(i)), key=lambda i: int(i["number"]))
    return ours[0] if ours else None


def is_uploaded(body: str) -> bool:
    return bool(UPLOADED_DONE.search(body or ""))


def baseline(issues: list[dict], tags: list[tuple[str, str]]) -> dict[str, str]:
    """What the next package is compared with, and which issue to update or close.

    - An open issue whose box 'uploaded' is not ticked: Gustav has not uploaded that package yet, so the new package
      replaces it in the same issue, compared with the same baseline as before (everything since the last upload).
    - An open issue that is ticked, or none: compare with the last package this workflow offered (the highest
      workload-pkg/ tag), or before the first one, with INITIAL_REF.
    """
    issue = find_issue(issues)
    last = (tags[-1][1], f"{tags[-1][1]} (the last package this workflow offered)") if tags else (INITIAL_REF, INITIAL_NOTE)
    out = {"previous_ref": last[0], "baseline_note": last[1], "issue": "", "close_issue": ""}
    if issue is None:
        return out
    body = issue.get("body") or ""
    if is_uploaded(body):
        out["close_issue"] = str(issue["number"])
        return out
    m = BASELINE_MARKER.search(body)
    ref = m.group(1) if m else ""
    if SAFE_REF.match(ref):
        note = next((ln[len("**Compared with:**"):].strip() for ln in body.splitlines()
                     if ln.startswith("**Compared with:**")), ref)
        out.update(previous_ref=ref, baseline_note=note)
    out["issue"] = str(issue["number"])
    return out


def title(summary: dict) -> str:
    return f"{TITLE_PREFIX} {summary['name']} {summary['version']}"


def body(summary: dict, *, artifact_url: str, run_url: str, previous_ref: str, baseline_note: str) -> str:
    """The issue: what changes for Fabric, where the file is, and the exact portal steps. Nothing is uploaded."""
    name, version, file = summary["name"], summary["version"], summary["file"]
    shown = wp.DISPLAY_NAME.get(name, name)
    diff = [ln.replace("```", "'''") for ln in summary.get("diff", [])]     # a text cannot close the code block
    repo = run_url.split("/actions/")[0] if "/actions/" in run_url else "https://github.com/Krusmaster/fabric-backend"
    lines = [
        MARKER,
        f"<!-- workload-package baseline: {previous_ref} -->",
        f"A new Fabric workload package was built from `main`: **{name} {version}** (`{file}`). "
        "Nothing was uploaded: Microsoft documents no API for that, so it is a portal step "
        f"([docs/WORKLOAD-PACKAGE-UPDATES.md]({repo}/blob/main/docs/WORKLOAD-PACKAGE-UPDATES.md)).",
        "",
        f"**Compared with:** {baseline_note}",
        "",
    ]
    if summary.get("identity"):
        lines += ["> [!WARNING]",
                  "> **The workload name or an item type changes.** Fabric keeps a name for good once it is uploaded. "
                  "Upload only if that is intended.", ""]
    lines += ["### What changes for Fabric", "", "```text", *(diff or ["(no lines)"]), "```", ""]
    if summary.get("tests_skipped"):
        lines += ["**The manifest tests were skipped for this build.**", ""]
    else:
        lines += ["The build's manifest checks and all workload manifest tests passed in the run.", ""]
    lines += [
        "### Download",
        "",
        f"- The package and the diff: [the run's artifact]({artifact_url}) (a zip; unzip it to get `{file}`). "
        "Kept for 30 days.",
        f"- The run: {run_url}",
        "",
        "### Upload it (as a Fabric administrator)",
        "",
        f"1. Open {wp.PORTAL_URL} (OneLake catalog > Govern > Configurations > Workloads).",
        f"2. **Upload workload** > choose `{file}`.",
        f"3. The dialog must name **{name}**. If it names anything else, cancel.",
        f"4. Open **{shown}** > select version **{version}** > **Activate**. Reload the Fabric tab.",
        "5. Undo: open the same page and activate the previous version again.",
        "",
        "When it is done, tick the box. The next package then starts a new issue and is compared with this one.",
        "",
        "- [ ] uploaded",
        "",
        "_Built by `.github/workflows/workload-package.yml`. A new package before the box is ticked replaces this one "
        "here, still compared with the same starting point._",
    ]
    return "\n".join(lines) + "\n"


def _git_tags() -> list[tuple[str, str]]:
    return wp.tag_versions()


def main(argv=None, *, tags: Callable[[], list[tuple[str, str]]] = _git_tags, out=print) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("baseline")
    b.add_argument("--issues", type=Path, required=True)
    for cmd in ("title", "outputs"):
        sub.add_parser(cmd).add_argument("--summary", type=Path, required=True)
    p = sub.add_parser("body")
    p.add_argument("--summary", type=Path, required=True)
    p.add_argument("--artifact-url", required=True)
    p.add_argument("--run-url", required=True)
    p.add_argument("--previous-ref", required=True)
    p.add_argument("--baseline-note", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "baseline":
        result = baseline(json.loads(a.issues.read_text(encoding="utf-8") or "[]"), tags())
        for k, v in result.items():
            out(f"{k}={v.replace(chr(10), ' ')}")
        return 0
    summary = json.loads(a.summary.read_text(encoding="utf-8"))
    if not wp._VERSION.match(summary.get("version", "")) or summary.get("name") not in ("Org.Krusgraph", "Krusgraph.Modeler"):
        out("STOP: the summary does not name a Krusgraph package and version")
        return 1
    if a.cmd == "title":
        out(title(summary))
    elif a.cmd == "outputs":
        for k in ("name", "version", "file"):
            out(f"{k}={summary[k]}")
        out(f"changed={'true' if summary.get('changed') else 'false'}")
    else:
        out(body(summary, artifact_url=a.artifact_url, run_url=a.run_url, previous_ref=a.previous_ref,
                 baseline_note=a.baseline_note).rstrip("\n"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
