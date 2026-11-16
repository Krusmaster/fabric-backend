# What Krusgraph may do by itself about a problem, and what it never does

Written by round B3 on 15 November 2026 from `fabric_backend/issue_catalogue.py`, which holds the same content as
data; a test keeps the two tables below equal to the code (`tests/test_b3_issue_catalogue.py`). The design is
`LIFECYCLE-DESIGN.md`, sections 2 to 4.

**Status.** The catalogue and its recognisers exist and are unit-tested on synthetic data. Nothing else of the
Lifecycle is built: no proposal, approval, autonomy level, automatic action, Undo or audit log runs today, in the
hosted service or in the workload. So today nothing is ever applied by itself, for any class. The table says what the
design allows once those parts exist, so that a reader can hold Krusgraph to it. It ran against no Fabric workspace.

## The policy per issue class

Three policies, in plain words:

- **always a person**: Krusgraph proposes with a dry run; a person approves each change. No setting changes that.
- **opt-in rule**: nothing is applied until the data product's owner turns on a level or writes a rule; then the named
  action runs, the owner is told at once, and it can be undone. The default is off.
- **never automatic**: there is nothing to apply. Krusgraph says what it counted and a person decides.

The owner sets one level per data product. Level 0, suggest only, is the default. Level 1 covers the safe classes
(a re-run, once; quarantine with an alert). Level 2 adds changes that match a rule the owner wrote.

<!-- policy:begin -->
| Issue class | Policy | Level 0 | Level 1 | Level 2 | Why |
| --- | --- | --- | --- | --- | --- |
| `schema_drift.added_column` | opt-in rule | suggest | suggest | rule | It changes a definition and the model, so it is applied only under a rule the owner wrote. |
| `schema_drift.dropped_column` | always a person | suggest | suggest | suggest | It breaks reports and apps. |
| `schema_drift.retyped_column` | opt-in rule | suggest | suggest | rule | Only a widening change (such as int to bigint) may run under the owner's rule; narrowing can lose data and stays with a person. |
| `schema_drift.new_table` | always a person | suggest | suggest | suggest | A plan change needs the row check and a person's review. |
| `schema_drift.dropped_table` | always a person | suggest | suggest | suggest | It breaks reports and apps. |
| `orphan_spike` | opt-in rule | suggest | auto | auto | Silver already quarantines by default; when the owner opts in to level 1, only the alert is added. |
| `duplicate_keys` | always a person | suggest | suggest | suggest | Which row wins is a business decision. |
| `sums_mismatch` | always a person | suggest | suggest | suggest | How an amount is split is a business decision. |
| `row_drop` | never automatic | inform | inform | inform | There is nothing to apply; only a person knows whether the source is complete. |
| `stale_data` | never automatic | inform | inform | inform | There is nothing to apply; the load is the source's. |
| `failed_run` | opt-in rule | suggest | auto | auto | A re-run changes no definition and is idempotent: silver overwrites, gold views are recreated. Once per run, never in a loop. |
| `capacity_limit` | opt-in rule | suggest | auto | auto | Not a data problem; waiting is the fix. Once per run, never in a loop. |
| `permission_lost` | always a person | suggest | suggest | suggest | It needs a person with rights; Krusgraph grants nothing. |
| `item_deleted` | always a person | suggest | suggest | suggest | It needs a person with rights, and only a person knows whether the deletion was meant. |
| `item_changed_outside` | always a person | suggest | suggest | suggest | An Update overwrites what someone changed by hand; a person chooses. |
<!-- policy:end -->

8 classes always wait for a person, 5 can run under a level or rule the owner opted in to, and 2 are information only.
In the columns: *suggest* is a proposal that waits for approval, *auto* is applied and reported, *rule* is applied only
when it matches the owner's own rule, *inform* is shown and nothing more.

## The catalogue: how each class is recognised

A diagnosis is a lookup, not a guess. Each class is recognised on a signal Krusgraph already has: a row of the health
table (names, rules, statuses and counts; never a value from the data), a failed run with Fabric's own error text, the
state of an item Krusgraph made, or a read that Fabric refused. A signal that matches no class is shown as
**Unclassified** with its own fields; it is never forced into a class. Health per data product is the worst open
class: any red is red, else any amber is amber, else green, with the word written beside the colour.

<!-- catalogue:begin -->
| Issue class | Signal | Recognised by | Severity | Proposed fix |
| --- | --- | --- | --- | --- |
| `schema_drift.added_column` | health: drift row, rule column_added | A column in the source today that the plan does not have. | amber | Add it to silver (and to the model if the owner ticks it). |
| `schema_drift.dropped_column` | health: drift row, rule column_removed | A column in the plan that the source no longer has; red when a key, a relationship, an ordering or a gold view uses it. | amber | Remove it from silver, gold and the model, and list each measure, report visual and API field that used it. |
| `schema_drift.retyped_column` | health: drift row, rule type_changed | The same column with another type family; red when the drift step says it breaks silver. | amber | Update the silver notebook's cast; for a narrowing type, quarantine the rows that do not cast. |
| `schema_drift.new_table` | health: drift row, rule table_added | A table in the source that is not in the plan. | info | Add it to the plan: the review step opens with the new table and its inferred keys and links. |
| `schema_drift.dropped_table` | health: drift row, rule table_removed | A table in the plan that the source no longer has. | red | Take it out of the plan and every output, or stop and ask. |
| `orphan_spike` | health: orphans row, or quarantine row of a reference rule (R...) | The orphan count is above the previous run's count times the owner's factor (default 3) and above an absolute floor (default 10). | amber | Quarantine the orphans (they already go there by default) and alert the owner with the counts. |
| `duplicate_keys` | health: key row, status fail | A key that was declared, given by a person or counted has duplicates or NULLs. | red | Keep one row per key (with the winner rule), or quarantine. |
| `sums_mismatch` | health: join_sums row, status fail | A gold join adds or loses amounts. | red | Show the join that fans out and propose the header-amount split. |
| `row_drop` | health: row_count row, status warn | A table's row count fell by the owner's threshold or more since the previous run (default: by half). | amber | No change. Ask the owner whether the source is complete. |
| `stale_data` | health: freshness row, status warn or fail | The last write to a source table is older than the owner's limit (default: warn after 2 schedule intervals, fail after 3). | amber | No change. Show the source's last write and the schedule. |
| `failed_run` | run: a failed job instance | A job instance that failed; the sub-class is run_results.classify's (import error, table not found, timeout, unknown), a heuristic on Fabric's error text. | red | Re-run once, with Fabric's error shown and the catalogue's next step. |
| `capacity_limit` | run: a failed job instance whose error text says the capacity is paused or throttled | run_results.classify gives capacity_paused_or_throttled. | amber | Re-run once after the owner's wait (default 30 minutes), with a link to the capacity. |
| `permission_lost` | run: error text that says permission denied; read: an output answers 403 | run_results.classify gives permission_denied, or the item's own read of an output answers 403. | red | No change. Say which identity lacks which role; a person grants it. |
| `item_deleted` | item: state missing | An item Krusgraph made is no longer listed in its workspace. | red | Re-create the item from the recorded plan, or forget it. |
| `item_changed_outside` | item: state changed_outside | The item exists, but it was renamed, is of another type, or its description names another plan. | amber | Show the difference; offer Update (overwrite) or Keep (record it as accepted). |
<!-- catalogue:end -->

The sub-class of a failed run (import error, table not found, timeout, unknown) and the two classes read from a run's
error text (`capacity_limit`, `permission_lost`) come from `run_results.classify`, which is a heuristic: the first
pattern that occurs in Fabric's text. It is a guess at the cause and is marked as one wherever it is shown.

## What B3 chose

Where the design left a choice open, the code does the following, and the design's owner may decide otherwise:

1. **The three policy words** are derived from the design's level table (section 4): a class that is *inform* at every
   level is "never automatic"; a class that is *auto* or *rule* at some level is "opt-in rule"; the rest are "always a
   person". The design has no such column.
2. **`orphan_spike` reads the quarantine counts too.** The design recognises it on the `orphans` check. The silver
   notebook puts orphans in quarantine before the check runs, so on a pipeline Krusgraph built that count is zero and
   the orphans show as `quarantine` rows of a reference rule (R1, R3 and so on). The recogniser reads both.
3. **No earlier run, no spike.** On the first run of a plan there is no count to compare with, so nothing is a spike;
   the count is shown as counted.
4. **Signals without a class stay unclassified**: duplicates under a key that was only guessed from names (a `key`
   warning), a gold join that changes the row count (`join_rows`), a table that is missing at the check, and orphans
   left in silver below the spike thresholds. Whether any of them should become a class is open.
5. **Unclassified signals do not change the health word.** The design defines the word from classes only.
6. **Severity "amber or red"**: a dropped or retyped column is red when the drift step itself says it breaks silver or
   gold (its row fails), amber otherwise; stale data is red when the freshness row fails, amber when it warns.

## Not built

The proposals of section 3, the levels and rules of section 4 (only the table of what each level may do is here), the
approvals, audit log and notifications of section 5, the Lifecycle view of section 6, and this table on the site and
in the Model editor. No tool, pipeline cell or screen calls the catalogue yet.
