# Operations: limits, Key Vault, usage statistics, health and alerts

Everything here is run by the maintainer in Azure Cloud Shell (Bash), from a checkout of this repository with
`deploy/krusgraph.json` in place (or built from the running app with `--from-azure`, section 0). Nothing in this file has been run against Azure yet: the server code is
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

From a temporary Cloud Shell (no storage, so no `deploy/krusgraph.json`, and a default subscription that is not the
one Krusgraph runs in), paste this block instead:

```bash
git clone https://github.com/Krusmaster/fabric-backend && cd fabric-backend &&
bash deploy/krusgraph.sh --from-azure --update &&
curl -s https://krusgraph.com/health
```

`--from-azure` reads the configuration from the container app that already runs (the one with `krusgraph` in its
name), shows it and saves it as `deploy/krusgraph.json` when that file is missing (an existing one is replaced only
with `--overwrite-config`). With it, `--update` changes the image and `KRUSGRAPH_BUILD` and nothing else: the other
environment variables and `min_replicas` stay as the app has them, and no secret is read, written or shown. If the app
is in another subscription, the script searches the others, stops without changing anything and prints
`az account set --subscription <id>`: run that line as printed, then, still in `fabric-backend`,
`bash deploy/krusgraph.sh --from-azure --update && curl -s https://krusgraph.com/health`. An app without `krusgraph`
in its name is given with `--app <name> --resource-group <group>`. Unit-tested against a faked `az`
(`tests/test_deploy_from_azure.py`), not yet run against Azure.

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

## 5. More MCP clients: Claude Code, VS Code (GitHub Copilot agent mode) and Cursor (prepared, not switched on)

Today the hosted service is used from Claude, and the site says so until the clients below have been tried. Each of
them signs in to a remote MCP server itself, with its own redirect address; Entra has no dynamic client registration,
so each one uses this app's client id as a **public client** (PKCE, no secret). Their addresses go under the app's
*Mobile and desktop applications* platform (`publicClient.redirectUris`), next to the unchanged *Web* list that holds
Claude's `https://claude.ai/api/mcp/auth_callback`. No secret is handed to anyone, and "Allow public client flows"
(`isFallbackPublicClient`) stays off: authorization code with PKCE does not need it (entra-docs
`msal-client-applications.md`), and the server's own on-behalf-of call sends the secret.

| Client | Redirect address it sends | Registered as | Client id given in | Source (read 26 October 2026) |
| --- | --- | --- | --- | --- |
| Claude Code | `http://localhost:<port>/callback`, a random port unless `--callback-port` (or `oauth.callbackPort`) fixes it | `http://localhost/callback` | `claude mcp add --transport http --client-id <APP_ID> --callback-port 8080 krusgraph https://krusgraph.com/mcp` | code.claude.com/docs/en/mcp ("Use a fixed OAuth callback port", "Use pre-configured OAuth credentials") |
| VS Code with GitHub Copilot | VS Code's built-in Microsoft sign-in serves `login.microsoftonline.com` servers (MSAL); with `oauth.clientId` set, MSAL's loopback `http://localhost:<random port>` | `http://localhost` | `.vscode/mcp.json`: `{"servers": {"krusgraph": {"type": "http", "url": "https://krusgraph.com/mcp", "oauth": {"clientId": "<APP_ID>"}}}}` (VS Code 1.123 or later) | microsoft/vscode a0e17bd `extensions/microsoft-authentication/src/extension.ts` and `src/common/scopeData.ts`; microsoft/vscode-docs release notes v1_123; MSAL Node `LoopbackClient.ts` |
| Cursor (desktop) | `http://localhost:8787/callback`; older builds `cursor://anysphere.cursor-mcp/oauth/callback` | `http://localhost/callback` (optionally the `cursor://` one too) | `~/.cursor/mcp.json`: `{"mcpServers": {"krusgraph": {"url": "https://krusgraph.com/mcp", "auth": {"CLIENT_ID": "<APP_ID>"}}}}` | Cursor's MCP docs and forum, **through search summaries only**: cursor.com was not reachable from the build environment, so this row is unverified |

On Entra the port of an `http://localhost` redirect address is ignored, so `http://localhost/callback` covers Claude
Code's port and Cursor's 8787 (entra-docs `identity-platform/reply-url.md`, 54c82d4: "Do not register multiple
localhost redirect URIs where only the port differs"; `http` is allowed only for localhost; `[::1]` is not supported).
VS Code on Windows may use the account broker (WAM), which needs `ms-appx-web://Microsoft.AAD.BrokerPlugin/<APP_ID>`;
add it, or set `"microsoft-authentication.implementation": "msal-no-broker"` in VS Code. Without `oauth.clientId`,
VS Code signs in with its own client id instead, which needs consent for that client to this app's
`user_impersonation` (or pre-authorising it under *Expose an API*); the client id route avoids that.

The commands, printed (never run) by the deploy helper:

```bash
bash deploy/krusgraph.sh --client-redirects
```

which prints, for the app in `deploy/krusgraph.json`:

```bash
APP_ID="<client id>"
# what the app has today (changes nothing)
az ad app show --id "$APP_ID" --query "{web:web.redirectUris, publicClient:publicClient.redirectUris, fallback:isFallbackPublicClient}"
# --public-client-redirect-uris replaces the whole list, so the existing one is read first and merged;
# --web-redirect-uris (Claude's callback) is not touched
NEW=("http://localhost" "http://localhost/callback")
# if the read fails (an expired sign-in, throttling), nothing is changed: an empty read would replace the list
if CUR=$(az ad app show --id "$APP_ID" --query "publicClient.redirectUris[]" -o tsv); then
  mapfile -t ALL < <({ printf '%s\n' "$CUR"; printf '%s\n' "${NEW[@]}"; } | grep -v '^$' | sort -u)
  az ad app update --id "$APP_ID" --public-client-redirect-uris "${ALL[@]}"
else
  echo "Could not read the app's list; nothing changed."
fi
# check: the web list unchanged, the new addresses under publicClient, fallback still false or null
az ad app show --id "$APP_ID" --query "{web:web.redirectUris, publicClient:publicClient.redirectUris, fallback:isFallbackPublicClient}"
```

`az ad app update` sends the lists as a PATCH, which replaces a collection as a whole (Azure/azure-cli 003e032,
`role/_params.py` and `_msgrpah/_graph_objects.py`; microsoft-graph-docs `application-update.md`), hence the merge.

**Trying each client** (fill in the result in `docs/LIVE-TEST.md`, section *Clients*):

1. **Claude Code:** the `claude mcp add` line above, then `claude mcp login krusgraph` (or `/mcp` in a session); sign in
   with the work account; ask *"Which Fabric workspaces can I see?"*. `claude mcp get krusgraph` shows the state.
2. **VS Code:** add the `mcp.json` entry, run *MCP: List Servers* → krusgraph → *Start*, sign in when asked; in Copilot
   Chat, agent mode, ask the same question. *Show Output* on the server has the log.
3. **Cursor:** add the `mcp.json` entry, sign in from Cursor's MCP settings, and before signing in look at the
   `redirect_uri` in the address the browser opens: it should be one of the registered addresses.

Things to watch, written down rather than guessed:
- Clients built on the MCP TypeScript SDK add `prompt=consent` when `offline_access` is in the requested scopes
  (modelcontextprotocol/typescript-sdk b415e60, `client/auth.ts`), and the server advertises `offline_access`. In a
  tenant where users may not consent to apps, that can loop on "Approval required" even after admin consent; reported
  for Cursor and in Claude Code issues, not verified here.
- Claude Code 2.1.229 sent `http://127.0.0.1:<port>/callback`; 2.1.231 went back to `localhost` (Claude Code changelog).
  Entra does not say that the port is ignored for `127.0.0.1`.
- Cursor's cloud agents use `https://www.cursor.com/agents/mcp/oauth/callback`, a web address; it is not covered here.

When a client works, its row in `docs/LIVE-TEST.md` gets the date, and the site's "supports Claude" lines can name it.

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
