# Nordic pack: the spike (30 October 2026)

What a second knowledge pack, after the SAP pack ([SAP.md](SAP.md)), could cover for the ERP systems common in the
Nordic countries, and which one to build first. This is the investigation of 30 October 2026 as it was handed to the
repository, nothing more: the round that wrote it down made no web calls of its own (Microsoft Learn is not reachable
from where it ran), so nothing below has been re-checked, and nothing has been added to it.

**The rule.** Only a public page that was actually opened counts as verified. A table, a key or a column that is
listed without a page having been opened is marked as such, and goes under "What remains to verify" at the end. No
figure or source in this file is from memory.

## Business Central (verified on Learn)

Business Central has a table reference on Microsoft Learn, one page per table of the base application, with the
fields and the keys. Opened on 30 October 2026:

| Table | ID | Keys and fields seen |
| --- | --- | --- |
| G/L Entry | 17 | Primary key `Entry No.`; secondary keys `G/L Account No.` + `Posting Date`, and `Transaction No.` |
| Cust. Ledger Entry | 21 | `Entry No.`, `Customer No.`, `Document Type`, `Document No.`, `Currency Code`, `Amount`, `Amount (LCY)`, `Open`, `Reversed` |
| Customer | 18 | the customer master |
| Sales Header | 36 | primary key (`Document Type`, `No.`), derived from the fields on the page, not quoted from a keys section |
| Sales Line | 37 | primary key (`Document Type`, `Document No.`, `Line No.`), derived from the fields on the page, not quoted from a keys section |

Sources (opened):

- https://learn.microsoft.com/en-us/dynamics365/business-central/application/base-application/table/microsoft.finance.generalledger.ledger.g-l-entry
- the corresponding pages for `cust.-ledger-entry` and `customer` under the same path.

**How Business Central lands in Fabric.** Native Data Mirroring: "production-ready preview" in October 2026, up to
1 000 tables, several companies, a curated package of 256 tables named MS-STD, the schema `BusinessCentral`;
Business Central marks which tables are per company. Sources (opened):
https://learn.microsoft.com/en-us/dynamics365/business-central/admin-fabric and `admin-manage-fabric-export` under
the same path. The column names after mirroring (for example `No_` for `No.`) are **not** verified. The older route,
bc2adls (github.com/microsoft/bc2adls), was archived in September 2023.

**Traps a pack must explain:**

- the `Document Type` enum inside the same table;
- `Amount` versus `Amount (LCY)` versus ACY;
- `Reversed`;
- the company key;
- `Code[20]` keys are text, so leading zeros matter.

## D365 Finance & Supply Chain Management

Finance & SCM reaches Fabric through Link to Fabric / Synapse Link. Sources (opened):
https://learn.microsoft.com/en-us/power-apps/maker/data-platform/azure-synapse-link-select-fno-data and
`fabric-link-faq` under the same path. What the linked tables carry:

- `Id` (the `RecId`, as a GUID), `IsDelete` (soft delete; deleted rows are purged after 28 days),
  `SinkCreatedOn` / `SinkModifiedOn`, `sysrowversion`, `sysdatastatecode`;
- enums as integers, with their names in `GlobalOptionsMetadata`;
- `FnO_Id`; reserved words get a trailing `_`; entities are prefixed `mserp_`.

Traps: `DataAreaId` + `Partition` (the company and the partition belong in every key), joins on `RecId`,
`IsDelete`, and the enum integers.

## Fortnox

A REST API with an OpenAPI description (https://api.fortnox.se/apidocs): Invoices, Orders, Offers, Customers,
Articles, Vouchers. A voucher's key is `/vouchers/{Series}/{Number}?financialyear=`
(fortnox.se/developer/guides-and-good-to-know/best-practices/vouchers). There are no tables, only what the API
returns, so a Fortnox pack would describe API extracts, not a database. Traps: one resource per document type,
voucher numbers restart per financial year, one company per token.

## The others

- **Visma.net**: docs.vismasoftware.no/vismanetapi exists, but the field pages answered 404 or 403, so nothing is
  verified at field level.
- **Unit4** (develop.unit4cloud.com): no sales or ledger tables are public.
- **IFS** (a CAPTCHA in the way), **Monitor** (api.monitor.se, without a field reference), **Jeeves**, **Hogia**,
  **Abacus**: not publicly documented.
- **Bexio**: docs.bexio.com is public; `contacts` verified, `kb_invoice` not reached.

## Spread (one old source)

IDC 2019, via https://erp-software.org/en/erp-worldwide/sweden/: Visma about 28 %, SAP 10 %, Unit4 6 %, Fortnox 4 %.
Monitor states 46 % of Swedish manufacturing; that is the vendor's own figure. Business Central: no public figure
found. The source is old and second-hand; it is here because it is the only one that was found, not because it is
good.

## Ranking

1. Business Central
2. D365 Finance & SCM
3. Fortnox
4. Visma.net
5. Bexio

Monitor and Unit4: C. The rest: not documented publicly, so no pack can be sourced for them under the rule above.

## Recommendation

Business Central first, then Finance & SCM. A pack definition, in the shape of the SAP pack:

- **Tables, each with its Learn link**: Customer (18), Sales Header (36), Sales Line (37), G/L Entry (17),
  Cust. Ledger Entry (21), Item (27), Item Ledger Entry and Value Ledger Entry.
- **Keys**, including the company column.
- **Relationships, each with its source**: Sales Line → Sales Header on `Document Type` + `Document No.`;
  Cust. Ledger Entry → Customer on `Customer No.`; G/L Entry ↔ Cust. Ledger Entry through `Transaction No.` /
  `Document No.`.
- **The traps** listed under Business Central above.

## What remains to verify

- The column names after Data Mirroring (`No_` and the like), and the name and form of the company column in the
  mirrored `BusinessCentral` schema: not verified; a pack cannot name a mirrored column until a mirrored table has
  been seen.
- The Learn pages for Item (27), Item Ledger Entry and Value Ledger Entry, and the keys sections of Sales Header
  (36) and Sales Line (37): the primary keys above are derived from the fields, not quoted. The G/L Entry ↔
  Cust. Ledger Entry link through `Transaction No.` / `Document No.` needs its page reference too.
- Visma.net at field level (the pages answered 404 or 403); Bexio's `kb_invoice`; Monitor's field reference; any
  public documentation at all for IFS, Jeeves, Hogia, Abacus and Unit4's sales and ledger tables.
- A current, first-hand figure for the spread of ERP systems in the Nordic countries, and any figure for Business
  Central; the IDC 2019 numbers above are second-hand and seven years old.
