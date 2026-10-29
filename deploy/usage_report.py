#!/usr/bin/env python3
"""A short usage report from the Log Analytics workspace: the last 7 and 30 days. Reads only; changes nothing.

Run in Cloud Shell, after the logs go to Log Analytics (docs/OPERATIONS.md, section 3):

    bash deploy/usage-report.sh                    # deploy/krusgraph.json names the workspace and the app
    bash deploy/usage-report.sh --workspace-id <customerId> --app krusgraph

Each query is in QUERIES below and, word for word, in docs/USAGE.md (a test keeps the two in step). The lines they read
are the ones fabric_backend/usage.py writes: krusgraph.tool_call (tool, outcome, ms, dry_run, org),
krusgraph.page_view (path) and krusgraph.check (step). No line carries content, names, queries or user ids.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

TABLE = "ContainerAppConsoleLogs_CL"      # what --logs-destination log-analytics writes; the line is in Log_s

BASE = (f'{TABLE}\n'
        '| where TimeGenerated > ago({days}d) and ContainerAppName_s == "{app}" and Log_s startswith "{{\\"event\\":\\"krusgraph."\n'
        '| extend e = parse_json(Log_s) | extend ev = tostring(e.event)\n')

QUERIES = {
    "calls_per_day": BASE + '| where ev == "krusgraph.tool_call"\n'
                            '| summarize ["calls"] = count(), ["errors"] = countif(tostring(e.outcome) != "ok") by ["day"] = startofday(TimeGenerated)\n'
                            '| order by ["day"] asc',
    "per_tool": BASE + '| where ev == "krusgraph.tool_call"\n'
                       '| summarize ["calls"] = count(), ["errors"] = countif(tostring(e.outcome) != "ok"), ["p50_ms"] = percentile(toint(e.ms), 50), '
                       '["p95_ms"] = percentile(toint(e.ms), 95) by ["tool"] = tostring(e.tool)\n'
                       '| order by ["calls"] desc',
    "errors_by_kind": BASE + '| where ev == "krusgraph.tool_call" and tostring(e.outcome) != "ok"\n'
                             '| summarize ["calls"] = count() by ["error_kind"] = tostring(e.outcome)\n'
                             '| order by ["calls"] desc',
    "totals": BASE + '| where ev == "krusgraph.tool_call"\n'
                     '| summarize ["calls"] = count(), ["p50_ms"] = percentile(toint(e.ms), 50), ["p95_ms"] = percentile(toint(e.ms), 95), '
                     '["orgs"] = dcountif(tostring(e.org), isnotempty(tostring(e.org))), '
                     '["consent"] = countif(tostring(e.outcome) == "consent"), ["no_access"] = countif(tostring(e.outcome) == "no_access"), '
                     '["rate_limited"] = countif(tostring(e.outcome) == "rate_limited")',
    "page_views": BASE + '| where ev == "krusgraph.page_view"\n'
                         '| summarize ["views"] = count() by ["path"] = tostring(e.path)\n'
                         '| order by ["views"] desc',
    "check": BASE + '| where ev == "krusgraph.check"\n'
                    '| summarize ["events"] = count() by ["step"] = tostring(e.step)',
}
PAGES = ("/", "/check", "/explore", "/start", "/partners")
WINDOWS = (7, 30)


def kql(name: str, days: int, app: str) -> str:
    return QUERIES[name].replace("{days}", str(int(days))).replace("{app}", app).replace("{{", "{")


def _n(value) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _share(part: int, whole: int) -> str:
    return f"{part} ({100 * part / whole:.1f} %)" if whole else str(part)


def summary(days: int, results: dict) -> str:
    """The report for one window, from the rows each query returned (lists of dicts, as `az ... -o json` gives them)."""
    totals = (results.get("totals") or [{}])[0]
    calls = _n(totals.get("calls"))
    out = [f"Senaste {days} dagarna", "-" * 22]
    if not calls:
        out.append("Anrop: 0")
    else:
        out.append(f"Anrop: {calls}, median {_n(totals.get('p50_ms'))} ms, 95:e percentilen {_n(totals.get('p95_ms'))} ms")
        out.append(f"Organisationer (saltade hashar): {_n(totals.get('orgs'))}")
        out.append("Slutar i consent: " + _share(_n(totals.get("consent")), calls) + ", no_access: "
                   + _share(_n(totals.get("no_access")), calls) + ", rate_limited: " + _share(_n(totals.get("rate_limited")), calls))
        days_rows = results.get("calls_per_day") or []
        if days_rows:
            out.append("Per dag: " + ", ".join(f"{str(r.get('day', ''))[:10]} {_n(r.get('calls'))}" for r in days_rows[-7:]))
        out.append("Per verktyg:")
        for r in (results.get("per_tool") or [])[:10]:
            out.append(f"  {r.get('tool', '?'):<28}{_n(r.get('calls')):>6} anrop {_n(r.get('errors')):>5} fel"
                       f"   median {_n(r.get('p50_ms'))} ms, p95 {_n(r.get('p95_ms'))} ms")
        kinds = results.get("errors_by_kind") or []
        if kinds:
            out.append("Fel per kind: " + ", ".join(f"{r.get('error_kind', '?')} {_n(r.get('calls'))}" for r in kinds))
    views = {r.get("path"): _n(r.get("views")) for r in results.get("page_views") or []}
    out.append("Sidvisningar: " + ", ".join(f"{p} {views.get(p, 0)}" for p in PAGES))
    steps = {r.get("step"): _n(r.get("events")) for r in results.get("check") or []}
    out.append(f"/check: motorn laddad {steps.get('loaded', 0)}, kontroll klar {steps.get('done', 0)}")
    return "\n".join(out)


TIMEOUT = 180                             # seconds per az call; the report must never hang silently


def _az(command: list, runner=subprocess.run):
    try:
        return runner(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"az svarade inte på {TIMEOUT} sekunder ({' '.join(command[:4])}). Kontrollera inloggningen "
                           "(az account show) och försök igen.") from None
    except FileNotFoundError:
        raise RuntimeError("Hittar inte kommandot az. Kör skriptet i Azure Cloud Shell eller installera Azure CLI.") from None


def ensure_extension(runner=subprocess.run) -> None:
    """az monitor log-analytics query needs the log-analytics extension; add it without az asking (it waits silently
    for a yes/no when the output is captured). Only a preview version exists, so az notes that; --only-show-errors hides it."""
    result = _az(["az", "extension", "add", "--name", "log-analytics", "--yes", "--only-show-errors"], runner)
    if result.returncode:
        raise RuntimeError("Kunde inte lägga till az-tillägget log-analytics: "
                           + ((result.stderr or result.stdout).strip()[-2000:] or "okänt fel")
                           + "\nKör: az extension add --name log-analytics --yes")


def run_query(workspace_id: str, text: str, days: int, runner=subprocess.run) -> list:
    command = ["az", "monitor", "log-analytics", "query", "--workspace", workspace_id, "--analytics-query", text,
               "--timespan", f"P{int(days)}D", "--only-show-errors", "--output", "json"]
    result = _az(command, runner)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout).strip()[-2000:] or "az monitor log-analytics query misslyckades")
    return json.loads(result.stdout or "[]")


def report(workspace_id: str, app: str, runner=subprocess.run) -> str:
    ensure_extension(runner)
    parts = []
    for days in WINDOWS:
        results = {name: run_query(workspace_id, kql(name, days, app), days, runner) for name in QUERIES}
        parts.append(summary(days, results))
    return "\n\n".join(parts) + "\n"


def workspace_from_config(config: dict, runner=subprocess.run) -> str:
    name = (config.get("log_analytics_workspace") or "").strip()
    if not name:
        raise RuntimeError("log_analytics_workspace saknas i deploy/krusgraph.json; ange --workspace-id i stället.")
    result = _az(["az", "monitor", "log-analytics", "workspace", "show", "--resource-group", config["resource_group"],
                     "--workspace-name", name, "--subscription", config["subscription_id"], "--query", "customerId",
                     "--only-show-errors", "--output", "tsv"], runner)
    if result.returncode or not result.stdout.strip():
        raise RuntimeError((result.stderr or "").strip()[-2000:] or f"Hittar inte arbetsytan {name}.")
    return result.stdout.strip()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("krusgraph.json"))
    parser.add_argument("--workspace-id", help="Arbetsytans customerId (annars läses den via log_analytics_workspace i konfigurationen)")
    parser.add_argument("--app", help="Container-appens namn (annars app i konfigurationen, eller krusgraph)")
    parser.add_argument("--print-queries", action="store_true", help="Skriv ut KQL-frågorna för 30 dagar och avsluta (inga Azure-anrop)")
    args = parser.parse_args(argv)
    config = json.loads(args.config.read_text(encoding="utf-8")) if args.config.exists() else {}
    app = args.app or config.get("app") or "krusgraph"
    if args.print_queries:
        for name in QUERIES:
            print(f"// {name}\n{kql(name, 30, app)}\n")
        return 0
    try:
        workspace_id = args.workspace_id or workspace_from_config(config)
        print(report(workspace_id, app), end="")
    except (RuntimeError, KeyError, ValueError) as exc:
        print(f"STOPP: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
