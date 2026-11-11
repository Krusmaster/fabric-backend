"""Round n207: Create never adopts or overwrites an item it did not build.

The audit of main (11 November 2026): the editor records each step's own item names as pending in outputs.json before
it sends the step (createRun.withPending), and the engine adopted any existing item of a pending name as its own
(workload_api._pending, n197). So with a colleague's notebook or semantic model of the same name, the dry run said
"already exists in this workspace and was not built by this Krusgraph Model; nothing was written", and Create then
answered "Fabric finished it after the wait" and kept it as built by this Model; the pipeline step called
updateDefinition on the colleague's notebook, and with skip_built false a semantic model was overwritten directly.

Now a pending entry adopts an existing item only when Krusgraph made it (its description, workload_api._krusgraph_made)
or when Fabric's listing gives a creation time later than the entry's `at`; with no creation time it is not adopted,
and Create says what the dry run says. n197's purpose stands: an item this Model's own Create started and Fabric
finished after the wait is still adopted (tests/test_n197_background.py), so a retry does not orphan it. The editor
sends no step its dry run refused (createEach in buildWords.ts, workload/Workload/app/items/ModelItem/createEach.test.ts).
"""
from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("jwt")

from test_workload_api import SRC  # noqa: E402,F401
from test_workload_build import NEW_SM  # noqa: E402
from test_workload_api import keys  # noqa: E402,F401
from test_workload_create import Workspace, _one, _post, _review, make  # noqa: E402,F401
from fabric_backend import workload_api  # noqa: E402

SENT = "2026-11-11T08:00:00.000Z"                                   # when the editor recorded the step as pending
OUTPUTS = [
    {"kind": "silver_notebook", "name": "their_silver"},
    {"kind": "gold_views", "name": "their_gold"},
    {"kind": "pipeline", "name": "their_flow"},
    {"kind": "semantic_model", "name": "their_model"},
    {"kind": "report", "name": "their_report", "model": NEW_SM},        # on a model built earlier (its id)
    {"kind": "graphql", "name": "their_api"},
    {"kind": "ontology", "name": "their_onto"},
    {"kind": "data_agent", "name": "their_agent"},
    {"kind": "rayfin_app", "name": "their_app"},
]


def _theirs(output: dict, **extra) -> list[dict]:
    """A colleague's items with the output's own names, made by hand (no Krusgraph description)."""
    chosen = {output["kind"]: output["name"]}
    return [{"id": f"theirs-{i}", "displayName": name, "type": typ, "description": "made by hand", **extra}
            for i, (typ, name) in enumerate(workload_api._names(output, chosen, "shop"))]


def _pending_of(items: list[dict], output: dict, at=SENT) -> list[dict]:
    """outputs.json's pending list as the editor sends it (createRun.withPending)."""
    return [{"output": output["kind"], "type": it["type"], "name": it["displayName"], "at": at} for it in items]


def _writes_on(fake, ids) -> list:
    """Every call that writes to (or updates the definition of) one of these items."""
    return [c for c in fake.calls if c[0] != "GET" and not c[1].endswith("/getDefinition") and any(i in c[1] for i in ids)]


def _creates(fake) -> list:
    """Every create of a new item (POST /workspaces/{ws}/{collection})."""
    return [c for c in fake.calls if c[0] == "POST" and c[1].split("/")[-1] in (
        "notebooks", "dataPipelines", "semanticModels", "reports", "graphQLApis", "ontologies", "dataAgents", "appBackends", "items")]


@pytest.mark.parametrize("output", OUTPUTS, ids=[o["kind"] for o in OUTPUTS])
@pytest.mark.parametrize("skip_built", [True, False], ids=["skip_built", "no_skip_built"])
def test_a_foreign_item_of_the_same_name_is_refused_even_when_the_editor_lists_it_as_pending(make, output, skip_built):
    there = _theirs(output)
    client, fake, priv = make(Workspace(items=there))
    rv = _review(client, priv)
    dry = _post(client, "/build", {**SRC, "review": rv, "outputs": [output], "dry_run": True, "created": []}, priv).json()
    said = dry["outputs"][0]["refusal"]
    assert said["kind"] == "already_exists" and "was not built by this Krusgraph Model" in said["error"], dry["outputs"][0]
    fake.calls.clear()
    r = _one(client, priv, rv, output, skip_built=skip_built, pending=_pending_of(there, output), only=[output["kind"]])
    assert r.status_code == 200, r.text
    card = r.json()["outputs"][0]
    assert not card.get("already_built") and not card.get("created"), card
    assert card["refusal"]["kind"] == "already_exists" and card["refusal"]["error"] == said["error"], card
    assert "Fabric finished it" not in str(card)
    assert not _writes_on(fake, [it["id"] for it in there]), fake.calls     # no updateDefinition, no overwrite, no PATCH
    assert not any(c[1].endswith("/updateDefinition") for c in fake.calls), fake.calls
    assert not _creates(fake), fake.calls


def test_a_foreign_item_created_before_the_step_was_sent_is_not_adopted(make):
    """Where Fabric's listing carries a creation time, an item made before the pending entry's `at` is not this Model's."""
    output = {"kind": "semantic_model", "name": "their_model"}
    before = (datetime(2026, 11, 11, 8, 0, tzinfo=timezone.utc) - timedelta(days=3)).isoformat().replace("+00:00", "Z")
    there = _theirs(output, createdDate=before)
    client, fake, priv = make(Workspace(items=there))
    rv = _review(client, priv)
    r = _one(client, priv, rv, output, skip_built=False, pending=_pending_of(there, output), only=[output["kind"]])
    assert r.json()["outputs"][0]["refusal"]["kind"] == "already_exists"
    assert not _writes_on(fake, ["theirs-0"]), fake.calls


def test_an_item_created_after_the_step_was_sent_is_adopted(make):
    """An item this Model's Create sent, finished by Fabric after the wait: its creation time is later than `at`, so it
    is adopted even without Krusgraph's description (a description Fabric did not keep)."""
    output = {"kind": "semantic_model", "name": "demo_lh_model4"}
    later = "2026-11-11T08:04:31.250Z"
    there = _theirs(output, createdDate=later)
    client, fake, priv = make(Workspace(items=there))
    rv = _review(client, priv)
    r = _one(client, priv, rv, output, pending=_pending_of(there, output), only=[output["kind"]])
    card = r.json()["outputs"][0]
    assert not card.get("refusal") and card["already_built"] and card["answer"]["adopted"] == 1, card
    assert card["created"][0]["id"] == "theirs-0" and "Fabric finished it" in card["answer"]["note"]


def test_an_item_this_model_started_and_fabric_finished_late_is_adopted(make):
    """n197's purpose (demo_lh_model4): the item carries Krusgraph's description, written by the create Fabric finished
    after the editor's wait; with its pending entry it is adopted, so Try again does not orphan it."""
    output = {"kind": "semantic_model", "name": "demo_lh_model4"}
    there = [{"id": "late-sm", "displayName": "demo_lh_model4", "type": "SemanticModel", "description": "Created by Krusgraph"}]
    client, fake, priv = make(Workspace(items=there))
    rv = _review(client, priv)
    r = _one(client, priv, rv, output, pending=_pending_of(there, output), only=[output["kind"]])
    card = r.json()["outputs"][0]
    assert not card.get("refusal") and card["already_built"] and card["created"][0]["id"] == "late-sm", card


def test_the_pending_entrys_time_reaches_the_engine():
    req = {"pending": [{"output": "semantic_model", "type": "SemanticModel", "name": "m", "at": SENT}]}
    assert workload_api._pending_at(req, "SemanticModel", "M") == [datetime(2026, 11, 11, 8, 0, tzinfo=timezone.utc)]
    assert workload_api._pending_at({"pending": [{"type": "SemanticModel", "name": "m"}]}, "SemanticModel", "m") == []
    assert workload_api._created_at({"createdDate": "2026-11-11T08:04:31.25Z"}) > workload_api._pending_at(req, "SemanticModel", "m")[0]
    assert workload_api._created_at({"description": "made by hand"}) is None
