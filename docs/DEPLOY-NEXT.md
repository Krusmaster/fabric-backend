# Next deploy: what is live, and what to check (internal)

Rewritten in round BL31 on 21 November 2026 (sprint item BL31, backlog C-01, issue #135) from `main` at `27ea969`
and the runs of `.github/workflows/deploy.yml`. The first version (round n127, 6 November 2026) listed what came after
build `src-8d6c473bf26f45f9` (`main` up to n111, `78aabdf`); this one replaces it.

## Short answer

- **Issue #135 was a one-off.** The automatic deploy of `48f735d` (ED2's release, 14:54 UTC) stopped in its first Azure
  step, `azure/login`, before any Azure call:
  `##[error]Failed to fetch federated token from GitHub. Please make sure to give write permissions to id-token in the workflow.`
  followed by `Error Message: Request timeout: /309//idtoken/...?api-version=2.0&audience=api%3A%2F%2FAzureADTokenExchange`.
  The `deploy` job does have `id-token: write`, and the gate job had passed with every variable set, so this was
  GitHub's token service timing out, not a missing permission, variable or one-time step. The snapshot, update and
  rollback steps were "skipped" because the step before them failed; nothing in Azure changed.
- **It did not stay broken.** The next commit's run (`215441f`, 15:15 UTC) deployed, and so did every later commit
  that was `main`'s tip when its CI finished. Runs whose commit was no longer the tip end in the gate with
  "go=false" (by design, the newer commit deploys).
- **Live now:** build `src-bc278814ec357d5d`, `main` at `27ea969` (SM6's release), deployed by run 44950163228 at
  21:15 UTC on 21 November. Its log ends with "Hemsida, dokumentation, sekretessida och MCP-inloggningskrav svarar
  korrekt." Everything on `main` up to `27ea969` is in that image, including all rounds listed below. What later rounds
  merge goes out by itself after green CI.
- **Not deployed by the workflow** (unchanged since CD1): the Fabric workload package upload, changes in
  `deploy/krusgraph.json`, secrets, domains, Key Vault. Those stay `bash deploy/krusgraph.sh --update` in Cloud Shell.

## Deploy runs on `main` on 21 November 2026 (UTC)

| Time | Commit | Result |
| --- | --- | --- |
| 11:21 to 13:46 | `dbb130b`, `8ab0b53`, `ae3e0a0`, `4c79568`, `4e81c0e`, `a1131c8` | deployed (a run of 4 to 5 minutes each; `a1131c8` checked step by step) |
| 14:54 | `48f735d` | **failed** in `azure/login` (token timeout above); issue #135 opened by the workflow |
| 15:15 | `215441f` | deployed: the first run after #135 got through every step |
| 15:28 to 20:34 | `c86d353`, `cccc920`, `d4a2192`, `dc2c3fa`, `2b94747`, `0680adf`, `b41b2cc`, `457fd15`, `84d9beb`, `feae6fd`, `d300659` | deployed; the other runs on these commits stopped in the gate (not the tip any more, or waiting behind a running deploy) |
| 21:10 | `27ea969` | deployed, build `src-bc278814ec357d5d` |

Read from run durations; `457fd15` and `27ea969` were also checked step by step (every step green, rollback and issue
skipped). No run failed after 14:54. Issue #135 is still open; closing it is Gustav's call (no round comments on issues).

## What came after build `src-8d6c473bf26f45f9`, by group

Every round with a release commit between `78aabdf` and `27ea969` (241 release commits, 209 rounds), grouped by the
areas its release commit names: editor if it names Workload; else chat if MCP tools or Krusgraph CLI; else engine if
Engine, SAP pack, Pipeline jobs, Catalog publish or Rayfin; else site if Website; else docs. All of it is in the live
image; the "look at" lines are what to check once, since nobody has checked the live site by hand since 6 November.

**Engine (56):** n114, n115, n116, n119, n120, n122, n123, n124, n125, n126, n128 to n134, n136 to n141, n143, n144,
n150, n192, n200, n202, n204, n208, n230, W7, B3, Q1, CDS2, PK1, PK2, LT1, WB1, SAPD1, DP1, SRC3, DBT1, BL3, BL5, BL8,
BL10, BL14, BL17, BL19, BL23, BL25, BL27, BL29, SM5.
Look at: from Claude, on the demo workspace with synthetic data, `validate_plan` on `sap_demo` (counts, receipt rows,
the catalog quality line) and one dry run of `create_pipeline`; nothing is written with `dry_run=true`.

**Chat (32):** n149, n151, n164, n169, n170, n172, n205, n218, n219, n220, n226, n227, F2, L1, MG1, Q2, WB12, WB13,
WB15, AP2, AP3, DA2, RQ1, UM2, DIR1, CL1, BL1, BL21, SM2, SM4, SM6, DP2.
Look at: `/llms.txt` says "Forty-eight tools"; the tool list in Claude matches it; the MCP Apps check card shows on
`validate_plan` (the deploy config has `mcp_apps: true`); a write tool asks for `target_lakehouse` (SM6) and still
defaults to a dry run.

**Editor (53):** n166, n168, n171, n173 to n177, n179 to n181, n183 to n185, n189, n195, n197, n198, n201, n207,
n209, n210, n213 to n216, n221 to n223, n225, n228, n229, n243, W11 to W14, F1, CSN2, CA1, WB2, WB4, WB10, WB11, WB14,
UM1, FA1, CO1, MOD1, SM3, ED1, ED2, ED3.
Look at: the Krusgraph Model item opens in Fabric from workload.krusgraph.com and the Model editor loads (ED1 to
ED3). The workload's `Manifest` last changed on 17 November (W13, `dfe4e4a`): if the package in the tenant was uploaded
before that, it must be built and uploaded again by hand (`docs/WORKLOAD-DEV.md`); the workflow never uploads it.

**Site (34):** n86b, n117, n135, n142, n145, n146, n154, n157, n160, n161, n165, n188, n190, n194, n196, n203, n206,
n211, n212, n217, n224, n231 to n234, n239, n240, G1, D2, SRC1, BL2, DOCV1, DOCV2, DBTV1.
Look at: 200 from `/`, `/check`, `/start`, `/sap`, `/sources`, `/docs`, `/trust`, `/security`, `/privacy`, `/pricing`,
`/partners`, `/use-cases`, `/llms.txt`, `/llms-full.txt`, `/sitemap.xml`; the home page replay card; `/sap` plays the
film with captions.

**Docs (18):** n113, n118, n121, n127, n167, n186, n191, S1, D1, W8, W10, A1, C1, P1, K1, WP1, LS2, BL12.
Look at: nothing live beyond the `/docs` pages above; these are repository documents.

**Other (16):** deploy and CI (n159, n235, B2, CD1, CI1), tests (n163), hub readiness (n178), evolution (E1), social
media images (I1, H1, n236, C2, n241, n242), the chat demo's files (n162), WB3's claims. Nothing to look at live.

## Settings the live app runs with

From the deploy log of run 44950163228 (the saved `deploy/krusgraph.json`; ids and names left out here):
`mcp_apps: true`, `read_only: false`, `no_row_values: false`, `pipeline_execute: false`, `ontology_write: false`,
`marketplace: false`, `entitlements: false`, `trial: false`, `min_replicas: 1`, `log_retention_days: 30`. The workflow
changes only the image and `KRUSGRAPH_BUILD`; changing any of these is a Cloud Shell `--update` by Gustav.

## What Gustav does next (in order)

1. Nothing to repair: automatic deploy works. Optionally close issue #135 with a pointer to this page.
2. Open `https://krusgraph.com/healthz`: it answers 200 with `src-bc278814ec357d5d` or a newer build.
3. Open the site pages in the Site group above once (each answers 200).
4. In Claude, against the demo workspace with synthetic data: the Engine and Chat checks above.
5. In Fabric: open the Krusgraph Model item; if the uploaded workload package predates 17 November, rebuild and
   upload it (`docs/WORKLOAD-DEV.md`).
6. Record what ran, where and when in `docs/LIVE-TEST.md`.
7. If a later deploy fails: read the issue the workflow opens and the job log's first red step. A token timeout in
   `azure/login` (as in #135) needs no fix: the next commit deploys, or **Actions → Deploy → Run workflow** once. A
   troubleshooting table for `docs/AUTO-DEPLOY.md` and a proposed `azure/login` retry wait in PR #150 (`needs-gustav`,
   because path-guard counts that file as deployment).
