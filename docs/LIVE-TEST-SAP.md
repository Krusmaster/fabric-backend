# Live test checklist: the SAP pack against real SAP tables

For the maintainer. This is the first test of whether the SAP pack ([SAP.md](SAP.md)) is right about SAP. The unit
tests only show that the engine applies the pack as written, against a schema generated from the pack itself. Fill in
**Result** (✓, or what came instead) and **Date** for each row; a row passes when the answer says what **Expected**
says. As in [LIVE-TEST.md](LIVE-TEST.md), the protocol of a run stays outside the repository; what goes in is the
`verified` entry per relationship (step 6), written by `fabric-backend sap-verify --write`.

## Before you start

- **A system you may describe.** Use an SAP sandbox, a training or demo system, or a mirror of one, whose tables you
  are allowed to read and whose existence you may mention. The `where` you record (step 5) describes it without naming
  a company: "SAP S/4HANA sandbox, demo data", "SAP ECC training system". Never a customer's or an employer's system
  unless they have agreed in writing, and even then no names in the repository.
- **The tables in Fabric.** The SAP tables sit in a lakehouse, a mirrored database (Fabric mirroring of SAP through
  SAP Datasphere) or a warehouse, in one schema. Names may carry a prefix (`sap_vbak`) or not. The more of the order-to-cash tables
  there are, the more relationships get checked: at least `KNA1`, `MARA`, `VBAK`, `VBAP`, `LIKP`, `LIPS`, `VBRK`,
  `VBRP` and `VBFA`.
- **The client column.** Note whether the extract kept `MANDT`. If it did not, the pack drops it on both sides and
  says so (`client_dropped`).
- **A deployed build** from main at or after round n31 (`curl -s https://krusgraph.com/healthz`).

## 0. A synthetic run first (round n32)

Before a real system, run the whole chain on synthetic SAP-shaped tables in the demo workspace. That shows the tools
work on SAP-shaped data in Fabric: the prefix `sap_`, the client column, the extended relationships, the masking.
It does **not** show that the pack is right about SAP, because the rows are written from the pack;
`sap-verify --write` refuses to record such a run.

1. **The quickest way (round n33):** open
   [`examples/sap_demo/load_sap_demo_inline.py`](../examples/sap_demo/load_sap_demo_inline.py) on GitHub, copy all of
   it, paste it into one cell of a new notebook attached to `demo_lh`, and run it. The rows are inside the cell;
   nothing to upload. It writes the same 17 tables as below. Then go to step 3.

   Or, on your machine: `fabric-backend sap-demo --out sap_demo` writes 17 CSV files, `_types.json` and
   `load_sap_demo.py` (every value made up: "Demo Customer 10", e-mail at `example.invalid`).
2. In Fabric: upload the files to `demo_lh` under `Files/sap_demo`, open `load_sap_demo.py` as a notebook attached to
   `demo_lh`, run it. It writes `sap_t001`, `sap_kna1`, `sap_vbak` … as Delta tables (replacing tables of those names).
3. In Claude, against `demo_lh` and the schema the tables landed in (`dbo` unless the lakehouse has schemas):

| # | Question in Claude | Expected (the same as `tests/test_sap_demo.py` finds in SQLite) | Result | Date |
| --- | --- | --- | --- | --- |
| 0.1 | *"Which SAP tables does the SAP pack recognise in demo_lh?"* (`sap_pack_draft`) | 17 tables, from `sap_t001` to `sap_adr6`; keys with `MANDT` (`CLIENT` for `ADRC`, `ADR6`) | as expected (earlier run, PR #4) | earlier run |
| 0.2 | *"Check the plan of demo_lh against the data, max_items 200."* (`validate_plan`) | 17 of 17 keys unique, 32 of 34 relationships hold without orphans; `sap_vbap` → `sap_vbak` has 1 orphan (the planted item of order 0000000009) | summary verbatim "17 of 17 keys unique, 32 of 34 relationships hold without orphans"; `sap_vbap` → `sap_vbak` "1 of 6 rows (16.7%) point at nothing"; `sap_vbfa` → `sap_vbak` (VBTYP_N A–L) "no rows with a value: nothing to check"; no SQL Server error 130 | 29 Oct 2026, build src-6423dd7301bf53c2 (747768a) |
| 0.3 | (same answer) `amount_levels` | `sap_vbak.NETWR` over `sap_vbap` rows, up to 3 lines per order; the explanation names the referenced header values and how many of them are in `sap_vbak` ("4 referenced header value(s), 3 of them in sap_vbak": the fourth is the orphan order 0000000009) | `sap_vbak.NETWR` over `sap_vbap`, avg_lines 1.5, max_lines 3; also `sap_vbap.NETWR` over `sap_vbep`, `sap_lips` and `sap_vbrp`, and `sap_vbrk.NETWR`, `MWSBK` over `sap_vbrp` with 2 rows. The explanation then said "(4 row(s) of sap_vbak referenced)" although `sap_vbak` has 3 rows; reworded in n50 | 29 Oct 2026, build src-6423dd7301bf53c2 (747768a) |
| 0.4 | (same answer) `sap_kna1` → `sap_adrc` | 3 rows with a value, 0 orphans, 0 matching twice (version I and the expired period are left out) | rows_with_value 3, orphans 0, several 0 (valid_on, NATION blank) | 29 Oct 2026, build src-6423dd7301bf53c2 (747768a) |
| 0.5 | *"Show five rows of sap_adr6."* (`sample_rows`) | `SMTP_ADDR` shown as `***`, the reason naming the SAP pack | as expected (earlier run, PR #4) | earlier run |
| 0.6 | `fabric-backend sap-verify validation.json --where "synthetic SAP demo" --when YYYY-MM-DD` | 32 verified, 1 review (`VBAP` → `VBAK`), 1 no evidence (`VBFA` → `VBAK`), 6 not checked; with `--write` it refuses | not run yet: needs validation.json locally | remains |

The counts assume the schema holds only these 17 tables; other tables in it add their own keys and relationships to the answer. They can also differ from SQLite in one way: Spark reads an empty CSV field as `NULL`, SQLite keeps `''`. The
checks treat both as no value, so the expected numbers are the same.

## 1. What the pack recognises

| # | Tool | Question in Claude | Expected | Result | Date |
| --- | --- | --- | --- | --- | --- |
| 1 | `list_tables` | *"Which tables are in <source>, schema <schema>?"* | the SAP tables with their columns | | |
| 2 | `sap_pack_draft` | *"Which SAP tables does the SAP pack recognise in <source>, schema <schema>?"* | the tables named above; `variant_hint` ecc or s4hana if a table only one variant has is there; `missing_columns` empty or explained | | |
| 3 | `sap_pack_draft` on a source **without** SAP tables | *"…and in demo_lh, schema shop?"* | begins "no SAP tables recognised": the pack does not touch other schemas | | |
| 4 | `plan_backend` | *"Plan <source>, schema <schema>."* | keys with `MANDT` and rule `SAP pack`; `extended_relationships` present if `VBFA`, `ACDOCA`/`CSKS`, `ADRC` or the CVI tables are there | | |

## 2. Against the rows

| # | Tool | Question in Claude | Expected | Result | Date |
| --- | --- | --- | --- | --- | --- |
| 5 | `validate_plan` | *"Check the plan of <source>, schema <schema> against the data, max_items 200."* | a verdict per key and relationship; save the whole JSON answer to a file on your machine, not in the repository | | |
| 6 | `validate_plan` → `amount_levels` | (same answer) | `VBAK.NETWR` over `VBAP` rows named, with the line rows per order counted | | |
| 7 | `sample_rows` | *"Show five rows of ADR6"* (or `KNA1`) | `SMTP_ADDR` (or `TELF1`, `STRAS`) shown as `***`, the reason naming the SAP pack | | |

## 3. From counts to a status

| # | Command (on your machine, in the repository) | Expected | Result | Date |
| --- | --- | --- | --- | --- |
| 8 | `fabric-backend sap-verify validation.json --where "SAP S/4HANA sandbox, demo data" --when YYYY-MM-DD` | a table: *verified* (held for every row with a value), *review* (orphans, or rows matching twice), *no evidence* (no values), *not checked* (listed only, or past max_items) | | |
| 9 | Read every *review* row | its condition explains the orphans (order-related billing, partner rows of other documents, empty references), or it does not: then the pack is wrong there, and the relationship needs a fix or a condition | | |
| 10 | `fabric-backend sap-verify validation.json --where "…" --when YYYY-MM-DD --write` | `verified: …` per relationship; `git diff fabric_backend/packs/sap/` shows a `verified` entry with where, when and the number of rows | | |
| 11 | `python -m pytest -q tests/test_sap_pack.py` | green: the entries follow the format | | |

Commit the `verified` entries with a message that names the system as described in `where` and the date. A module's
`status` stays `documented` until the relationships that matter to it are verified; then change it to `verified` by
hand and say in `status_note` where and when.

## What a run does not show

- That a relationship means what the pack says: counts show that values match, not that the join answers a question.
- That it holds elsewhere: another release, another configuration or a customer's own conventions can differ. A
  `verified` entry says where and when, and nothing more.
- Anything about the `Z*`/`Y*` tables of the system; the pack does not describe them and never will.
