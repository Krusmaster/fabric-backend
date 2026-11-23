"""The evidence register: every public claim next to its proof (round BL12, 21 November 2026; backlog C-24).

Written 21 November 2026 by round BL12. Listing texts, the sales sheet and a reseller's sentences should point at a row
here. The claims and their proofs were spread over `docs/MISSING-EVIDENCE.md`, `docs/TRUST.md`,
`fabric_backend/claims.py`, the README and `docs/LIVE-TEST.md`; the register names, for each claim, the file that says
it (with a piece of text that must still be in that file), the test that backs it, the `docs/LIVE-TEST.md` row when a
live run on synthetic data backs it, the date the evidence was recorded, and its class:

  U  unit test: the repository's own tests show it, on fakes and synthetic data;
  S  synthetic run: a recorded run against a live Fabric workspace or a real client, on synthetic data only;
  C  customer: a run on a customer's or pilot's own data. No such row exists yet.

    python tools/evidence_register.py            writes docs/EVIDENCE-REGISTER.md
    python tools/evidence_register.py --check    fails on a missing file, text, test or LIVE-TEST row, or a stale doc

The line in the doc is not a fixed number: the register keeps a piece of text (`anchor`), and `--check` finds the line
it is on, so other rounds can edit a file without making the register stale. Deterministic: no model, no network.
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOC = Path("docs/EVIDENCE-REGISTER.md")
LIVE_TEST = Path("docs/LIVE-TEST.md")
CLASSES = {
    "U": "unit test: the repository's own tests show it, on fakes and synthetic data",
    "S": "synthetic run: a recorded run against a live Fabric workspace or a real client, on synthetic data only",
    "C": "customer: a run on a customer's or pilot's own data",
}


@dataclass(frozen=True)
class Claim:
    id: str
    claim: str
    file: str       # the file that states the claim
    anchor: str     # text that must be in that file; its line is the claim's line
    test: str       # "tests/test_x.py::test_name", or "" when a live run is the only proof
    live_row: str   # text of the docs/LIVE-TEST.md row or heading, or ""
    date: str       # when the evidence was recorded (ISO date)
    cls: str        # U, S or C


REGISTER: tuple[Claim, ...] = (
    # From the README's claims.
    Claim("E01", "Every proposed link shows its basis, and the row checks show their counts.",
          "README.md", "Checked against your rows: every link shows its basis",
          "tests/test_bl3_counts.py::test_counts_equal_the_evidence_report", "", "2026-11-21", "U"),
    Claim("E02", "A check that was not run is open, never passed.",
          "README.md", "Checked against your rows: every link shows its basis",
          "tests/test_bl3_counts.py::test_an_uncounted_check_is_open_and_never_passed", "", "2026-11-21", "U"),
    Claim("E03", "Every number from the row checks comes with SQL that reruns to the same count.",
          "README.md", "Checked against your rows: every link shows its basis",
          "tests/test_bl1_receipt.py::test_every_receipt_sql_reruns_to_its_count", "", "2026-11-21", "U"),
    Claim("E04", "Orphans (references with no matching row) are found in files dropped on /check.",
          "README.md", "references with no matching row",
          "tests/test_check.py::test_files_are_read_with_the_demo_adapter_and_orphans_are_found", "", "2026-11-21", "U"),
    Claim("E05", "SAP keys start with the client (MANDT), and every SAP pack statement has a source.",
          "README.md", "keys with MANDT and the order-to-cash links",
          "tests/test_sap_pack.py::test_every_claim_has_a_source_and_every_client_specific_key_starts_with_the_client",
          "", "2026-11-21", "U"),
    Claim("E06", "SAP tables are matched with and without a name prefix.",
          "docs/SAP.md", "SAP table and column names survive, with or without a prefix.",
          "tests/test_sap_pack.py::test_match_with_and_without_prefix", "", "2026-11-21", "U"),
    Claim("E07", "The manufacturing sample holds exactly its planted problems, and the check finds exactly those.",
          "README.md", "a few planted problems to find",
          "tests/test_mill.py::test_check_finds_exactly_the_planted_issues", "", "2026-11-21", "U"),
    Claim("E08", "The benchmark rerun reproduces the committed results and the README table.",
          "README.md", "`tests/test_benchmark.py` checks that a new run gives the",
          "tests/test_benchmark.py::test_the_run_reproduces_the_committed_results_and_the_readme_table",
          "", "2026-11-21", "U"),
    Claim("E09", "The benchmark's baseline is an approximation and is never called Power BI itself.",
          "README.md", "against an approximation",
          "tests/test_benchmark.py::test_the_baseline_is_never_called_power_bi_itself", "", "2026-11-21", "U"),
    # From fabric_backend/claims.py (read only).
    Claim("E10", "The status chips on /docs are derived from tool_status, never typed per page.",
          "fabric_backend/claims.py", "The chips (CHIPS) are derived, never typed per page",
          "tests/test_n194_site.py::test_only_the_docs_carry_the_chips", "", "2026-11-21", "U"),
    Claim("E11", "The creating tools are dry run by default; the claim matches the tools' signatures.",
          "fabric_backend/claims.py", "Krusgraph creates an item only when you ask, after a dry run",
          "tests/test_site.py::test_the_dry_run_claim_matches_the_tool_signatures", "", "2026-11-21", "U"),
    # From docs/TRUST.md.
    Claim("E12", "Tokens and secrets never reach the logs or stdout.",
          "docs/TRUST.md", "are never written to disk or logs",
          "tests/test_security.py::test_tokens_and_secrets_never_reach_logs_or_stdout", "", "2026-11-21", "U"),
    Claim("E13", "The on-behalf-of token cache never shares tokens between users.",
          "docs/TRUST.md", "Tokens from Claude's sign-in are held in memory only",
          "tests/test_security.py::test_on_behalf_of_cache_never_shares_tokens_between_users", "", "2026-11-21", "U"),
    Claim("E14", "A usage record holds no content: no user id, no IP address, no names, queries or results.",
          "docs/TRUST.md", "Each tool call leaves one usage record",
          "tests/test_operations.py::test_no_content_reaches_the_usage_line_or_metrics", "", "2026-11-21", "U"),
    Claim("E15", "The /it page says how long logs are kept, as the privacy page does.",
          "docs/TRUST.md", "Retention is a setting, `log_retention_days`",
          "tests/test_site.py::test_it_page_says_how_long_logs_are_kept_as_the_privacy_page_does",
          "", "2026-11-21", "U"),
    Claim("E16", "The /it page lists exactly the delegated permissions the deploy check requires.",
          "docs/TRUST.md", "all the app's permissions are delegated",
          "tests/test_site.py::test_it_page_lists_the_app_permissions_the_deploy_check_requires",
          "", "2026-11-21", "U"),
    Claim("E17", "A refresh-token retry within 60 seconds gets the same answer; after the window an old token ends the "
                 "sign-in.",
          "docs/TRUST.md", "Refresh tokens for MCP clients other than Claude rotate at every use",
          "tests/test_refresh_rotation.py::test_after_the_window_the_old_token_ends_the_line_as_before",
          "", "2026-11-21", "U"),
    Claim("E18", "Signed-in tool calls are rate-limited per organisation, and a refusal costs nothing.",
          "docs/TRUST.md", "Signed-in tool calls are rate-limited per user and per organisation",
          "tests/test_operations.py::test_the_organisation_limit_covers_all_its_users_and_a_refusal_costs_nothing",
          "", "2026-11-21", "U"),
    Claim("E19", "Every tool has a title and a read-only or write hint.",
          "docs/TRUST.md", "Planning, checking and the drafts only read.",
          "tests/test_submission.py::test_every_tool_has_a_title_and_a_hint", "", "2026-11-21", "U"),
    Claim("E20", "security.txt follows RFC 9116, with a fixed expiry.",
          "docs/TRUST.md", "the same address in `security.txt` (RFC 9116)",
          "tests/test_site_extras.py::test_security_txt_follows_rfc_9116", "", "2026-11-21", "U"),
    Claim("E21", "Every tool error is scrubbed of token-shaped strings and secret-like header pairs.",
          "docs/TRUST.md", "every tool error is scrubbed of token-shaped strings",
          "tests/test_security.py::test_error_layer_scrubs_tokens_and_secrets_from_messages", "", "2026-11-21", "U"),
    Claim("E22", "Every GitHub Action is pinned by commit, with its version in a comment.",
          "CONTRIBUTING.md", "is pinned by commit with its version in a",
          "tests/test_b2_supply_chain.py::test_every_action_is_pinned_by_commit_with_its_version_in_a_comment",
          "", "2026-11-21", "U"),
    Claim("E23", "Personal columns are masked in sample rows by rule, and shown only on request.",
          "docs/LIVE-TEST.md", "`name` shows `***` with a `personal_data` notice",
          "tests/test_privacy.py::test_sample_rows_masks_with_the_rule_and_shows_on_request",
          "| 5 | `sample_rows` |", "2026-10-27", "S"),
    # Round BL36 (23 November 2026): the workload rounds merged that day (WB5, WB7, WB8, WB9).
    Claim("E29", "Every workload request has one correlation id, on every log line of that request and in every error.",
          "docs/TRUST.md", "Every workload request has one correlation id",
          "tests/test_wb8_correlation.py::test_the_editors_id_is_on_every_line_and_in_the_answer", "", "2026-11-23", "U"),
    Claim("E30", "A CSN file chosen in the workload editor is checked again by the engine and never written to a log.",
          "docs/TRUST.md", "A CSN file chosen in the workload editor is read in the browser",
          "tests/test_wb5_sap_item.py::test_an_uploaded_csn_is_used_and_said_to_come_from_the_editor", "", "2026-11-23", "U"),
    Claim("E31", "Load SAP demo data creates one notebook after a dry run and never runs it.",
          "docs/TRUST.md", "*Load SAP demo data* is a dry run first",
          "tests/test_wb5_sap_item.py::test_load_sap_demo_data_is_a_dry_run_first_then_one_notebook_never_run",
          "", "2026-11-23", "U"),
    Claim("E32", "The pilot self-check only reads, and says the tenant setting is unknown instead of guessing.",
          "docs/TRUST.md", "The pilot self-check (*Is everything ready?*) only reads",
          "tests/test_wb9_selfcheck.py::test_a_ready_workspace_says_ready_and_the_tenant_setting_is_unknown",
          "", "2026-11-23", "U"),
    Claim("E33", "With the licence check off nothing is gated; on, only Create is, and dry runs stay open.",
          "docs/TRUST.md", "The Marketplace licence check is off unless switched on",
          "tests/test_wb7_marketplace_gate.py::test_flags_off_change_nothing", "", "2026-11-23", "U"),
    # Live runs on synthetic data (from docs/MISSING-EVIDENCE.md and docs/LIVE-TEST.md).
    Claim("E24", "validate_plan, live on the demo workspace: 6 of 6 keys unique, 7 of 7 relationships without orphans.",
          "docs/LIVE-TEST.md", "✓ 6 of 6 keys unique, 7 of 7 relationships without orphans",
          "tests/test_evidence.py::test_synthetic_shop_keys_are_unique_and_relationships_hold",
          "| 6 | `validate_plan` |", "2026-11-02", "S"),
    Claim("E25", "create_backend updated the existing API shop_api in place, live; creating a new API has not run live.",
          "docs/MISSING-EVIDENCE.md", "then `create_backend` updating `shop_api` in place",
          "tests/test_create_backend_dry_run.py", "| 7 | `create_backend` |", "2026-10-27", "S"),
    Claim("E26", "create_semantic_model created shop_model_live in the demo workspace (synthetic data).",
          "docs/MISSING-EVIDENCE.md", "`create_semantic_model` created `shop_model_live` on 29 October 2026",
          "tests/test_creating_tools.py::test_create_semantic_model_posts_then_updates_in_place",
          "| 18 | `create_semantic_model` |", "2026-10-29", "S"),
    Claim("E27", "create_report: shop_report opened in the Fabric portal with data; a report of the same name is left "
                 "alone.",
          "docs/MISSING-EVIDENCE.md", "Gustav opened `shop_report` in the Fabric portal",
          "tests/test_create_report.py::test_a_report_of_that_name_is_left_alone",
          "| 39 | `create_report` |", "2026-10-30", "S"),
    Claim("E28", "A Lovable app read shop_api live (orders, customers and the ship-to address).",
          "docs/MISSING-EVIDENCE.md", "A Lovable app read `shop_api` live on 30 October 2026",
          "", "### 30 October 2026: `create_report`, Lovable as an MCP client", "2026-10-30", "S"),
)

TEST_RE = re.compile(r"^tests/[\w/]+\.py(::test_\w+)?$")


def _line_of(text: str, needle: str) -> int:
    i = text.find(needle)
    return text.count("\n", 0, i) + 1 if i >= 0 else 0


def problems(register=REGISTER, root: Path = ROOT) -> list[str]:
    """Every missing file, text, test or LIVE-TEST row, as one sentence each; empty when the register holds."""
    out: list[str] = []
    seen: set[str] = set()
    live = root / LIVE_TEST
    live_text = live.read_text(encoding="utf-8") if live.is_file() else ""
    for c in register:
        if c.id in seen:
            out.append(f"{c.id}: the id is used twice")
        seen.add(c.id)
        if c.cls not in CLASSES:
            out.append(f"{c.id}: unknown class {c.cls!r}")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", c.date):
            out.append(f"{c.id}: the date {c.date!r} is not YYYY-MM-DD")
        f = root / c.file
        if not f.is_file():
            out.append(f"{c.id}: the file {c.file} is missing")
        elif not _line_of(f.read_text(encoding="utf-8"), c.anchor):
            out.append(f"{c.id}: {c.file} no longer says {c.anchor!r}")
        if not c.test and not c.live_row:
            out.append(f"{c.id}: neither a test nor a LIVE-TEST row backs it")
        if c.test:
            if not TEST_RE.match(c.test):
                out.append(f"{c.id}: {c.test!r} is not tests/<file>.py or tests/<file>.py::test_<name>")
            path, _, name = c.test.partition("::")
            t = root / path
            if not t.is_file():
                out.append(f"{c.id}: the test file {path} is missing")
            elif name and not re.search(rf"^\s*(async\s+)?def {re.escape(name)}\(", t.read_text(encoding="utf-8"), re.M):
                out.append(f"{c.id}: the test {name} is missing from {path}")
        if c.live_row and not _line_of(live_text, c.live_row):
            out.append(f"{c.id}: {LIVE_TEST} has no row {c.live_row!r}")
    return out


def _cell(s: str) -> str:
    return s.replace("|", "\\|")


def render(register=REGISTER, root: Path = ROOT) -> str:
    """docs/EVIDENCE-REGISTER.md, generated. Stable: no line numbers and no date of generation in it."""
    count = {k: sum(c.cls == k for c in register) for k in CLASSES}
    rows = "\n".join(
        f"| {c.id} | {_cell(c.claim)} | `{c.file}`: “{_cell(c.anchor)}” | "
        f"{'`' + c.test + '`' if c.test else 'none; the live run is the proof'} | "
        f"{'“' + _cell(c.live_row.strip('| ').strip()) + '”' if c.live_row else '-'} | {c.date} | {c.cls} |"
        for c in register)
    classes = "\n".join(f"- **{k}** ({count[k]}): {v}." for k, v in CLASSES.items())
    no_c = ("**No class C row exists yet.** No customer or pilot has run Krusgraph on their own data, and the repository "
            "records no such run (`docs/MISSING-EVIDENCE.md`, row 9). Every row below rests on the repository's tests or "
            "on synthetic data.") if not count["C"] else ""
    return f"""# Evidence register

<!-- Generated by `python tools/evidence_register.py` from the register in that file; do not edit by hand.
     `python tools/evidence_register.py --check` fails on a missing file, text, test or LIVE-TEST row, or when this
     file is stale; `tests/test_bl12_evidence_register.py` runs it. -->

Created 21 November 2026 by round BL12 (backlog C-24). Every claim that a listing text, a sales sheet or a reseller may
repeat, with its proof: the file that states it and a piece of its text (`--check` prints the line it is on), the test
that backs it, the `docs/LIVE-TEST.md` row when a live run on synthetic data backs it, the date the evidence was
recorded (for class U, the day the test was read for the register; for class S, the day of the live run) and its
class. A sentence that is not in this table has no recorded proof and should not be repeated. To add a
claim, add a row to `REGISTER` in `tools/evidence_register.py` and run the tool.

{len(register)} claims. Classes:

{classes}

{no_c}

| Id | Claim | Stated in | Test | `LIVE-TEST.md` | Date | Class |
| --- | --- | --- | --- | --- | --- | --- |
{rows}

What is still missing, and who takes it: `docs/MISSING-EVIDENCE.md`. Statements about security and data handling, each
with its source: `docs/TRUST.md`.
"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="fail on a missing file, text, test or row, or a stale doc")
    ap.add_argument("--root", type=Path, default=ROOT, help="repository root (default: this checkout)")
    a = ap.parse_args(argv)
    doc = a.root / DOC
    want = render(root=a.root)
    if not a.check:
        doc.write_text(want, encoding="utf-8")
        print(f"wrote {DOC} ({len(REGISTER)} claims)")
        return 0
    found = problems(root=a.root)
    if not doc.is_file() or doc.read_text(encoding="utf-8") != want:
        found.append(f"{DOC} is stale: run python tools/evidence_register.py")
    if found:
        print("\n".join(found), file=sys.stderr)
        return 1
    live = (a.root / LIVE_TEST).read_text(encoding="utf-8")
    for c in REGISTER:
        line = _line_of((a.root / c.file).read_text(encoding="utf-8"), c.anchor)
        extra = f", {LIVE_TEST}:{_line_of(live, c.live_row)}" if c.live_row else ""
        print(f"{c.id} {c.cls} {c.file}:{line}{extra}")
    print(f"ok: {len(REGISTER)} claims, every file, text, test and row found")
    return 0


if __name__ == "__main__":
    sys.exit(main())
