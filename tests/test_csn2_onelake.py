"""CSN2: SAP CSN files in the lakehouse's Files used by the hosted tools and the workload (fabric_backend/csn_onelake.py).

OneLake is faked: a listing and file reads served from tests/fixtures/csn (public SAP samples under Apache-2.0 and
synthetic files; README.md there). The rows are csn_demo's synthetic sample in SQLite. Nothing reaches the network.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import pytest

from fabric_backend import csn, csn_demo, csn_onelake as co, server, workload_api
from fabric_backend.infer import PlanInputError

FIX = Path(__file__).parent / "fixtures" / "csn"
ORDERS = FIX / "synthetic_service_orders.json"
BIKE = FIX / "datasphere_bike_sales_model.json"
WS, ITEM = "11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222"
DOC = Path(__file__).resolve().parent.parent / "docs" / "SAP-CSN.md"


class _Resp:
    def __init__(self, status: int, body: bytes = b"", js=None) -> None:
        self.status_code, self._body, self._js = status, body, js

    def json(self):
        return self._js

    def iter_content(self, n):
        for i in range(0, len(self._body), n):
            yield self._body[i:i + n]

    def close(self):
        pass


class FakeOneLake:
    """files: {path under the item ('Files/krusgraph/csn/x.json'): bytes}. Records every call with its method."""

    def __init__(self, files: dict[str, bytes], status: int = 200) -> None:
        self.files, self.status, self.calls = files, status, []

    def get(self, url, headers=None, timeout=None, stream=False):
        self.calls.append(("GET", url, headers))
        assert headers["Authorization"] == "Bearer lake-token"
        if self.status != 200:
            return _Resp(self.status)
        u = urlparse(url)
        assert u.netloc == co.HOST
        q = parse_qs(u.query)
        if q.get("resource") == ["filesystem"]:
            assert u.path == f"/{WS}" and q["recursive"] == ["false"]
            folder = unquote(q["directory"][0])
            assert folder.startswith(f"{ITEM}/Files/")
            inside = [p for p in self.files if p.rsplit("/", 1)[0] == folder[len(ITEM) + 1:]]
            if not inside and not any(p.startswith(folder[len(ITEM) + 1:] + "/") for p in self.files):
                return _Resp(404)
            return _Resp(200, js={"paths": [{"name": f"{ITEM}/{p}", "contentLength": str(len(self.files[p])),
                                             "isDirectory": "false"} for p in inside]})
        path = unquote(u.path)
        assert path.startswith(f"/{WS}/{ITEM}/")
        rel = path[len(f"/{WS}/{ITEM}/"):]
        return _Resp(200, self.files[rel]) if rel in self.files else _Resp(404)


def _lake(fake) -> co.OneLake:
    return co.OneLake(WS, ITEM, "lake-token", get=fake.get)


# ------------------------------------------------------------------------------------------------ discovery and checks

def test_the_default_folder_is_found_and_only_csn_is_used():
    fake = FakeOneLake({"Files/krusgraph/csn/service_orders.json": ORDERS.read_bytes(),
                        "Files/krusgraph/csn/bikes.csn": BIKE.read_bytes(),
                        "Files/krusgraph/csn/notes.txt": b"hello",
                        "Files/krusgraph/csn/settings.json": json.dumps({"name": "not csn"}).encode(),
                        "Files/krusgraph/csn/broken.json": b"{not json",
                        "Files/krusgraph/csn/noversion.json": json.dumps({"definitions": {}}).encode()})
    found = co.find(_lake(fake))
    assert found.path == "Files/krusgraph/csn"
    assert [u["file"] for u in found.used] == ["Files/krusgraph/csn/bikes.csn", "Files/krusgraph/csn/service_orders.json"]
    why = {s["file"].rsplit("/", 1)[1]: s["why"] for s in found.skipped}
    assert why["notes.txt"].startswith("not a .json or .csn")
    assert "no 'definitions'" in why["settings.json"] and why["broken.json"] == "not JSON"
    assert "no '$version'" in why["noversion.json"]
    assert set(found.model.files) == {u["file"] for u in found.used}
    assert found.model.entity("ZI_ServiceOrder").file == "Files/krusgraph/csn/service_orders.json"
    assert all(c[0] == "GET" for c in fake.calls)                       # read-only: nothing but GET is ever sent


def test_is_csn_accepts_the_three_version_markers_and_nothing_else():
    for f in FIX.glob("*.json"):
        assert co.is_csn(json.loads(f.read_text(encoding="utf-8")))[0], f.name
    assert co.is_csn({"definitions": {}, "csnInteropEffective": "1.0"})[0]
    assert co.is_csn({"definitions": {}, "version": {"csn": "0.1.0"}})[0]
    assert not co.is_csn({"definitions": {}, "version": "1.0"})[0]
    assert not co.is_csn([{"definitions": {}}])[0]


def test_a_missing_default_folder_says_nothing_and_an_asked_path_says_why():
    fake = FakeOneLake({})
    found = co.find(_lake(fake))
    assert found.model is None and not found.worth_saying()
    asked = co.find(_lake(fake), "Files/sap/model.json")
    assert asked.worth_saying() and asked.not_read["kind"] == "missing" and "Upload" in asked.not_read["hint"]


def test_one_file_by_path():
    fake = FakeOneLake({"Files/sap/exports/model.json": ORDERS.read_bytes(), "Files/sap/exports/other.json": BIKE.read_bytes()})
    found = co.find(_lake(fake), "sap/exports/model.json")
    assert [u["file"] for u in found.used] == ["Files/sap/exports/model.json"]
    assert not any("resource=filesystem" in c[1] for c in fake.calls)   # a file is read, not listed


def test_access_denied_is_reported_with_the_permission_and_never_raises():
    found = co.find(_lake(FakeOneLake({}, status=403)), "Files/krusgraph/csn")
    assert found.model is None and found.not_read["kind"] == "denied"
    assert co.DELEGATED in found.not_read["why"] and co.DELEGATED in found.not_read["hint"]


def test_size_limits(monkeypatch):
    monkeypatch.setattr(co, "MAX_FILE_BYTES", 1000)
    monkeypatch.setattr(co, "MAX_FILES", 1)
    big = b'{"$version":"2.0","definitions":{}}' + b" " * 2000
    fake = FakeOneLake({"Files/krusgraph/csn/a.json": b'{"$version":"2.0","definitions":{}}',
                        "Files/krusgraph/csn/b.json": big, "Files/krusgraph/csn/c.json": b'{"$version":"2.0","definitions":{}}'})
    found = co.find(_lake(fake))
    why = {s["file"].rsplit("/", 1)[1]: s["why"] for s in found.skipped}
    assert "larger than" in why["b.json"] and "more than 1 files" in why["c.json"]
    assert [u["file"] for u in found.used] == ["Files/krusgraph/csn/a.json"]
    assert not any(c[1].endswith("/b.json") for c in fake.calls)       # a file over the limit is not opened


def test_a_file_larger_than_its_listing_said_is_cut_off(monkeypatch):
    monkeypatch.setattr(co, "MAX_FILE_BYTES", 100)
    lake = _lake(FakeOneLake({"Files/x/a.json": b" " * 500}))
    with pytest.raises(co.NotRead, match="larger than"):
        lake.read("Files/x/a.json", 100)


@pytest.mark.parametrize("bad", ["../secrets", "Files/../Tables/x", "https://evil.example/x.json", "C:/x.json",
                                 "Tables/dbo/x", "Files\\x.json"])
def test_paths_stay_under_files(bad):
    with pytest.raises(ValueError):
        co.clean_path(bad)


def test_paths_are_normalised_under_files():
    assert co.clean_path(None) == co.DEFAULT_DIR == "Files/krusgraph/csn"
    assert co.clean_path("/Files/sap/") == "Files/sap"
    assert co.clean_path("sap/model.json") == "Files/sap/model.json"
    assert co.clean_path("files/sap") == "Files/sap"


def test_the_module_sends_only_get_and_keeps_nothing():
    src = Path(co.__file__).read_text(encoding="utf-8")
    code = src.split('"""', 2)[2]                                       # the code, not the docstring
    for verb in ("requests.put", "requests.post", "requests.patch", "requests.delete", "open(", "write_", ".write(",
                 "tempfile", "cache"):
        assert verb not in code, verb


# ------------------------------------------------------------------------------------------------ the hosted tools

@pytest.fixture
def hosted(monkeypatch):
    """The hosted server over the CSN sample's SQLite rows, with a lakehouse whose Files hold the CSN file."""
    src = csn_demo.source()
    fake = FakeOneLake({"Files/krusgraph/csn/service_orders.json": ORDERS.read_bytes(),
                        "Files/krusgraph/csn/readme.md": b"# notes"})
    monkeypatch.setattr(co, "_http_get", fake.get)
    monkeypatch.setattr(server, "_headers", lambda ctx: {"Authorization": "Bearer fabric"})
    monkeypatch.setattr(server, "_workspace_id", lambda w, h: WS)
    item = {"type": "Lakehouse", "id": ITEM, "displayName": "sap_landing", "sql_host": "x", "sql_db": "sap_landing"}
    monkeypatch.setattr(server, "_resolve_source", lambda ws, s, h: dict(item))
    monkeypatch.setattr(server.auth, "sql", lambda ctx: "sql")
    monkeypatch.setattr(server.auth, "onelake", lambda ctx: "lake-token")

    def execute_factory(it, tok):
        def run(sql, *a, **k):
            return src.execute(sql, *a, **k)
        run.dialect = getattr(src.execute, "dialect", None)
        return run
    monkeypatch.setattr(server, "_execute_factory", execute_factory)
    monkeypatch.setattr(server._fabric.PLATFORM, "read_schema", lambda execute, schema: csn_demo.schema(schema))
    monkeypatch.setattr(server, "limiter", None)
    return fake, item


def test_plan_backend_uses_the_csn_in_files_and_names_the_file(hosted):
    fake, _ = hosted
    out = json.loads(server.plan_backend("ws", "sap_landing", csn_demo.SCHEMA, detail="full"))
    c = out["csn"]
    assert c["provenance"] == csn.PROVENANCE == "declared by metadata (CSN)"
    assert c["files"] == ["Files/krusgraph/csn/service_orders.json"]
    assert len(c["keys"]) == 5 and len(c["links"]) == 4
    assert {k["file"] for k in c["keys"]} == {"Files/krusgraph/csn/service_orders.json"}
    assert all(d["file"] == "Files/krusgraph/csn/service_orders.json" for link in c["links"] for d in link["declared_in"])
    assert c["lakehouse"]["looked_in"] == "Files/krusgraph/csn"
    assert c["lakehouse"]["skipped"] == [{"file": "Files/krusgraph/csn/readme.md", "why": "not a .json or .csn file; not opened"}]
    assert any(a["column"] == "TOTALNETAMOUNT" and a["level"] == "header" for a in c["amounts"])
    assert all(m == "GET" for m, _, _ in fake.calls)


def test_validate_plan_counts_the_csn_keys_and_links_in_the_rows(hosted):
    out = json.loads(server.validate_plan("ws", "sap_landing", csn_demo.SCHEMA, detail="full"))
    assert out["csn"]["files"] == ["Files/krusgraph/csn/service_orders.json"]
    keys = {k["table"]: k for k in out["keys"]}
    assert not str(keys["dsp_zi_customer"]["verdict"]).startswith("unique")      # the CSN declared it; the rows refute it
    rels = [r for r in out["relationships"] if r["source"] == "dsp_zi_serviceorderitem" and r["target"] == "dsp_zi_serviceorder"]
    assert rels and rels[0]["orphans"] == 1
    assert csn_demo.EXPECTED["keys_unique"] == sum(1 for k in out["keys"] if str(k.get("verdict", "")).startswith("unique"))


def test_without_the_folder_the_plan_is_as_before(hosted, monkeypatch):
    fake, _ = hosted
    fake.files.clear()
    out = json.loads(server.plan_backend("ws", "sap_landing", csn_demo.SCHEMA, detail="full"))
    assert "csn" not in out
    assert not any(r.get("rule") == csn.RULE for r in out.get("relationships", []))


def test_switched_off_the_default_folder_is_not_read_but_a_path_still_is(hosted, monkeypatch):
    fake, _ = hosted
    monkeypatch.setenv(co.SWITCH, "0")
    out = json.loads(server.plan_backend("ws", "sap_landing", csn_demo.SCHEMA, detail="full"))
    assert "csn" not in out and fake.calls == []
    out = json.loads(server.plan_backend("ws", "sap_landing", csn_demo.SCHEMA, detail="full",
                                         csn_path="Files/krusgraph/csn/service_orders.json"))
    assert out["csn"]["files"] == ["Files/krusgraph/csn/service_orders.json"]


def test_a_path_outside_files_is_refused(hosted):
    out = json.loads(server.plan_backend("ws", "sap_landing", csn_demo.SCHEMA, csn_path="../../Tables/x"))
    assert "error" in out and "Files" in out["error"]


def test_a_warehouse_has_no_files_and_an_asked_path_says_so(hosted, monkeypatch):
    _, item = hosted
    monkeypatch.setattr(server, "_resolve_source", lambda ws, s, h: {**item, "type": "Warehouse"})
    out = json.loads(server.plan_backend("ws", "sap_landing", csn_demo.SCHEMA, detail="full", csn_path="Files/x"))
    assert out["csn"]["lakehouse"]["not_read"]["kind"] == "not_a_lakehouse"


def test_no_onelake_sign_in_never_fails_the_plan(hosted, monkeypatch):
    def no_consent(ctx):
        raise RuntimeError("AADSTS65001: consent")
    monkeypatch.setattr(server.auth, "onelake", no_consent)
    out = json.loads(server.plan_backend("ws", "sap_landing", csn_demo.SCHEMA, detail="full"))
    assert "csn" not in out and out.get("relationships") is not None
    out = json.loads(server.plan_backend("ws", "sap_landing", csn_demo.SCHEMA, detail="full", csn_path="Files/krusgraph/csn"))
    assert out["csn"]["lakehouse"]["not_read"]["kind"] == "no_sign_in"
    assert "AADSTS" not in json.dumps(out["csn"])                     # the error class, never the message


def test_the_contents_are_never_logged(hosted, caplog):
    caplog.set_level(logging.DEBUG)
    server.plan_backend("ws", "sap_landing", csn_demo.SCHEMA)
    text = caplog.text
    assert "files_used=1" in text
    for word in ("ZI_ServiceOrder", "SERVICEORDER", "service_orders.json", "definitions"):
        assert word not in text


def test_the_onelake_token_is_the_users_never_the_servers(monkeypatch):
    a = server.Auth()
    a.entra = None
    monkeypatch.setattr(a, "_client_credentials", lambda scope: pytest.fail("no client credentials for OneLake"))
    assert a.onelake(None) is None
    ctx = type("C", (), {"headers": {"X-OneLake-Token": " t "}})()
    assert a.onelake(ctx) == "t"


# ------------------------------------------------------------------------------------------------ the workload

def test_the_workload_tokens_ask_for_the_storage_audience():
    class OBO:
        def token(self, user, tenant, scope):
            return f"{scope}"
    assert workload_api.Tokens(OBO(), "u", "t").onelake() == co.STORAGE_SCOPE == "https://storage.azure.com/.default"


def test_the_workload_review_and_check_carry_the_csn(hosted):
    req = workload_api.review_request({"workspace": WS, "source": ITEM, "source_name": "sap_landing",
                                       "schema": csn_demo.SCHEMA})
    out = workload_api.run_review(req)
    assert out["csn"]["files"] == ["Files/krusgraph/csn/service_orders.json"]
    assert len(out["csn"]["keys"]) == 5
    chk = workload_api.check_request({"workspace": WS, "source": ITEM, "source_name": "sap_landing",
                                      "schema": csn_demo.SCHEMA, "review": out["review"]})
    done = workload_api.run_check(chk)
    assert done["csn"]["files"] == ["Files/krusgraph/csn/service_orders.json"]


def test_the_workload_takes_a_csn_path_and_refuses_one_outside_files():
    base = {"workspace": WS, "source": ITEM, "schema": "dbo"}
    assert workload_api.review_request({**base, "csn_path": "sap/x.json"})["csn_path"] == "Files/sap/x.json"
    assert "csn_path" not in workload_api.review_request(base)
    with pytest.raises(workload_api.BadRequest):
        workload_api.review_request({**base, "csn_path": "../x"})


# ------------------------------------------------------------------------------------------------ docs

def test_the_docs_say_how_to_use_it_in_fabric_and_claim_nothing():
    text = DOC.read_text(encoding="utf-8")
    assert "Files/krusgraph/csn/" in text and "csn_path" in text and "user_impersonation" in text and "Azure Storage" in text
    assert "How to use it in Fabric" in text
    low = text.lower()
    for word in ("certified by", "sap-certified", "compatible with sap", "endorsed by sap"):
        assert word not in low
