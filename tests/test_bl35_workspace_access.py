"""BL35 (21 November 2026, sprint item BL35, backlog B-25): workspace roles and sensitivity labels proposed, dry run
only. Role choice per output, request bodies in the cited shape, no network, no invented group or user id."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from fabric_backend import access
from fabric_backend import workspace_access as wa
from fabric_backend.tenant_settings import OUTPUTS

DOC = Path(__file__).resolve().parents[1] / "docs" / "WORKSPACE-ACCESS.md"
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
ALL = list(OUTPUTS)


def _role(p, output, group):
    item = next(i for i in p["items"] if i["output"] == output)
    return next(r for r in item["roles"] if r["group"] == group)


@pytest.mark.parametrize("output", ["lakehouse", "notebook", "pipeline", "semantic_model", "report"])
def test_builders_get_contributor_and_readers_viewer_confirmed(output):
    p = wa.propose([output])
    assert _role(p, output, "data engineers")["role"] == "Contributor"
    assert _role(p, output, "report readers")["role"] == "Viewer"
    assert _role(p, output, "access managers")["role"] == "Member"
    for r in next(i for i in p["items"] if i["output"] == output)["roles"]:
        assert r["status"] == wa.CONFIRMED and r["learn"].startswith("https://learn.microsoft.com/") and r["read_on"]


@pytest.mark.parametrize("output", ["ontology", "data_agent", "graphql_api"])
def test_items_learn_does_not_name_are_unverified(output):
    p = wa.propose([output])
    assert {r["status"] for r in p["items"][0]["roles"] if r["activity"] != "manage"} == {wa.UNVERIFIED}


def test_admin_is_never_proposed_and_one_role_per_group_is_the_highest():
    p = wa.propose(ALL)
    assert all(r["role"] != "Admin" for i in p["items"] for r in i["roles"])
    roles = {g["group"]: g["role"] for g in p["groups"]}
    assert roles == {"data engineers": "Contributor", "report readers": "Viewer", "access managers": "Member"}
    assert [n["output"] for n in p["not_items"]] == ["catalog_write"]
    assert p["written"] is False


def test_custom_groups_and_unknowns():
    p = wa.propose(["report"], {"finance analysts": "read"})
    assert p["groups"] == [{"group": "finance analysts", "activity": "read", "role": "Viewer", "because": ["Report"]}]
    with pytest.raises(ValueError):
        wa.propose(["report"], ["finance"])
    with pytest.raises(ValueError):
        wa.propose(["report"], {"x": "own"})
    with pytest.raises(ValueError):
        wa.propose(["warehouse"])


def test_bodies_match_the_cited_shape_and_invent_no_id():
    bodies = wa.request_bodies(wa.propose(ALL))
    assert len(bodies) == 3
    for b in bodies:
        assert b["method"] == "POST" and b["sent"] is False
        assert b["url"].startswith("https://api.fabric.microsoft.com/v1/workspaces/") and b["url"].endswith("/roleAssignments")
        assert set(b["body"]) == {"principal", "role"} and set(b["body"]["principal"]) == {"id", "type"}
        assert b["body"]["principal"]["type"] == "Group"
        assert b["body"]["role"] in ("Admin", "Member", "Contributor", "Viewer")
        assert b["scope"] == "Workspace.ReadWrite.All" and "not asked for today" in b["scope_state"]
        assert "add-workspace-role-assignment" in b["learn"]
    blob = json.dumps(bodies) + wa.markdown(ALL)
    assert not UUID.search(blob)


def test_the_scope_is_not_granted_and_listed_as_not_requested():
    assert wa.SCOPE not in access.scopes()
    assert wa.SCOPE in [s for s, _, _ in access.NOT_REQUESTED]


def test_labels_cite_learn_and_are_never_set_by_krusgraph():
    labs = {x["output"]: x for x in wa.labels(ALL)}
    assert "catalog_write" not in labs
    assert labs["report"]["inherits"] == "yes" and "downstream" in labs["report"]["learn"]
    assert labs["semantic_model"]["inherits"] == "no" and "data-sources" in labs["semantic_model"]["learn"]
    assert labs["lakehouse"]["inherits"] == "not stated" and labs["lakehouse"]["status"] == wa.UNVERIFIED
    for x in labs.values():
        assert x["set_by_krusgraph"] is False and "a person" in x["set_by"]


def test_markdown_summary_lines_are_25_words_or_fewer():
    md = wa.markdown(ALL)
    assert "Nothing is written" in md
    summaries = md.split("\n\n")[1].splitlines()
    assert len(summaries) == len(ALL)
    for line in summaries:
        assert len(line.lstrip("- ").split()) <= 25, line


def test_a_fake_fails_any_post(monkeypatch):
    import http.client
    import urllib.request

    def boom(*a, **k):
        raise AssertionError("no network")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    monkeypatch.setattr(http.client.HTTPConnection, "request", boom)
    try:
        import httpx
        monkeypatch.setattr(httpx.Client, "send", boom)
        monkeypatch.setattr(httpx.AsyncClient, "send", boom)
    except ImportError:
        pass
    try:
        import requests
        monkeypatch.setattr(requests.Session, "request", boom)
    except ImportError:
        pass
    p = wa.propose(ALL)
    wa.request_bodies(p)
    wa.labels(ALL)
    wa.markdown(ALL)


def test_no_model_call_or_network_import_in_the_module():
    src = Path(wa.__file__).read_text(encoding="utf-8")
    for word in ("import httpx", "import requests", "urllib", "anthropic", "openai"):
        assert word not in src, word


def test_the_doc_says_what_the_module_does():
    text = DOC.read_text(encoding="utf-8").lower()
    assert text.startswith("<!-- 2026-11-21, round bl35")
    for word in ("contributor", "viewer", "member", "workspace.readwrite.all", "not asked for today", "never sets",
                 "direct lake", "upon creation", "wiring into the dry run", "learn.microsoft.com"):
        assert word in text, word
