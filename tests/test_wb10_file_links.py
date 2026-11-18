"""WB10 (Gustav's live test in Fabric, 18 Nov 2026, #57): downloads inside Fabric's sandboxed frame. The editor sends
the file to POST /workload/v1/file and opens the answer's path with the host's openBrowserTab; GET serves it once, with
Content-Disposition: attachment, for ten minutes, behind a signed token; nothing of the file is in the URL or the log."""
import base64
import json

import pytest

pytest.importorskip("jwt")

from fabric_backend import file_links as fl, operations, registration_store as rs, workload_api  # noqa: E402
from test_workload_api import _post, api, keys, tok  # noqa: E402,F401

SECRET_TEXT = "<mxfile><diagram name='shop_lh.shop'>customers -> orders</diagram></mxfile>"


@pytest.fixture(autouse=True)
def store():
    s = rs.MemoryStore()
    operations.use_store(s)
    yield s
    operations.use_store(None)


def _get(client, path):
    return client.get(path)


def test_a_file_is_served_once_as_an_attachment(api, capsys):
    client, fake, _, priv = api
    r = _post(client, "/file", {"filename": "shop_lh.shop-map.drawio", "mime": "application/xml", "content": SECRET_TEXT}, tok(priv))
    assert r.status_code == 200, r.text
    out = r.json()
    path = out["path"]
    assert path.startswith("/workload/v1/file/") and out["expires_in"] == 600
    assert "shop" not in path and "mxfile" not in path                                  # no data in the URL
    got = _get(client, path)
    assert got.status_code == 200 and got.text == SECRET_TEXT
    assert got.headers["content-disposition"].startswith('attachment; filename="shop_lh.shop-map.drawio"')
    assert got.headers["cache-control"] == "no-store" and got.headers["referrer-policy"] == "no-referrer"
    again = _get(client, path)
    assert again.status_code == 410 and "already used" in again.text                  # single use
    logged = capsys.readouterr().out + capsys.readouterr().err
    assert "shop_lh" not in logged and "mxfile" not in logged                         # nothing personal in the log


def test_a_binary_file_comes_back_byte_for_byte(api):
    client, _, _, priv = api
    blob = bytes(range(256)) * 400
    r = _post(client, "/file", {"filename": "app.zip", "mime": "application/zip",
                                "content_base64": base64.b64encode(blob).decode()}, tok(priv)).json()
    assert _get(client, r["path"]).content == blob


def test_the_link_expires_and_a_forged_signature_is_refused(store):
    out = fl.offer(b"x" * 10, "a.md", "text/markdown", now=1_000_000)
    token = out["path"].rsplit("/", 1)[1]
    assert fl.take(token, now=1_000_000 + fl.TTL + 1) == "expired"
    file_id, exp, sig = token.split(".")
    assert fl.take(f"{file_id}.{int(exp) + 3600}.{sig}", now=1_000_000) == "bad"          # a longer life cannot be forged
    assert fl.take("../../etc/passwd") == "bad"
    assert fl.take(token, now=1_000_000 + 5) == (b"x" * 10, "a.md", "text/markdown")


def test_a_large_file_is_cut_into_parts_that_fit_table_storage(store):
    import os
    data = os.urandom(200_000)                                                         # does not compress
    out = fl.offer(data, "big.zip", "application/zip")
    file_id = out["path"].rsplit("/", 1)[1].split(".")[0]
    head = store.get("op", f"file-{file_id}")[0]
    assert head["parts"] > 5
    assert all(len(json.dumps(store.get("op", f"file-{file_id}-p{n}")[0])) < 32_000 for n in range(head["parts"]))
    assert fl.take(out["path"].rsplit("/", 1)[1])[0] == data


def test_the_route_needs_a_sign_in_and_refuses_what_it_does_not_offer(api):
    client, _, _, priv = api
    assert _post(client, "/file", {"filename": "a.md", "mime": "text/markdown", "content": "x"}, None).status_code == 401
    assert _post(client, "/file", {"filename": "a.html", "mime": "text/html", "content": "<script>"}, tok(priv)).status_code == 400
    assert _post(client, "/file", {"filename": "a.md", "mime": "text/markdown"}, tok(priv)).status_code == 400
    big = "x" * (fl.MAX_BYTES + 1)
    assert _post(client, "/file", {"filename": "a.md", "mime": "text/markdown", "content": big}, tok(priv)).status_code == 400
    assert _get(client, "/workload/v1/file/not-a-token").status_code == 404


def test_names_are_made_safe_for_the_header():
    assert fl.safe_name("contracts/customers.odcs.yaml") == "customers.odcs.yaml"
    assert fl.safe_name('a"b\r\nc.md') == "a-b-c.md"
    assert fl.disposition("handover/fabric-admin.md") == "attachment; filename=\"fabric-admin.md\"; filename*=UTF-8''fabric-admin.md"
    assert workload_api.PREFIX == "/workload/v1"
