"""WB10 (Gustav's live test in Fabric, 18 Nov 2026, #64): the Data Science starter is created in the workspace like the
other next steps: a dry run first that creates nothing, then Create with the dry run's confirm. Krusgraph never runs the
notebook, trains no model and never overwrites an item of the same name. Synthetic shop schema and Fabric doubles."""
import base64

import pytest

pytest.importorskip("jwt")

import golden_support as gs  # noqa: E402
from fabric_backend import billing  # noqa: E402
from test_workload_api import SRC, _post, _writes, api, keys, tok  # noqa: E402,F401

CELLS = ["# Krusgraph starter\nprint('cell 1')", "from pyspark.sql import functions as F\nparent = spark.read.table('`shop`.`orders`')"]
BODY = {**SRC, "source": gs.LH, "name": "orders_features", "cells": CELLS}


def test_the_dry_run_says_what_would_be_created_and_creates_nothing(api):
    client, fake, _, priv = api
    fake.calls.clear()
    out = _post(client, "/starter", BODY, tok(priv)).json()
    assert out["would"] == "create" and out["runs"] is False and out["confirm"].startswith("starter-")
    assert "runs it only when you choose Run now" in out["words"] and "attached to demo_lh" in out["words"] and out["cells"] == 2
    assert _writes(fake) == [] and not fake.created


def test_create_needs_the_dry_runs_confirm_and_makes_one_notebook_attached_to_the_lakehouse(api):
    client, fake, _, priv = api
    dry = _post(client, "/starter", BODY, tok(priv)).json()
    no = _post(client, "/starter", {**BODY, "dry_run": False, "confirm": "starter-0000"}, tok(priv)).json()
    assert no["kind"] == "not_allowed" and not fake.created
    out = _post(client, "/starter", {**BODY, "dry_run": False, "confirm": dry["confirm"]}, tok(priv)).json()
    assert out["would"] == "created" and out["created"]["output"] == "ds_features" and out["created"]["type"] == "Notebook"
    assert [c["route"] for c in fake.created] == ["notebooks"]
    body = fake.created[0]["body"]
    assert body["displayName"] == "orders_features"
    src = base64.b64decode(body["definition"]["parts"][0]["payload"]).decode()
    assert "print('cell 1')" in src and gs.LH in src                      # the cells, and the default lakehouse
    assert "nothing was run" in out["note"].lower()


def test_an_item_of_the_same_name_is_never_overwritten(api, monkeypatch):
    client, fake, _, priv = api
    monkeypatch.setattr(gs, "ITEMS", gs.ITEMS + [{"id": "nb-1", "displayName": "orders_features", "type": "Notebook"}])
    out = _post(client, "/starter", BODY, tok(priv)).json()
    assert out["would"] == "exists" and out["confirm"] is None and "does not overwrite" in out["words"]
    again = _post(client, "/starter", {**BODY, "dry_run": False, "confirm": "starter-x"}, tok(priv)).json()
    assert again["would"] == "exists" and not fake.created


def test_bad_input_is_refused(api):
    client, _, _, priv = api
    assert _post(client, "/starter", {**BODY, "name": "a b"}, tok(priv)).status_code == 400
    assert _post(client, "/starter", {**BODY, "cells": []}, tok(priv)).status_code == 400
    assert _post(client, "/starter", {**BODY, "cells": ["x" * 70_000]}, tok(priv)).status_code == 400


def test_create_counts_as_a_write_for_the_trial():
    assert billing.route_writes("starter", {"dry_run": False}) is True
    assert billing.route_writes("starter", {"dry_run": True}) is False
