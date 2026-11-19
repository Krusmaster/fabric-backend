"""WB3, finding F5 of docs/WORKLOAD-TEST-2026-11-17.md: when items the Model recorded have ids that are not GUIDs, the
Data product page's actions (Look for leftovers among them) answer a sentence for a person, not the field's name."""
import pytest

from fabric_backend.workload_api import BadRequest, product_request

WS = "11111111-1111-1111-1111-111111111111"
G1 = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def body(action, created):
    return {"action": action, "workspace": WS, "product": "Shop sales", "outputs": {"created": created}}


@pytest.mark.parametrize("created, which", [
    ([{"id": "semantic-model-1", "workspace": WS}], "the item this Model recorded has"),
    ([{"id": "a", "workspace": WS}, {"id": "b", "workspace": "not-a-guid"}], "all 2 items this Model recorded have"),
    ([{"id": G1, "workspace": WS}, {"id": "b", "workspace": WS}], "1 of the 2 items this Model recorded have"),
])
def test_leftovers_with_ids_that_are_not_guids_is_one_sentence_for_a_person(created, which):
    with pytest.raises(BadRequest) as e:
        product_request(body("leftovers", created))
    words = str(e.value)
    assert words == f"Krusgraph cannot look for leftovers: {which} no Fabric id it can look up, so nothing was checked or changed."
    assert "outputs" not in words and "GUID" not in words and "created" not in words


@pytest.mark.parametrize("action, doing", [("status", "check this data product"), ("retire", "retire this data product"),
                                           ("adopt", "adopt items into this data product")])
def test_every_product_action_names_what_it_could_not_do(action, doing):
    with pytest.raises(BadRequest) as e:
        product_request({**body(action, [{"id": "x", "workspace": WS}]), "scope": "soft", "items": [G1]})
    assert str(e.value).startswith(f"Krusgraph cannot {doing}: the item this Model recorded has no Fabric id")


def test_guids_still_pass():
    out = product_request(body("leftovers", [{"id": G1, "workspace": WS}]))
    assert out["outputs"]["created"] == [{"id": G1, "workspace": WS}]
