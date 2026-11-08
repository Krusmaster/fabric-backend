# Remote MCP server for fabric-backend. Runs on any container host (Azure Container Apps, Fly, a VM).
#   docker build -t fabric-backend-server .
#   docker run -p 8000:8000 -e FABRIC_TENANT_ID=... -e FABRIC_CLIENT_ID=... -e FABRIC_CLIENT_SECRET=... fabric-backend-server
# The service principal needs: the workspaces it should see (Contributor), and the tenant setting
# "Service principals can call Fabric public APIs". Put TLS in front (the directory requires https).

# n168: the Krusgraph Model editor (workload/Workload), production build. The server serves it on KRUSGRAPH_WORKLOAD_HOST
# (fabric_backend/workload_host.py). Built here, in Azure (az acr build), so nothing is built on anyone's machine. The
# engine URL and scope are left empty: the editor calls /workload/v1 on its own host and reads the scope from the meta
# tag the server writes into index.html. A Node LTS line, pinned to one release.
FROM node:22.12.0-bookworm-slim AS editor
WORKDIR /src
COPY workload/Workload/package.json workload/Workload/package-lock.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund
COPY workload/Workload/tsconfig.json workload/Workload/webpack.config.js ./
COPY workload/Workload/app ./app
ENV WORKLOAD_NAME=Org.Krusgraph ITEM_NAMES=Model WORKLOAD_VERSION=1.0.0 LOG_LEVEL=info ENABLE_PLAYGROUND=false \
    KRUSGRAPH_ENGINE_URL= KRUSGRAPH_ENGINE_SCOPE= NODE_OPTIONS=--max-old-space-size=4096
RUN npx webpack --config ./webpack.config.js --output-path /editor --mode production \
 && test -f /editor/index.html && rm -f /editor/web.config

FROM python:3.12-slim-bookworm

# ODBC Driver 18 for SQL Server — the SQL analytics endpoint is read over TDS
RUN apt-get update && apt-get install -y --no-install-recommends curl gnupg2 ca-certificates apt-transport-https \
 && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft.gpg \
 && echo "deb [arch=amd64,arm64 signed-by=/usr/share/keyrings/microsoft.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" > /etc/apt/sources.list.d/mssql-release.list \
 && apt-get update && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 unixodbc-dev gcc \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY deploy/constraints.txt ./deploy/constraints.txt
COPY fabric_backend ./fabric_backend
RUN pip install --no-cache-dir -c deploy/constraints.txt ".[server]"     # exact versions: see deploy/constraints.txt
COPY --from=editor /editor /app/workload-dist

RUN useradd --uid 10001 --create-home app
USER 10001
ENV HOST=0.0.0.0 PORT=8000 PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 KRUSGRAPH_WORKLOAD_DIST=/app/workload-dist
EXPOSE 8000
CMD ["fabric-backend-server"]
