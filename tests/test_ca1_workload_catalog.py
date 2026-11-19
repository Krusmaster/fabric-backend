"""CA1: the Model editor's "Publish to OneLake catalog" step (POST /workload/v1/catalog). As the signed-in user, on the
review: a dry run by default that writes nothing and answers the product cards, the diff, the confirm and the handover
files; a write only with the confirm and in a workspace on the operator's list."""
import pytest

pytest.importorskip("jwt")

import golden_support as gs  # noqa: E402
from fabric_backend.catalog_publish import recorded, writes  # noqa: E402
from test_workload_api import SRC, _post, _writes, api, keys, tok  # noqa: E402,F401


def _review(client, priv):
    return _post(client, "/review", SRC, tok(priv)).json()["review"]


def test_the_dry_run_answers_cards_diff_and_handover_and_writes_nothing(api, monkeypatch):
    monkeypatch.delenv(writes.ALLOW_ENV, raising=False)
    client, fake, _, priv = api
    rv = _review(client, priv)
    fake.calls.clear()
    r = _post(client, "/catalog", {**SRC, "review": rv, "owner": "Data team"}, tok(priv))
    assert r.status_code == 200, r.text
    out = r.json()
    assert [c["name"] for c in out["products"]] == ["customers", "products"]
    assert all(c["owner"] == "Data team" for c in out["products"])
    # WB10: the lakehouse is not Krusgraph's: nothing is written to it unless it is ticked (include)
    assert out["confirm"] is None and out["writable"] is False and "Nothing was created" in out["note"]
    assert [(d["item"], d["action"]) for d in out["diff"]] == [("demo_lh", "optional")]
    ticked = _post(client, "/catalog", {**SRC, "review": rv, "include": [gs.LH]}, tok(priv)).json()
    assert ticked["confirm"] and [w["item"] for w in ticked["writes"]] == ["demo_lh"]
    assert "handover/endorsement.md" in out["handover"]["files"]
    assert _writes(fake) == []


def test_a_rejected_link_is_left_out_of_the_cards(api):
    client, _, _, priv = api
    rv = _review(client, priv)
    rel = next(it for it in rv["items"] if it["type"] == "relationship")
    rel["review"] = "rejected"
    out = _post(client, "/catalog", {**SRC, "review": rv}, tok(priv)).json()
    assert [x["id"] for x in out["left_out"]] == [rel["id"]]


def test_writing_is_refused_outside_the_list_and_done_inside_it(api, monkeypatch):
    client, fake, _, priv = api
    # WB2: one minute for the whole test. The cards state the check's time to the minute, and the confirm is a hash of
    # exactly what was shown, so a dry run at 19:09 and a write at 19:10 differ (PR #98's CI, 19 Nov 2026)
    stamp = recorded.with_recorded
    monkeypatch.setattr(recorded, "with_recorded", lambda v, r, now: stamp(v, r, "2026-11-19T19:09Z"))
    rv = _review(client, priv)
    dry = _post(client, "/catalog", {**SRC, "review": rv, "include": [gs.LH]}, tok(priv)).json()
    monkeypatch.delenv(writes.ALLOW_ENV, raising=False)
    no = _post(client, "/catalog", {**SRC, "review": rv, "include": [gs.LH], "dry_run": False, "confirm": dry["confirm"]}, tok(priv)).json()
    assert no["kind"] == "not_allowed" and _writes(fake) == []
    monkeypatch.setenv(writes.ALLOW_ENV, gs.WS)
    real = fake._route

    def route(method, url, body=None):
        if method == "PATCH" and "/items/" in url:
            fake.calls.append((method, url))
            return gs.Response(200, {})
        return real(method, url, body)
    monkeypatch.setattr(fake, "_route", route)
    out = _post(client, "/catalog", {**SRC, "review": rv, "include": [gs.LH], "dry_run": False, "confirm": dry["confirm"]},
                tok(priv)).json()
    assert [r["ok"] for r in out["results"]] == [True] and out["undo"][0]["operation"] == "Items_UpdateItem"
    assert [c[0] for c in _writes(fake)] == ["PATCH"]


def test_bad_input_is_refused(api):
    client, _, _, priv = api
    assert _post(client, "/catalog", {**SRC}, tok(priv)).status_code == 400
    assert _post(client, "/catalog", {**SRC, "review": {}, "dry_run": "no"}, tok(priv)).status_code == 400
