#!/usr/bin/env python3
"""CD1 (16 November 2026): the paths a round may never merge on its own.

CONTRIBUTING.md, "Merging and deploying", lets a round merge its own pull request when every CI job is green and the
pull request touches only code, tests and public docs. Some changes always wait for the maintainer: the pull request
carries the label `needs-gustav` and the round stops. This script is the check behind that rule
(.github/workflows/path-guard.yml): it lists what a pull request changes between two commits and fails when any of it
is protected and the label is missing. With the label it passes and says which rules matched, so the maintainer sees
why.

    python tools/path_guard.py --base <sha> --head <sha> --labels "needs-gustav,other"

Only the standard library; no network.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import sys

LABEL = "needs-gustav"

# (reason, patterns). A pattern is an fnmatch pattern on the repository path, where * also matches "/".
RULES: list[tuple[str, tuple[str, ...]]] = [
    ("social media or marketing copy meant for publishing", (
        "social/*", "docs/marketing/*", "*/marketing/*")),
    ("pricing or sales material (does not belong in this repository; see CONTRIBUTING.md)", (
        "*pricing*", "*price-list*", "*price_list*", "*sales-deck*", "*sales_deck*", "*battlecard*",
        "docs/BILLING-MODEL.md")),
    ("legal pages' text", (
        "fabric_backend/legal.py", "fabric_backend/page_templates/PRIVACY.md", "fabric_backend/page_templates/terms.html",
        "fabric_backend/page_templates/cookies.html", "fabric_backend/page_templates/SECURITY-POLICY.md",
        "docs/DPA-DRAFT.md", "LICENSE", "workload/LICENSE", "CODE_OF_CONDUCT.md")),
    ("the workload name or manifest identity", (
        "workload/Workload/Manifest/*", "workload/scripts/build_package.py", "workload/scripts/build-package",
        "workload/scripts/Build/*", "workload/Workload/.env*", "docs/WORKLOAD-PUBLISH.md", "server.json")),
    ("secrets, permissions or deployment", (
        ".github/workflows/*", ".github/dependabot.yml", ".github/CODEOWNERS", "CODEOWNERS",
        "deploy/*.py", "deploy/*.sh", "deploy/krusgraph.example.json", "Dockerfile", ".dockerignore",
        "fabric_backend/entra.py", "fabric_backend/access.py", "SECURITY.md", "docs/AUTO-DEPLOY.md")),
    ("deletion or retention of user data", (
        "fabric_backend/registration_store.py", "fabric_backend/usage.py")),
    ("the merge policy and this check", (
        "CONTRIBUTING.md", "tools/path_guard.py", ".github/PULL_REQUEST_TEMPLATE.md")),
]

# Dependency files whose pins are compared for a major bump (path -> parser kind).
DEPENDENCY_FILES = {
    "deploy/constraints.txt": "pip",
    "pyproject.toml": "pip",
    "workload/Workload/package.json": "npm",
}


def protected(paths) -> list[tuple[str, str]]:
    """(path, reason) for every changed path a protected rule matches; the first matching rule names the reason."""
    hits = []
    for path in paths:
        for reason, patterns in RULES:
            if any(fnmatch.fnmatchcase(path.lower(), p.lower()) for p in patterns):   # PRICING.md too
                hits.append((path, reason))
                break
    return hits


_PIP = re.compile(r"^\s*\"?([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]*\])?\s*(?:==|>=|~=|===)\s*v?(\d+)(?:\.(\d+))?")


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def pip_versions(text: str) -> dict[str, tuple[int, int]]:
    """name -> (major, minor) of each pinned or lower-bounded requirement (constraints.txt lines, pyproject lists)."""
    out = {}
    for line in (text or "").splitlines():
        m = _PIP.match(line.split("#", 1)[0].strip().strip(","))
        if m:
            out[_norm(m.group(1))] = (int(m.group(2)), int(m.group(3) or 0))
    return out


def npm_versions(text: str) -> dict[str, tuple[int, int]]:
    """name -> (major, minor) of package.json's dependencies, devDependencies, peer and optional dependencies."""
    try:
        data = json.loads(text or "{}")
    except ValueError:
        return {}
    out = {}
    for section in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        for name, spec in (data.get(section) or {}).items():
            m = re.search(r"(\d+)(?:\.(\d+))?", str(spec))
            if m:
                out[f"{section}:{name}"] = (int(m.group(1)), int(m.group(2) or 0))
    return out


def _breaking(old: tuple[int, int], new: tuple[int, int]) -> bool:
    """A new major, or for 0.x a new minor (semver's rule for versions before 1.0). A downgrade counts too."""
    if old[0] != new[0]:
        return True
    return old[0] == 0 and old[1] != new[1]


def major_bumps(old_text: str, new_text: str, kind: str) -> list[str]:
    read = npm_versions if kind == "npm" else pip_versions
    old, new = read(old_text), read(new_text)
    return [f"{name} {old[name][0]}.{old[name][1]} -> {new[name][0]}.{new[name][1]}"
            for name in sorted(old.keys() & new.keys()) if _breaking(old[name], new[name])]


def evaluate(paths, labels, file_at=None) -> tuple[bool, list[str]]:
    """(ok, lines). `file_at(rev, path)` returns a file's text at "base" or "head" (or "" when absent); without it,
    dependency files are not compared."""
    labels = {label.strip() for label in labels if label.strip()}
    reasons = [f"{path}: {reason}" for path, reason in protected(paths)]
    if file_at:
        for path, kind in DEPENDENCY_FILES.items():
            if path in paths:
                reasons += [f"{path}: dependency major bump ({b})"
                            for b in major_bumps(file_at("base", path), file_at("head", path), kind)]
    if not reasons:
        return True, ["No protected path changed; a round may merge this pull request itself once every CI job is green."]
    if LABEL in labels:
        return True, [f"Protected changes, and the label '{LABEL}' is set: the maintainer merges this one."] + reasons
    return False, [f"Protected changes without the label '{LABEL}'. Add the label and leave the merge to the maintainer "
                   "(CONTRIBUTING.md, \"Merging and deploying\"):"] + reasons


def _git(*args) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout


def changed_paths(base: str, head: str) -> list[str]:
    """Every path the pull request adds, changes, deletes or renames (both names of a rename), against the merge base."""
    paths = []
    for line in _git("diff", "--name-status", "-z", f"{base}...{head}").split("\0"):
        if line and not re.fullmatch(r"[ACDMRTUX]\d*", line):
            paths.append(line)
    return sorted(set(paths))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--labels", default="", help="comma-separated label names of the pull request")
    args = parser.parse_args(argv)
    merge_base = _git("merge-base", args.base, args.head).strip()
    revs = {"base": merge_base, "head": args.head}

    def file_at(which, path):
        try:
            return _git("show", f"{revs[which]}:{path}")
        except subprocess.CalledProcessError:
            return ""

    ok, lines = evaluate(changed_paths(args.base, args.head), args.labels.split(","), file_at)
    print("\n".join(lines))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
