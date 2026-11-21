"""Score the spike's results against the corpus's expected answers (throwaway; see README.md).

Joins: per statement, precision = found-and-expected / found and recall = found-and-expected / expected, over
unordered {TABLE.COL, TABLE.COL} pairs; totals are micro-averaged (sums over all statements). Lineage: an output column
counts as right only when its set of base TABLE.COLUMN origins equals the expected set exactly. Parse failures: the
statement did not parse (sqlglot ParseError; sqllens syntax diagnostics). Writes results/score.md and prints it.
"""
from __future__ import annotations

import json

import spike_corpus as sc

RUNS = [("sqlglot", "sqlglot.json"), ("sqllens", "sqllens.json"),
        ("sqlglot raw", "sqlglot-raw.json"), ("sqllens raw", "sqllens-raw.json")]


def ratio(a: int, b: int) -> str:
    return "-" if b == 0 else f"{a}/{b}"


def score(items: list[dict], results: dict) -> dict:
    rows, tot = [], {"tp": 0, "found": 0, "expected": 0, "lin_ok": 0, "lin_n": 0, "parse_fail": 0}
    for it in items:
        r = results[it["id"]]
        exp, got = set(it["expected_joins"]), set(r["joins"])
        tp = len(exp & got)
        lin_ok = sum(r["lineage"].get(col) == want for col, want in it["expected_lineage"].items())
        rows.append({"id": it["id"], "dialect": it["dialect"], "tp": tp, "found": len(got), "expected": len(exp),
                     "lin_ok": lin_ok, "lin_n": len(it["expected_lineage"]), "parse_ok": r["parse_ok"],
                     "glue": r.get("glue", []), "wrong": sorted(got - exp), "missed": sorted(exp - got)})
        for k, v in (("tp", tp), ("found", len(got)), ("expected", len(exp)), ("lin_ok", lin_ok),
                     ("lin_n", len(it["expected_lineage"])), ("parse_fail", not r["parse_ok"])):
            tot[k] += v
    return {"rows": rows, "total": tot}


def pct(a: int, b: int) -> str:
    return "-" if b == 0 else f"{100 * a / b:.0f}%"


def main() -> None:
    items = sc.load()
    scored = {}
    for label, fname in RUNS:
        data = json.loads((sc.RESULTS / fname).read_text(encoding="utf-8"))
        scored[label] = {"version": data["version"], **score(items, data["results"])}
    lines = ["| Statement | Dialect | " + " | ".join(f"{t} joins P / R / lineage" for t, _ in RUNS[:2]) + " |",
             "|---|---|---|---|"]
    for i, it in enumerate(items):
        cells = []
        for label, _ in RUNS[:2]:
            r = scored[label]["rows"][i]
            mark = "" if r["parse_ok"] else " (parse fail)"
            cells.append(f"{ratio(r['tp'], r['found'])} / {ratio(r['tp'], r['expected'])} / {ratio(r['lin_ok'], r['lin_n'])}{mark}")
        lines.append(f"| {it['id']} | {it['dialect']} | " + " | ".join(cells) + " |")
    lines += ["", "| Run | Version | Join precision | Join recall | Lineage exact | Parse failures |", "|---|---|---|---|---|---|"]
    for label, _ in RUNS:
        t = scored[label]["total"]
        lines.append(f"| {label} | {scored[label]['version']} | {t['tp']}/{t['found']} ({pct(t['tp'], t['found'])}) | "
                     f"{t['tp']}/{t['expected']} ({pct(t['tp'], t['expected'])}) | {t['lin_ok']}/{t['lin_n']} "
                     f"({pct(t['lin_ok'], t['lin_n'])}) | {t['parse_fail']}/{len(items)} |")
    lines += ["", "Misses and wrong pairs/columns per run:"]
    for label, _ in RUNS:
        for r, it in zip(scored[label]["rows"], items):
            res = json.loads((sc.RESULTS / dict(RUNS)[label]).read_text(encoding="utf-8"))["results"][it["id"]]
            bad = [c for c, want in it["expected_lineage"].items() if res["lineage"].get(c) != want]
            if r["wrong"] or r["missed"] or bad:
                lines.append(f"- {label} {it['id']}: missed joins {r['missed'] or '-'}; wrong joins {r['wrong'] or '-'}; "
                             f"lineage wrong {[(c, res['lineage'].get(c)) for c in bad] or '-'}")
    text = "\n".join(lines) + "\n"
    (sc.RESULTS / "score.md").write_text(text, encoding="utf-8")
    sc.write_json(sc.RESULTS / "score.json", scored)
    print(text)


if __name__ == "__main__":
    main()
