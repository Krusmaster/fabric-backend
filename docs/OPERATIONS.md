# Operations: limits, Key Vault, usage statistics, health and alerts

Everything here is run by the maintainer in Azure Cloud Shell (Bash), from a checkout of this repository with
`deploy/krusgraph.json` in place. Nothing in this file has been run against Azure yet: the server code is
unit-tested, and the `az` parameters below were checked against the source of azure-cli (commit 003e032) and the
application-insights extension (commit 40c323a) on 26 October 2026, not against a live subscription. Run the steps
in order; each one can be run again.

The variables used below (adjust to `deploy/krusgraph.json`):

```bash
RG=rg-krusgraph; LOC=swedencentral; ENV=cae-krusgraph; APP=krusgraph; DOMAIN=krusgraph.com
LAW=log-krusgraph; APPI=appi-krusgraph; AG=ag-krusgraph; EMAIL=<the address that gets the alerts>
```

## 0. Deploy this version

The limits, `/health`, `/metrics`, the usage lines and the Key Vault support are in the server image:

```bash
git pull
bash deploy/krusgraph.sh --update
curl -s https://$DOMAIN/health                       # {"status":"ok"}
```

## 1. Fair-use limits (on by default)

Signed-in calls are limited per user (`oid`) and per organisation (`tid`); a refused call answers
`kind: rate_limited` with `retry_after` (seconds) and runs nothing. Only tool calls count; `initialize`,
`tools/list`, the site and the 401 sign-in challenge are never limited. Defaults, per replica:

| Scope | Default | Variable |
| --- | --- | --- |
| user | 30 calls per minute, 600 per hour | `KRUSGRAPH_RATE_USER="30/minute,600/hour"` |
| organisation | 120 calls per minute, 3000 per hour | `KRUSGRAPH_RATE_ORG="120/minute,3000/hour"` |
| all | on | `KRUSGRAPH_RATE_LIMITS=0` turns them off |

To change them (a malformed value stops the new revision at startup, and the old one keeps serving):

```bash
az containerapp update -n $APP -g $RG --set-env-vars KRUSGRAPH_RATE_USER="60/minute,1000/hour"
```

With `maxReplicas` 2 a user can briefly reach twice the limit; the counters are in memory and start empty on a new
revision.

## 2. The client secret in Azure Key Vault (optional)

Today `ENTRA_CLIENT_SECRET` is a secret of the container app. With Key Vault, the server reads it at the first
sign-in exchange with the container app's managed identity (the user-assigned identity the app already uses to pull
images), keeps it in memory for an hour, and reads it again at once if Entra says it is wrong or expired. Without
the setting, the server works exactly as before.

1. Pick a vault name (globally unique, 3–24 letters, digits and hyphens) and put it in `deploy/krusgraph.json`:
   `"key_vault": "kv-krusgraph-<something>"`.
2. Run the step. It creates the vault with RBAC if it does not exist (tagged `managed-by=krusgraph-deploy`), gives
   you "Key Vault Secrets Officer" and the app's identity "Key Vault Secrets User" on that vault only, asks for the
   client secret's **value** (hidden, as in the first deployment), stores it as `entra-client-secret`, and sets
   `ENTRA_CLIENT_SECRET_KEYVAULT_URI` and `AZURE_CLIENT_ID` on the app:

   ```bash
   bash deploy/krusgraph.sh --key-vault
   ```

3. Check it: in Claude, open the Krusgraph connector and run `list_workspaces`. A wrong setup answers
   `kind: server_config` with the reason ("needs the role 'Key Vault Secrets User'", "no such secret", …).
4. Only after step 3 works, remove the old copy from the container app (the server no longer reads it):

   ```bash
   az containerapp update -n $APP -g $RG --remove-env-vars ENTRA_CLIENT_SECRET
   az containerapp secret remove -n $APP -g $RG --secret-names entra-secret
   ```

Rotating later: create a new client secret in Entra, run `bash deploy/krusgraph.sh --key-vault` again with the new
value (a new version of the same Key Vault secret), and give Anthropic the new value for the directory listing; the
server picks it up within the hour, or at once when Entra rejects the old one. Delete the old secret in Entra last.
A full deployment run (`deploy/krusgraph.sh` without a flag) puts a container-app secret back; repeat step 4 after one.

## 3. Usage statistics

Each tool call writes one JSON line on stdout and nothing else:

```json
{"event":"krusgraph.tool_call","tool":"plan_backend","outcome":"ok","ms":2140}
{"event":"krusgraph.tool_call","tool":"create_views","outcome":"consent","ms":830,"dry_run":false}
```

`outcome` is `ok` or the error `kind`. With a salt configured (below) a line also carries `org`, a 16-character
salted SHA-256 hash of the tenant id. Never user ids, names, IP addresses, workspace/table/column names, queries or
results (`fabric_backend/usage.py`; a test checks it). `/privacy` describes exactly this, and changes with the
settings below.

The Container Apps environment was created with `--logs-destination none`, so today these lines are only in the live
console stream. To keep them in Log Analytics:

1. Tell the server first, so `/privacy` says the logs are kept and the per-request access line (which carries IP
   addresses) is switched off before anything is kept. In `deploy/krusgraph.json` set `"log_retention_days": 30`, then:

   ```bash
   bash deploy/krusgraph.sh --update
   curl -s https://$DOMAIN/privacy.md | grep -A2 "Logs"     # "... deleted after 30 days"
   ```

2. Create the workspace and point the environment at it:

   ```bash
   az monitor log-analytics workspace create -g $RG -n $LAW -l $LOC --retention-time 30 --tags managed-by=krusgraph-deploy
   LAW_ID=$(az monitor log-analytics workspace show -g $RG -n $LAW --query customerId -o tsv)
   LAW_KEY=$(az monitor log-analytics workspace get-shared-keys -g $RG -n $LAW --query primarySharedKey -o tsv)
   az containerapp env update -n $ENV -g $RG --logs-destination log-analytics --logs-workspace-id $LAW_ID --logs-workspace-key $LAW_KEY
   ```

3. Optional, to count organisations: a salt the server keeps as a container-app secret.

   ```bash
   az containerapp secret set -n $APP -g $RG --secrets usage-salt=$(openssl rand -hex 32)
   az containerapp update -n $APP -g $RG --set-env-vars KRUSGRAPH_USAGE_SALT=secretref:usage-salt
   ```

   Keep the salt where it is: with it, a known tenant id can be hashed and compared; without it, the hashes say nothing.

4. Read the numbers in the workspace (Logs, KQL):

   ```kusto
   ContainerAppConsoleLogs_CL
   | where ContainerAppName_s == "krusgraph" and Log_s startswith "{\"event\":\"krusgraph.tool_call\""
   | extend e = parse_json(Log_s)
   | summarize calls = count(), errors = countif(tostring(e.outcome) != "ok"),
               p50_ms = percentile(toint(e.ms), 50), p95_ms = percentile(toint(e.ms), 95)
       by tool = tostring(e.tool), day = bin(TimeGenerated, 1d)
   | order by day desc, calls desc
   ```

   Errors per kind: `| summarize count() by tool = tostring(e.tool), outcome = tostring(e.outcome)`. Organisations per
   week (with the salt): `| summarize dcount(tostring(e.org)) by bin(TimeGenerated, 7d)`. If the table in your
   workspace is `ContainerAppConsoleLogs` (without `_CL`), the column is `Log` instead of `Log_s`.

`/metrics` (optional) serves the totals since the replica started in the Prometheus text format. It is a 404 unless a
token of 32 characters or more is set, and then answers only a request that carries it:

```bash
az containerapp secret set -n $APP -g $RG --secrets metrics-token=$(openssl rand -hex 32)
az containerapp update -n $APP -g $RG --set-env-vars KRUSGRAPH_METRICS_TOKEN=secretref:metrics-token
TOKEN=$(az containerapp secret show -n $APP -g $RG --secret-name metrics-token --query value -o tsv)
curl -s -H "Authorization: Bearer $TOKEN" https://$DOMAIN/metrics | head -20
```

With two replicas each one has its own totals; the Log Analytics query above is the complete picture.

## 4. Health and alerts

`/health` answers `{"status":"ok"}` without sign-in and says nothing else about the server (no version, no build, no
sign-in mode). `/healthz` stays as it is for the container probes and the deploy script's build check.

Two alerts, both to one action group that e-mails `$EMAIL`:

```bash
APP_ID=$(az containerapp show -n $APP -g $RG --query id -o tsv)
az monitor action-group create -n $AG -g $RG --short-name krusgraph --action email operator $EMAIL
AG_ID=$(az monitor action-group show -n $AG -g $RG --query id -o tsv)
```

**The server answers 5xx.** First check that the metric and its dimension have the names used below (the list should
contain `statusCodeCategory`), then create the rule:

```bash
az monitor metrics list-definitions --resource $APP_ID --query "[?name.value=='Requests'].dimensions[].value" -o tsv
az monitor metrics alert create -n krusgraph-5xx -g $RG --scopes $APP_ID \
  --condition "total Requests >= 3 where statusCodeCategory includes 5xx" \
  --window-size 5m --evaluation-frequency 1m --severity 1 --action $AG_ID \
  --description "Krusgraph answered three or more 5xx responses within five minutes"
```

**The server does not answer.** An Application Insights standard availability test calls `https://$DOMAIN/health`
every five minutes from three European locations; the alert fires when fewer than half of the results in five
minutes succeeded (two of three locations failing):

```bash
az extension add --name application-insights --upgrade --yes
az monitor app-insights component create --app $APPI -g $RG -l $LOC --kind web --application-type web --workspace $LAW
APPI_ID=$(az monitor app-insights component show --app $APPI -g $RG --query id -o tsv)
az monitor app-insights web-test create -n krusgraph-health -g $RG -l $LOC \
  --web-test-kind standard --defined-web-test-name krusgraph-health --synthetic-monitor-id krusgraph-health \
  --enabled true --frequency 300 --timeout 30 --retry-enabled true \
  --request-url https://$DOMAIN/health --http-verb GET --expected-status-code 200 \
  --ssl-check true --ssl-lifetime-check 14 \
  --locations Id=emea-nl-ams-azr --locations Id=emea-gb-db3-azr --locations Id=emea-fr-pra-edge \
  --tags "hidden-link:$APPI_ID=Resource"
az monitor metrics alert create -n krusgraph-down -g $RG --scopes $APPI_ID \
  --condition "avg availabilityResults/availabilityPercentage < 50" \
  --window-size 5m --evaluation-frequency 1m --severity 0 --action $AG_ID \
  --description "Krusgraph's /health failed from at least two of three locations"
```

The location ids are West Europe, North Europe and France Central as the availability-test documentation names them;
the portal lists the current ones under the test's Locations. The component needs the Log Analytics workspace from
step 3.2. Cost note: a test every five minutes from three places means a request every couple of minutes, so the
app will rarely scale to zero (the same effect as `"min_replicas": 1`); `--frequency 900` makes that rarer, at the
price of the first request after a quiet spell waiting for a cold start.

To test the alerts without breaking anything: `az monitor metrics alert show -n krusgraph-5xx -g $RG` shows the rule;
the action group's "Test" button in the portal sends a sample e-mail.

## What the server reads from the environment (summary)

| Variable | Default | Meaning |
| --- | --- | --- |
| `KRUSGRAPH_RATE_LIMITS` | on | `0` turns the per-user and per-organisation limits off |
| `KRUSGRAPH_RATE_USER`, `KRUSGRAPH_RATE_ORG` | `30/minute,600/hour`, `120/minute,3000/hour` | the limits |
| `ENTRA_CLIENT_SECRET_KEYVAULT_URI`, `AZURE_CLIENT_ID` | unset | read the client secret from Key Vault with this identity |
| `KRUSGRAPH_USAGE_LOG` | on | `0` turns the usage line off |
| `KRUSGRAPH_USAGE_SALT` | unset | counts organisations as salted hashes |
| `KRUSGRAPH_METRICS_TOKEN` | unset (404) | enables `/metrics` for this bearer token (32+ characters) |
| `KRUSGRAPH_LOG_RETENTION_DAYS` | unset | tells `/privacy` that console logs are kept that many days |
| `KRUSGRAPH_ACCESS_LOG` | on | `0` drops uvicorn's per-request line with the client IP |
| `KRUSGRAPH_ENTITLEMENTS` | `0` | the dormant paid-plan check, see `docs/PRICING-NOTES.md` |
