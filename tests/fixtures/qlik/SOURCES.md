# Public Qlik load scripts used as test fixtures

16 November 2026, round Q2 (a scheduled Claude session, no live user).

These files test Krusgraph's reader for Qlik load scripts (`fabric_backend/migration_read.py`, `fabric_backend/qlik/`)
on scripts that Krusgraph's own rounds did not write. No customer data: every file comes from a public repository
whose licence file was opened and read at the commit named here, and which is under a permissive licence (MIT in all
four cases). Each folder holds that licence file, and each fixture's first line names its source.

Qlik, QlikView and Qlik Sense are trademarks of QlikTech International AB. Krusgraph is not affiliated with Qlik or
with the authors of these repositories; the files are used under their licences, as test input only.

## Sources

| Folder | Repository | Commit (its date) | Licence, as its `LICENSE` file says at that commit | Files | What it is |
|---|---|---|---|---|---|
| `qdf/` | [QlikDeploymentFramework/Qlik-Deployment-Framework](https://github.com/QlikDeploymentFramework/Qlik-Deployment-Framework) | `0e0adaaffc26fa79087b6867e80fa3aa70cf91a7` (2023-04-05) | MIT License, Copyright (c) 2019 Qlik (`qdf/LICENSE-Qlik-Deployment-Framework.txt`) | 34 | Qlik's own framework of include scripts: variables, subroutines, containers, a calendar generator. Mostly control flow, SET and LET. |
| `core-data-loading/` | [qlik-oss/core-data-loading](https://github.com/qlik-oss/core-data-loading) | `0b79c835e30af66f06590b93e5dfa4d4d8bc1ff5` (2020-10-12) | MIT License, Copyright (c) 2018 Qlik - Open Source Software (`core-data-loading/LICENSE-core-data-loading.txt`) | 16 | Qlik's own small examples of loads: files, inline tables, preceding loads, resident loads, concatenation, CrossTable. |
| `corectl/` | [qlik-oss/corectl](https://github.com/qlik-oss/corectl) | `38cdf7a4ff697892f89ef12b95019eb5129d1286` (2021-09-28) | The MIT License, Copyright (c) 2017-present QlikTech International AB (`corectl/LICENSE-corectl.txt`) | 7 | The load scripts of Qlik's command line tool for Qlik Core: its example and its test projects. |
| `butler/` | [ptarmiganlabs/butler](https://github.com/ptarmiganlabs/butler) | `ccc017cb883940d3318c6ca765e1dab420d7708f` (2026-11-14) | The MIT License (MIT), Copyright (c) 2016-2023, Göran Sander (`butler/LICENSE-butler.txt`) | 1 | One long script of subroutines that call a REST service: LIB CONNECT, SQL SELECT over a REST connection, mapping tables. |

All four were fetched with `git clone --depth 1` on 16 November 2026; the licence was read in the cloned `LICENSE`
file, not taken from a page's metadata.

## What was changed in the copies

- One line was added at the top of every file: where it comes from and its licence. Line numbers are therefore one
  higher than in the source.
- Files were renamed to their path with `/` and blanks replaced by `_`, so that every source file has its own name.
- A byte order mark was removed from 8 files, and 5 files were re-encoded from Windows-1252 to UTF-8 (the locale files
  of the Qlik Deployment Framework that hold non-ASCII day and month names).
- `butler/butler_subs.qvs`: two mentions of a private IP address in comments were replaced by `butler.example`.
- Nothing else. The files were searched for passwords, tokens, connection strings, UNC paths, drive paths, e-mail
  addresses and IP addresses before they were copied; apart from the two comment lines above there was none. Their
  `LIB CONNECT TO` statements name connections (`Butler_GET`, `myconnection`), not servers.

## Looked at and not used

| Source | Why not |
|---|---|
| Qlik's tutorials and sample apps on help.qlik.com | The host could not be reached from the session (the network policy answered 403), and those files carry no permissive open licence that could be read. Not used. |
| RobWunderlich/Qlikview-Components (63 `.qvs` files) | No `LICENSE` file at the repository root; the file headers say GNU Lesser General Public License. Not a permissive licence. Not used. |
| eapowertools/qs-telemetry-dashboard | GNU General Public License. Not used. |
| qlik-oss repositories without a `.qvs` file (enigma.js, halyard.js, gopherciser, core-get-started, core-scaling, core-orchestration, core-authorization, qlik-cli and others) | MIT, but their load scripts are strings inside JavaScript, Go or YAML files; taking them out would be writing a new file, not copying one. Not used. |

## What the corpus is, and is not

58 scripts, 1 856 statements. They are heavy on what real scripts are full of and Krusgraph's own fixtures had
little of: control flow, variables, subroutines, dollar-sign expansion, includes, partial-reload prefixes. They are
light on data models: no file here has two tables that share a field, so **associations, synthetic keys and circular
references are not exercised by this corpus**. Those are tested on the synthetic script `tests/fixtures/q1/sales.qvs`
with synthetic rows. A load script exported from a customer's app has not been read.

## Coverage

Counted by `tests/test_q2_qlik_corpus.py`, which fails when a number below changes. A statement is **read** when the
reader applied it to the tables or knows that it leaves them as they are (SET, LET, TRACE, STORE, a connection);
**control flow** (IF, FOR, SUB, CALL and the like) is listed and the loads inside it are read as if each ran once;
an **include** names another file, which the reader was not given; **not read** is listed with its line and reason.

| Statement type | Total | Read | Control flow | Include | Not read |
|---|---:|---:|---:|---:|---:|
| control | 722 | 0 | 722 | 0 | 0 |
| set | 535 | 535 | 0 | 0 | 0 |
| let | 303 | 303 | 0 | 0 | 0 |
| trace | 86 | 86 | 0 | 0 | 0 |
| load | 64 | 64 | 0 | 0 | 0 |
| drop | 42 | 31 | 0 | 0 | 11 |
| include | 29 | 0 | 0 | 29 | 0 |
| select | 20 | 20 | 0 | 0 | 0 |
| connect | 19 | 19 | 0 | 0 | 0 |
| comment | 11 | 11 | 0 | 0 | 0 |
| qualify | 8 | 8 | 0 | 0 | 0 |
| store | 5 | 5 | 0 | 0 | 0 |
| execute | 4 | 4 | 0 | 0 | 0 |
| exit | 3 | 3 | 0 | 0 | 0 |
| other | 2 | 0 | 0 | 0 | 2 |
| declare | 1 | 1 | 0 | 0 | 0 |
| derive | 1 | 1 | 0 | 0 | 0 |
| sleep | 1 | 1 | 0 | 0 | 0 |
| **All** | **1856** | **1092** | **722** | **29** | **13** |

| Folder | Statements | Read | Control flow | Include | Not read |
|---|---:|---:|---:|---:|---:|
| `butler/` | 235 | 172 | 63 | 0 | 0 |
| `core-data-loading/` | 26 | 26 | 0 | 0 | 0 |
| `corectl/` | 8 | 8 | 0 | 0 | 0 |
| `qdf/` | 1587 | 886 | 659 | 29 | 13 |

Read: 1092 of 1856 (58.8 %). Read or listed as control flow or an include: 1843 of 1856 (99.3 %). Before round Q2's fixes the reader left 813 of
these statements under `not_read` (722 of them control statements, which it now lists on their own).

The 13 statements not read: 11 `DROP TABLE` of a table that this text never loads (it is made by a subroutine of
another file, or its name is built when the script runs), one `WHERE` that follows a `;` in the source, and one
`LOAD` whose prefix and field list are dollar-sign expansions.

What "read" does not mean: that the result equals what Qlik would load. No Qlik engine ran these scripts; the
tables the reader finds were compared with the scripts by eye for the `core-data-loading` and `corectl` folders only.

## Files

| Fixture | Source file | Changes beside the first line |
|---|---|---|
| `qdf/3.Include_1.BaseVariable_1.Init.qvs` | `3.Include/1.BaseVariable/1.Init.qvs` | none |
| `qdf/3.Include_1.BaseVariable_3.SystemVariables.qvs` | `3.Include/1.BaseVariable/3.SystemVariables.qvs` | byte order mark removed |
| `qdf/3.Include_1.BaseVariable_4.Custom.qvs` | `3.Include/1.BaseVariable/4.Custom.qvs` | byte order mark removed |
| `qdf/3.Include_2.Locale_1.US.qvs` | `3.Include/2.Locale/1.US.qvs` | none |
| `qdf/3.Include_2.Locale_10.Ger.qvs` | `3.Include/2.Locale/10.Ger.qvs` | byte order mark removed |
| `qdf/3.Include_2.Locale_11.Aus.qvs` | `3.Include/2.Locale/11.Aus.qvs` | none |
| `qdf/3.Include_2.Locale_12.Bra.qvs` | `3.Include/2.Locale/12.Bra.qvs` | byte order mark removed |
| `qdf/3.Include_2.Locale_13.Fin.qvs` | `3.Include/2.Locale/13.Fin.qvs` | none |
| `qdf/3.Include_2.Locale_2.Swe.qvs` | `3.Include/2.Locale/2.Swe.qvs` | re-encoded from Windows-1252 to UTF-8 |
| `qdf/3.Include_2.Locale_3.UK.qvs` | `3.Include/2.Locale/3.UK.qvs` | byte order mark removed |
| `qdf/3.Include_2.Locale_4.Fra.qvs` | `3.Include/2.Locale/4.Fra.qvs` | re-encoded from Windows-1252 to UTF-8 |
| `qdf/3.Include_2.Locale_5.Spa.qvs` | `3.Include/2.Locale/5.Spa.qvs` | re-encoded from Windows-1252 to UTF-8 |
| `qdf/3.Include_2.Locale_6.Ita.qvs` | `3.Include/2.Locale/6.Ita.qvs` | re-encoded from Windows-1252 to UTF-8 |
| `qdf/3.Include_2.Locale_7.Por.qvs` | `3.Include/2.Locale/7.Por.qvs` | re-encoded from Windows-1252 to UTF-8 |
| `qdf/3.Include_2.Locale_8.Rus.qvs` | `3.Include/2.Locale/8.Rus.qvs` | byte order mark removed |
| `qdf/3.Include_2.Locale_9.Jap.qvs` | `3.Include/2.Locale/9.Jap.qvs` | byte order mark removed |
| `qdf/3.Include_4.Sub_1.FileExist.qvs` | `3.Include/4.Sub/1.FileExist.qvs` | none |
| `qdf/3.Include_4.Sub_10.QVDLoad.qvs` | `3.Include/4.Sub/10.QVDLoad.qvs` | none |
| `qdf/3.Include_4.Sub_11.DynamicContainerLoader.qvs` | `3.Include/4.Sub/11.DynamicContainerLoader.qvs` | none |
| `qdf/3.Include_4.Sub_12.Index.qvs` | `3.Include/4.Sub/12.Index.qvs` | none |
| `qdf/3.Include_4.Sub_13.NiceTrace.qvs` | `3.Include/4.Sub/13.NiceTrace.qvs` | none |
| `qdf/3.Include_4.Sub_14.QVDReduce.qvs` | `3.Include/4.Sub/14.QVDReduce.qvs` | none |
| `qdf/3.Include_4.Sub_15.ETLLog.qvs` | `3.Include/4.Sub/15.ETLLog.qvs` | none |
| `qdf/3.Include_4.Sub_2.LoadVariableCSV.qvs` | `3.Include/4.Sub/2.LoadVariableCSV.qvs` | none |
| `qdf/3.Include_4.Sub_3.LoadContainerMap.qvs` | `3.Include/4.Sub/3.LoadContainerMap.qvs` | none |
| `qdf/3.Include_4.Sub_4.GenericContainerLoader.qvs` | `3.Include/4.Sub/4.GenericContainerLoader.qvs` | byte order mark removed |
| `qdf/3.Include_4.Sub_5.DoDir.qvs` | `3.Include/4.Sub/5.DoDir.qvs` | none |
| `qdf/3.Include_4.Sub_6.CreateFolder.qvs` | `3.Include/4.Sub/6.CreateFolder.qvs` | none |
| `qdf/3.Include_4.Sub_7.CalendarGen.qvs` | `3.Include/4.Sub/7.CalendarGen.qvs` | none |
| `qdf/3.Include_4.Sub_8.QVFileInfo.qvs` | `3.Include/4.Sub/8.QVFileInfo.qvs` | none |
| `qdf/3.Include_4.Sub_9.QVDMigration.qvs` | `3.Include/4.Sub/9.QVDMigration.qvs` | none |
| `qdf/3.Include_4.Sub_99.LoadAll.qvs` | `3.Include/4.Sub/99.LoadAll.qvs` | none |
| `qdf/InitLink.qvs` | `InitLink.qvs` | none |
| `qdf/InitLinkSkip.qvs` | `InitLinkSkip.qvs` | none |
| `core-data-loading/compound-field.qvs` | `scripts/compound-field.qvs` | none |
| `core-data-loading/concat-tables-auto.qvs` | `scripts/concat-tables-auto.qvs` | none |
| `core-data-loading/concat-tables-forced.qvs` | `scripts/concat-tables-forced.qvs` | none |
| `core-data-loading/crosstable.qvs` | `scripts/crosstable.qvs` | none |
| `core-data-loading/csv-file.qvs` | `scripts/csv-file.qvs` | none |
| `core-data-loading/field-functions.qvs` | `scripts/field-functions.qvs` | none |
| `core-data-loading/formating-functions.qvs` | `scripts/formating-functions.qvs` | none |
| `core-data-loading/inline-table.qvs` | `scripts/inline-table.qvs` | none |
| `core-data-loading/preceding-load-calc-field.qvs` | `scripts/preceding-load-calc-field.qvs` | none |
| `core-data-loading/preceding-load-reuse-calc.qvs` | `scripts/preceding-load-reuse-calc.qvs` | none |
| `core-data-loading/rename-fields.qvs` | `scripts/rename-fields.qvs` | none |
| `core-data-loading/resident-load.qvs` | `scripts/resident-load.qvs` | none |
| `core-data-loading/split-field.qvs` | `scripts/split-field.qvs` | none |
| `core-data-loading/subset-of-fields.qvs` | `scripts/subset-of-fields.qvs` | none |
| `core-data-loading/webpage.qvs` | `scripts/webpage.qvs` | none |
| `core-data-loading/xlsx-file.qvs` | `scripts/xlsx-file.qvs` | none |
| `corectl/examples_script.qvs` | `examples/script.qvs` | none |
| `corectl/test_projects_abac_script.qvs` | `test/projects/abac/script.qvs` | none |
| `corectl/test_projects_presedence_script.qvs` | `test/projects/presedence/script.qvs` | none |
| `corectl/test_projects_using-entities_script.qvs` | `test/projects/using-entities/script.qvs` | none |
| `corectl/test_projects_using-script_script1.qvs` | `test/projects/using-script/script1.qvs` | none |
| `corectl/test_projects_using-script_script2.qvs` | `test/projects/using-script/script2.qvs` | none |
| `corectl/test_projects_using-script_script3.qvs` | `test/projects/using-script/script3.qvs` | none |
| `butler/butler_subs.qvs` | `docs/sense_script/butler_subs.qvs` | 2 private IP address(es) in comments replaced by butler.example |
