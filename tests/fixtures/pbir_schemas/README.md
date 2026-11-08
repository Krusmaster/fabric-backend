# PBIR JSON schemas (test fixtures)

The schemas of a Power BI report definition (PBIR) that `fabric_backend/report.py` writes, copied unmodified from
github.com/microsoft/json-schemas at commit `eecc60d35b9ab18b884d35c50abe7d09d2753cdf` (directory `fabric/item/report/`,
same paths below this folder). They are published at `https://developer.microsoft.com/json-schemas/fabric/item/report/...`,
the `$schema` URLs the parts name; `tests/test_create_report.py` maps those URLs to these files and validates every part
create_report writes (round n151).

Only the files the parts use and the files they refer to (`$ref`) are here: definitionProperties 2.0.0, versionMetadata
1.0.0, report 3.1.0, pagesMetadata 1.0.0, page 2.0.0, visualContainer 2.0.0, visualConfiguration 2.0.0 (embedded),
formattingObjectDefinitions 1.3.0 and 1.4.0, semanticQuery 1.2.0 and 1.3.0, filterConfiguration 1.1.0 and 1.2.0 (embedded).

Licence: MIT, Copyright (c) Microsoft Corporation; the `LICENSE` file at that commit is `LICENSE-microsoft-json-schemas.txt`.
