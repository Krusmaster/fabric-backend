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
