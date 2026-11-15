"""Compare two score files and fail when any score got worse (round E1, docs/EVOLUTION.md, the gate).

A score file (written by tools/evolution/scores.py, or by any later corpus that uses the same form):

    {"format": "krusgraph-scores", "version": 1, "source": "...",
     "scores": {"inference/northwind/key_hits": {"value": 11, "better": "higher"}, ...}}

`better` says which direction is an improvement: "higher", "lower", or "same" (a number that describes the corpus
itself, such as how many keys a fixture declares; any change to it is reported, because a corpus that shrinks makes
every other score easier).

The rule, per score and with no trading between scores:
  - "higher": the new value below the baseline is a regression
  - "lower":  the new value above the baseline is a regression
  - "same":   any other value is a regression
  - a score in the baseline that is missing from the new file is a regression
  - a score whose `better` changed is a regression (the direction is part of the score)
  - a score only in the new file is listed as new and never fails

A regression that is wanted (a wrong fixture removed, a rule traded for another) is made by changing the baseline file
in a commit of its own that says why and who said yes; this script has no switch that lets one through.

Usage:
    python tools/evolution/score_diff.py BASELINE.json CURRENT.json [--json]

Exit code 0: nothing got worse. 1: at least one regression. 2: a file could not be read or is not a score file.
Standard library only; no network.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

FORMAT = "krusgraph-scores"
VERSION = 1
BETTER = ("higher", "lower", "same")


class ScoreFileError(ValueError):
    """The file is not a readable score file."""


def check_scores(doc, where: str = "score file") -> dict:
    """The `scores` mapping of a score document, or ScoreFileError saying what is wrong with it."""
    if not isinstance(doc, dict) or doc.get("format") != FORMAT or doc.get("version") != VERSION:
        raise ScoreFileError(f"{where}: not a {FORMAT} version {VERSION} file")
    scores = doc.get("scores")
    if not isinstance(scores, dict) or not scores:
        raise ScoreFileError(f"{where}: no scores")
    for name, s in scores.items():
        ok = (isinstance(s, dict) and set(s) == {"value", "better"} and s["better"] in BETTER
              and isinstance(s["value"], (int, float)) and not isinstance(s["value"], bool))
        if not ok:
            raise ScoreFileError(f"{where}: score {name!r} must be {{'value': number, 'better': one of {BETTER}}}")
    return scores


def load(path) -> dict:
    try:
        return check_scores(json.loads(Path(path).read_text(encoding="utf-8")), str(path))
    except (OSError, ValueError) as e:
        if isinstance(e, ScoreFileError):
            raise
        raise ScoreFileError(f"{path}: {e}") from e


def diff(baseline: dict, current: dict) -> dict:
    """Both arguments are `scores` mappings. Returns the four lists, each sorted by score name, and `ok`."""
    regressions, improvements, new = [], [], []
    for name in sorted(baseline):
        b = baseline[name]
        c = current.get(name)
        if c is None:
            regressions.append({"score": name, "baseline": b["value"], "current": None, "why": "missing from the new file"})
            continue
        if c["better"] != b["better"]:
            regressions.append({"score": name, "baseline": b["value"], "current": c["value"],
                                "why": f"direction changed from {b['better']} to {c['better']}"})
            continue
        if c["value"] == b["value"]:
            continue
        row = {"score": name, "baseline": b["value"], "current": c["value"]}
        worse = {"higher": c["value"] < b["value"], "lower": c["value"] > b["value"], "same": True}[b["better"]]
        if worse:
            regressions.append({**row, "why": {"higher": "lower than the baseline", "lower": "higher than the baseline",
                                               "same": "changed, and this number describes the corpus"}[b["better"]]})
        else:
            improvements.append(row)
    for name in sorted(set(current) - set(baseline)):
        new.append({"score": name, "current": current[name]["value"]})
    return {"ok": not regressions, "compared": len(baseline), "unchanged": len(baseline) - len(regressions) - len(improvements),
            "regressions": regressions, "improvements": improvements, "new": new}


def text(result: dict) -> str:
    lines = [f"{result['compared']} scores compared: {len(result['regressions'])} worse, "
             f"{len(result['improvements'])} better, {result['unchanged']} unchanged, {len(result['new'])} new."]
    for title, key in (("Worse", "regressions"), ("Better", "improvements")):
        if result[key]:
            lines += ["", f"{title}:"]
            lines += [f"  {r['score']}: {r['baseline']} -> {r['current']}" + (f" ({r['why']})" if "why" in r else "")
                      for r in result[key]]
    if result["new"]:
        lines += ["", "New:"] + [f"  {r['score']}: {r['current']}" for r in result["new"]]
    lines += ["", "No score got worse." if result["ok"] else "FAILED: a score got worse. See the module text for how a wanted change is made."]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Fail when a score got worse than the baseline.")
    ap.add_argument("baseline")
    ap.add_argument("current")
    ap.add_argument("--json", action="store_true", help="print the result as JSON")
    a = ap.parse_args(argv)
    try:
        result = diff(load(a.baseline), load(a.current))
    except ScoreFileError as e:
        print(f"score_diff: {e}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True) if a.json else text(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
