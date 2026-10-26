"""The command-line entry point on the synthetic shop schema (columns as CSV, as INFORMATION_SCHEMA exports them)."""
import csv

from fabric_backend import cli, seed


def write_columns(path, tables=None):
    rows = [r for r in seed.schema("shop").to_rows() if tables is None or r["table_name"] in tables]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)
    return str(path)


def test_plan_prints_the_summary_and_every_link_with_its_rule(tmp_path, capsys):
    columns = write_columns(tmp_path / "columns.csv")
    assert cli.main(["plan", columns, "--schema", "shop"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("7 tables, 6 with keys, 6 relationships") and "orders.customer_id -> customers.customer_id  [R1]" in out


def test_a_typo_in_keys_is_one_line_on_stderr_not_a_traceback(tmp_path, capsys):
    columns = write_columns(tmp_path / "columns.csv")
    keys = tmp_path / "keys.csv"
    keys.write_text("table_name,column_name\norders,ghost\n", encoding="utf-8")
    assert cli.main(["plan", columns, "--schema", "shop", "--keys", str(keys)]) == 2
    err = capsys.readouterr().err
    assert err.strip() == "fabric-backend: keys: column 'ghost' is not in table 'orders'"


def test_definition_and_rayfin_commands_write_files(tmp_path, capsys):
    columns = write_columns(tmp_path / "columns.csv")
    out = tmp_path / "graphql.json"
    assert cli.main(["definition", columns, "--schema", "shop", "--name", "shop_api", "--workspace", "ws", "--source-item", "src", "--out", str(out)]) == 0
    assert out.exists() and "shop_api" in out.read_text()
    assert cli.main(["rayfin", columns, "--schema", "shop", "--connector", "shop", "--out", str(tmp_path)]) == 0
    assert (tmp_path / "rayfin" / "connectors" / "shop" / "Orders.ts").exists()


def test_semantic_model_join_path_dictionary_dbt_analyze_and_views_commands(tmp_path, capsys):
    columns = write_columns(tmp_path / "columns.csv")
    assert cli.main(["semantic-model", columns, "--schema", "shop", "--name", "shop_model", "--sql-endpoint", "x.datawarehouse.fabric.microsoft.com",
                     "--source-name", "shop_lh", "--out", str(tmp_path)]) == 0
    model_dir = tmp_path / "shop_model.SemanticModel"
    assert (model_dir / "definition" / "tables" / "orders.tmdl").exists() and (model_dir / "README.generated.md").exists()
    assert 'Sql.Database("x.datawarehouse.fabric.microsoft.com", "shop_lh")' in (model_dir / "definition" / "expressions.tmdl").read_text()
    assert "7 tables, 6 active and 0 inactive relationships" in capsys.readouterr().out
    assert cli.main(["join-path", columns, "customers", "categories", "--schema", "shop"]) == 0
    out = capsys.readouterr().out
    assert "path 1: customers -> orders -> order_items -> products -> categories  (4 hops" in out and "FROM [shop].[customers] AS t0" in out
    two = write_columns(tmp_path / "two.csv", tables={"orders", "addresses"})
    assert cli.main(["join-path", two, "orders", "addresses", "--schema", "shop"]) == 1                     # no path: exit 1 and a suggestion
    out = capsys.readouterr().out
    assert "no chain of relationships" in out and '"source_cols": ["ship_to_id"]' in out
    assert cli.main(["dictionary", columns, "--schema", "shop", "--source-name", "shop_lh", "--out", str(tmp_path / "d.md")]) == 0
    assert "# Data dictionary: shop_lh / shop" in (tmp_path / "d.md").read_text() and "## Roles, subject areas and ambiguity" in (tmp_path / "d.md").read_text()
    assert cli.main(["dbt", columns, "--schema", "shop", "--database", "shop_lh", "--out", str(tmp_path / "schema.yml")]) == 0
    yml = (tmp_path / "schema.yml").read_text()
    assert "sources:\n  - name: shop\n    database: shop_lh" in yml and "arguments:" in yml
    assert cli.main(["dbt", columns, "--schema", "shop", "--legacy-arguments", "--out", str(tmp_path / "old.yml")]) == 0
    assert "arguments:" not in (tmp_path / "old.yml").read_text()
    assert cli.main(["analyze", columns, "--schema", "shop", "--json", str(tmp_path / "a.json")]) == 0
    out = capsys.readouterr().out
    assert "order_items: fact" in out and "no cycles" in out and (tmp_path / "a.json").exists()
    assert cli.main(["views", columns, "--schema", "shop"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'krusgraph')") and "CREATE OR ALTER VIEW [krusgraph].[vw_order_items] AS" in out
