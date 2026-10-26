"""The local 20-minute demo (`fabric-backend demo`): the four steps on the shop seed in SQLite and on a folder of CSV and
Excel files, the decisions (Accept / Skip) changing the plan, the exports, the HTTP surface, and that the server only
ever binds to 127.0.0.1."""
import json
import zipfile

import pytest

from fabric_backend import cli, demo_app, seed


@pytest.fixture
def shop():
    s = demo_app.Session(demo_app.sample_source())
    yield s
    s.source.close()


def test_step_one_before_a_source_shows_the_steps_and_nothing_else():
    st = demo_app.Session().state()
    assert [s["title"] for s in st["steps"]] == ["Connect", "The map", "Health check", "The value"]
    assert sum(s["minutes"] for s in st["steps"]) == 20 and st["current_step"] == 1
    assert st["source"] is None and st["plan"] is None and st["questions"] == []


def test_the_map_on_the_shop_seed_is_the_engine_plan_with_roles_and_areas(shop):
    st = shop.state()
    assert st["current_step"] == 1 and st["source"]["kind"] == "sample" and st["source"]["has_data"]
    assert st["plan"]["summary"].startswith("7 tables, 6 with keys, 6 relationships")
    names = {t["name"] for t in st["plan"]["tables"]}
    assert names == set(seed.SCHEMAS) and st["plan"]["keyless"] == ["audit_log"]
    assert st["analysis"]["roles"]["orders"]["role"] == "fact" and st["analysis"]["roles"]["customers"]["role"] == "dimension"
    assert st["analysis"]["areas"] and "mermaid" in st["plan"]


def test_the_health_check_finds_the_unlinked_column_and_the_keyless_table_with_evidence(shop):
    h = shop.state()["health"]
    assert h["checked"] and h["summary"].startswith("6 of 6 keys unique, 6 of 6 relationships hold")
    by_id = {f["id"]: f for f in h["findings"]}
    sug = by_id["sug:orders.ship_to_id>addresses"]
    assert sug["can_accept"] and sug["next"]["confirmed"] == {"source": "orders", "source_cols": ["ship_to_id"], "target": "addresses", "target_cols": ["address_id"]}
    assert "inclusion 100%" in sug["saw"] and "SELECT COUNT_BIG" in sug["evidence"] and sug["strength"] == "strong"
    assert "not a verified fact" in sug["next_text"]
    nokey = by_id["nokey:audit_log"]
    assert not nokey["can_accept"] and "rule K3" in nokey["saw"] and nokey["next"]["sql"].startswith("SELECT COUNT(*)")
    for f in h["findings"]:                                        # every finding has the four parts the demo promises
        assert f["saw"] and f["means"] and f["next_text"] and f["evidence"]


def test_accept_adds_a_confirmed_relationship_and_the_plan_updates_at_once(shop):
    shop.accept("sug:orders.ship_to_id>addresses")
    st = shop.state()
    assert st["plan"]["summary"].startswith("7 tables, 6 with keys, 7 relationships")
    conf = [r for r in st["plan"]["relationships"] if r["accepted_here"]]
    assert conf == [{"source": "orders", "source_cols": ["ship_to_id"], "target": "addresses", "target_cols": ["address_id"], "rule": "confirmed",
                     "field": "ship_to", "reverse": "orders_as_ship_to", "accepted_here": True}]
    assert st["health"]["summary"].startswith("6 of 6 keys unique, 7 of 7 relationships hold")
    f = next(x for x in st["health"]["findings"] if x["id"] == "sug:orders.ship_to_id>addresses")
    assert f["accepted"] and not f["skipped"]
    shop.skip("sug:orders.ship_to_id>addresses")                   # skip after accept is the undo: out of the plan again
    assert shop.state()["plan"]["summary"].startswith("7 tables, 6 with keys, 6 relationships")
    shop.accept("sug:orders.ship_to_id>addresses")
    shop.reset()
    assert shop.state()["plan"]["summary"].startswith("7 tables, 6 with keys, 6 relationships")


def test_skip_hides_the_suggestion_and_accepting_a_finding_without_an_action_is_refused(shop):
    shop.skip("sug:orders.ship_to_id>addresses")
    st = shop.state()
    assert st["health"]["open"] == 1 and next(f for f in st["health"]["findings"] if f["id"].startswith("sug:"))["skipped"]
    with pytest.raises(ValueError):
        shop.accept("nokey:audit_log")
    with pytest.raises(KeyError):
        shop.accept("ghost")


def test_five_questions_run_locally_with_their_sql_and_rows(shop):
    qs = shop.state()["questions"]
    assert len(qs) == 5 and all(q["sql"] and q["why"] and "error" not in q for q in qs)
    ids = [q["id"] for q in qs]
    assert ids[0] == "count:orders>customers" and "month:orders.order_date" in ids and "path:" in "".join(ids)
    count = qs[0]
    assert count["columns"] == ["name", "rows"] and len(count["rows"]) <= demo_app.ROW_CAP and "LIMIT 10" in count["sql"]
    path = next(q for q in qs if q["id"].startswith("path:"))
    assert path["rows"] and len(path["columns"]) >= 2 and "JOIN" in path["sql"]
    assert all(q["rows"] for q in qs if not q["id"].startswith("none:"))   # on the seed every customer has orders, so that one is empty, and says so


def test_exports_are_the_hand_over_files(shop):
    for name in ("dictionary.md", "schema.yml", "lovable-prompt.md", "plan.json", "er.mmd"):
        status, ctype, body = shop.handle("GET", f"/export/{name}")
        assert status == 200 and body, name
    prompt = shop.handle("GET", "/export/lovable-prompt.md")[2].decode()
    assert "## Data model" in prompt and "orders.customer_id → customers.customer_id" in prompt and "Never put a database password" in prompt
    assert "- **order_items**: order_id, line_no, product_id, quantity (key: order_id + line_no)" in prompt
    assert json.loads(shop.handle("GET", "/export/plan.json")[2])["summary"].startswith("7 tables")
    assert shop.handle("GET", "/export/secret.txt")[0] == 404


def test_the_http_surface(shop):
    status, ctype, body = shop.handle("GET", "/")
    assert status == 200 and ctype.startswith("text/html") and b"Health check" in body and b"127.0.0.1" in body
    assert b"<script src=\"/static/demo.js" in body and b"https://" not in body   # bundled: no external script, font or style
    assert shop.handle("GET", "/static/demo.js")[0] == 200 and shop.handle("GET", "/static/site.css")[0] == 200
    assert shop.handle("GET", "/static/../pyproject.toml")[0] == 404 and shop.handle("GET", "/static/nope.js")[0] == 404
    st = json.loads(shop.handle("POST", "/api/step", b'{"step": 3}')[2])
    assert st["current_step"] == 3 and st["steps"][2]["current"] and st["steps"][2]["entered"]
    st = json.loads(shop.handle("POST", "/api/accept", b'{"id": "sug:orders.ship_to_id>addresses"}')[2])
    assert st["plan"]["summary"].startswith("7 tables, 6 with keys, 7 relationships")
    status, _, body = shop.handle("POST", "/api/accept", b'{"id": "ghost"}')
    assert status == 400 and json.loads(body)["kind"] == "bad_input"
    assert shop.handle("GET", "/nope")[0] == 404 and shop.handle("POST", "/api/nope")[0] == 404


def test_connect_from_the_page_replaces_the_source_and_moves_to_step_two(tmp_path):
    s = demo_app.Session()
    status, _, body = s.handle("POST", "/api/connect", b'{"kind": "sample"}')
    st = json.loads(body)
    assert status == 200 and st["current_step"] == 2 and st["source"]["tables"] == 7
    status, _, body = s.handle("POST", "/api/connect", json.dumps({"kind": "folder", "value": str(tmp_path / "missing")}).encode())
    assert status == 400 and "not a folder" in json.loads(body)["error"]
    assert s.state()["source"]["kind"] == "sample"                 # a failed connect keeps the old source
    status, _, body = s.handle("POST", "/api/connect", b'{"kind": "ftp"}')
    assert status == 400


def _xlsx(path, sheets):
    """A minimal .xlsx: shared strings, one date style, several sheets. Enough to prove the reader without openpyxl."""
    strings, cells = [], {}

    def sref(v):
        if v not in strings:
            strings.append(v)
        return strings.index(v)
    sheet_xml = {}
    for i, (name, rows) in enumerate(sheets, 1):
        out = []
        for r, row in enumerate(rows, 1):
            cs = []
            for c, v in enumerate(row):
                ref = chr(65 + c) + str(r)
                if isinstance(v, str):
                    cs.append(f'<c r="{ref}" t="s"><v>{sref(v)}</v></c>')
                elif isinstance(v, tuple):                         # ("date", serial)
                    cs.append(f'<c r="{ref}" s="1"><v>{v[1]}</v></c>')
                elif v is None:
                    continue
                else:
                    cs.append(f'<c r="{ref}"><v>{v}</v></c>')
            out.append(f'<row r="{r}">{"".join(cs)}</row>')
        sheet_xml[f"xl/worksheets/sheet{i}.xml"] = ('<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                                                   f'<sheetData>{"".join(out)}</sheetData></worksheet>')
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("xl/workbook.xml", f'<?xml version="1.0"?><workbook {ns}><sheets>' + "".join(f'<sheet name="{n}" sheetId="{i}" r:id="rId{i}"/>' for i, (n, _) in enumerate(sheets, 1)) + "</sheets></workbook>")
        z.writestr("xl/_rels/workbook.xml.rels", '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   + "".join(f'<Relationship Id="rId{i}" Type="x" Target="worksheets/sheet{i}.xml"/>' for i in range(1, len(sheets) + 1)) + "</Relationships>")
        z.writestr("xl/sharedStrings.xml", '<?xml version="1.0"?><sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">' + "".join(f"<si><t>{s}</t></si>" for s in strings) + "</sst>")
        z.writestr("xl/styles.xml", '<?xml version="1.0"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><cellXfs count="2"><xf numFmtId="0"/><xf numFmtId="14"/></cellXfs></styleSheet>')
        for n, x in sheet_xml.items():
            z.writestr(n, x)


def test_a_folder_of_csv_and_excel_files_becomes_tables_with_keys_relationships_and_questions(tmp_path):
    (tmp_path / "kunder.csv").write_text("KundNr;Namn;Land\n1;Harbour Bikes;DE\n2;Fjord Outdoor;NO\n3;Nordic Pedal;SE\n", encoding="utf-8")
    (tmp_path / "order.csv").write_text("OrderNr;KundNr;Datum;Belopp\n10;1;2026-01-02;12,5\n11;2;2026-01-03;7\n12;2;2026-02-01;3\n13;9;2026-02-02;1\n", encoding="utf-8")
    _xlsx(tmp_path / "artikel.xlsx", [("Blad1", [["ArtikelNr", "Namn", "Pris", "Införd"], [1, "Trail bike", 1200, ("date", 46000)], [2, "Helmet", 80.5, ("date", 46010)]])])
    _xlsx(tmp_path / "noteringar.xlsx", [("Intern", [["Text"], ["ignore me"]]), ("Extern", [["Text", "Datum"], ["hello", ("date", 46020)]])])
    (tmp_path / "~$artikel.xlsx").write_bytes(b"lock file")
    (tmp_path / "readme.txt").write_text("not data", encoding="utf-8")
    src = demo_app.folder_source(tmp_path)
    s = demo_app.Session(src)
    st = s.state()
    assert st["source"]["kind"] == "folder" and st["source"]["schema"] == "data"
    tables = {t["name"]: t for t in st["plan"]["tables"]}
    assert set(tables) == {"kunder", "order", "artikel", "noteringar_Intern", "noteringar_Extern"}
    assert tables["kunder"]["key"] == ["KundNr"] and tables["order"]["key"] == ["OrderNr"] and tables["artikel"]["key"] == ["ArtikelNr"]
    assert [c["type"] for c in tables["order"]["columns"]] == ["int", "int", "date", "real"]
    assert [c["type"] for c in tables["artikel"]["columns"]] == ["int", "text", "real", "date"]
    rels = [(r["source"], r["source_cols"], r["target"], r["rule"]) for r in st["plan"]["relationships"]]
    assert rels == [("order", ["KundNr"], "kunder", "R2")]
    h = st["health"]
    orphan = next(f for f in h["findings"] if f["id"].startswith("rel:order"))
    assert "1 orphan" in orphan["title"] and orphan["severity"] == "warning" and "LEFT JOIN" in orphan["next"]["sql"]
    assert "artikel.xlsx / Blad1 → artikel: 2 rows, 4 columns" in st["source"]["notes"] and "noteringar.xlsx / Extern → noteringar_Extern: 1 rows, 2 columns" in st["source"]["notes"]
    rows = src.execute("SELECT * FROM [data].[artikel] ORDER BY ArtikelNr")
    assert rows[0]["Införd"] == "2025-12-09" and rows[1]["Pris"] == 80.5
    qs = st["questions"]
    assert any(q["id"] == "counts" for q in qs) and all("error" not in q for q in qs)
    counts = next(q for q in qs if q["id"] == "counts")
    assert ["kunder", "3"] in counts["rows"] and ["order", "4"] in counts["rows"]
    src.close()


def test_odd_file_and_column_names_and_bad_files_do_not_stop_the_demo(tmp_path):
    (tmp_path / "2024 sales.csv").write_text('Order "Nr";Kund]Nr;Belopp;--\n1;7;"1,5";x\n2;7;2;y\n', encoding="utf-8")
    (tmp_path / "header only.csv").write_text("a;b\n", encoding="utf-8")
    (tmp_path / "bad.xlsx").write_bytes(b"not a zip")
    src = demo_app.folder_source(tmp_path)
    s = demo_app.Session(src)
    st = s.state()
    tables = {t["name"]: [c["name"] for c in t["columns"]] for t in st["plan"]["tables"]}
    assert tables["t_2024_sales"] == ["Order _Nr_", "Kund_Nr", "Belopp", "--"] and tables["header_only"] == ["a", "b"]
    assert any(n.startswith("bad.xlsx: could not be read") for n in st["source"]["notes"])
    assert st["health"]["checked"] and all("error" not in q for q in st["questions"])      # bracket quoting works on every name
    assert src.execute("SELECT [Kund_Nr] FROM [data].[t_2024_sales]")[0]["Kund_Nr"] == 7
    src.close()


def test_decisions_before_a_source_are_refused_not_crashed():
    s = demo_app.Session()
    for route in ("/api/accept", "/api/skip", "/api/reset"):
        status, _, body = s.handle("POST", route, b'{"id": "x"}')
        assert status == 409 and json.loads(body)["kind"] == "bad_input"
    assert s.handle("POST", "/api/connect", b"{bad")[0] == 400 and s.handle("POST", "/api/step", b'[1]')[0] == 400
    assert s.handle("POST", "/api/step", b'{"step": "x"}')[0] == 400


def test_a_columns_list_gives_the_map_only(tmp_path):
    from tests.test_cli import write_columns
    path = write_columns(tmp_path / "columns.csv")
    s = demo_app.Session(demo_app.columns_source(path, "shop"))
    st = s.state()
    assert not st["source"]["has_data"] and st["plan"]["summary"].startswith("7 tables")
    assert not st["health"]["checked"] and "No rows to check" in st["health"]["summary"]
    assert all(q.get("note") == "needs a connection with rows" for q in st["questions"]) and len(st["questions"]) == 5
    assert "TOP (10)" in st["questions"][0]["sql"]                 # T-SQL for a real server


def test_the_server_binds_to_the_loopback_address_only(shop):
    srv = demo_app.make_server(shop, 0)
    try:
        assert srv.server_address[0] == "127.0.0.1" and srv.server_address[1] > 0
    finally:
        srv.server_close()
    assert demo_app.HOST == "127.0.0.1"
    import inspect
    assert "0.0.0.0" not in inspect.getsource(demo_app) and "--host" not in inspect.getsource(cli)


def test_the_cli_command_exists_with_the_four_sources_and_no_host_flag(capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(["demo", "--help"])
    assert e.value.code == 0
    out = capsys.readouterr().out
    assert "--sample" in out and "--folder" in out and "--odbc" in out and "--columns" in out and "--no-browser" in out and "--host" not in out


def test_sqlite_translation_of_the_engine_sql():
    assert demo_app.sqlite_sql("SELECT TOP (5) [a] FROM [s].[t]") == "SELECT [a] FROM [s].[t]\nLIMIT 5"
    assert demo_app.sqlite_sql("SELECT COUNT_BIG(*) AS n FROM [s].[t]") == "SELECT COUNT(*) AS n FROM [s].[t]"
