# SAP tables: the SAP pack

General naming rules cannot read SAP. `VBAP.VBELN` is the order an item belongs to, `LIPS.VBELN` a delivery and
`VBRP.VBELN` an invoice; every key starts with the client `MANDT`; the names are German abbreviations; amounts sit on
both header and item. The SAP pack says these things outright, per table and per relationship, with the public source
each claim rests on, and the engine uses it before the name rules.

The pack describes tables, not a tool. The same files serve data that arrives through Fabric mirroring (SAP
Datasphere), Databricks, Data API builder, a pipeline of your own or any other replication: what matters is that the
SAP table and column names survive, with or without a prefix.

## What is in it

`fabric_backend/packs/sap/` (format: `fabric_backend/packs/pack.schema.json`, checked by `tests/test_sap_pack.py`):

| Module | Tables | Relationships |
| --- | --- | --- |
| `order_to_cash` | customers `KNA1`, `KNVV`; materials `MARA`, `MAKT`; organisation `TVKO`, `TVTW`, `TSPA`, `T001`; orders `VBAK`, `VBAP`, `VBEP`; status `VBUK`, `VBUP` (ECC only); partners `VBPA`; deliveries `LIKP`, `LIPS`; billing `VBRK`, `VBRP`; document flow `VBFA` | 31, of which 25 are applied and 6 listed but not applied (conditional, or many-to-many through `VBFA`) |
| `procure_to_pay` (round n21) | suppliers `LFA1`, `LFB1`, `LFM1`; organisation `T024E`, `T001W`; requisitions `EBAN`; purchase orders `EKKO`, `EKPO`, `EKET`; purchase order history `EKBE`; supplier invoices `RBKP`, `RSEG` | 22, of which 21 are applied; `EKBE` → `RBKP` is listed only (it holds for invoice rows, not goods receipts) |
| `finance` (round n22) | charts of accounts `T004`; G/L accounts `SKA1`, `SKB1`; customer and supplier open and cleared items `BSID`, `BSAD`, `BSIK`, `BSAK` (ECC); controlling area `TKA01`; cost centers `CSKS`; profit centers `CEPC` | 23, of which 21 are applied; journal line → cost center and → profit center are listed only (both masters are time-dependent) |
| `accounting_document` | `BKPF`; `BSEG` (ECC); `ACDOCA` (S/4HANA) | 3: `BSEG` → `BKPF`, `ACDOCA` → `BKPF`, `VBRK` → `BKPF` |

Per table: key (with `MANDT`), level (header, item, schedule line, master, text, organisation, status, partner,
document flow), an English and a German name in our own words, the amount columns with their level and currency
column, quantity columns with their unit column, the number columns that carry leading zeros, the columns a delta
load can watch, and the variants it exists in. Per relationship: source and target columns, cardinality, the role
when one table points at another twice (`VBRK.KUNAG` sold-to, `VBRK.KUNRG` payer), a condition when it holds for some
rows only, and its sources.

### Variants

`ecc` and `s4hana`. A table or relationship without `variants` is described for both; `VBUK`/`VBUP` and `BSEG` are
marked ECC, `ACDOCA` S/4HANA. The tables present tell which variant a schema looks like (`variant_hint`); nothing is
claimed to be verified per release or enhancement package. Known open points: the key of `VBFA` in S/4HANA (the table
was simplified; we give the key as documented for ECC and say so), and whether `BSEG` is read as a table or a
compatibility view in a given S/4HANA release (not asserted).

## The traps it explains

- **`MANDT` in every join.** One database can hold several clients; a join on `VBELN` alone pairs documents across
  clients. All pack keys and relationships carry the client. When an extract has dropped `MANDT`, the pack drops it on
  both sides and lists the tables under `client_dropped`.
- **Header and item amounts are different levels.** `VBAK.NETWR` is the whole order, `VBAP.NETWR` one item. The pack
  feeds its amount columns to the check *the total that doubles* (`amounts.py`, `validate_plan` → `amount_levels`), so
  `VBAK.NETWR` over `VBAP` rows and `VBAP.NETWR` over `VBEP` schedule lines are reported, although the name `NETWR`
  says nothing to the general amount rules.
- **Currency per document.** `NETWR` is in the document currency `WAERK`; `VBRP` has no currency of its own and uses
  `VBRK.WAERK`.
- **Leading zeros.** `VBELN`, `KUNNR`, `MATNR` are text with leading zeros; a join with a source that stores numbers
  finds nothing.
- **`VBFA` is many-to-many.** An order item can have several deliveries, a delivery several orders. The pack lists the
  `VBFA` links but does not apply them as relationships; aggregate on one side first and filter `VBTYP_V`/`VBTYP_N`.
- **The purchase order history multiplies order items.** `EKBE` has a row per goods receipt, invoice and reversal;
  `EKPO.NETWR` over `EKBE` rows is reported by *the total that doubles*, and so is `RBKP.RMWWR` (the invoice's gross
  amount on the header) over `RSEG` items.
- **Two different `BELNR`.** `RBKP.BELNR` is the invoice number, `BKPF.BELNR` the accounting document number, from
  different number ranges. `RBKP` also has `BUKRS` and `GJAHR`, so the name rules (R3, with keys given) link it to
  `BKPF`; the pack does not, and names the real link (`BKPF.AWKEY`) in its traps. Invoice numbers are unique only
  within `GJAHR`.
- **Open items are copies.** `BSID`/`BSAD`/`BSIK`/`BSAK` copy customer and supplier lines of `BSEG`; adding them to
  `BSEG` or `ACDOCA` counts a posting twice, and an item moves from the open to the cleared table when it is cleared.
- **Time-dependent masters.** `CSKS` and `CEPC` have `DATBI` in the key; a journal line joined on the cost center
  number alone is repeated once per validity period. The pack lists these links and does not apply them.
- **An account needs its chart of accounts.** `SKB1` and journal lines carry no `KTOPL`; it comes from
  `T001.KTOPL`, so `SKA1` is reached through `T001`.
- **Debit and credit.** ECC lines are unsigned with `SHKZG`; `ACDOCA` is signed.
- **Sold-to, ship-to and payer.** `VBAK.KUNNR`, `LIKP.KUNNR`, `VBRK.KUNRG` and the partner functions in `VBPA` can be
  three different customers.

## How the engine uses it

When two or more tables of a schema are tables the pack describes and have their key columns, `plan()` takes their
keys and the relationships between them from the pack, with the rule **`SAP pack`** and the source on the
relationship's note, before the name rules (the docstring of `infer.py`). Names match without case, schema or a
leading `sap_`/`raw_`/`stg_`/`bronze_` word: `VBAK`, `vbak`, `sap_vbak`, `bronze.SAP_VBAK`. Declared keys, the caller's
`keys` and `confirmed` still win. Name rules add nothing between two pack tables, and still link pack tables to your
own tables. A schema without SAP tables gets exactly the plan it got before (the golden tests are unchanged).

A pack relationship is a suggestion with a source, not evidence. `validate_plan` counts orphans and key duplicates for
it like for any other, and the test `test_validate_plan_checks_pack_relationships_against_rows` shows an item without
its header and a customer of another client found that way.

`sap_pack_draft` (read-only) shows what the pack recognises in a source, what it applies, what it lists but does not
apply, which pack tables and columns are missing, and the traps; with `export=` it adds one export (below).

## Exports

Text and files only; nothing is connected or created (`fabric_backend/exports.py`).

| Export | Format | Verified against |
| --- | --- | --- |
| `krusgraph` | the plan as `keys` and `confirmed`, the arguments every Krusgraph tool takes | the engine (round trip in the tests) |
| `dbt` | dbt sources with `unique`, `not_null`, `relationships` | dbt documentation, see `dbt.py` |
| `dab` | Data API builder configuration: entities with `source.key-fields` (or `fields[].primary-key` for DAB 2.0), relationships both ways, read permission | MicrosoftDocs/data-api-builder-docs `configuration/entities.md` and `configuration/data-source.md`, read 28 October 2026; validated in the tests against `Azure/data-api-builder` `schemas/dab.draft.schema.json` (copy in `tests/fixtures/dab/`) |
| `extraction` | a neutral list (`krusgraph.extraction/1`): per table the key, delta columns and the open-mirroring `_metadata.json` (`keyColumns`) | MicrosoftDocs/fabric-docs `docs/mirroring/open-mirroring-landing-zone-format.md`, read 28 October 2026 |

Not built, because no public specification could be checked: an SAP Datasphere replication flow file and the
configuration formats of third-party SAP extractors. The extraction list is the neutral input to translate into them.

## Sources, and what is verified

| Source | Used for | Fetched when the pack was written |
| --- | --- | --- |
| SAP Help Portal, SAP ERP / S/4HANA Sales and Distribution (help.sap.com/docs/SAP_ERP) | tables, keys, relationships of order to cash | no: help.sap.com was outside the session's network policy; cited from public knowledge of the documentation, **to be re-checked** |
| SAP Help Portal, Materials Management (purchasing, purchase order history, logistics invoice verification) | procure to pay | no, as above |
| SAP Help Portal, S/4HANA business partner | `LFA1` behind the business partner in S/4HANA | no, as above |
| SAP Help Portal, ABAP keyword documentation, client handling | `MANDT` as first key field | no, as above |
| SAP Learning, *Identifying data model simplifications in SAP S/4HANA* (Sales) | `VBUK`/`VBUP` folded into the document tables; `VBFA` simplified | found in a web search on 28 October 2026; the page could not be fetched |
| SAP Help Portal, S/4HANA Finance, universal journal | `ACDOCA`, and the ECC index tables it replaces | no, as above |
| SAP Help Portal, Financial Accounting (G/L accounts, open items) and Controlling (cost and profit centers) | finance | no, as above |
| Microsoft Fabric docs, *Mirroring SAP* (fabric-docs `docs/mirroring/sap.md`) | which SAP systems the mirroring supports (S/4HANA, ECC, BW/4HANA, BW, Datasphere) | yes, 28 October 2026; it names no tables |
| Krusmaster/sap-ontology README | the header/item pairs `VBAK` → `VBAP` → `VBEP` and their join keys | yes; used only where it agrees with SAP's documentation |

Every claim in the files names its sources (`sources` per table, relationship and trap; `fetched` per source).
**Verified against data: nothing yet.** All content is `status: documented`. It has been tested on a synthetic SAP
schema generated in the tests (names only, and a few synthetic rows in SQLite), never against an SAP system or a real
installation. When a module has been checked against a system with `validate_plan`, its `status` can become
`verified`, with where and when in `status_note`.

Left out of `Krusmaster/sap-ontology` on purpose: its list of S/4HANA CDS view relationships
(`relationships_standard.yaml`, `I_SALESDOCUMENT` and others) — CDS views, not tables, and the per-view field names
could not be checked against public documentation in this session; its example `ZC_SALESKPI` and
`I_PURCHASEORDER_P01` (a customer-specific Z view and a numbered variant); its inventory and storage-location entries
(no logistics or warehouse examples); and the Data Dictionary extract examples under `examples/dd`.

## Next modules

Not built yet, in this order:

1. ~~Procure to pay~~: built in round n21 (above). Left for later: contracts and scheduling agreements as their own
   relationships (`EKAB`), account assignment `EKKN`, and the goods-receipt documents (`MKPF`/`MSEG`, `MATDOC` in
   S/4HANA), which belong to inventory.
2. ~~Finance~~: built in round n22 (above). Left for later: the G/L open-item tables `BSIS`/`BSAS`, ledgers and
   currency types in S/4HANA, fixed assets (`ANLA`, `ANLC`), and a time-dependent join (a date between `DATAB` and
   `DATBI`) as a relationship kind of its own, so cost and profit centers can be applied instead of only listed.
3. **Pricing**: `KONV` (ECC) and `PRCD_ELEMENTS` (S/4HANA) — a clear variant case.
4. **Business partner** in S/4HANA: `BUT000`, `BUT100`, `CVI_CUST_LINK` between partner and customer.

## Contributing

1. Add or change a module in `fabric_backend/packs/sap/<module>.json`. Table and field names are facts; write every
   description in your own words. Never copy SAP's short texts or any SAP source code.
2. Only public sources: SAP's own documentation (help.sap.com, learning.sap.com), Microsoft's public material on SAP
   on Fabric. Add each to `sources` with `fetched` true only if you read it. Every table, relationship and trap needs at
   least one.
3. Nothing customer-specific: no `Z*`/`Y*` tables, company codes, customer names, volumes or configuration from any
   installation (`test_no_customer_specific_tables`).
4. A relationship that holds for some rows only gets a `condition`, and `"apply": false` when applying it would make
   `validate_plan` report orphans by design.
5. Run `python -m pytest -q tests/test_sap_pack.py tests/test_sap_inference.py`; the numbers in
   `tests/test_sap_inference.py` are asserted exactly, so a change to the pack shows up there and in
   [INFERENCE.md](INFERENCE.md).
