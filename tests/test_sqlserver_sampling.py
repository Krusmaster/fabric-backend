"""sample_rows on the SQL Server types a DB-API driver cannot fetch as they come (pyodbc: "ODBC SQL type -151 is not yet
supported" for hierarchyid, geography and geometry, -150 for sql_variant) and on binary columns, whose bytes say nothing
about a column's meaning. The SQL text is checked here; no SQL Server runs in the sandbox."""
import json

from fabric_backend import evidence, mcp_server


def test_sample_sql_reads_clr_types_as_text_variants_as_nvarchar_and_binary_as_size():
    types = {"BusinessEntityID": "int", "OrganizationNode": "hierarchyid", "SpatialLocation": "geography", "Photo": "varbinary",
             "Extra": "sql_variant", "Notes": "nvarchar", "rowguid": "uniqueidentifier"}
    sql = evidence.sample_sql("HumanResources", "Employee", list(types), 5, types)
    assert sql == ("SELECT TOP (5) [BusinessEntityID], [OrganizationNode].ToString() AS [OrganizationNode], "
                   "[SpatialLocation].ToString() AS [SpatialLocation], DATALENGTH([Photo]) AS [Photo (bytes)], "
                   "CAST([Extra] AS nvarchar(4000)) AS [Extra], [Notes], [rowguid] FROM [HumanResources].[Employee]")
    assert evidence.sample_sql("shop", "orders", ["a", "b"], 3) == "SELECT TOP (3) [a], [b] FROM [shop].[orders]"   # no types: as before
    assert evidence.sample_expr("x]y", "GEOMETRY") == "[x]]y].ToString() AS [x]]y]"                               # quoted, any case
    assert evidence.sample_expr("thumb", "varbinary(max)") == "DATALENGTH([thumb]) AS [thumb (bytes)]"
    assert evidence.sample_expr("happened_at", "timestamp") == "[happened_at]"          # a lakehouse timestamp is a date, left alone


def test_local_sample_rows_passes_the_column_types(monkeypatch):
    columns = [("dbo", "Employee", "BusinessEntityID", "int", 1), ("dbo", "Employee", "OrganizationNode", "hierarchyid", 2),
               ("dbo", "Employee", "Photo", "varbinary", 3)]
    seen = []

    def factory(schema):
        def execute(sql):
            seen.append(sql)
            if "INFORMATION_SCHEMA.COLUMNS" in sql:
                return [dict(zip(["TABLE_SCHEMA", "TABLE_NAME", "COLUMN_NAME", "DATA_TYPE", "ORDINAL_POSITION"], r)) for r in columns]
            if "TABLE_CONSTRAINTS" in sql:
                return []
            return [{"BusinessEntityID": 1, "OrganizationNode": "/1/", "Photo (bytes)": 1234}]
        execute.close = lambda: None
        return execute
    monkeypatch.setattr(mcp_server, "_execute_factory", factory)
    out = json.loads(mcp_server.sample_rows("Employee", schema="dbo", n=2))
    assert out == {"table": "Employee", "rows": [{"BusinessEntityID": 1, "OrganizationNode": "/1/", "Photo (bytes)": 1234}]}
    assert seen[-1] == ("SELECT TOP (2) [BusinessEntityID], [OrganizationNode].ToString() AS [OrganizationNode], "
                        "DATALENGTH([Photo]) AS [Photo (bytes)] FROM [dbo].[Employee]")
