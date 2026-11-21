> 21 November 2026, round BL27 (sprint item BL27, backlog B-26). Code: `fabric_backend/schedules.py`.
> Tests: `tests/test_bl27_schedules.py`.

# Schedules drafted: the pipeline's daily run and the model refresh after it

A model that is not refreshed after the load shows yesterday's numbers as today's. `schedules.draft` writes down, as a
dry run, how a Krusgraph data product would be kept current: when the pipeline runs, and when the semantic model is
refreshed. It sends nothing. **Create does not use it yet** (see "What wiring Create needs" below).

## What it drafts

```python
from fabric_backend import schedules
d = schedules.draft(outputs, timezone="UTC", time="02:00")   # outputs: a Krusgraph Model's outputs.json
schedules.preview(d)
# ["Pipeline shop_pipeline runs daily at 02:00 UTC.",
#  "Model shop_model refreshes after it, once the check has passed."]
```

| Data product has | Pipeline | Semantic model refresh | Why |
| --- | --- | --- | --- |
| a pipeline and a model | daily at `time`, one Fabric Job Scheduler schedule on the pipeline | the pipeline's last step, after the check | a model on its own clock can refresh before the load ends, or after a load the check failed |
| a model, no pipeline | none | daily at `time`, a Power BI refresh schedule on the model | nothing to follow; pick a time after the tables' own load ends |
| neither | none | none | nothing to schedule yet |

Each schedule in the draft carries the method, URL and request body, the delegated scopes per call, the Learn pages it
rests on, and the reason for the choice. Items not created yet get placeholders (`<workspace id>`, `<id of the
pipeline …>`). The start date is tomorrow, because Fabric starts a run at once when the start time is in the past; the
end date is ten years on, as `pipeline_jobs.py` sets it, since Fabric requires one.

`timezone` is one of the IANA names `pipeline_jobs.WINDOWS_ZONES` maps to Fabric's Windows time zone ids (for example
`UTC`, `Europe/Stockholm`); `time` is `hh:mm` on a 24-hour clock. Anything else is refused with a message that says
which and why.

## The calls and their scopes

| Call | Body | Delegated scopes (all groups, any one in a group) | Krusgraph's app today |
| --- | --- | --- | --- |
| Create Item Schedule on the pipeline: `POST /v1/workspaces/{ws}/dataPipelines/{id}/jobs/execute/schedules` | `{enabled, configuration: {startDateTime, endDateTime, localTimeZoneId, type: "Daily", times}}` | `DataPipeline.Execute.All` or `Item.Execute.All`; and `DataPipeline.ReadWrite.All` or `Item.ReadWrite.All` | `DataPipeline.ReadWrite.All` and `Item.ReadWrite.All` granted; `DataPipeline.Execute.All` opt-in (off unless the operator turns it on); `Item.Execute.All` not asked for today |
| Add the refresh step to the pipeline: `updateDefinition` | the pipeline definition with one more activity | `DataPipeline.ReadWrite.All` or `Item.ReadWrite.All` | granted |
| Update Refresh Schedule In Group (model alone): `PATCH https://api.powerbi.com/v1.0/myorg/groups/{ws}/datasets/{id}/refreshSchedule` | `{"value": {days, times, enabled, localTimeZoneId, notifyOption}}` | `Dataset.ReadWrite.All`; the signed-in person must own the model | not asked for today |

The "Krusgraph's app today" column is computed from `fabric_backend/access.py` when the draft is made, so it follows
any later change there. The refresh step itself runs with the Power BI connection's credentials, not with Krusgraph's
token.

## Sources

- Microsoft Learn, Fabric REST API, Core / Job Scheduler, "Items - Create Item Schedule", page updated 10 November
  2026, read 21 November 2026: the route, the Daily configuration (its example "create item schedule with execution
  data" is the test fixture), and the generic route's scopes "Item.Execute.All and Item.ReadWrite.All".
- microsoft/fabric-rest-api-specs `dataPipeline/swagger.json` (ScheduleExecute), read 11 November 2026 and cited in
  `pipeline_jobs.py`: the dataPipelines route with job type `execute` and the narrower `DataPipeline.*` scopes.
- Microsoft Learn, Data Factory, "Semantic model refresh activity in Data Factory for Microsoft Fabric", ms.date
  7 April 2026, read 21 November 2026: the activity is set by a Power BI connection, the workspace and the dataset;
  "Wait on completion" is on by default; a full refresh by default; it works only with semantic models you create
  yourself; it needs a Premium, Premium Per User or Embedded capacity.
- Microsoft Learn, Power BI REST API, "Datasets - Update Refresh Schedule In Group", page updated 5 February 2025, read
  21 November 2026: the route, the body (its example "Change the days and times of a refresh schedule" is the test
  fixture), at least one day, `Dataset.ReadWrite.All`, the owner requirement, and `notifyOption` (`NoNotification` or
  `MailOnFailure`; service principals only `NoNotification`).

## Open points

- **The refresh activity has no JSON here.** The Learn page shows the activity in the pipeline editor only. Krusgraph
  does not guess its JSON, so `draft` describes the step (connection, workspace, dataset, wait on completion) and
  leaves `json` empty. Until Microsoft documents the shape, the step is added in Fabric's pipeline editor, after the
  check activity.
- **The Power BI connection** the step uses is made by the workspace owner in Fabric; Krusgraph does not create
  connections.
- **Direct Lake.** `semantic_model.py` drafts Direct Lake models. Whether such a model also picks up new data without a
  refresh depends on a model setting this draft does not read; the refresh step makes the moment explicit either way.
- Not verified against Fabric: none of these bodies has been sent to a workspace.

## What wiring Create needs

Nothing calls `schedules.draft` today; `create_pipeline`'s existing Schedule choice (`pipeline_jobs.py`, round n185) is
unchanged. To use the draft, a later round (outside the files this round may touch) would:

1. In SM2's closing step, call `schedules.preview(schedules.draft(outputs, ...))` and show the sentences next to
   "Schedule" (`start_flow.py`, `coach.py`; the chain's files, not this round's).
2. On the person's confirmation, send the pipeline body through `pipeline_jobs.ensure_schedule`, which already lists
   the pipeline's schedules and updates only the one Krusgraph made; it needs `DataPipeline.Execute.All` (opt-in).
3. Add the refresh step to the pipeline definition once its JSON is documented (`pipeline.pipeline_content`), or tell
   the person to add it in the editor, with the connection, workspace and model named.
4. For a model without a pipeline, send the Power BI body; this needs `Dataset.ReadWrite.All` asked for in
   `access.py` and the Entra app, which is a permissions change for the maintainer to decide.
