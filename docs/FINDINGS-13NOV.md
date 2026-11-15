# Findings: a first user's test of the MCP, the website and the workload

Round F1, run on 15 November 2026 on `main` at `15ac3b3` (after n224, n225, n226 and D1; n227, n229 and n230 had claimed
and not yet released). The founder's instruction of 12 November 2026: "test, develop, find new solutions and update: the
MCP, the website and the workload."

Everything here was done **without Fabric**. What that means for each part:

| Part | How it was tested | What was not tested |
| --- | --- | --- |
| Test suite | `pytest -q` on Python 3.12 with CI's pins, Chromium present (the browser tests ran) | the `notebooks` job (local Spark) |
| MCP, hosted server (`server.py`) | Every tool function called in-process, as the chat calls them. The SQL analytics endpoint was an in-memory SQLite with the engine's own T-SQL translated (`dialects.sqlite_sql`): the synthetic shop in schema `shop`, the synthetic SAP-shaped sample `sap_sd` in schema `dbo`, `sap_mm` in `sap_mm`. Fabric's REST API was a double that answers "a lakehouse, with or without schemas, in an empty workspace" | Sign-in, real Fabric answers, anything that needs an existing item (`describe_backend`, `plan_drift`, `app_starter`, `app_readiness`, `compare_semantic_model`, `query_graphql`, `create_report` past "no such model"), and every `dry_run=false` |
| MCP, local server (`mcp_server.py`) | All 24 tools on the same SQLite | a real ODBC source |
| Website | Served locally, every page at 375, 768 and 1280 px, light and dark, in Chromium; links, images, the Try-a-demo chat and `/check` driven by script and read on screenshots | external links the proxy would not open; other browsers |
| Model editor | `npm ci`, `npm test`, type check, production build, both packages; every view rendered outside Fabric at 375 px | inside the Fabric portal |

Every finding says **verified** (reproduced here, with the call or the page) or **suspected**. Numbers are from synthetic
data. Nothing in this file is a measurement of speed, and no finding was tried against a tenant.

Severity: **A** blocks a tester, **B** misleads, **C** looks bad. "Round" is who should take it: n227 (chat cards and
Start), n228 (drawio), n229 (verify, next steps, build gate), n230 (CDS, the SAP pack), n234 (visitor texts), or **new**.

The findings follow in the next commit of this round (the test is still running).
