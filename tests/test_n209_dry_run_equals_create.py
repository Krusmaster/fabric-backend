"""Round n209, item 1: the dry run predicts what Create does.

The founder's live tests of 10 November 2026: the dry run showed red "already exists ... not built by this Krusgraph
Model" for items another Krusgraph Model item had built from the same plan, and Create then said "already built from
this plan by an earlier Create"; and the dry run said 6 items "would be updated" while Create on the same plan said
"already built ... nothing was written again". Now both ask one decision function (workload_api.existing_decision) and
every card carries its `decision` (workload_api.decision_of): skip (already built from this plan, will be skipped), choose
(built from another plan or plan unknown: Create writes nothing and asks Update or a new name), refuse (a foreign item,
n207's rule; a report is never updated), update (Create really writes), create. These tests run the dry run and then
Create on the same workspace and check that each output's decision is the same, and that "update" and "create" appear
only where Create writes."""
import pytest

pytest.importorskip("jwt")

from test_workload_api import SRC, keys  # noqa: E402,F401
from test_workload_create import _one, _post, _review, make  # noqa: E402,F401
from test_workload_plans import Defined  # noqa: E402
from fabric_backend import workload_api  # noqa: E402

OUTPUTS = [
    {"kind": "silver_notebook", "name": "shop_silver"},
    {"kind": "gold_views", "name": "shop_gold"},
    {"kind": "pipeline", "name": "shop_flow"},
    {"kind": "semantic_model", "name": "n209_model"},
    {"kind": "graphql", "name": "n209_api"},
    {"kind": "ontology", "name": "shop_onto"},
]
WRITES = ("POST", "PATCH")


def _dry(client, priv, rv, created=(), pending=()):
    body = {**SRC, "review": rv, "outputs": OUTPUTS, "dry_run": True, "product": None, "created": list(created),
            "pending": list(pending)}
    r = _post(client, "/build", body, priv)
    assert r.status_code == 200, r.text
    return {c["output"]: c for c in r.json()["outputs"]}


def _create(client, priv, rv, fake, created=(), pending=()):
    """Create as the editor sends it: one request per output, skip_built, outputs.json's created growing."""
    cards, made = {}, list(created)
    for o in OUTPUTS:
        r = _one(client, priv, rv, o, created=made, pending=list(pending), only=[o["kind"]])
        assert r.status_code == 200, r.text
        card = r.json()["outputs"][0]
        cards[o["kind"]] = card
        made += card.get("created") or []
    return cards, made


def _writes(fake) -> list:
    return [c for c in fake.calls if c[0] in WRITES and not c[1].endswith("/getDefinition")]


def test_decision_of_names_one_action_per_card():
    assert workload_api.decision_of({"already_built": True, "dry_run": True})["action"] == "skip"
    assert workload_api.decision_of({"already_built": True, "dry_run": True})["words"] == \
        "Already built from this plan; Create will skip it."
    assert workload_api.decision_of({"built_from": {"words": "x"}, "choices": ["update", "new_name"]})["action"] == "choose"
    assert workload_api.decision_of({"refusal": {"kind": "already_exists"}})["action"] == "refuse"
    assert workload_api.decision_of({"would": "update", "answer": {}})["action"] == "update"
    assert workload_api.decision_of({"would": "create", "answer": {}})["action"] == "create"


def test_after_a_create_the_dry_run_and_a_second_create_both_skip_everything_and_write_nothing(make):
    client, fake, priv = make(Defined())
    rv = _review(client, priv)
    first, made = _create(client, priv, rv, fake)
    assert all(c["decision"]["action"] in ("create",) for c in first.values()), {k: c["decision"] for k, c in first.items()}
    dry = _dry(client, priv, rv, created=made)
    fake.calls.clear()
    again, _ = _create(client, priv, rv, fake, created=made)
    for kind in dry:
        assert dry[kind]["decision"]["action"] == again[kind]["decision"]["action"] == "skip", (kind, dry[kind], again[kind])
        assert not dry[kind].get("refusal") and dry[kind]["would"] != "update", dry[kind]
    assert not [c for c in _writes(fake) if "/jobs/" not in c[1]], _writes(fake)


def test_items_another_krusgraph_model_built_from_the_same_plan_are_skipped_not_red(make):
    """Another Krusgraph Model item in the workspace built the same outputs from the same plan: this Model's
    outputs.json does not list them, their description carries the plan's marker. Skipped in both, never refused."""
    client, fake, priv = make(Defined())
    rv = _review(client, priv)
    _create(client, priv, rv, fake)                                # the other Model's Create
    dry = _dry(client, priv, rv, created=[])                       # this Model: nothing in its outputs.json
    fake.calls.clear()
    create, _ = _create(client, priv, rv, fake, created=[])
    for kind in dry:
        assert dry[kind]["decision"]["action"] == create[kind]["decision"]["action"] == "skip", (kind, dry[kind], create[kind])
        assert "not built by this Krusgraph Model" not in str(dry[kind])
    assert not [c for c in _writes(fake) if "/jobs/" not in c[1]], _writes(fake)


def test_items_built_from_another_plan_wait_for_a_choice_in_both_and_are_not_said_to_be_updated(make):
    client, fake, priv = make(Defined())
    rv = _review(client, priv)
    _, made = _create(client, priv, rv, fake)
    old = "[Krusgraph plan plan-0123456789ab, schema Shop (sha256:00112233aabbccdd), 6 links]"
    for it in fake.items:
        it["description"] = workload_api.MARK.sub("", it.get("description") or "").strip() + " " + old
    made = [{k: v for k, v in c.items() if k != "plan"} for c in made]   # outputs.json from before plans were recorded
    dry = _dry(client, priv, rv, created=made)
    fake.calls.clear()
    create, _ = _create(client, priv, rv, fake, created=made)
    for kind in dry:
        assert dry[kind]["decision"]["action"] == create[kind]["decision"]["action"] == "choose", (kind, dry[kind], create[kind])
        assert "different plan" in dry[kind]["decision"]["words"]
    assert not _writes(fake), _writes(fake)


def test_a_foreign_item_is_red_in_both(make):
    theirs = [{"id": "x-1", "displayName": "n209_model", "type": "SemanticModel", "description": "made by hand"}]
    client, fake, priv = make(Defined(items=theirs))
    rv = _review(client, priv)
    dry = _dry(client, priv, rv)
    create, _ = _create(client, priv, rv, fake)
    assert dry["semantic_model"]["decision"]["action"] == create["semantic_model"]["decision"]["action"] == "refuse"
    assert not [c for c in fake.calls if c[0] in WRITES and "x-1" in c[1]]


def test_the_dry_run_with_the_pending_list_adopts_what_create_adopts(make):
    """n207: an item Fabric finished after the wait (created after the step was sent) is adopted by Create; the dry run,
    sent with the same pending list, says the same (skip), not red."""
    later = "2026-11-11T08:04:31.250Z"
    there = [{"id": "late-1", "displayName": "shop_onto", "type": "Ontology", "description": "", "createdDate": later}]
    pending = [{"output": "ontology", "type": "Ontology", "name": "shop_onto", "at": "2026-11-11T08:00:00.000Z"}]
    client, fake, priv = make(Defined(items=there))
    rv = _review(client, priv)
    dry = _dry(client, priv, rv, pending=pending)
    r = _one(client, priv, rv, OUTPUTS[-1], pending=pending, only=["ontology"]).json()["outputs"][0]
    assert dry["ontology"]["decision"]["action"] == r["decision"]["action"] == "skip", (dry["ontology"], r)
