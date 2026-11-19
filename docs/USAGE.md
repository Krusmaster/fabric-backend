# Usage – how Krusgraph is used

Ready-made KQL queries for the Log Analytics workspace the console logs go to once statistics are switched on
(`docs/OPERATIONS.md`, section 3). Run them in the Azure portal → the workspace → **Logs**, or all at once:

```bash
bash deploy/usage-report.sh
```

The script (`deploy/usage_report.py`) finds the workspace named in `log_analytics_workspace` in `deploy/krusgraph.json`,
runs the queries below with `az monitor log-analytics query` for the last 7 and 30 days, and prints a short summary (in
Swedish). It changes nothing. `--workspace-id <customerId>` and `--app <name>` override the configuration;
`--print-queries` only prints the queries. The queries here and in the script are the same (a test keeps them in step);
here they are shown for 30 days and the app `krusgraph`. The script's formatting is unit-tested with made-up answers.

`az monitor log-analytics query` needs the Azure CLI extension `log-analytics` (only a preview version exists). The
script adds it first with `az extension add --name log-analytics --yes --only-show-errors`, so az never stops to ask, and
every az call has a timeout of 180 seconds with a message in Swedish. By hand: `az extension add --name log-analytics --yes`.

Every column alias and every column in `order by` is quoted as `["..."]`: `kind`, `views` and `step` are reserved words in
KQL, and unquoted they gave SYN0002 "Query could not be parsed". The errors column is called `error_kind`. A test fails
if an alias or an `order by` column is left unquoted. These queries ran against the real workspace on 29 October 2026,
in the maintainer's Cloud Shell, with the same local fix (quoted aliases, `error_kind`); the committed script with the
fix (round n42) has not run against Azure until the maintainer runs it again.

## What the lines contain

| Event | Fields | Written by |
| --- | --- | --- |
| `krusgraph.tool_call` | `tool`, `outcome` (`ok` or the error's `kind`), `ms`, `dry_run` for the creating tools, `org` (16 characters of SHA-256 of salt + tenant id, only with `KRUSGRAPH_USAGE_SALT`) | `fabric_backend/usage.py`, one per tool call |
| `krusgraph.page_view` | `path`: one of `/`, `/check`, `/start`, `/partners` | the server, when it serves the page as HTML |
| `krusgraph.check` | `step`: `loaded` (the engine started in the visitor's browser) or `done` (a check finished) | `/check`, as an image request to `/check/event?e=…` |

Never content, files, file names, workspace, table or column names, queries, results, user ids, e-mail or IP
addresses. Organisations are counted only as the salted hash; without the salt there is no `org` and that count is 0.

Reading the numbers:

- Pages are served with `Cache-Control: max-age=300`: a visitor who reloads within five minutes is often not counted again.
- Search engines and other robots count as page views; the line has no user agent to tell them apart.
- The `/check` events need the visitor's browser to load the image; a blocker can stop them.
- If the table in your workspace is `ContainerAppConsoleLogs` (without `_CL`), the columns are `Log` and `ContainerAppName`.

## Calls per day (and how many ended in an error)

```kusto
ContainerAppConsoleLogs_CL
| where TimeGenerated > ago(30d) and ContainerAppName_s == "krusgraph" and Log_s startswith "{\"event\":\"krusgraph."
| extend e = parse_json(Log_s) | extend ev = tostring(e.event)
| where ev == "krusgraph.tool_call"
| summarize ["calls"] = count(), ["errors"] = countif(tostring(e.outcome) != "ok") by ["day"] = startofday(TimeGenerated)
| order by ["day"] asc
```

## Per tool: calls, errors, median and 95th percentile

```kusto
ContainerAppConsoleLogs_CL
| where TimeGenerated > ago(30d) and ContainerAppName_s == "krusgraph" and Log_s startswith "{\"event\":\"krusgraph."
| extend e = parse_json(Log_s) | extend ev = tostring(e.event)
| where ev == "krusgraph.tool_call"
| summarize ["calls"] = count(), ["errors"] = countif(tostring(e.outcome) != "ok"), ["p50_ms"] = percentile(toint(e.ms), 50), ["p95_ms"] = percentile(toint(e.ms), 95) by ["tool"] = tostring(e.tool)
| order by ["calls"] desc
```

## Errors per `kind` (the column is `error_kind`)

```kusto
ContainerAppConsoleLogs_CL
| where TimeGenerated > ago(30d) and ContainerAppName_s == "krusgraph" and Log_s startswith "{\"event\":\"krusgraph."
| extend e = parse_json(Log_s) | extend ev = tostring(e.event)
| where ev == "krusgraph.tool_call" and tostring(e.outcome) != "ok"
| summarize ["calls"] = count() by ["error_kind"] = tostring(e.outcome)
| order by ["calls"] desc
```

## Totals: response time, distinct organisations (salted hash), and the share ending in consent, no_access, rate_limited

```kusto
ContainerAppConsoleLogs_CL
| where TimeGenerated > ago(30d) and ContainerAppName_s == "krusgraph" and Log_s startswith "{\"event\":\"krusgraph."
| extend e = parse_json(Log_s) | extend ev = tostring(e.event)
| where ev == "krusgraph.tool_call"
| summarize ["calls"] = count(), ["p50_ms"] = percentile(toint(e.ms), 50), ["p95_ms"] = percentile(toint(e.ms), 95), ["orgs"] = dcountif(tostring(e.org), isnotempty(tostring(e.org))), ["consent"] = countif(tostring(e.outcome) == "consent"), ["no_access"] = countif(tostring(e.outcome) == "no_access"), ["rate_limited"] = countif(tostring(e.outcome) == "rate_limited")
```

## Page views for /, /check, /start, /partners

```kusto
ContainerAppConsoleLogs_CL
| where TimeGenerated > ago(30d) and ContainerAppName_s == "krusgraph" and Log_s startswith "{\"event\":\"krusgraph."
| extend e = parse_json(Log_s) | extend ev = tostring(e.event)
| where ev == "krusgraph.page_view"
| summarize ["views"] = count() by ["path"] = tostring(e.path)
| order by ["views"] desc
```

## /check: engine loaded and check done

```kusto
ContainerAppConsoleLogs_CL
| where TimeGenerated > ago(30d) and ContainerAppName_s == "krusgraph" and Log_s startswith "{\"event\":\"krusgraph."
| extend e = parse_json(Log_s) | extend ev = tostring(e.event)
| where ev == "krusgraph.check"
| summarize ["events"] = count() by ["step"] = tostring(e.step)
```

## Daily counts and /metrics

Since round UM1 (18 November 2026) the server also keeps anonymous counts per UTC day (`fabric_backend/usage_metrics.py`),
so usage can be read without Log Analytics. They are shown at `/metrics`, for the operator only.

**What is counted, per UTC day.** Distinct organisations (the Entra tenant id as a salted hash: HMAC-SHA256 with
`KRUSGRAPH_USAGE_SALT`, 16 hex characters, never the id); distinct signed-in users (a salted hash of tenant and object
id, used only to count them); MCP sessions (the `initialize` requests to `/mcp`); the MCP client's name if the client
sends one in `initialize` (`clientInfo.name`, such as `claude-ai` or `cursor`; anything else than a short plain name is
counted as `(other)`); tool calls per tool name; errors per tool and error kind; Fabric workload API calls per route and
how many answered with an error. Without `KRUSGRAPH_USAGE_SALT` no hash is made and organisations and users are not
counted.

**What is never kept.** User names, e-mail addresses, IP addresses, user agents, workspace, item, table or column names,
row values, prompts, tool arguments or tool answers. The tool's answer is read only for its error kind; the MCP request
body only for `method` and `clientInfo.name`.

**Where and how long.** In the Azure table the client registration already uses (`KRUSGRAPH_REGISTRATION_STORE`, the
container app's managed identity), under its own PartitionKey `usage`: no new Azure resource or role. Each replica
writes one row per day with its own totals, at most once a minute, and the page adds the rows up, so restarts and a
second replica are covered. Without that table the counts are in memory only and the page says "since the last
restart". The salted hashes are kept 35 days (enough for a 30-day distinct count); then the day keeps only the numbers.
Daily numbers are deleted after 400 days.

**The page.** `GET /metrics` with `Authorization: Bearer <KRUSGRAPH_METRICS_TOKEN>`: HTML for a browser, JSON with
`?format=json`, and for any other client usage.py's Prometheus text as before (`?format=prometheus` forces it). In a
browser without the header, `/metrics` shows a form; the token typed there is sent in the POST body, never in the
address. 404 when `KRUSGRAPH_METRICS_TOKEN` is unset (or shorter than 32 characters), 401 for a wrong token; the
comparison is constant-time. The page loads no script and nothing from elsewhere, and no page of the site links to it.

**Switching it off.** `KRUSGRAPH_METRICS=off` counts nothing and writes nothing (the per-call console line
`krusgraph.tool_call` and the Prometheus totals stop too); the page still shows what was stored before.

## Weekly digest to the founder's webhook

Since round UM2 (19 November 2026) the server can post a short weekly summary of the same daily counts to the founder's
Teams channel, so the numbers arrive without opening `/metrics` and without the metrics token ever leaving Azure
(`fabric_backend/usage_digest.py`).

**What it says.** The last complete ISO week (Monday to Sunday, UTC) next to the week before it: organisations, users,
MCP sessions, tool calls, tool errors and workload API calls; the 5 most used tools, the 3 most common error kinds, the
MCP client names, and the line "Se /metrics för detaljer: https://krusgraph.com/metrics" (the address only, never the
token). It is built from the stored daily rows `/metrics` reads, so the two always agree. Counts and the names the
counters already hold (tool names, error kinds, client names) only: no hash, tenant or object id, name, e-mail, IP
address, workspace, table or column name. A test checks the payload for the token, the salt, the hashes, the ids and
the webhook address.

**When.** Once per ISO week: Monday 07:00 UTC, or the first check after that (each replica checks every 15 minutes, in
a background thread of the running server; no new Azure resource, no Azure Functions, no new role). A server that is
down the whole week does not send the old week late into the next one.

**Exactly once.** Before sending, a replica inserts the row `digest-<YYYY>-W<ww>` (the week and the time, nothing
else) under PartitionKey `usage` in the same table as the daily counts, with Insert Entity, which the Table service
refuses when the row already exists. Only the replica whose insert made the row sends; the other replica and a later
restart see the row and do nothing. No table (`KRUSGRAPH_REGISTRATION_STORE` unset or `memory`), a failed insert or
rows that cannot be read: nothing is sent. `/metrics` and the retention sweep leave these rows alone (one small row a
week).

**Sending.** Through the same sender the trial's founder notices use (`billing.post_founder_card`): one POST of an
Adaptive Card message with a 10-second timeout, one retry 30 seconds later at most, and then nothing more that week.
A failure is logged as `{"krusgraph": "usage_digest", "event": "send_failed", ...}` with the error type only, never the
address (the address carries its own signature).

**Switches.** `KRUSGRAPH_USAGE_DIGEST=off` turns the digest off; `KRUSGRAPH_METRICS=off` turns it off too. Without
`KRUSGRAPH_FOUNDER_WEBHOOK_URL` nothing runs and the console says so once (`"event": "no_webhook"`). On 19 November
2026 the hosted app has no `founder-webhook` secret yet, so the digest is off there until the steps below are done.

**Setting up the webhook (Teams Workflows, done once by the maintainer).**

1. In Teams, open the channel the digest should go to, choose **⋯** (more options) next to the channel name, then
   **Workflows**. Pick the template **Post to a channel when a webhook request is received**, give it a name (for
   example "Krusgraph"), check that the team and channel are right and choose **Add workflow**. Copy the address
   Teams shows (the workflow's HTTP POST URL). Treat it like a password: anyone who has it can post to the channel.
2. In Azure Cloud Shell (Bash), with `RG` and `APP` as in `docs/OPERATIONS.md` section 3:

   ```bash
   read -rsp "Webhookadressen från Teams-arbetsflödet (döljs): " FW; echo
   # optional: one test card without any data, to see that the channel receives it
   curl -sS -o /dev/null -w "%{http_code}\n" -X POST -H "Content-Type: application/json" "$FW" -d '{"type":"message","attachments":[{"contentType":"application/vnd.microsoft.card.adaptive","contentUrl":null,"content":{"$schema":"http://adaptivecards.io/schemas/adaptive-card.json","type":"AdaptiveCard","version":"1.4","body":[{"type":"TextBlock","text":"Krusgraph: test av veckosammanfattningen","wrap":true}]}}]}'
   az containerapp secret set -n $APP -g $RG --secrets founder-webhook="$FW" --output none; unset FW
   az containerapp update -n $APP -g $RG --set-env-vars KRUSGRAPH_FOUNDER_WEBHOOK_URL=secretref:founder-webhook --output none
   ```

   The test should print a 2xx code (the Workflows trigger usually answers `202` and posts a moment later) and the card
   should appear in the channel. The update starts a new revision; the first digest arrives on the next Monday at 07:00 UTC (08:00 Swedish winter time) or, if
   that has passed this week and no replica has sent this week's yet, within about 15 minutes.
3. To stop it: `az containerapp update -n $APP -g $RG --set-env-vars KRUSGRAPH_USAGE_DIGEST=off`, or turn the workflow
   off in Teams.

The same secret also carries the trial's founder notices (`docs/BILLING-MODEL.md`) when `KRUSGRAPH_TRIAL=1`.

**What is untested.** The card was checked in tests against the envelope the trial notices already send and against
the format Microsoft documents for the Workflows template (a `message` with one
`application/vnd.microsoft.card.adaptive` attachment; Adaptive Card 1.4, which Teams renders). It has not been posted to
a real Teams channel: no Teams, Azure or krusgraph.com call was made from the round's sandbox. The step 2 test card is
the first real check. The exactly-once insert was tested against a faked Table service (201/204 for the first insert,
409 for the second), not against the real table.

**A full deploy run.** `bash deploy/krusgraph.sh` without `--update` replaces the container app's secret list with
`entra-secret` alone, which removes `usage-salt`, `metrics-token` and `founder-webhook` and the variables that point at
them. The run now says so and prints the commands that store them again; `--update` points `KRUSGRAPH_USAGE_SALT`,
`KRUSGRAPH_METRICS_TOKEN` and `KRUSGRAPH_FOUNDER_WEBHOOK_URL` at their secrets whenever the app has them. The automatic
deploy (`--from-azure --update`) never changes them.
