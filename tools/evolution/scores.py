"""Write today's scores as one score file (round E1, docs/EVOLUTION.md).

Until a larger regression corpus with its own published scores exists, the scores are the ones the repository already
asserts: how many declared keys and foreign keys `plan()` recovers from names alone on the openly licensed and the
hand-written schemas in tests/fixtures/schemas/ (tests/test_inference_quality.py, docs/INFERENCE.md). This script only
puts those numbers into the form tools/evolution/score_diff.py compares; it computes nothing of its own. A later corpus
adds its scores to the same file under its own prefix.

    python tools/evolution/scores.py                 # print the score file
    python tools/evolution/scores.py --out FILE      # write it
    python tools/evolution/score_diff.py tools/evolution/baseline/scores.json FILE

tools/evolution/baseline/scores.json is the baseline on main. tests/test_e1_evolution.py runs the comparison in the
ordinary suite, so a push that lowers a score is red. No network; synthetic and public schemas only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = Path(__file__).resolve().parent / "baseline" / "scores.json"

# what each number of tests/test_inference_quality.score() means for the gate
DIRECTION = {
    "key_hits": "higher", "rel_hits": "higher",                 # declared keys and foreign keys that were found
    "key_wrong": "lower", "rel_wrong": "lower",                 # inferred, and not what the schema declares
    "tables": "same", "keys_declared": "same", "fks_declared": "same",   # the corpus itself
}


def collect() -> dict:
    for p in (str(ROOT), str(ROOT / "tests")):
        if p not in sys.path:
            sys.path.insert(0, p)
    import test_inference_quality as q

    scores = {}
    for name in q.NAMES + q.SYNTHETIC:
        got = q.score(q.load(name))
        for metric, better in DIRECTION.items():
            scores[f"inference/{name}/{metric}"] = {"value": got[metric], "better": better}
    return {"format": "krusgraph-scores", "version": 1,
            "source": "tests/test_inference_quality.py: keys and foreign keys recovered from names alone",
            "scores": dict(sorted(scores.items()))}


def dumps(doc: dict) -> str:
    return json.dumps(doc, indent=1, sort_keys=True) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Write the current scores as a score file.")
    ap.add_argument("--out", help="file to write (default: print)")
    a = ap.parse_args(argv)
    out = dumps(collect())
    if a.out:
        Path(a.out).write_text(out, encoding="utf-8")
    else:
        sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
