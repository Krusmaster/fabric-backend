"""WB5: SAP in the workload item. (1) A CSN chosen in the editor travels with the request and is used like a CSN in the
lakehouse's Files, validated, size-capped, never logged. (2) The SAP pack's fields in plain words, only from what the pack
documents. (3) "Load SAP demo data": the sap_demo36 generator notebook, dry run then create, never run. Synthetic data only."""
import json

import pytest

from fabric_backend import csn_demo, csn_onelake as co, mirroring, sap_pack, workload_api
from test_csn2_onelake import ITEM, ORDERS, WS, hosted  # noqa: F401  (fixture)
from test_n201_mirrored import keys, make  # noqa: F401  (fixtures)
from test_workload_api import api  # noqa: F401,E402  (fixture)


BASE = {"workspace": WS, "source": ITEM, "source_name": "sap_landing", "schema": csn_demo.SCHEMA}


def _upload():
    return {"name": "service_orders.json", "csn": json.loads(ORDERS.read_text(encoding="utf-8"))}


def test_an_uploaded_csn_is_used_and_said_to_come_from_the_editor(hosted, capsys):
    fake, _ = hosted
    fake.files.clear() if hasattr(fake, "files") else None
    out = workload_api.run_review(workload_api.review_request({**BASE, "csn_upload": _upload()}))
    assert out["csn"]["files"] == ["service_orders.json"]
    assert len(out["csn"]["keys"]) == 5
    assert out["csn"]["lakehouse"]["where"] == co.FROM_EDITOR
    chk = workload_api.run_check(workload_api.check_request({**BASE, "review": out["review"], "csn_upload": _upload()}))
    assert chk["csn"]["files"] == ["service_orders.json"]
    logged = capsys.readouterr().out
    assert "definitions" not in logged and "service_orders" not in logged        # the CSN is never logged


def test_an_uploaded_file_that_is_not_csn_is_reported_and_the_plan_goes_on(hosted):
    out = workload_api.run_review(workload_api.review_request({**BASE, "csn_upload": {"name": "x.json", "csn": {"a": 1}}}))
    assert out["review"]["items"]                                                  # planned without it
    lake = out.get("csn", {}).get("lakehouse") or {}
    assert lake.get("not_read", {}).get("kind") == "not_csn"


def test_the_upload_is_checked_and_size_capped():
    with pytest.raises(workload_api.BadRequest):
        workload_api.review_request({**BASE, "csn_upload": {"name": "x.json", "csn": "not an object"}})
    with pytest.raises(workload_api.BadRequest):
        workload_api.review_request({**BASE, "csn_upload": {"name": "x" * 200, "csn": {}}})
    big = {"definitions": {"x": {"doc": "a" * (co.MAX_FILE_BYTES + 10)}}}
    with pytest.raises(workload_api.BadRequest):
        workload_api.review_request({**BASE, "csn_upload": {"name": "big.json", "csn": big}})
    assert "csn_upload" not in workload_api.review_request(BASE)


def test_sap_fields_say_only_what_the_pack_documents():
    from fabric_backend.schema import Column, Table
    from types import SimpleNamespace
    pack = sap_pack.load("sap")
    vbak = Table("VBAK", [Column(c) for c in ("MANDT", "VBELN", "KUNNR", "ERDAT", "NETWR")])
    plan = SimpleNamespace(schema=[vbak])
    got = {r["column"]: r["words"] for r in mirroring.sap_fields(plan, pack, {"VBAK": "VBAK"})["VBAK"]}
    assert got["MANDT"] == mirroring.CLIENT_WORDS
    assert got["VBELN"].startswith("part of the key")
    assert "ERDAT" not in got and "NETWR" not in got                               # the pack says nothing: left out
    assert all(c in [c.name for c in vbak.columns] for c in got)
    assert mirroring.sap_fields(plan, pack, {}) == {}                             # not a pack table: nothing


def test_the_review_of_sap_tables_carries_the_fields_in_plain_words(make):
    from test_n201_mirrored import SAP_SRC, _post, sap_endpoint
    client, _fake, priv, _sql = make(sap_endpoint)
    a = _post(client, "/review", {**SAP_SRC, "decisions": []}, priv).json()
    fields = a["sap"]["fields"]
    vbak = {r["column"]: r["words"] for r in fields["VBAK"]}
    assert vbak["MANDT"] == mirroring.CLIENT_WORDS and vbak["VBELN"].startswith("part of the key")
    assert any("links to the customer" in w or "links to the sold to" in w for w in vbak.values()), vbak


# ------------------------------------------------------------------ 3. Load SAP demo data --------------------------------

def test_load_sap_demo_data_is_a_dry_run_first_then_one_notebook_never_run(api):
    import base64
    import golden_support as gs
    from test_workload_api import SRC, _post, _writes, tok
    client, fake, _, priv = api
    body = {**SRC, "source": gs.LH}
    fake.calls.clear()
    dry = _post(client, "/sap-demo", body, tok(priv)).json()
    assert dry["would"] == "create" and dry["runs"] is False and dry["confirm"].startswith("sapdemo-")
    assert dry["target_schema"] == "sap_demo36" and "does not run it" in dry["words"] and dry["tables"] >= 10
    assert _writes(fake) == [] and not fake.created
    no = _post(client, "/sap-demo", {**body, "dry_run": False, "confirm": "sapdemo-0"}, tok(priv)).json()
    assert no["kind"] == "not_allowed" and not fake.created
    out = _post(client, "/sap-demo", {**body, "dry_run": False, "confirm": dry["confirm"]}, tok(priv)).json()
    assert out["would"] == "created" and out["created"]["output"] == "sap_demo36"
    assert [c["route"] for c in fake.created] == ["notebooks"]
    src = base64.b64decode(fake.created[0]["body"]["definition"]["parts"][0]["payload"]).decode()
    assert "DRY_RUN = True" in src and '"sap_demo36"' in src and "REFUSED" in src       # never writes until the person says so
    assert "nothing was run" in out["note"].lower()


def test_load_sap_demo_data_refuses_dbo_silver_and_gold(api):
    import golden_support as gs
    from test_workload_api import SRC, _post, tok
    client, _, _, priv = api
    for bad in ("dbo", "sap_silver", "SAP_GOLD", "a b"):
        assert _post(client, "/sap-demo", {**SRC, "source": gs.LH, "target_schema": bad}, tok(priv)).status_code == 400
