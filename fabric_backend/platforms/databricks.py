"""The Databricks adapter (round n13). Draft only: unit-tested with Databricks mocked at its REST API, not yet run
against a workspace. Used by the local stdio server only (KRUSGRAPH_PLATFORM=databricks); the hosted server and its
Entra sign-in are unchanged.

1. Read: Unity Catalog's information_schema in one catalog (docs.databricks.com/aws/en/sql/language-manual/
   sql-ref-information-schema): COLUMNS for tables and types; TABLE_CONSTRAINTS, KEY_COLUMN_USAGE and
   REFERENTIAL_CONSTRAINTS for the informational PRIMARY KEY and FOREIGN KEY constraints, which become K0 and R0 exactly
   as a Fabric warehouse's declared keys do (schema.Schema.from_information_schema); COLUMN_TAGS for the personal-data
   rules P1-P6 (privacy.py). information_schema shows only what the signed-in principal may see. Lineage comes from the
   system table system.access.table_lineage (LINEAGE_SQL), which needs access to the system catalog.
2. Run SQL: the SQL Statement Execution API (POST /api/2.0/sql/statements, then GET .../{statement_id} and its result
   chunks) against a SQL warehouse, in the Databricks SQL dialect (dialects.DATABRICKS). Chosen over
   databricks-sql-connector because it is plain HTTPS like the Fabric side (no Thrift or Arrow dependency), and every
   call can be tested with the REST layer mocked, which is how this adapter is tested. Results come back INLINE as
   JSON_ARRAY (every value a string or null) and are typed from the manifest.
3. Build: the drafts in fabric_backend/databricks_drafts.py (constraints, views, the pipeline, metric views, the bundle).

Sign-in: Databricks' own unified client authentication through databricks-sdk's Config: DATABRICKS_HOST with a profile
in ~/.databrickscfg (DATABRICKS_CONFIG_PROFILE), an OAuth sign-in made with `databricks auth login`, or OAuth M2M
(DATABRICKS_CLIENT_ID / DATABRICKS_CLIENT_SECRET). DATABRICKS_WAREHOUSE_ID names the SQL warehouse, DATABRICKS_CATALOG
the catalog. Nothing is stored. docs/DATABRICKS.md has the set-up and the status of every tool.
"""
from __future__ import annotations

import os
import time

from ..dialects import DATABRICKS
from ..errors import PlatformError
from ..schema import Schema
from .base import Builder, Platform, Unsupported, connection

QUERY_TIMEOUT = 120          # seconds a statement may take before it is cancelled (a starting warehouse included)
WAIT = "30s"                 # how long one POST waits for the result before polling
POLL_SECONDS = 1.0

# Unity Catalog information_schema, in the catalog the connection names. full_data_type is the SQL spelling (bigint,
# decimal(10,2), string), which the engine's type families read; data_type is the type's name only.
COLUMNS_SQL = """
SELECT table_schema, table_name, column_name, full_data_type AS data_type, ordinal_position, is_nullable
FROM {catalog}.information_schema.columns
WHERE lower(table_schema) = lower('{schema}')
ORDER BY table_name, ordinal_position
"""

# The same rows schema.KEYS_SQL gives on Fabric, so declared keys are read the same way. A foreign key into another
# catalog or schema answers with that catalog and schema in ref_schema, which the reader leaves out (no target here).
KEYS_SQL = """
SELECT tc.table_name, tc.constraint_type, kcu.column_name, kcu.ordinal_position, tc.constraint_name,
       ref.table_name AS ref_table, refcol.column_name AS ref_column,
       CASE WHEN ref.table_catalog = tc.table_catalog THEN ref.table_schema
            ELSE concat(ref.table_catalog, '.', ref.table_schema) END AS ref_schema
FROM {catalog}.information_schema.table_constraints tc
JOIN {catalog}.information_schema.key_column_usage kcu
       ON kcu.constraint_catalog = tc.constraint_catalog AND kcu.constraint_schema = tc.constraint_schema
      AND kcu.constraint_name = tc.constraint_name
LEFT JOIN {catalog}.information_schema.referential_constraints rc
       ON rc.constraint_catalog = tc.constraint_catalog AND rc.constraint_schema = tc.constraint_schema
      AND rc.constraint_name = tc.constraint_name
LEFT JOIN {catalog}.information_schema.table_constraints ref
       ON ref.constraint_catalog = rc.unique_constraint_catalog AND ref.constraint_schema = rc.unique_constraint_schema
      AND ref.constraint_name = rc.unique_constraint_name
LEFT JOIN {catalog}.information_schema.key_column_usage refcol
       ON refcol.constraint_catalog = rc.unique_constraint_catalog AND refcol.constraint_schema = rc.unique_constraint_schema
      AND refcol.constraint_name = rc.unique_constraint_name
      AND refcol.ordinal_position = coalesce(kcu.position_in_unique_constraint, kcu.ordinal_position)
WHERE lower(tc.table_schema) = lower('{schema}') AND tc.constraint_type IN ('PRIMARY KEY', 'FOREIGN KEY')
ORDER BY tc.table_name, tc.constraint_name, kcu.ordinal_position
"""

TAGS_SQL = """
SELECT table_name, column_name, tag_name, tag_value
FROM {catalog}.information_schema.column_tags
WHERE lower(schema_name) = lower('{schema}')
ORDER BY table_name, column_name, tag_name
"""

# What reads from or writes to the schema's tables (system.access.table_lineage; the system catalog is enabled and
# granted by an account or metastore admin). One row per pair and entity, newest first.
LINEAGE_SQL = """
SELECT source_table_full_name, target_table_full_name, entity_type, entity_id, max(event_time) AS last_seen, count(*) AS events
FROM system.access.table_lineage
WHERE event_date >= date_sub(current_date(), {days})
  AND (lower(source_table_full_name) LIKE lower('{prefix}.%') OR lower(target_table_full_name) LIKE lower('{prefix}.%'))
GROUP BY source_table_full_name, target_table_full_name, entity_type, entity_id
ORDER BY last_seen DESC
LIMIT {limit}
"""

INT_TYPES = {"BYTE", "SHORT", "INT", "LONG", "TINYINT", "SMALLINT", "INTEGER", "BIGINT"}
FLOAT_TYPES = {"FLOAT", "DOUBLE"}


# ------------------------------------------------------------------ sign-in -----------------------------------------

def sdk_auth(host: str | None = None, profile: str | None = None):
    """(host, headers()) from Databricks' unified client authentication (databricks-sdk Config): the host and profile
    given, else DATABRICKS_HOST / DATABRICKS_CONFIG_PROFILE / ~/.databrickscfg; `Config.authenticate()` returns the
    request headers and refreshes an OAuth token when it has to."""
    try:
        from databricks.sdk.core import Config
    except ImportError as e:
        raise PlatformError("server_config", "The Databricks adapter signs in with Databricks' own client (databricks-sdk), which is "
                            "not installed.", 'pip install "fabric-backend[databricks]", then sign in with `databricks auth login '
                            '--host <workspace URL>` or a profile in ~/.databrickscfg.') from e
    try:
        cfg = Config(host=host or None, profile=profile or None)
        cfg.authenticate()
    except Exception as e:  # noqa: BLE001 — the SDK's message names what is missing; it never contains the token
        raise PlatformError("sign_in", f"Databricks sign-in failed: {e}",
                            "Set DATABRICKS_HOST to the workspace URL and sign in with `databricks auth login --host <workspace URL>`, "
                            "or name a profile from ~/.databrickscfg in DATABRICKS_CONFIG_PROFILE.") from e
    return cfg.host.rstrip("/"), cfg.authenticate


# ------------------------------------------------------------------ the Statement Execution API --------------------

def _http_error(r, where: str) -> PlatformError:
    try:
        body = r.json()
    except ValueError:
        body = {}
    code = str((body or {}).get("error_code") or "")
    msg = str((body or {}).get("message") or getattr(r, "text", "") or "")[:300]
    status = getattr(r, "status_code", 0)
    if status == 401:
        return PlatformError("sign_in", f"Databricks did not accept the sign-in for {where} (HTTP 401).",
                             "Sign in again with `databricks auth login --host <workspace URL>` or check the profile in ~/.databrickscfg.")
    if status == 403 or code == "PERMISSION_DENIED":
        return PlatformError("no_access", f"Databricks refused {where} (HTTP {status}{': ' + msg if msg else ''}).",
                             "The signed-in principal needs CAN USE on the SQL warehouse, and USE CATALOG, USE SCHEMA and SELECT on the "
                             "tables (docs/DATABRICKS.md lists the privileges per tool).")
    if status == 404 or code in ("RESOURCE_DOES_NOT_EXIST", "NOT_FOUND"):
        return PlatformError("not_found", f"Databricks found nothing for {where} (HTTP {status}{': ' + msg if msg else ''}).",
                             "Check DATABRICKS_HOST and DATABRICKS_WAREHOUSE_ID: the warehouse id is in the SQL warehouse's "
                             "Connection details.")
    if status == 429:
        return PlatformError("throttled", f"Databricks is rate-limiting {where} (HTTP 429).", "Wait a little and try again.")
    if status >= 500:
        return PlatformError("unreachable", f"Databricks answered HTTP {status} for {where}.", "Try again in a few minutes.")
    return PlatformError("sql_error", f"Databricks answered HTTP {status} for {where}{': ' + code if code else ''}{' ' + msg if msg else ''}.",
                         "Check the message above.")


def _sql_failure(error: dict, where: str) -> PlatformError:
    """A FAILED statement: its error_code and message (the message starts with the error class, e.g.
    [TABLE_OR_VIEW_NOT_FOUND]) → the tools' kinds."""
    code = str(error.get("error_code") or "")
    msg = str(error.get("message") or "")[:400]
    low = (code + " " + msg).lower()
    if "table_or_view_not_found" in low:
        return PlatformError("table_not_found", f"Databricks has no such table or view for {where}: {msg}",
                             "list_tables shows the tables; the catalog is DATABRICKS_CATALOG.")
    if "schema_not_found" in low or "no_such_catalog" in low or "catalog_not_found" in low:
        return PlatformError("schema_not_found", f"Databricks has no such catalog or schema for {where}: {msg}",
                             "Check DATABRICKS_CATALOG and the schema name; information_schema lists only what you may see.")
    if "unresolved_column" in low:
        return PlatformError("column_not_found", f"Databricks has no such column for {where}: {msg}",
                             "Check the column names: the keys you passed must exist in the table.")
    if "permission" in low or "insufficient_permissions" in low or "unauthorized" in low:
        return PlatformError("no_access", f"Databricks refused {where}: {msg}",
                             "The signed-in principal needs USE CATALOG, USE SCHEMA and SELECT on the tables; creating needs the rights "
                             "docs/DATABRICKS.md names.")
    return PlatformError("sql_error", f"The SQL warehouse answered with an error for {where}: {msg}", "Check the message above.")


def _typed(value, type_name: str):
    if value is None:
        return None
    t = (type_name or "").upper()
    try:
        if t in INT_TYPES:
            return int(value)
        if t in FLOAT_TYPES:
            return float(value)
        if t == "BOOLEAN":
            return str(value).lower() == "true"
    except (TypeError, ValueError):
        return value
    return value


class StatementClient:
    """One SQL warehouse through the SQL Statement Execution API. `headers` is a function returning the request
    headers (sdk_auth); `catalog` is the statement's default catalog."""

    def __init__(self, host: str, warehouse_id: str, headers, catalog: str | None = None, timeout: float = QUERY_TIMEOUT,
                 poll_seconds: float = POLL_SECONDS):
        self.host, self.warehouse_id, self.headers, self.catalog = host.rstrip("/"), warehouse_id, headers, catalog
        self.timeout, self.poll_seconds = timeout, poll_seconds

    def _get(self, url: str, where: str) -> dict:
        import requests
        r = requests.get(url, headers=self.headers(), timeout=60)
        if getattr(r, "status_code", 200) >= 400:
            raise _http_error(r, where)
        return r.json()

    def run(self, sql: str, where: str = "the statement") -> list[dict]:
        import requests
        body = {"statement": sql, "warehouse_id": self.warehouse_id, "wait_timeout": WAIT, "on_wait_timeout": "CONTINUE",
                "disposition": "INLINE", "format": "JSON_ARRAY"}
        if self.catalog:
            body["catalog"] = self.catalog
        r = requests.post(f"{self.host}/api/2.0/sql/statements", headers=self.headers(), json=body, timeout=60)
        if getattr(r, "status_code", 200) >= 400:
            raise _http_error(r, where)
        resp = r.json()
        started = time.monotonic()
        while (resp.get("status") or {}).get("state") in ("PENDING", "RUNNING"):
            if time.monotonic() - started > self.timeout:
                try:
                    requests.post(f"{self.host}/api/2.0/sql/statements/{resp['statement_id']}/cancel", headers=self.headers(), timeout=30)
                finally:
                    raise PlatformError("timeout", f"The SQL warehouse did not finish {where} in {int(self.timeout)} seconds; the statement was "
                                        "cancelled.", "A stopped warehouse takes a while to start: try again in a minute, or start it first.")
            time.sleep(self.poll_seconds)
            resp = self._get(f"{self.host}/api/2.0/sql/statements/{resp['statement_id']}", where)
        status = resp.get("status") or {}
        if status.get("state") != "SUCCEEDED":
            if status.get("state") == "FAILED":
                raise _sql_failure(status.get("error") or {}, where)
            raise PlatformError("sql_error", f"The statement for {where} ended {status.get('state') or 'without a state'}.",
                                "Try again; a statement is cancelled or closed when the warehouse stops.")
        columns = [(c.get("name"), c.get("type_name")) for c in ((resp.get("manifest") or {}).get("schema") or {}).get("columns", [])]
        rows: list[dict] = []
        result = resp.get("result") or {}
        while True:
            for values in result.get("data_array") or []:
                rows.append({name: _typed(v, t) for (name, t), v in zip(columns, values)})
            link = result.get("next_chunk_internal_link")
            if not link:
                break
            result = self._get(self.host + link, where)
        return rows


def connect(host: str, warehouse_id: str, headers, catalog: str | None = None, timeout: float = QUERY_TIMEOUT):
    """The engine's connection over one SQL warehouse: rows as dicts, DDL through the same API (`.statement`), Databricks
    SQL with the catalog bound for three-part names."""
    client = StatementClient(host, warehouse_id, headers, catalog, timeout)

    def execute(sql: str):
        return client.run(sql, "a query")

    def statement(sql: str) -> None:
        client.run(sql, "a statement")
    return connection(execute, dialect=DATABRICKS.with_catalog(catalog), statement=statement, client=client)


# ------------------------------------------------------------------ workspace files and pipelines (REST) ------------

class Rest:
    """The few REST calls the creating tools make, each answered in the tools' error format on failure."""

    def __init__(self, host: str, headers):
        self.host, self.headers = host.rstrip("/"), headers

    def call(self, method: str, path: str, where: str, json: dict | None = None, params: dict | None = None) -> dict:
        import requests
        r = getattr(requests, method)(self.host + path, headers=self.headers(), json=json, params=params, timeout=60) if json is not None \
            else getattr(requests, method)(self.host + path, headers=self.headers(), params=params, timeout=60)
        if getattr(r, "status_code", 200) >= 400:
            raise _http_error(r, where)
        try:
            return r.json() or {}
        except ValueError:
            return {}


def pipeline_folder(rest: Rest, name: str) -> str:
    """/Workspace/Users/<the signed-in user>/krusgraph/<name>: the user from SCIM Me (GET /api/2.0/preview/scim/v2/Me, the
    call databricks-sdk's Config makes for the same purpose)."""
    me = rest.call("get", "/api/2.0/preview/scim/v2/Me", "reading the signed-in user")
    user = me.get("userName") or ""
    if not user:
        raise PlatformError("sign_in", "Databricks did not name the signed-in user.", "Sign in again with `databricks auth login`.")
    return f"/Workspace/Users/{user}/krusgraph/{name}"


def find_pipeline(rest: Rest, name: str) -> dict | None:
    """The pipeline with exactly this name (GET /api/2.0/pipelines with filter name LIKE '<name>'), or None."""
    page, token = 0, None
    while page < 20:
        params = {"filter": f"name LIKE '{name}'", "max_results": 100}
        if token:
            params["page_token"] = token
        body = rest.call("get", "/api/2.0/pipelines", "listing pipelines", params=params)
        for st in body.get("statuses") or []:
            if st.get("name") == name:
                return st
        token = body.get("next_page_token")
        if not token:
            return None
        page += 1
    return None


def apply_pipeline(rest: Rest, name: str, settings: dict, files: dict[str, str], folder: str | None = None) -> dict:
    """Write the notebooks into the folder (POST /api/2.0/workspace/mkdirs, /api/2.0/workspace/import as SQL notebooks,
    overwriting only there) and create the pipeline (POST /api/2.0/pipelines) or update the one of that name in place
    (PUT /api/2.0/pipelines/{id}) when every notebook it runs is in that folder. Starts no update; deletes nothing."""
    import base64
    folder = folder or pipeline_folder(rest, name)
    existing = find_pipeline(rest, name)
    if existing:
        current = rest.call("get", f"/api/2.0/pipelines/{existing['pipeline_id']}", "reading the pipeline")
        libs = ((current.get("spec") or {}).get("libraries") or [])
        paths = [((lib.get("notebook") or lib.get("file") or {}).get("path") or "") for lib in libs]
        if not paths or any(not p.startswith(folder + "/") for p in paths):
            raise PlatformError("bad_input", f"A pipeline named {name!r} exists and runs code outside {folder}; it was not made by this tool, "
                                "so nothing was changed.", "Choose another name, or update that pipeline yourself.")
    rest.call("post", "/api/2.0/workspace/mkdirs", f"creating {folder}", json={"path": folder})
    written = []
    for fname, text in files.items():
        path = f"{folder}/{fname.rsplit('.', 1)[0]}"
        rest.call("post", "/api/2.0/workspace/import", f"writing {path}",
                  json={"path": path, "format": "SOURCE", "language": "SQL", "overwrite": True,
                        "content": base64.b64encode(text.encode("utf-8")).decode()})
        written.append(path)
    body = {**settings, "libraries": [{"notebook": {"path": p}} for p in written]}
    if existing:
        rest.call("put", f"/api/2.0/pipelines/{existing['pipeline_id']}", "updating the pipeline", json={**body, "id": existing["pipeline_id"]})
        return {"status": "Succeeded", "mode": "updated", "pipeline_id": existing["pipeline_id"], "notebooks": written}
    created = rest.call("post", "/api/2.0/pipelines", "creating the pipeline", json=body)
    return {"status": "Succeeded", "mode": "created", "pipeline_id": created.get("pipeline_id"), "notebooks": written}


# ------------------------------------------------------------------ reading Unity Catalog ---------------------------

_NAME = __import__("re").compile(r"^[A-Za-z0-9_][A-Za-z0-9_-]{0,254}$")


def _literal(text: str) -> str:
    """A catalog or schema name for a string literal: letters, digits, _ and - only, so no escaping rule is needed."""
    from ..infer import PlanInputError
    for part in str(text).split("."):
        if not _NAME.match(part):
            raise PlanInputError(f"{text!r}: on Databricks the tools take catalog and schema names of letters, digits, _ and - "
                                 "(give the schema without the catalog; the catalog is DATABRICKS_CATALOG)")
    return str(text)


def read_schema(execute, schema: str, catalog: str) -> Schema:
    """Tables and columns of catalog.schema, the informational PRIMARY KEY / FOREIGN KEY constraints (K0/R0) and the
    column tags. A catalog without the constraints or tags views gives a plan from names, as a lakehouse does."""
    from ..errors import SchemaEmpty
    from ..infer import PlanInputError
    if "." in str(schema):
        raise PlanInputError(f"schema {schema!r}: give the schema without the catalog; the catalog is DATABRICKS_CATALOG ({catalog})")
    cat = DATABRICKS.quote(catalog)
    lit = _literal(schema)
    columns = list(execute(COLUMNS_SQL.format(catalog=cat, schema=lit)))
    if not columns:
        raise SchemaEmpty(f"Schema {schema!r} has no tables in catalog {catalog!r}, or none the signed-in principal may see.")
    try:
        keys = list(execute(KEYS_SQL.format(catalog=cat, schema=lit)))
    except PlatformError as e:
        if e.kind in ("sign_in", "timeout"):
            raise
        keys = []
    s = Schema.from_information_schema(columns, keys, schema=schema)
    nullable = {(str(r.get("table_name")).lower(), str(r.get("column_name")).lower()): str(r.get("is_nullable") or "").upper()
                for r in ({str(k).lower(): v for k, v in row.items()} for row in columns)}
    for t in s:
        for c in t.columns:
            flag = nullable.get((t.name.lower(), c.name.lower()))
            c.nullable = None if flag not in ("YES", "NO") else flag == "YES"
    try:
        tags = list(execute(TAGS_SQL.format(catalog=cat, schema=lit)))
    except PlatformError as e:
        if e.kind in ("sign_in", "timeout"):
            raise
        tags = []
    by_name = {t.name.lower(): t for t in s}
    for row in tags:
        r = {str(k).lower(): v for k, v in row.items()}
        t = by_name.get(str(r.get("table_name") or "").lower())
        if t is not None and r.get("column_name") and r.get("tag_name"):
            t.tags.setdefault(r["column_name"], {})[str(r["tag_name"])] = "" if r.get("tag_value") is None else str(r["tag_value"])
    return s


def lineage(execute, catalog: str, schema: str, days: int = 90, limit: int = 500) -> list[dict]:
    """Rows of system.access.table_lineage that read from or write to catalog.schema in the last `days` days."""
    prefix = _literal(f"{catalog}.{schema}")
    return list(execute(LINEAGE_SQL.format(days=int(days), prefix=prefix, limit=int(limit))))


# ------------------------------------------------------------------ the platform ------------------------------------

BUILDERS = (
    Builder("informational PRIMARY KEY / FOREIGN KEY constraints", "databricks_constraints_draft", "create_databricks_constraints",
            "databricks_drafts.py", "ownership of each table (ALTER TABLE)"),
    Builder("views in a schema of their own (Databricks SQL)", "create_views", "create_views", "views.py with dialects.DATABRICKS",
            "USE CATALOG, USE SCHEMA and CREATE TABLE on the views' schema, CREATE SCHEMA when it is new"),
    Builder("Lakeflow pipeline: silver and gold materialized views with expectations", "databricks_pipeline_draft",
            "create_databricks_pipeline", "databricks_drafts.py", "workspace files and pipeline create rights; CREATE MATERIALIZED VIEW "
            "and CREATE TABLE on the target schemas"),
    Builder("metric views (YAML)", "databricks_metric_view_draft", None, "databricks_drafts.py"),
    Builder("Databricks Asset Bundle", "export_databricks_bundle", None, "databricks_drafts.py"),
)

# Every tool of the local stdio server on Databricks: its status in the site's words, or why it does not apply.
TOOLS = {
    "list_tables": ("Draft only", "Unity Catalog information_schema.columns"),
    "plan_backend": ("Draft only", "inference on names; informational PRIMARY KEY / FOREIGN KEY constraints are K0 / R0"),
    "validate_plan": ("Draft only", "the counting queries in Databricks SQL on the SQL warehouse"),
    "sample_rows": ("Draft only", "LIMIT n in Databricks SQL; personal columns by name and by Unity Catalog column tag are masked"),
    "join_path": ("Draft only", "the chain with Databricks SQL (three-part names, LIMIT)"),
    "data_dictionary": ("Draft only", "as on Fabric, from the Unity Catalog schema"),
    "dbt_schema": ("Draft only", "database is the catalog, as dbt-databricks reads it"),
    "analyze_schema": ("Draft only", "as on Fabric"),
    "suggest_relationships": ("Draft only", "inclusion counts in Databricks SQL"),
    "create_views": ("Draft only", "CREATE OR REPLACE VIEW in a schema of their own; dry run by default"),
    "databricks_constraints_draft": ("Draft only", "ALTER TABLE ... ADD CONSTRAINT, RELY only where validate_plan's counts hold"),
    "create_databricks_constraints": ("Draft only", "applies the draft through the SQL warehouse; dry run by default; never drops"),
    "databricks_pipeline_draft": ("Draft only", "a Lakeflow pipeline in SQL: silver and gold with expectations, quarantine"),
    "create_databricks_pipeline": ("Draft only", "workspace files and the pipeline through REST; dry run by default; does not run it"),
    "databricks_metric_view_draft": ("Draft only", "one metric view per fact table"),
    "export_databricks_bundle": ("Draft only", "a bundle folder: databricks.yml, the pipeline, the SQL files"),
    "databricks_lineage": ("Draft only", "system.access.table_lineage; needs access to the system catalog"),
}
NOT_ON_DATABRICKS = {
    "create_backend": ("an API for GraphQL item is a Fabric object; Databricks has no equivalent item",
                       "Plan with plan_backend here; for the API, mirror the catalog into Fabric (Mirrored Azure Databricks catalog) and "
                       "use the hosted server, which creates the API over the mirrored item."),
    "rayfin_connector": ("Rayfin connectors read Fabric items (Fabric Apps)",
                         "Mirror the catalog into Fabric and generate the connector there."),
    "ontology_draft": ("a Fabric IQ ontology binds to tables of a Fabric item",
                       "Use plan_backend and data_dictionary for the model here, or mirror the catalog into Fabric."),
    "semantic_model_draft": ("a Power BI semantic model in Direct Lake mode reads a Fabric SQL analytics endpoint",
                             "databricks_metric_view_draft gives Databricks' own semantic layer (metric views) from the same plan."),
    "silver_notebook_draft": ("the silver notebook is a Fabric notebook for a lakehouse",
                              "databricks_pipeline_draft gives the same silver rules as a Lakeflow pipeline with expectations."),
    "answer_query_draft": ("the drafted query is T-SQL; a Databricks SQL version is Planned",
                           "join_path gives the joins in Databricks SQL for the same tables."),
}


class DatabricksPlatform(Platform):
    name = "databricks"
    title = "Databricks (Unity Catalog, SQL warehouse)"
    dialect = DATABRICKS
    builders = BUILDERS

    def __init__(self, catalog: str | None = None, warehouse_id: str | None = None, host: str | None = None, profile: str | None = None):
        self.catalog, self.warehouse_id, self.host, self.profile = catalog, warehouse_id, host, profile

    @classmethod
    def from_env(cls) -> "DatabricksPlatform":
        return cls(os.environ.get("DATABRICKS_CATALOG", "").strip() or None, os.environ.get("DATABRICKS_WAREHOUSE_ID", "").strip() or None,
                   os.environ.get("DATABRICKS_HOST", "").strip() or None, os.environ.get("DATABRICKS_CONFIG_PROFILE", "").strip() or None)

    def check(self) -> None:
        missing = [n for n, v in (("DATABRICKS_CATALOG", self.catalog), ("DATABRICKS_WAREHOUSE_ID", self.warehouse_id)) if not v]
        if missing:
            raise PlatformError("server_config", f"{' and '.join(missing)} {'is' if len(missing) == 1 else 'are'} not set: the Databricks adapter "
                                "needs the catalog to read and the SQL warehouse that runs the queries.",
                                "Set DATABRICKS_CATALOG (for example workspace or main) and DATABRICKS_WAREHOUSE_ID (the SQL warehouse's "
                                "Connection details) in the MCP client's configuration; docs/DATABRICKS.md has an example.")

    def connect(self, headers=None, host: str | None = None):
        self.check()
        if headers is None:
            host, headers = sdk_auth(self.host, self.profile)
        return connect(host or self.host or "", self.warehouse_id, headers, self.catalog)

    def rest(self, headers=None, host: str | None = None) -> Rest:
        if headers is None:
            host, headers = sdk_auth(self.host, self.profile)
        return Rest(host or self.host or "", headers)

    def read_schema(self, execute, schema: str) -> Schema:
        return read_schema(execute, schema, self.catalog or "")

    def unsupported(self, tool: str) -> Unsupported | None:
        if tool in NOT_ON_DATABRICKS:
            why, hint = NOT_ON_DATABRICKS[tool]
            return Unsupported(f"{tool} does not apply on Databricks: {why}.", hint)
        return None
