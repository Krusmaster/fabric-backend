# Remote MCP server for fabric-backend. Runs on any container host (Azure Container Apps, Fly, a VM).
#   docker build -t fabric-backend-server .
#   docker run -p 8000:8000 -e FABRIC_TENANT_ID=... -e FABRIC_CLIENT_ID=... -e FABRIC_CLIENT_SECRET=... fabric-backend-server
# The service principal needs: the workspaces it should see (Contributor), and the tenant setting
# "Service principals can call Fabric public APIs". Put TLS in front (the directory requires https).
FROM python:3.12-slim-bookworm

# ODBC Driver 18 for SQL Server — the SQL analytics endpoint is read over TDS
RUN apt-get update && apt-get install -y --no-install-recommends curl gnupg2 ca-certificates apt-transport-https \
 && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft.gpg \
 && echo "deb [arch=amd64,arm64 signed-by=/usr/share/keyrings/microsoft.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" > /etc/apt/sources.list.d/mssql-release.list \
 && apt-get update && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 unixodbc-dev gcc \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY fabric_backend ./fabric_backend
RUN pip install --no-cache-dir ".[server]"

RUN useradd --uid 10001 --create-home app
USER 10001
ENV HOST=0.0.0.0 PORT=8000 PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
EXPOSE 8000
CMD ["fabric-backend-server"]
