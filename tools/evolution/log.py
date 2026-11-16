"""Append one entry to the evolution log from a round's report (round E1, docs/EVOLUTION.md, "record").

The log is a JSON Lines file: one entry per line, appended and never edited. A correction is a new entry whose
`corrects` names the old entry's id. Where the log lives is the caller's choice (`--log`); the log this project keeps
is in the private repository, because an entry may point at a customer's signal. Nothing here opens a network
connection, and nothing in an entry may be a row value, a secret or (in a public file) a customer's name.

A round's report is one JSON object:

    {"date": "2026-11-15", "round": "E1", "title": "what changed, in one line",
     "status": "shipped",                                  # shipped | proposed | rejected | measured
     "signals": [{"kind": "founder", "ref": "12 Nov 2026"}],          # kinds: SIGNALS below
     "proposal": "what was proposed and why",
     "gate": {"scores": "no_regression",                   # no_regression | regression | not_run
              "scores_ref": "77 compared, 0 worse",
              "evidence": ["tests/test_e1_evolution.py"],  # what each claim in the change rests on
              "others_code": false,                        # true when code from another project is reused
              "founder_yes": "not_needed"},                # not_needed | yes | pending | no
     "shipped": ["8066dd0"],                               # commits
     "measure": {"scores_before": "...", "scores_after": "...", "evidence_coverage": "...",
                 "steps_to_first_trusted_model": "..."},   # free text or "not measured"
     "next": ["..."], "corrects": "<id>"}                  # both optional

The gate is checked again here, so the log cannot record what the gate forbids:
  - status "shipped" needs gate.scores "no_regression", at least one line of evidence and at least one commit
  - reused code that shipped needs founder_yes "yes"
  - gate.scores "regression" can only be recorded as "rejected" or "proposed"

Usage:
    python tools/evolution/log.py append REPORT.json --log LOG.jsonl
    python tools/evolution/log.py render --log LOG.jsonl [--out LOG.md]

Exit code 0: done. 1: the report breaks a rule above, or the entry is already in the log. 2: a file could not be read.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

FORMAT = "krusgraph-evolution-log"
VERSION = 1
SIGNALS = ("tenant_decision", "failed_check", "not_counted_check", "card_flag", "first_user_test", "mcp_scout",
           "platform_release", "pack_gap", "regression_score", "case_library", "founder")
STATUS = ("shipped", "proposed", "rejected", "measured")
GATE_SCORES = ("no_regression", "regression", "not_run")
FOUNDER_YES = ("not_needed", "yes", "pending", "no")
MEASURES = ("scores_before", "scores_after", "evidence_coverage", "steps_to_first_trusted_model")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
_ROUND = re.compile(r"[A-Za-z][A-Za-z0-9-]{0,15}\Z")
_COMMIT = re.compile(r"[0-9a-f]{7,40}\Z")


def _text(v, most: int) -> bool:
    return isinstance(v, str) and 0 < len(v.strip()) <= most and "\n" not in v


def problems(report) -> list[str]:
    """Everything wrong with a report, in a fixed order; empty when it may be appended."""
    if not isinstance(report, dict):
        return ["the report is not a JSON object"]
    out = []
    known = {"date", "round", "title", "status", "signals", "proposal", "gate", "shipped", "measure", "next", "corrects"}
    out += [f"unknown field {k!r}" for k in sorted(set(report) - known)]
    if not (isinstance(report.get("date"), str) and _DATE.match(report["date"])):
        out.append("date must be YYYY-MM-DD")
    if not (isinstance(report.get("round"), str) and _ROUND.match(report["round"])):
        out.append("round must be a round name such as E1 or n240")
    if not _text(report.get("title"), 160):
        out.append("title must be one line of at most 160 characters")
    if report.get("status") not in STATUS:
        out.append(f"status must be one of {STATUS}")
    signals = report.get("signals")
    if not (isinstance(signals, list) and signals):
        out.append("signals must name at least one signal: a change with no signal behind it is not recorded as evolution")
    else:
        for s in signals:
            if not (isinstance(s, dict) and set(s) == {"kind", "ref"} and s["kind"] in SIGNALS and _text(s["ref"], 200)):
                out.append(f"each signal is {{'kind': one of {SIGNALS}, 'ref': where it can be read}}")
                break
    if not _text(report.get("proposal"), 800):
        out.append("proposal must be one line of at most 800 characters")
    gate = report.get("gate")
    if not isinstance(gate, dict) or set(gate) - {"scores", "scores_ref", "evidence", "others_code", "founder_yes"}:
        out.append("gate must hold scores, scores_ref, evidence, others_code and founder_yes, and nothing else")
        gate = {}
    else:
        if gate.get("scores") not in GATE_SCORES:
            out.append(f"gate.scores must be one of {GATE_SCORES}")
        if "scores_ref" in gate and not _text(gate["scores_ref"], 200):
            out.append("gate.scores_ref must be one line")
        ev = gate.get("evidence", [])
        if not (isinstance(ev, list) and all(_text(e, 200) for e in ev)):
            out.append("gate.evidence must be a list of one-line references")
        if not isinstance(gate.get("others_code"), bool):
            out.append("gate.others_code must be true or false")
        if gate.get("founder_yes") not in FOUNDER_YES:
            out.append(f"gate.founder_yes must be one of {FOUNDER_YES}")
    shipped = report.get("shipped", [])
    if not (isinstance(shipped, list) and all(isinstance(c, str) and _COMMIT.match(c) for c in shipped)):
        out.append("shipped must be a list of commit ids (7 to 40 hex characters)")
        shipped = []
    measure = report.get("measure", {})
    if not (isinstance(measure, dict) and set(measure) <= set(MEASURES) and all(_text(v, 300) for v in measure.values())):
        out.append(f"measure may hold {MEASURES}, each one line")
    nxt = report.get("next", [])
    if not (isinstance(nxt, list) and all(_text(n, 300) for n in nxt)):
        out.append("next must be a list of one-line items")
    if "corrects" in report and not _text(report["corrects"], 60):
        out.append("corrects must be an entry id")
    if out:
        return out
    # the gate, checked again where it is recorded
    if report["status"] == "shipped":
        if gate["scores"] != "no_regression":
            out.append("shipped needs gate.scores 'no_regression': run tools/evolution/score_diff.py first")
        if not gate.get("evidence"):
            out.append("shipped needs at least one line of evidence in gate.evidence")
        if not shipped:
            out.append("shipped needs at least one commit in shipped")
        if gate["others_code"] and gate["founder_yes"] != "yes":
            out.append("reused code ships only with gate.founder_yes 'yes'")
    if gate["scores"] == "regression" and report["status"] not in ("rejected", "proposed"):
        out.append("a change that lowers a score is recorded as 'rejected' or 'proposed', never as shipped or measured")
    return out


def entry_id(report: dict) -> str:
    return f"{report['date']}-{report['round']}-{hashlib.sha256(report['title'].strip().encode('utf-8')).hexdigest()[:8]}"


def entry(report: dict) -> dict:
    """The log entry for a valid report: the report's fields in a fixed order, plus format, version and id."""
    e = {"format": FORMAT, "version": VERSION, "id": entry_id(report)}
    for k in ("date", "round", "title", "status", "signals", "proposal", "gate", "shipped", "measure", "next", "corrects"):
        if k in report:
            e[k] = report[k]
    e.setdefault("shipped", [])
    return e


def read(log) -> list[dict]:
    p = Path(log)
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def append(report: dict, log) -> dict:
    """Append the report to the log and return the entry. ValueError with every problem when it may not be appended."""
    bad = problems(report)
    if bad:
        raise ValueError("; ".join(bad))
    e = entry(report)
    existing = read(log)
    if any(x.get("id") == e["id"] for x in existing):
        raise ValueError(f"{e['id']} is already in the log; a correction is a new entry with 'corrects'")
    if "corrects" in e and not any(x.get("id") == e["corrects"] for x in existing):
        raise ValueError(f"corrects names {e['corrects']!r}, which is not in the log")
    p = Path(log)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(e, ensure_ascii=False, sort_keys=False) + "\n")
    return e


def render(entries: list[dict]) -> str:
    """The log as Markdown, newest first; the same entries always give the same text."""
    lines = ["# Evolution log", "",
             "Rendered from the JSON Lines log by `tools/evolution/log.py render`. Do not edit: append a report instead.", ""]
    corrected = {e["corrects"] for e in entries if "corrects" in e}
    for e in sorted(entries, key=lambda x: (x["date"], x["id"]), reverse=True):
        g = e["gate"]
        lines += [f"## {e['date']} · {e['round']} · {e['title']}" + (" (corrected by a later entry)" if e["id"] in corrected else ""), "",
                  f"- Id: `{e['id']}`" + (f", corrects `{e['corrects']}`" if "corrects" in e else ""),
                  f"- Status: {e['status']}",
                  "- Signals: " + "; ".join(f"{s['kind']} ({s['ref']})" for s in e["signals"]),
                  f"- Proposal: {e['proposal']}",
                  f"- Gate: scores {g['scores']}" + (f" ({g['scores_ref']})" if g.get("scores_ref") else "")
                  + f"; evidence: {'; '.join(g.get('evidence') or ['none'])}; reused code: {'yes' if g['others_code'] else 'no'}"
                  + f"; founder's yes: {g['founder_yes']}",
                  "- Shipped: " + (", ".join(f"`{c}`" for c in e["shipped"]) or "nothing")]
        if e.get("measure"):
            lines.append("- Measure: " + "; ".join(f"{k.replace('_', ' ')}: {e['measure'][k]}" for k in MEASURES if k in e["measure"]))
        if e.get("next"):
            lines.append("- Next: " + "; ".join(e["next"]))
        lines.append("")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Append to and render the evolution log.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a_ = sub.add_parser("append")
    a_.add_argument("report")
    a_.add_argument("--log", required=True)
    r_ = sub.add_parser("render")
    r_.add_argument("--log", required=True)
    r_.add_argument("--out")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "append":
            report = json.loads(Path(a.report).read_text(encoding="utf-8"))
            try:
                e = append(report, a.log)
            except ValueError as err:
                print(f"log: not appended: {err}", file=sys.stderr)
                return 1
            print(f"appended {e['id']} to {a.log}")
            return 0
        out = render(read(a.log))
        if a.out:
            Path(a.out).write_text(out, encoding="utf-8")
        else:
            sys.stdout.write(out)
        return 0
    except (OSError, json.JSONDecodeError) as err:
        print(f"log: {err}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
