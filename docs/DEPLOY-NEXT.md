# Next deploy — what changes (internal)

Written in round n127 on 6 November 2026 from the code on `main`. The last deploy served build `src-8d6c473bf26f45f9`
on 6 November 2026 and held `main` up to and including n111 (`78aabdf n111 releases Engine`). Everything below came
after it. Round n122 (quality suites) is included; n126 (column usage) was still running when this was written and is not
covered. Deploying stays with the maintainer (`bash deploy/krusgraph.sh --update`).

## What changes for users

New tool (38 → 39):

- `create_pipeline` (n120): creates or updates the silver, gold and check notebooks and a data pipeline that runs them
  in that order, stopping on a failed check. `dry_run=true` is the default; it never runs or schedules the pipeline.

New options on existing tools (all off or unchanged by default):

- `dbt_schema(project=true, check_rows=...)` (n114): a whole dbt project draft instead of the sources file.
- `dbt_schema(quality="gx"|"soda"|"both", profile=true)` (n122): Great Expectations and SodaCL check drafts, and a
  dbt-fabric `profiles.yml` with placeholders.
- `validate_plan` findings carry a `fix` (n115) in the evidence report's checklist, and the silver notebook draft can
  take the fix steps with every decision left as `None`.
- `export_item_definitions(items=["catalog"])` (n116): the description and tags per Fabric item and the REST calls for
  them. No tool sends them.
- `lineage(format="openlineage")` (n125): the graph as OpenLineage run events. Default `format="graph"` is unchanged.

Changed defaults: none for a user. The operator settings below are new and off by default, so the hosted service behaves
as today unless they are set.

New pages: the Concepts group of `/docs` (n86b, n117):

- `/docs/concepts/how-it-works`, `/docs/concepts/ontologies`, `/docs/concepts/data-products`,
  `/docs/concepts/how-they-connect`, `/docs/concepts/where-it-runs`, `/docs/concepts/vision`
- the same content in `/docs.md`, `/llms.txt`, `/llms-full.txt` and the sitemap; `/healthz` gains a `mode` field.

Internal docs only, not on the site: `docs/COMPARISON-MYRIADE.md` (n113), `docs/LANDSCAPE.md` (n118),
`docs/SEGMENTATION.md` (n121).

## Environment settings and their defaults

Read from the code (`os.environ.get(...)`). "On" means one of `1`, `true`, `yes`, `on` unless noted.

| Setting | Default | What it does | Set by `deploy/azure_containerapp.py` |
| --- | --- | --- | --- |
| `KRUSGRAPH_MCP_APPS` | off (only `"1"` turns it on) | n119/n124: the two MCP Apps cards for `validate_plan` and `review_plan` | no |
| `KRUSGRAPH_READ_ONLY` | off | n123: no tool that creates or changes something in Fabric is registered | no |
| `KRUSGRAPH_NO_ROW_VALUES` | off | n123: no `sample_rows`; row values removed from answers, names and counts kept | no |
| `KRUSGRAPH_ONTOLOGY_WRITE` | off | offers `create_ontology` | yes, when `ontology_write` is in the config |
| `KRUSGRAPH_BUILD` | unset | the build shown on `/healthz` | yes |
| `KRUSGRAPH_LOG_RETENTION_DAYS` | unset (logs not kept) | days of console logs, said on `/privacy` | yes, from `log_retention_days` |
| `KRUSGRAPH_ACCESS_LOG` | on (`"1"`) | access log lines | set to `0` when log retention is set |
| `KRUSGRAPH_RATE_LIMITS` | on (`"1"`) | rate limits per user and organisation | no |
| `KRUSGRAPH_RATE_USER` / `KRUSGRAPH_RATE_ORG` | `30/minute,600/hour` / `120/minute,3000/hour` | the limits | no |
| `KRUSGRAPH_USAGE_LOG` | on (`"1"`) | the anonymous usage record per tool call | no |
| `KRUSGRAPH_USAGE_SALT` | unset | per-organisation usage when set | no |
| `KRUSGRAPH_METRICS_TOKEN` | unset | `/metrics` is a 404 unless set (32 characters or more, sent as a bearer token) | no |
| `KRUSGRAPH_DEBUG_ERRORS` | unset | adds the exception type as `debug` to error answers | no |
| `KRUSGRAPH_PREVIEW` | off (only `"1"`) | the sales-planning example at `/example/sales-planning` | no |
| `KRUSGRAPH_PLATFORM` | unset | `databricks` switches the local server to Databricks | no (local server) |
| `KRUSGRAPH_ENTITLEMENTS` | `0` | tenant entitlements; with `KRUSGRAPH_ENTITLEMENTS_SOURCE` (`env`), `KRUSGRAPH_ENTITLED_TENANTS` (`{}`), `KRUSGRAPH_ENTITLEMENTS_TABLE`, `KRUSGRAPH_UPGRADE_URL` | no |
| `KRUSGRAPH_CLIENT_REGISTRATION` / `_DCR` | off | client registration for MCP clients other than Claude | no |
| `KRUSGRAPH_REGISTRATION_STORE`, `_KEY`, `_KEY_KEYVAULT_URI`, `_CLIENT_DOMAINS` | unset | where and how registrations are kept | no |
| `KRUSGRAPH_REGISTRATION_RATE_IP` / `_CLIENT` / `_REGISTER` | `60/minute,600/hour` / `300/minute,6000/hour` / `10/hour` | registration rate limits | no |

The deploy script does not set the three new settings, so after `--update` they are all off unless set on the
container app by hand.

## Permissions the hosted app does not have today

From `fabric_backend/tool_status.py` (`available = OPERATOR`, "Available when enabled by the operator"):

- `create_semantic_model`, `create_ontology`, `create_data_agent` (creating) and `compare_semantic_model` (reading).
- `create_drift_monitor` is hosted, but its schedule needs `DataPipeline.Execute.All`, which the app does not have.
- `create_pipeline` (new) is hosted: it needs `Notebook.ReadWrite.All` and `DataPipeline.ReadWrite.All` (or
  `Item.ReadWrite.All`), which tool_status says the hosted app has.
- The catalog draft (n116) would need `Tag.Read.All` to be sent, but no tool sends it.

Note: the `/llms.txt` text still says "Creating semantic models, ontologies, data agents, notebooks and pipelines needs
permissions the hosted app does not ask for today", while tool_status lists the notebook and pipeline tools as hosted.
Worth a Website round; not changed here.

## Checklist after deploy

1. `/healthz` answers 200 with the new build and `"mode": "default"`.
2. These answer 200: `/`, `/docs`, `/docs.md`, `/llms.txt`, `/llms-full.txt`, `/check`, `/it`, `/privacy`, and the six
   Concepts pages listed above.
3. `/llms.txt` says "Thirty-nine tools" and names `create_pipeline`.
4. From Claude, against the demo workspace with synthetic data, one call per new option:
   - `create_pipeline` with the default `dry_run=true`: definitions and REST calls, no write.
   - `dbt_schema` with `project=true`: the file list of the dbt project.
   - `dbt_schema` with `quality="both"` and `profile=true`: the GX suites, the SodaCL checks and `profiles.yml`.
   - `validate_plan`: the checklist rows carry `fix`.
   - `export_item_definitions` with `items=["catalog"]`: descriptions, tags and calls, no files.
   - `lineage` with `format="openlineage"`: run events, no row values.
5. Without setting `KRUSGRAPH_MCP_APPS`, `validate_plan` and `review_plan` answer as before (no card).
6. Record what ran, where and when in `docs/LIVE-TEST.md`.
