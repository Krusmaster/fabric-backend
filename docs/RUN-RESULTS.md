# Run results: what a pipeline or notebook run did, read by the agent

Round n143, 7 November 2026. `lineage` with `runs=<pipeline or notebook>` reads the latest runs of a data pipeline or a
notebook in the workspace: each run's status and times, each activity's status, the error text as Fabric returns it, a
category and a suggested next step from a small catalog of Spark and Fabric errors (marked as a heuristic), and whether
Krusgraph created the item. It replaces copying an error from the Fabric portal by hand, as was needed after the first
run of `pipeline_shop` that day. It starts, cancels, schedules and fixes nothing. The code is
`fabric_backend/run_results.py`; the tests, with Fabric's REST API as a test double, are `tests/test_n143_run_results.py`.

**Status:** unit-tested only; not yet run against a live workspace.

## What it calls

| Call | Source | Delegated scope | Hosted app has it |
| --- | --- | --- | --- |
| `GET /v1/workspaces/{ws}/items/{id}/jobs/instances` (`JobScheduler_ListItemJobInstances`), for the item and for each notebook its pipeline runs | fabric-rest-api-specs `6f817cb`, `platform/swagger.json`; the same call in microsoft/mcp `ee11217`, `FabricCoreService.JobList.cs` | `Item.Read.All` or `Item.ReadWrite.All`, or `DataPipeline.Read.All` / `Notebook.Read.All` | yes (`Item.Read.All`, `Item.ReadWrite.All`; `docs/SCOPES.md`) |
| `POST /v1/workspaces/{ws}/dataPipelines/{id}/getDefinition`, for a pipeline's activities | the read `lineage` already makes for other items | `DataPipeline.ReadWrite.All` or `Item.ReadWrite.All` | yes (`Item.ReadWrite.All`, since 28 October 2026) |

Neither source documents an endpoint for the activity runs of one pipeline run, so none is called. A Notebook
activity's status is that notebook's own run that started inside the pipeline run's time window.

## The catalog

Searched in this order against Fabric's error message (then its error code); the first match wins.

| Category | Matches, for example | Suggested next step |
| --- | --- | --- |
| `import_error` | `ImportError`, `ModuleNotFoundError`, `No module named`, `cannot import name` | Compare the notebook's imports with its environment; create a Krusgraph notebook again with the current release, then run again in Fabric |
| `table_not_found` | `TABLE_OR_VIEW_NOT_FOUND`, `Table or view not found`, `Invalid object name` | Check the default lakehouse and schema and the order of the steps; `list_tables`, `plan_drift` |
| `permission_denied` | `403 … Forbidden`, `PermissionDenied`, `not authorized`, `does not have permission` | A person gives the identity the run used the role or permission it lacks |
| `capacity_paused_or_throttled` | `CapacityNotActive`, `TooManyRequestsForCapacity`, `Capacity level limit exceeded` | A person resumes the capacity or waits for its load to fall, then runs again |
| `timeout` | `timed out`, `timeout`, `exceeded the maximum execution time` | Look at earlier durations and data volume; a person decides about the activity's timeout |
| `unknown` | anything else | Read the whole error in the monitoring hub (the request id is given) |

## Know the limits

| Area | What it is |
| --- | --- |
| Category and next step | A heuristic: the first catalog entry whose pattern occurs in the error text. Several causes can share one text; an error no entry matches is `unknown`. |
| Per-activity status | A heuristic: each Notebook activity is matched to the notebook's own run that started in the pipeline run's time window (± 60 s). Two pipeline runs at once, or the notebook run by hand meanwhile, can match the wrong run. Activities after a failed one are `NotRun`, read from the definition's `dependsOn`. |
| Which runs | Fabric's job list: the latest five runs by start time, of the about 100 completed ones Fabric keeps. |
| Error text | As Fabric returns it: `failureReason`'s `message`, `errorCode`, `requestId`; cut only past 4 000 characters, and then marked. No row values are read. |
| Krusgraph-created | The item's description names Krusgraph (the create tools write it); an item whose description was changed is not recognised. |
| Fixing | Needs a person: granting a role, resuming a capacity, changing a timeout, running again are done in Fabric. |
| Starting, cancelling, scheduling, changing an item | Never: only the GET above and `getDefinition`. |

## Borrowed

The catalog's layout (an ordered list of pattern, category and hint, searched case-insensitively, first match wins), the
loop that applies it and two pattern fragments (capacity limit exceeded, timed out) come from `error_catalog.py` and
`diagnostics.py` of [FreelexHo/power-bi-mcp](https://github.com/FreelexHo/power-bi-mcp) at commit `8d2e873` (MIT,
"Copyright (c) 2026 Freelex Ho"; the notice is at the top of `run_results.py` and in `THIRD_PARTY_NOTICES.md`), as is
the style of the limits table above. The call shapes were read, not copied, from Microsoft's sources named above.
