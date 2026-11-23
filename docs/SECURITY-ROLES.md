# Row-level and object-level security, drafted from the plan

21 November 2026, round BL17 (backlog B-24). Code: `fabric_backend/security_roles.py`. Tests:
`tests/test_bl17_security_roles.py`. Verified by unit tests on the synthetic SAP demo and the synthetic shop (SQLite) on
21 November 2026; the TMDL has not yet been opened in Power BI Desktop or applied to a Fabric model.

A buyer's IT asks "who sees which company's rows" before a model goes to a pilot's users. Krusgraph answers with a
**draft**: the roles a model would need, which tables each reaches and which it does not, and the columns to hide.
**Nothing is written**: no role, table or permission is created in Fabric or Power BI, no row value is read, and no
model, AI or language model is involved; every proposal comes from a named rule.

## Which columns a role would filter on (`candidates`)

By column name and the knowledge packs only, never by a value:

| Rule | What | Names |
| --- | --- | --- |
| S1 | SAP company code | `BUKRS` (`RBUKRS` in ACDOCA) |
| S2 | SAP sales organisation | `VKORG` |
| S3 | SAP plant | `WERKS` |
| S4 | SAP client | `MANDT`; `CLIENT` and `RCLNT` only in a table the SAP pack recognises |
| B1 | Business Central company | `$Company` (a bc2adls export; the pack reads it as `COMPANY`) |
| G1 | a generic company, region or country | `company`, `company_code`, `company_id`, `region`, `region_code`, `region_id`, `country`, `country_code`, `country_id` |

S1-S4 and B1 are the systems' own names for the unit data is kept by, so every table that carries one is filtered. A G1
name is proposed only when the rows are kept by it: it is in at least two tables, or it is part of a table's key. A
`country` in one table and no key is an attribute (where a customer lives), not a boundary, and is passed over with
that reason.

- **The synthetic SAP demo** proposes `BUKRS` (company code: T001, TVKO, VBRK) and `VKORG` (sales organisation:
  TVKO, VBAK, LIKP, VBRK) first, then `MANDT` (the client, in every table).
- **The shop proposes no role**: its only such column is `customers.country`, in one table and no key. Its
  object-level draft still hides `customers.name` and `addresses.city`.

## What a role does (`draft`)

One TMDL role per proposed column. Every table that carries the column gets a `tablePermission` whose DAX keeps the
rows whose value the signed-in user (`USERPRINCIPALNAME()`) is mapped to in **`security_user_map`**, a table the
customer fills in:

| Column | What |
| --- | --- |
| `user_principal_name` | the signed-in user's name as Entra ID gives it (USERPRINCIPALNAME() in DAX) |
| `filter_column` | the column the role filters on, as written in the role (for example BUKRS) |
| `filter_value` | one value of that column the user may see, as text; one row per user and value |

Fill this in: `security_user_map` is a table the customer keeps in the lakehouse, one row per user and value they may see. Krusgraph does not create it, fill it or read it. A user with no row sees no rows of a filtered table. One map serves every role: `filter_column` says which.

Tables without the column are reached only over the plan's **counted links**: relationships `validate_plan` counted
and that hold for every row with a value, followed from the one side to the many side (the direction a filter flows
in a tabular model). A link with an orphan row is not counted, so the table behind it is listed as **not reached**
rather than guessed into the role. A path over a link of several columns (SAP's MANDT + VBELN) needs a combined key
column in the model first, as the semantic model draft explains; the explanation says so per table.

The BUKRS role on the SAP demo, as `markdown(plan, validation)` explains it:

```text

Why: S1: SAP's company code by its name (BUKRS), in 3 tables; the sap pack recognises sap_t001 as T001, sap_tvko as TVKO, sap_vbrk as VBRK.

What it does: a user sees the rows of these tables whose `BUKRS` is one of the values mapped to them in `security_user_map` (filter_column = "BUKRS"). A user with no row there sees none of these rows.

Filtered directly (the table carries the column):
- `sap_t001` on `BUKRS`
- `sap_tvko` on `BUKRS`
- `sap_vbrk` on `BUKRS`

Reached over counted links (the filter flows from the one side to the many side):
- `sap_likp`: sap_likp.MANDT+VKORG → sap_tvko (a link of several columns: the model needs a combined key column first, see semantic_model)
- `sap_lips`: sap_likp.MANDT+VKORG → sap_tvko ; sap_lips.MANDT+VBELN → sap_likp (a link of several columns: the model needs a combined key column first, see semantic_model)
- `sap_vbak`: sap_vbak.MANDT+VKORG → sap_tvko (a link of several columns: the model needs a combined key column first, see semantic_model)
- `sap_vbrp`: sap_vbrp.MANDT+VBELN → sap_vbrk (a link of several columns: the model needs a combined key column first, see semantic_model)

Not reached (no counted path to a filtered table; the role does not filter them):
- `sap_kna1`
- `sap_mara`
- `sap_makt`
- `sap_vbap`
- `sap_vbep`
- `sap_vbfa`
- `sap_vbpa`
- `sap_knvk`
- `sap_adrc`
- `sap_adr6`
```

Its TMDL (`definition/roles/Rows by company code (BUKRS).tmdl`):

```text
/// Draft by Krusgraph: S1: SAP's company code by its name (BUKRS), in 3 tables; the sap pack recognises sap_t001 as T001, sap_tvko as TVKO, sap_vbrk as VBRK.
/// Each table that carries the column keeps the rows whose value the user is mapped to in security_user_map.
role 'Rows by company code (BUKRS)'
	modelPermission: read

	tablePermission sap_t001 = 'sap_t001'[BUKRS] IN CALCULATETABLE(VALUES('security_user_map'[filter_value]), 'security_user_map'[user_principal_name] = USERPRINCIPALNAME(), 'security_user_map'[filter_column] = "BUKRS")

	tablePermission sap_tvko = 'sap_tvko'[BUKRS] IN CALCULATETABLE(VALUES('security_user_map'[filter_value]), 'security_user_map'[user_principal_name] = USERPRINCIPALNAME(), 'security_user_map'[filter_column] = "BUKRS")

	tablePermission sap_vbrk = 'sap_vbrk'[BUKRS] IN CALCULATETABLE(VALUES('security_user_map'[filter_value]), 'security_user_map'[user_principal_name] = USERPRINCIPALNAME(), 'security_user_map'[filter_column] = "BUKRS")

	/// The signed-in user sees only their own rows of security_user_map.
	tablePermission security_user_map = 'security_user_map'[user_principal_name] = USERPRINCIPALNAME()
```

The map table (`definition/tables/security_user_map.tmdl`):

```text
/// Fill this in: `security_user_map` is a table the customer keeps in the lakehouse, one row per user and value they may see. Krusgraph does not create it, fill it or read it. A user with no row sees no rows of a filtered table.
table security_user_map

	/// the signed-in user's name as Entra ID gives it (USERPRINCIPALNAME() in DAX)
	column user_principal_name
		dataType: string
		summarizeBy: none
		sourceColumn: user_principal_name

	/// the column the role filters on, as written in the role (for example BUKRS)
	column filter_column
		dataType: string
		summarizeBy: none
		sourceColumn: filter_column

	/// one value of that column the user may see, as text; one row per user and value
	column filter_value
		dataType: string
		summarizeBy: none
		sourceColumn: filter_value

	partition security_user_map = entity
		mode: directLake
		source
			entityName: security_user_map
			expressionSource: DatabaseQuery
```

## Object-level security (`ols_draft`)

One role, `Without personal data`, hides every column `privacy.py` flags (rules P1-P6, or the pack) with
`metadataPermission: none`, so a user in that role does not see the columns at all. On the SAP demo:

```text
/// Draft by Krusgraph: object-level security for the columns privacy.py flags by name (rules P1-P6, or the pack).
role 'Without personal data'
	modelPermission: read

	tablePermission sap_adr6
		/// P2: the sap pack names ADR6.SMTP_ADDR an e-mail address
		columnPermission SMTP_ADDR
			metadataPermission: none

	tablePermission sap_adrc
		/// P5: the sap pack names ADRC.CITY1 an address
		columnPermission CITY1
			metadataPermission: none
		/// P1: the sap pack names ADRC.NAME1 a person's name
		columnPermission NAME1
			metadataPermission: none
		/// P5: the column name 'POST_CODE1' names an address
		columnPermission POST_CODE1
			metadataPermission: none
		/// P5: the column name 'STREET' names an address
		columnPermission STREET
			metadataPermission: none

	tablePermission sap_kna1
		/// P1: the sap pack names KNA1.NAME1 a person's name
		columnPermission NAME1
			metadataPermission: none
		/// P5: the sap pack names KNA1.ORT01 an address
		columnPermission ORT01
			metadataPermission: none
		/// P5: the sap pack names KNA1.PSTLZ an address
		columnPermission PSTLZ
			metadataPermission: none
		/// P5: the sap pack names KNA1.STRAS an address
		columnPermission STRAS
			metadataPermission: none
		/// P3: the sap pack names KNA1.TELF1 a telephone number
		columnPermission TELF1
			metadataPermission: none

	tablePermission sap_knvk
		/// P1: the sap pack names KNVK.NAME1 a person's name
		columnPermission NAME1
			metadataPermission: none
		/// P1: the sap pack names KNVK.NAMEV a person's name
		columnPermission NAMEV
			metadataPermission: none
		/// P3: the sap pack names KNVK.TELF1 a telephone number
		columnPermission TELF1
			metadataPermission: none
```

## Syntax, and where it was read

Read on Microsoft Learn on 21 November 2026:

- "Tabular Model Definition Language (TMDL)", learn.microsoft.com/analysis-services/tmdl/tmdl-overview:
  `role` / `modelPermission: read` / `tablePermission <table> = <DAX filter>`; roles under `definition/roles/`.
- "Object-level security (OLS)", learn.microsoft.com/fabric/security/service-admin-object-level-security:
  `tablePermission <table>` / `columnPermission <column>` / `metadataPermission: none`.

The tests parse every part with the reader `compare_semantic_model` uses (`model_compare.from_tmdl`): the map table
is read with its three columns and no role is mistaken for a table.

## Next step

**Done in round BL43 (23 November 2026):** the model draft takes the roles on request. `semantic_model.draft(...,
roles=["BUKRS"])` adds the role drafted here and the `security_user_map` table (with `ref table` in `model.tmdl`), and
the summary's `security_roles` lists the roles added, those not added and why (a role whose tables are not all in the
model is left out), and the "fill this in" note. Without `roles` the model is exactly as before
(`tests/test_bl43_model_roles.py`).

**Done in round BL46 (23 November 2026):** the candidates are offered in the model dry run, off by default.
`create_semantic_model`'s dry run lists them as `role_candidates`: per role its name, the column, the rule, the tables
it filters (`filters`), why, whether it fits the model's `tables` filter and whether it is added. Names only; no row
value is read or shown. Nothing is added unless the caller passes the roles they accept, by column: `roles=["BUKRS"]`
on the tool, or `roles` on the workload build's semantic model output (`{"kind": "semantic_model", "name": ...,
"roles": ["BUKRS"]}`), whose card shows the same list as `roles`. A name no rule proposes is refused with kind
`bad_input` before anything is read, naming the roles proposed. A source with no candidate (the shop) answers exactly
as before. A model on the gold views takes no role yet (refused in plain words). `tests/test_bl46_roles_dry_run.py`.

Next: a tick box per role in the workload editor's model step (the engine takes `roles` already); roles on a model over
the gold views; and open one in Power BI Desktop on the SAP demo.
