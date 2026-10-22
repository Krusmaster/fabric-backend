#!/usr/bin/env bash
# Host the remote MCP server on Azure Container Apps, in the PUBLISHER's subscription.
#
#   MCP_DOMAIN=<domain> PRODUCT_NAME=<name> CONTACT_EMAIL=<email> COMPANY_ORGNR=<org nr> \
#   ENTRA_CLIENT_ID=... ENTRA_CLIENT_SECRET=... ./deploy/containerapp.sh
#
# Scales to zero when idle; at directory volumes that is a few euros a month. TLS comes from the managed
# certificate on the custom domain (Claude requires https).
set -euo pipefail
: "${MCP_DOMAIN:?set MCP_DOMAIN, e.g. mcp.example.com}"
: "${ENTRA_CLIENT_ID:?}"; : "${ENTRA_CLIENT_SECRET:?}"
RG="${RG:-rg-fabric-mcp}"; LOC="${LOC:-swedencentral}"; ENV="${ENV_NAME:-cae-fabric-mcp}"; APP="${APP:-fabric-mcp}"
ACR="${ACR:-acrfabricmcp$RANDOM}"

az group create -n "$RG" -l "$LOC" -o none
az acr create -n "$ACR" -g "$RG" --sku Basic --admin-enabled true -o none
az acr build -r "$ACR" -t fabric-backend-server:latest "$(dirname "$0")/.."
az containerapp env create -n "$ENV" -g "$RG" -l "$LOC" -o none

az containerapp create -n "$APP" -g "$RG" --environment "$ENV" \
  --image "$ACR.azurecr.io/fabric-backend-server:latest" --registry-server "$ACR.azurecr.io" \
  --target-port 8000 --ingress external --min-replicas 0 --max-replicas 3 \
  --secrets entra-secret="$ENTRA_CLIENT_SECRET" \
  --env-vars MCP_PUBLIC_URL="https://$MCP_DOMAIN/mcp" ENTRA_CLIENT_ID="$ENTRA_CLIENT_ID" ENTRA_CLIENT_SECRET=secretref:entra-secret \
             PRODUCT_NAME="${PRODUCT_NAME:?}" CONTACT_EMAIL="${CONTACT_EMAIL:?}" COMPANY_ORGNR="${COMPANY_ORGNR:-}" \
  -o none

FQDN=$(az containerapp show -n "$APP" -g "$RG" --query properties.configuration.ingress.fqdn -o tsv)
cat <<EOF

Running at https://$FQDN (health: /healthz).
Now point DNS:  CNAME $MCP_DOMAIN -> $FQDN   and   TXT asuid.$MCP_DOMAIN -> \$(az containerapp show -n $APP -g $RG --query properties.customDomainVerificationId -o tsv)
Then:           az containerapp hostname add  -n $APP -g $RG --hostname $MCP_DOMAIN
                az containerapp hostname bind -n $APP -g $RG --hostname $MCP_DOMAIN --environment $ENV --validation-method CNAME
Check:          curl -i -X POST https://$MCP_DOMAIN/mcp    -> 401 with WWW-Authenticate: Bearer resource_metadata=…
EOF
