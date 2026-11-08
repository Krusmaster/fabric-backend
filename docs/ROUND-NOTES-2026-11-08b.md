# Round notes, 8 November 2026 (b): n155 and n156

Two rounds run in sequence by a scheduled session, with nobody watching. Code, docs and tests only: nothing was
deployed, and nothing called Fabric or another external service. Claims: `2f3d17b` (n155 claims MCP tools and errors,
Engine, and, after n154 released them during the rebase, Website, Docs and submission, and Tests).

## n155: Fix data issues (proposed fixes per finding)

Commit: `78216e1`. CI: green (CI run 42474744445).

**The choice:** an option on `validate_plan` (`fixes=true`), not a new tool. The proposal stands only on
`validate_plan`'s counts and inputs and is read-only like it; a new tool would also change the tool count that the
discovery text, the README and the registry submission state. The engine for it already existed since n115
(`fixes.py`, `evidence_report.py`, `silver.apply_fixes`); n155 reuses it and adds `fabric_backend/fix_plan.py`.

What changed:

- `validate_plan(fixes=true, review=..., tables=...)` returns `fix_plan`: per finding an `id`, a `type` (`mechanical`
  or `business_decision`), what is wrong, the fix in plain words, the PySpark the silver notebook adds once accepted
  and the T-SQL that counted it, counts before and expected after, and the questions with options and no default.
  Mechanical: a NULL key, exact copies, differing rows when the table has a change-time column (latest wins), an orphan
  to quarantine, a flat table's header amount moved. Business decision: differing rows without a time column, whether
  an orphan should be dropped or its parent created (asked next to the quarantine fix), which level a header amount a
  join repeats belongs to (the two sums are run and returned), and every finding with no mechanical fix. Two extra
  read-only queries: key values whose rows differ, and the two sums.
- `silver_notebook_draft` and `create_silver_notebook` take `fixes=[ids or {id, choice|winner}]`: exactly those are
  applied, the decisions are written into the parameters cell, an id that is only a question is refused, and the
  notebook prints a table of counts per fix at the end. `create_silver_notebook`'s dry run stays the default.
- validate_plan's MCP Apps card (off by default) lists each proposed fix as one line.
- Docs: *Fix data issues* under Explore and check, the tool reference rows. The chat's "Fix data issues" item
  (a link since n154) now links `/docs/explore-and-check/fix-data-issues` and says what exists. Its label was kept: n154
  set it the same morning after the founder's feedback, and it still says what the link leads to.
- Tests: `tests/test_n155_fix_plan.py` on the /check fixtures (04 duplicate parent: 4 rows, 3 distinct, 1 exact copy
  to quarantine; 03: 3 rows with a value, 1 orphan, the 2 NULLs kept; 05: the composite orphan, 4 kept and 1 to
  quarantine, and the fan-out sums 700 and 600; 01: the composite key holds, the fan-out sums 1300 and 600) and the shop
  seed (a differing duplicate without a time column stops the notebook until a winner is named).
- The read-only listing's own growth guard (n26) went from 64 000 to 64 500 characters: after shortening the new
  parameter descriptions the listing was still 105 characters over.

Left: `fixes=true` has not run against a live workspace. A rejected relationship in a review file shows as the
finding's `review` status; it does not remove the finding.

## n156: Create a dbt flow (a full dbt project from the checked plan)

Commit: `065abc0`. CI: green (CI run 42475309724).

**The choice:** an option on `dbt_schema`, which has written a project draft with `project=true` since n114 (staging,
marts joined only over relationships counted many-to-one, child facts summed before the join). A `dbt_project` tool
would repeat it. The chat's dbt item had said "a whole dbt project is planned", which was already out of date.

What changed:

- Staging columns renamed to snake_case (the sources file keeps the source's names; the README and the answer's
  `renamed` list them). Casts only where the metadata gives a type, as before.
- Composite keys and composite relationships are singular tests in `tests/`, without dbt_utils (dbt-fabric's
  documentation says dbt-utils is not supported); `test-paths` in `dbt_project.yml`.
- `profiles.example.yml` (placeholders, `authentication: CLI`, no secret) in every project; the README says how to run
  it (`dbt debug`, `dbt parse`, `dbt build`) and that Krusgraph has not run it.
- `fixes=[...]` with `project=true` (it counts the rows): accepted fixes as staging logic (the latest row by the
  accepted column; an orphan left out with its NULLs kept, or the reference set to NULL). Moving a header amount stays
  with the silver notebook and is listed under not templated.
- Docs: *Create a dbt flow* under Build from a plan and the dbt_schema row. The chat's dbt item is now "Draft a dbt
  project", linking `/docs/build-from-a-plan/create-a-dbt-flow`; nothing in the chat is said to be planned.
- Tests: `tests/test_n156_dbt_flow.py`: every SQL file parses with n139's T-SQL parser, every YAML file loads, golden
  files for the shop seed and fixtures 01 and 05 (`tests/golden/dbt_project_*.json`), no header amount at line grain
  (01: the header mart sums to 600, not 1300), the relationship onto a key counted not unique left out and listed (04),
  and the fixes run in SQLite (03: 4 rows kept with the orphan left out; set_null keeps 5).

Left: dbt has not been run on these files. A relationship rejected in a review file is not read by `dbt_schema`; only
the counts decide which relationships a mart joins over. Two tables whose accepted orphan fixes point at each other
would make a ref cycle in the staging models; it is not handled.

## Both rounds

- Suite: `python -m pytest -q` green before each push (2 607 and 2 626 passed, 4 skipped), except
  `tests/test_check.py::test_the_start_page_fetches_the_engine_ahead_only_when_asked_and_check_then_uses_the_cache`,
  which failed only under 8 parallel workers here (also in a first run on main before these rounds, though files were
  being edited during that run) and passed each time it ran alone.
- `tests/golden/local_listing.json` is left as it was: regenerated here, it picks up this environment's Databricks
  tools; nothing in these rounds changes the local server's listing.

Ready to deploy: bash deploy/krusgraph.sh --from-azure --update
