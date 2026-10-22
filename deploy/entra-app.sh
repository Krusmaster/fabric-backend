#!/usr/bin/env bash
# Register the multi-tenant Entra app that users sign in to from Claude.
# Run once, signed in (az login) to the PUBLISHER's tenant — Kruse Consulting AB's, never a customer's or employer's.
#
#   MCP_PUBLIC_URL=https://<domain>/mcp ./deploy/entra-app.sh
#
# Prerequisite: <domain> is a verified custom domain in this tenant (Entra → Custom domain names). Entra only
# accepts the MCP URL as an Application ID URI on a verified domain, and Claude needs it there (AADSTS9010010).
set -euo pipefail
: "${MCP_PUBLIC_URL:?set MCP_PUBLIC_URL=https://<domain>/mcp}"
NAME="${APP_NAME:-Fabric tables for Claude}"

POWERBI=00000009-0000-0000-c000-000000000000      # Power BI Service — the Fabric REST API's resource
AZURESQL=022907d3-0f1b-48f7-badc-1ba6abab6d66     # Azure SQL Database — SQL analytics endpoints

scope_id() { az ad sp show --id "$1" --query "oauth2PermissionScopes[?value=='$2'].id | [0]" -o tsv; }

echo "Creating app '$NAME' (multi-tenant)…"
APP_ID=$(az ad app create --display-name "$NAME" --sign-in-audience AzureADMultipleOrgs \
  --web-redirect-uris "https://claude.ai/api/mcp/auth_callback" \
  --public-client-redirect-uris "http://localhost" "http://127.0.0.1" \
  --query appId -o tsv)
OBJ=$(az ad app show --id "$APP_ID" --query id -o tsv)

echo "Application ID URI = $MCP_PUBLIC_URL, scope user_impersonation…"
SCOPE_GUID=$(python3 -c 'import uuid; print(uuid.uuid4())')
az ad app update --id "$APP_ID" --identifier-uris "$MCP_PUBLIC_URL"
az rest --method PATCH --uri "https://graph.microsoft.com/v1.0/applications/$OBJ" --headers 'Content-Type=application/json' --body "{
  \"api\": {\"requestedAccessTokenVersion\": 2, \"oauth2PermissionScopes\": [{
    \"id\": \"$SCOPE_GUID\", \"value\": \"user_impersonation\", \"type\": \"User\", \"isEnabled\": true,
    \"adminConsentDisplayName\": \"Use Fabric data on your behalf\",
    \"adminConsentDescription\": \"Lets the connector read your Fabric workspaces and create API for GraphQL items with your own permissions.\",
    \"userConsentDisplayName\": \"Use Fabric data on your behalf\",
    \"userConsentDescription\": \"Lets the connector read your Fabric workspaces and create API for GraphQL items with your own permissions.\"}]}}"

echo "Delegated permissions it needs downstream (on-behalf-of)…"
for p in Workspace.Read.All Item.ReadWrite.All; do
  az ad app permission add --id "$APP_ID" --api $POWERBI --api-permissions "$(scope_id $POWERBI $p)=Scope"
done
az ad app permission add --id "$APP_ID" --api $AZURESQL --api-permissions "$(scope_id $AZURESQL user_impersonation)=Scope"

echo "Client secret (for the server and for Anthropic — transfer as they instruct, never by email)…"
SECRET=$(az ad app credential reset --id "$APP_ID" --display-name "mcp-server" --years 1 --query password -o tsv)

cat <<EOF

Done.
  ENTRA_CLIENT_ID=$APP_ID
  ENTRA_CLIENT_SECRET=<printed once, store it in the container app secret now>
  MCP_PUBLIC_URL=$MCP_PUBLIC_URL

Customer admins grant consent once:
  https://login.microsoftonline.com/organizations/v2.0/adminconsent?client_id=$APP_ID&scope=https://api.fabric.microsoft.com/.default%20https://database.windows.net/.default&redirect_uri=https://claude.ai/api/mcp/auth_callback

Then email mcp-review@anthropic.com with the client id ($APP_ID) to set up Anthropic-held credentials.
EOF
echo "$SECRET" > .entra-secret && chmod 600 .entra-secret && echo "(secret written to ./.entra-secret — move it to the vault and delete the file)"
