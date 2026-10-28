"""`from fabric_backend import plan_sql_server`: the engine from your own Python on a SQL Server.

In CI the connection is the recorded INFORMATION_SCHEMA of tests/test_sqlserver.py (SQLite, the exact query text of
schema.py). With KRUSGRAPH_SQLSERVER_DSN set to a database seeded as docs/LOCAL.md describes (shop and demo schemas),
the last test runs against that SQL Server; on 28 October 2026 it ran against SQL Server 2022 in a container
(mcr.microsoft.com/mssql/server:2022-latest) with ODBC Driver 18 and a db_datareader login."""
import os

import pytest

import fabric_backend
from fabric_backend import plan_sql_server
from tests.test_sqlserver import recorded_execute


def test_the_name_is_exported_and_reads_declared_keys():
    assert "plan_sql_server" in fabric_backend.__all__
    with plan_sql_server("recorded", schema="shop", execute=recorded_execute()) as local:
        assert local.plan.keys["customers"][1] == "K0"
        assert any(r.rule == "R0" for r in local.plan.relationships)
        assert "version: 2" in local.dbt_schema()
        assert local.data_dictionary().startswith("# Data dictionary")


def test_an_empty_schema_is_an_error():
    with pytest.raises(ValueError):
        plan_sql_server("recorded", schema="nothing_here", execute=recorded_execute())


DSN = os.environ.get("KRUSGRAPH_SQLSERVER_DSN")


@pytest.mark.skipif(not DSN, reason="set KRUSGRAPH_SQLSERVER_DSN to run against a SQL Server")
def test_against_a_live_sql_server():
    with plan_sql_server(DSN, schema="shop") as shop:
        v = shop.validate()
        assert v["summary"].startswith("6 of 6 keys unique")
    with plan_sql_server(DSN, schema="demo") as demo:
        [f] = demo.amount_levels()["findings"]
        assert f["rows_per_header"]["max_lines"] == 2
