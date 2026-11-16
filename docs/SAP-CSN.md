# SAP CSN: keys, links and amounts from the metadata that comes with the data

Round CDS2, 16 November 2026. Krusgraph is independent: it is not affiliated with SAP or Microsoft, and nothing here is
certified, endorsed or tested by either. "CSN", "CDS", "SAP Datasphere", "SAP Business Data Cloud" and "CAP" name SAP's
formats and products as SAP's public documentation does.

**Why.** Round CDS1 stopped on purpose: api.sap.com's `robots.txt` disallows `/cdsviews/` for every agent and
help.sap.com disallows all, so the pages that list each CDS view's fields, keys and associations are not read, and
the SAP pack ([SAP-CDS.md](SAP-CDS.md)) can only *propose* them. The same metadata comes legally with the customer's
own data: SAP's Core Schema Notation (CSN), the JSON form of a CDS model, which SAP Datasphere exports for its tables,
views and flows and a CAP project compiles. Krusgraph reads that file where the customer keeps it and fetches nothing.

## 1. What it reads

`fabric_backend/csn.py` reads one CSN file (`.json` or `.csn`), a folder of them, or a parsed CSN object. Per
definition of kind `entity` or `view`:

| What | From | Becomes |
| --- | --- | --- |
| Key fields | `key: true` on an element (and on a managed association: its generated columns) | the table's key, rule **"CSN metadata"** |
| Element types | `type`, `length`, `precision`, `scale` (`cds.Decimal(15,2)`) | reported; a numeric element landed as text is listed (`type_differences`) |
| Associations and compositions | `target`, `cardinality` (`{src, min, max}`; none declared is `[0..1]`, to-one, as CAP's `cds/csn.md` states), the `on` condition as column pairs; managed ones by `keys` (CSN 1.0+) or `foreignKeys` (CSN 0.1) as `<association>_<key>`; the backlink form `_Item.parent = $self` | a link, rule **"CSN metadata"** (section 2) |
| Amounts | `@Semantics.amount.currencyCode`, `@Measures.ISOCurrency` | an amount with its currency column and its level (header or item) |
| Quantities | `@Semantics.quantity.unitOfMeasure`, `@Measures.Unit` | a quantity with its unit |
| Currency and unit fields | `@Semantics.currencyCode`, `@Semantics.unitOfMeasure` | reported |
| Text vs ID | `@ObjectModel.text.element`, `@ObjectModel.text.association`, `@Semantics.text` | reported (`texts`, `text_fields`) |
| Foreign key annotations | `@ObjectModel.foreignKey.association` | marked on the link (`foreign_key_annotation`) |
| Data category | `@Analytics.dataCategory` (#FACT, #DIMENSION, #CUBE, ...), `@ObjectModel.dataCategory` (#TEXT), `@ObjectModel.modelingPattern` (ANALYTICAL_FACT, ...) | reported per table |
| Measures | `@Aggregation.default` (#SUM, ...) | reported |
| Labels | `@EndUserText.label`, `@Common.Label`, `@title` | reported |
| Versions | `$version`, `version.csn`, `meta.creator`/`flavor`/`kind`, `csnInteropEffective` | reported per file |

Annotations are read flat (`"@Semantics.amount.currencyCode": {"=": "Currency"}`) or nested; values as `{"=": ...}`,
`{"#": ...}`, a list or a plain value. **What it does not understand it says, and does not guess**: other kinds
(`type`, `service`, `context`, `aspect`), other top-level properties, every annotation it does not read (by name, with
a count), a view without elements (parsed CSN: export the inferred one), an ON condition that is not equalities of
columns joined by AND (a literal, a function, OR, a filtered path). They are in `Model.ignored` and the plan report's
`not_applied`.

## 2. Metadata is a declaration, not evidence

- A CSN key goes in as the table's key with the rule "CSN metadata". `validate_plan` counts it like any other key:
  unique and never NULL in the rows, or not.
- An association whose ON condition is the **target's whole key** is a link from the source to the target. One whose
  ON condition is the **source's whole key** (a header's `_Item`, a product's `_Text`, Datasphere's
  `SalesOrders._SalesOrderItems`) is read the other way round, items → header, whatever cardinality is declared, and
  the note says so. Where the declaration and the keys disagree (declared `[0..*]` on the target's key, or no
  cardinality on a header-to-items join) the note says that too: the count in the rows decides.
- Anything else is **not applied**, with why: a part of a key (a time-dependent master `EMPLOYEEID` of
  `EMPLOYEEID + VALIDITY_ENDDATE`), a filtered association, a target that is not in the files or not in the lakehouse.
  Confirm such a link yourself (`confirmed`) if it is one.
- Every key and link carries `provenance: "declared by metadata (CSN)"` and where it was declared (file, entity,
  association, declared cardinality). Keys and links the caller passes win over the CSN, as everywhere.
- **Where amounts live.** An amount on a table that another table points at many-to-one is a *header* amount: a join
  with those rows repeats it. Its level comes from `@Semantics.amount` and the links, not from its name, and
  `amounts.py` adds it to the doubled-total check (`validate_plan`'s `amount_levels`, the semantic model draft, the
  gold views), so `Wert` or `NETWR` is checked as well as `TotalNetAmount`.

## 3. Names: from the CSN to what lands in OneLake

What a mirror or a Copy job writes may differ from the CSN's names. A table answers to an entity when its name, without
case, underscores and dots, is one of:

- the entity's name (`SalesDocument`, `SALESDOCUMENT`, `sales_document`; `my.bookshop.Books` as `my_bookshop_Books`);
- the name without its namespace (`my.bookshop.Books` as `Books`);
- the name without its VDM prefix `I_`, `C_`, `A_`, `R_`, `P_`, `X_`, `E_`, `D_`, `F_` (`I_SalesDocument` as
  `SalesDocument`), or without a customer prefix `Z?_`, `Y?_`, `YY1_` (`ZI_ServiceOrder` as `ServiceOrder`);
- each of these after a leading layer word (`sap_`, `bronze_`, `raw_`, `stg_`, `dsp_`, `cds_`, ...) or a prefix you
  give (`--prefix`, `KRUSGRAPH_CSN_PREFIX`) is dropped.

The stronger form wins; a tie between two entities for one table, or two tables for one entity, is reported in
`ambiguous` and not resolved. A table is taken only when every key element is among its columns. Columns are compared
without case and underscores (`SalesDocumentItem`, `SALESDOCUMENTITEM`, `sales_document_item`).

The three columns a Datasphere replication flow appends to a cloud storage target, `__operation_type`,
`__sequence_number` and `__timestamp` ([SAP-CDS.md](SAP-CDS.md), section 1), are reported per table (`cdc_columns`)
and are not data columns: `schema.py` leaves them out of every plan (CDS2 added `__operation_type` to the two it
already left out). Columns the CSN does not name are listed in `extra_columns`.

## 4. Pointing Krusgraph at a CSN file

No new external call: every route reads a file that is already where Krusgraph runs.

- **In a Fabric notebook** (the file uploaded to the lakehouse's *Files*, next to the tables):

  ```python
  %pip install git+https://github.com/Krusmaster/fabric-backend
  from fabric_backend import csn, evidence
  from fabric_backend.schema import Schema
  model = csn.read("/lakehouse/default/Files/csn/")           # a file or a folder of .json/.csn files
  p, report = csn.plan(Schema.from_spark(spark, "dbo"), model)  # prefix="dsp_" if the landing added one
  print(p.summary()); report["not_applied"], report["unmatched"], report["amounts"]
  ```

  `evidence.validate(p, execute)` then counts the keys and links with a SQL connection, as `validate_plan` does.
- **CLI**: `fabric-backend csn model.json` prints what the file declares; `fabric-backend csn model.json --columns
  columns.csv [--prefix dsp_] [--json report.json]` plans an `INFORMATION_SCHEMA.COLUMNS` export with it.
- **Local MCP server** (`fabric-backend-mcp`, [LOCAL.md](LOCAL.md)): set `KRUSGRAPH_CSN` to a file or folder on that
  machine (and `KRUSGRAPH_CSN_PREFIX` if needed); every tool that plans then plans with the CSN, and `validate_plan`
  counts its keys and links. A CSN kept in OneLake is read here after you copy it to disk.
- **Not yet**: the hosted MCP server takes no CSN, and nothing reads a file from OneLake over the network.

## 5. Exporting CSN from SAP Datasphere (in your own tenant)

From SAP's Datasphere documentation (github.com/SAP-docs/sap-datasphere at commit
`e011e9d04fe06def42cb5f0f9315da6ffa36c855`, 20 October 2026, CC BY 4.0: `exporting-objects-to-a-csn-json-file-3916101.md`
and `importing-and-exporting-objects-in-csn-json-files-f8ff062.md`; read, not tried):

1. A user with the privileges *Data Warehouse General*, *Space Files* and *Data Warehouse Data Builder* (the
   *DW Modeler* role template grants them) opens the object in the *Data Builder*.
2. In the editor toolbar: *Export* > *Export to CSN/JSON File*. The file `<Object_Name>.json` is downloaded.
3. What comes with it: a **replication flow** exports the definitions of all its sources and its target table, which
   is the useful one for a mirror or a Copy job (the CDS views and the table that lands); a view exports its sources;
   an analytic model its fact and dimension sources; an E/R model all its tables and views; a local table with delta
   capture an extra `_Delta` table.
4. Put the file in the lakehouse's *Files* (or on the machine running the CLI) and follow section 4.

The pages also name the Transport app and the `datasphere` command line's `objects` commands; neither was tried.
From a CAP project, `cds compile srv --to json > model.json` writes the inferred CSN (CAP's `cds compile` help,
github.com/cap-js/docs at commit `891141c0a91817f575192e6cfac3f6d56b9eed82`). SAP Business Data Cloud is said to
describe data products in CSN Interop; that was not tried and no such file was read (the reader does read SAP's public
CSN Interop examples, section 7).

## 6. Testing with an SAP trial

Gustav registers the trial himself; what a trial tenant offers (which sources, whether replication flows to a cloud
target are available) is not verified here.

1. In the trial, build or import something small with keys and associations (a view over sample tables, or an E/R
   model) and export it as in section 5. If the trial can run a replication flow to cloud storage, export that flow.
2. Keep the exported file **outside this repository** (it is the tenant's metadata, even in a trial): not in a
   commit, an issue, a PR or a chat log that is published.
3. Land the same objects' rows in a lakehouse (the replication flow, or a CSV export), then run section 4 in a
   notebook: `csn.plan(...)`, then `validate_plan` (or `evidence.validate`).
4. What to look at: `report["unmatched"]` and `report["ambiguous"]` (did the landing's names map?), `cdc_columns`,
   `not_applied` with its reasons, the key and link counts, and `amount_levels`. What may be shared back: the counts
   and the reasons, without the tenant's object names.

## 7. Test sources and licences

All in `tests/fixtures/csn/` with their provenance in its `README.md` and in [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md);
no metadata exported from an SAP system, no customer data.

| File | Source | Licence |
| --- | --- | --- |
| `datasphere_bike_sales_model.json` | github.com/SAP-samples/datasphere-content, commit `695af09278d8a57d0fb0a441f247060eaea5daf5`, `Sample_Bikes_Sales_content/Bike Sales Model.json`, unmodified | Apache-2.0 (`LICENSE` and `.reuse/dep5` read at that commit) |
| `interop_airline.json`, `interop_cap_ariba_supplier_service.json` | github.com/SAP/csn-interop-specification, commit `ccf90cbba0be6eae411be4cf8356c2989c40bd30`, `spec/v1/examples/airline.json` and `spec/v1/examples/cap/ariba-supplier-service.json`, unmodified | Apache-2.0 (`LICENSE` and `REUSE.toml` read at that commit) |
| `synthetic_service_orders.json`, `synthetic_cap_bookshop.json` | **Synthetic**, written for the tests (the `meta.creator` of each says so) | MIT, this repository |

The documentation read to write the reader (not copied): CAP's `cds/csn.md` and `cds/annotations.md`
(github.com/cap-js/docs, commit `891141c0a91817f575192e6cfac3f6d56b9eed82`, Apache-2.0) and the Datasphere pages
above. api.sap.com and help.sap.com were not fetched.

## 8. Measured on the synthetic sample

`fabric_backend/csn_demo.py`: five synthetic tables described by `synthetic_service_orders.json`, landed as a
replication might write them: lower-case names with a prefix (`dsp_zi_serviceorder`), upper-case columns
(`SERVICEORDER`) and the three change columns. Every row is made up. Measured on 16 November 2026 with the unit tests
(SQLite, `python -m fabric_backend.csn_demo`), not in Fabric:

- **Names**: 5 of 5 tables matched to their entity; `ZI_ServiceOrderStatusText` has no table and is reported.
- **Plan with the CSN**: 5 keys and 4 links, all rule "CSN metadata"; 1 association not applied
  (`ZI_ServiceOrder._StatusText`: its ON condition compares with a literal). Without the CSN the name rules find
  **0 keys and 0 links** on this landing.
- **Row check** (`validate_plan`): 4 of 5 keys unique, 3 of 4 relationships hold without orphans.
  - `dsp_zi_customer`'s declared key `CUSTOMER` is not unique: customer C2 is there as inserted and as updated, as an
    unmerged landing holds it. The CSN declared the key; the rows refute it.
  - `dsp_zi_serviceorderitem → dsp_zi_serviceorder`: 1 orphan (an item of order SO9, which does not exist).
- **Amounts**: the CSN marks `TOTALNETAMOUNT` (header level: the items point at the orders many-to-one) and
  `NETAMOUNT` (item level), and `QUANTITY` with its unit. The total that doubles: `TOTALNETAMOUNT` summed over the join
  with the items gives 2 800, against 1 800 summed once per order.

On the public files (tests, no rows): Datasphere's Bike Sales model plans 9 keys and 8 links, two of them read the
other way round (`SalesOrders._SalesOrderItems`, `Products._ProductTexts`), and `SalesOrders._Employees` is not applied
(part of `Employees`' key); SAP's airline Interop example plans 7 keys on a snake-case landing, with `Flight.Price` as
an amount.

## 9. Limits and unverified points

- **Not run on a CSN exported from a real tenant**, nor in Fabric. The Datasphere export steps are from SAP's
  documentation, not tried. Whether a Datasphere export of a replication flow names the *target* the way the mirror
  names the table is not verified; `unmatched` will show it.
- ABAP CDS views exported through Datasphere: whether their CSN carries the `@Semantics`/`@ObjectModel` annotations
  and the associations of the S/4HANA view, or only the replicated structure, is **not verified**. If only the
  structure comes, the keys still do; links then come from the SAP pack and the name rules.
- Not read: `@EntityRelationship.*` (CSN Interop's own reference annotations), `@ObjectModel.representativeKey`,
  `@Semantics.language`, `@ObjectModel.alternativeKey`, i18n texts, parameters of views, the `query`/`projection` of
  a view (lineage), extensions (`extend`), and anything under a definition kind other than entity and view. They are
  listed as ignored.
- An ON condition with a literal (a language, a text type) is not applied, even where the literal makes it a key
  join; confirm it by hand.
- Structured elements are flattened with `_`, as CAP does; another landing's flattening is not recognised.
- A CSN is the customer's metadata. Krusgraph keeps nothing: the file is read in the call and the plan returned.
