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
