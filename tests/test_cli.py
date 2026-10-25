"""The command-line entry point on the synthetic shop schema (columns as CSV, as INFORMATION_SCHEMA exports them)."""
import csv

from fabric_backend import cli, seed


def write_columns(path):
    rows = seed.schema("shop").to_rows()
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
