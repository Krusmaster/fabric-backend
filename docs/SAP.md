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
| `order_to_cash` | customers `KNA1`, `KNVV`; materials `MARA`, `MAKT`; organisation `TVKO`, `TVTW`, `TSPA`, `T001`; orders `VBAK`, `VBAP`, `VBEP`; status `VBUK`, `VBUP` (ECC only); partners `VBPA`; deliveries `LIKP`, `LIPS`; billing `VBRK`, `VBRP`; document flow `VBFA`; contact persons `KNVK` (round n30) | 51, of which 39 are applied (6 of them filtered on the document category in `VBFA`); 12 are listed: partner and status rows of several document kinds (`VBPA`, `VBUK`, `VBUP`) |
| `procure_to_pay` (round n21) | suppliers `LFA1`, `LFB1`, `LFM1`; organisation `T024E`, `T001W`; requisitions `EBAN`; purchase orders `EKKO`, `EKPO`, `EKET`; purchase order history `EKBE`; supplier invoices `RBKP`, `RSEG` | 25, all applied; `EKBE` → `RBKP` filtered on invoice-receipt rows (`VGABE` = `2`, round n26) |
| `finance` (round n22) | charts of accounts `T004`; G/L accounts `SKA1`, `SKB1`; customer company-code data `KNB1` (round n27); customer and supplier open and cleared items `BSID`, `BSAD`, `BSIK`, `BSAK` (ECC); controlling area `TKA01`; cost centers `CSKS`; profit centers `CEPC` | 39, all applied; journal line → cost center and → profit center as joins valid on the posting date (kind `valid_on`, round n25); `KNB1` from journal lines, open items and the billing document's payer (round n27) |
| `pricing` (round n23) | document conditions `KONV` (ECC) and `PRCD_ELEMENTS` (S/4HANA); condition records `KONH`, `KONP`; condition types `T685` | 11, of which 7 are applied: condition lines and rates to their record, and (filtered, round n26) conditions → `EKKO` and → `T685`; conditions → `VBAK` and → `VBRK` are listed only |
| `business_partner` (round n24) | business partner `BUT000`, roles `BUT100`, addresses `BUT020`, relationships between partners `BUT050`; links to customer and supplier `CVI_CUST_LINK`, `CVI_VEND_LINK`; central addresses `ADRC` (round n27); telephone numbers `ADR2` and e-mail addresses `ADR6` (round n29) | 15, all applied; link table → `BUT000` on the partner's GUID (kind `unique`); the address links to `ADRC` valid today in the standard version (round n28); `ADR2`/`ADR6` → `ADRC` on the standard version (round n29) |
| `accounting_document` | `BKPF`; `BSEG` (ECC); `ACDOCA` (S/4HANA) | 4: `BSEG` → `BKPF`, `ACDOCA` → `BKPF`, `VBRK` → `BKPF`, `BKPF` → `T001` |

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

Round n24 added links the first versions lacked, found when the measurement was corrected: `VBRK`, `BKPF`,
`T024E` → `T001`; `EKKO`, `RBKP`, `BSEG`, `BSIK`, `BSAK`, `ACDOCA` → `LFB1` (supplier per company code); open items
`BSID`/`BSAD`/`BSIK`/`BSAK` → their `BSEG` line; `KNVV` → `TVTW`/`TSPA`; `LIKP` → `TVKO`; `VBUP` → `VBUK`; and, listed
only, the partner, status and document-flow rows of deliveries and invoices (`VBPA`, `VBUK`, `VBUP`, `VBFA` → `LIKP`,
`LIPS`, `VBRK`, `VBRP`).

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
- **Conditions are found through `KNUMV`.** `VBAK`, `VBRK` and `EKKO` carry a condition number `KNUMV`; their
  pricing lines are the `KONV`/`PRCD_ELEMENTS` rows with it (and `KPOSN` = item number). `KNUMV` is unique in the
  document but not its key, so the pack lists the link instead of applying it. Summing every `KWERT` is not the net
  value: subtotals, statistical and inactive conditions are lines too, and `KBETR` is a rate, not an amount.
- **Open items are copies.** `BSID`/`BSAD`/`BSIK`/`BSAK` copy customer and supplier lines of `BSEG`; adding them to
  `BSEG` or `ACDOCA` counts a posting twice, and an item moves from the open to the cleared table when it is cleared.
- **Time-dependent masters.** `CSKS` and `CEPC` have `DATBI` in the key; a journal line joined on the cost center
  number alone is repeated once per validity period. The pack lists these links and does not apply them.
- **An account needs its chart of accounts.** `SKB1` and journal lines carry no `KTOPL`; it comes from
  `T001.KTOPL`, so `SKA1` is reached through `T001`.
- **Debit and credit.** ECC lines are unsigned with `SHKZG`; `ACDOCA` is signed.
- **The partner number is not the customer number.** `BUT000.PARTNER` and `KNA1.KUNNR` can differ; the link goes
  through `CVI_CUST_LINK` (and `CVI_VEND_LINK` for suppliers), which names the partner by `PARTNER_GUID`. Tools may
  write that GUID as binary, hex or dashed text. The business partner tables call the client column `CLIENT`.
- **Addresses have versions and periods.** `ADRC`'s key is `CLIENT`, `ADDRNUMBER`, `DATE_FROM` and `NATION` (the
  standard version is blank). `KNA1`, `LFA1`, `T001`, `VBPA` and `BUT020` point at it with an address number; a join on
  the number alone repeats a customer once per version and period. Since round n28 the pack applies these links as
  joins valid on the date of the call in the standard version (below). A document can carry its own address
  (`VBPA.ADRNR`, such as a one-time ship-to address); a blank `ADRNR` is no reference.
- **Personal data under SAP's own names.** `ADR6.SMTP_ADDR` is an e-mail address, `KNA1.TELF1` a telephone number,
  `KNA1.STRAS` a street; the general privacy rules read none of these names. Since round n29 a pack table can name
  its personal columns (`personal`, by rule P1–P6), and the privacy rules use them for the tables the pack recognises:
  `sample_rows` masks them, drafted queries and gold views leave them out, `show_personal_data=true` shows them, as for
  any flagged column. Named so far: `KNA1`, `LFA1` (customers and suppliers can be people), `ADRC`, `ADR2`, `ADR6`,
  `BUT000`, and the contact persons `KNVK` (round n30: first and last name, telephone, birth date). A name rule that already flags a column wins, and its reason is kept.
- **Several numbers and e-mail addresses per address.** `ADR2` and `ADR6` have a row per number (`CONSNUMBER`) and per
  contact person (`PERSNUMBER`); filter `FLGDEFAULT` for the standard one.
- **Customer data per company code.** `KNB1` holds a row per customer and company code (reconciliation account,
  payment terms); journal lines and open items reach it on customer and company code together.
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

### Joins that are not key joins (round n25)

Two kinds of relationship are not an equality join on the target's key, and the pack says which with `kind`:

- **`unique`**: equality on a column set the target declares unique besides its key (`unique_keys`):
  `CVI_CUST_LINK.PARTNER_GUID` → `BUT000.PARTNER_GUID`, `KONV.KNUMV` → `VBAK.KNUMV`.
- **`valid_on`**: equality on the target's key without its valid-to column, plus a date of the source row inside the
  target row's period: `ACDOCA.RCNTR` → `CSKS.KOSTL` with `ACDOCA.BUDAT BETWEEN CSKS.DATAB AND CSKS.DATBI`.

The engine keeps them in `plan.extended` (class `ExtendedRelationship` in `infer.py`), never in `plan.relationships`.
The API for GraphQL, the semantic model, the views, the notebooks and the ontology read `plan.relationships` as key
joins, and none of them can express these two kinds; they are left out there, not bent into a key join. What shows
them: `plan_backend` (`extended_relationships`, with the join as SQL), `validate_plan`, `data_dictionary`,
`sap_pack_draft`, the Krusgraph export (`extended`) and the Data API builder export (kind `unique` only: the format
takes any `source.fields`/`target.fields`; whether Data API builder accepts a target that is not the key at runtime is
not verified, and a date-range join has no form there).

`validate_plan` checks them against the rows: for `unique`, that the target columns are unique and how many source rows
find no target; for `valid_on`, how many rows find no period that holds their date and how many fall in more than one
(overlapping periods, which would repeat the row in a join). Both are unit-tested on synthetic rows in SQLite. Dates in
SAP are text in the form `YYYYMMDD`, which compares correctly as text as long as both sides have the same type.

### Filtered joins (round n26)

Any of the kinds can carry a filter, `where`: the join holds for the rows whose column has one of the given values,
on the source side or the target side. A filtered relationship lives in `plan.extended` like the other two kinds,
since an API or model built as a plain join would apply it to every row. Applied with a filter now:

| Relationship | Filter | Why |
| --- | --- | --- |
| `VBFA` → `VBAK`, `LIKP`, `VBRK` (header) and `LIPS`, `VBRP` (item), on the subsequent document | `VBFA.VBTYP_N` in the sales, delivery or billing categories | the document flow links any document to any other; the category says which table the number is in |
| `VBFA` → `VBAP`, on the preceding document | `VBFA.VBTYP_V` in the sales categories | the same, for the preceding side |
| `EKBE` → `RBKP` | `EKBE.VGABE` = `2` | only invoice-receipt rows carry a supplier invoice number |
| `KONV`/`PRCD_ELEMENTS` → `EKKO` (kind `unique`, on `KNUMV`) | `KAPPL` = `M` | purchasing conditions; sales and billing share the table |
| `KONV`/`PRCD_ELEMENTS` → `T685` on `KAPPL`+`KSCHL` | `T685.KVEWE` = `A` (target side) | the condition type's key also has the usage; pricing is `A` |

The document category values (`C` order, `J` delivery, `M` invoice and so on) are as documented for ECC; that
S/4HANA uses the same values is not verified, and the filters say so in their condition. `validate_plan` counts
orphans only among the rows the filter selects, and rows that match more than one target row. The Data API builder
export leaves filtered joins out: the format has no row filter on a relationship.

Still listed only: `KONV`/`PRCD_ELEMENTS` → `VBAK` and → `VBRK` (both have application `V`; no column of the condition
row says order or invoice), and the partner and status rows of several document kinds (`VBPA`, `VBUK`, `VBUP`), which
have no document category column of their own in the pack. A filter through another table (`VBPA` joined to `VBUK` for
its category) would be a join path, not a relationship, and is not built.

### The standard version, valid today (round n28)

Two additions to the join kinds, made for `ADRC` and usable by any module:

- **A blank filter**: `{"side": "target", "column": "NATION", "blank": true}` matches SAP's blank however the tool
  wrote it: `NULL`, `''` or `' '` (`COALESCE(LTRIM(RTRIM(col)), '') = ''`).
- **Valid today**: `valid_on` with `"on": "today"` instead of a source date. The date is the date of the call, as text
  in SAP's `YYYYMMDD` form, so the same SQL runs on every dialect (T-SQL, Spark SQL, SQLite). A plan read later is
  read for that day: `validate_plan` checks the addresses valid when it runs, and a report for another date needs that
  date instead.

So `KNA1.ADRNR` → `ADRC` is `CLIENT`+`ADDRNUMBER`, the row with `DATE_FROM ≤ today ≤ DATE_TO`, `NATION` blank. The
key check accepts it because the join columns, one end of the period and the columns a filter fixes make up the key.
In the checks of every extended relationship, a blank source column now counts as no reference (SAP writes "none" as a
blank, not `NULL`), so `VBPA` rows without an own address are not counted as orphans.

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
| SAP Help Portal, pricing and the condition technique (SD and MM) | pricing | no, as above |
| SAP Help Portal, business partner and customer/vendor integration | business partner | no, as above |
| SAP Help Portal, central address management | `ADRC`, `ADR2`, `ADR6` and their personal columns | no, as above |
| SAP Help Portal, ABAP keyword documentation, client handling | `MANDT` as first key field | no, as above |
| SAP Learning, *Identifying data model simplifications in SAP S/4HANA* (Sales) | `VBUK`/`VBUP` folded into the document tables; `VBFA` simplified | found in a web search on 28 October 2026; the page could not be fetched |
| SAP Help Portal, S/4HANA Finance, universal journal | `ACDOCA`, and the ECC index tables it replaces | no, as above |
| SAP Help Portal, Financial Accounting (G/L accounts, open items) and Controlling (cost and profit centers) | finance | no, as above |
| Microsoft Fabric docs, *Mirroring SAP* (fabric-docs `docs/mirroring/sap.md`) | which SAP systems the mirroring supports (S/4HANA, ECC, BW/4HANA, BW, Datasphere) | yes, 28 October 2026; it names no tables |
| Krusmaster/sap-ontology README | the header/item pairs `VBAK` → `VBAP` → `VBEP` and their join keys | yes; used only where it agrees with SAP's documentation |

Every claim in the files names its sources (`sources` per table, relationship and trap; `fetched` per source).
**Verified against data: nothing yet.** The way to change that is [LIVE-TEST-SAP.md](LIVE-TEST-SAP.md) (round n31; part 0 runs the chain on synthetic SAP-shaped tables from `fabric-backend sap-demo` first, round n32, which shows the tools work but proves nothing about the pack):
run `validate_plan` on SAP tables you may describe, save the answer, and `fabric-backend sap-verify` proposes a status
per pack relationship (verified, review, no evidence, not checked); `--write` records each verified one in the pack
file as `verified: [{where, when, rows_with_value}]`, with `where` describing the system without naming a company. All content is `status: documented`. It has been tested on a synthetic SAP
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
3. ~~Pricing~~: built in round n23 (above). Left for later: the condition tables `Annn` (one per key combination,
   numbered per installation, so only the standard ones could be described), and a relationship kind on a unique
   column that is not the key (`KNUMV`), so the document links can be applied.
4. ~~Business partner~~: built in round n24 (above); `KNB1` and `ADRC` in round n27, the `ADRC` links applied in round n28, `ADR2` and `ADR6` with the pack's personal columns in round n29. Left for later: fax and other communication tables (`ADR3`, `ADR12`), and naming the personal columns of the remaining modules.

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
