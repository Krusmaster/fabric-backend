"""BL54 (23 November 2026, sprint D, backlog B-25 and P-29): the start flow's dry-run step says which workspace roles
and sensitivity labels are proposed, and that a data contract comes along, without anything being written to Fabric.

On the synthetic `shop` sample (start with sample=true) and the synthetic SAP demo behind tests/wb15_fake.py (`sap_demo`,
no Fabric): the dry-run step carries `access` (workspace_access.dry_run_line, BL35) and `contract` (data_contract.draft,
BL38), each one line of at most 25 words saying nothing is written. No POST, PATCH, PUT or DELETE is made during the dry
run, including the "Dry run everything" calls it offers."""
import json

import pytest
import requests

import wb15_fake as fake

from fabric_backend import server, start_flow as sf, tenant_settings as ts, workspace_access as wa

B = {"workspace": "demo", "source": "demo_lh", "schema": "dbo"}     # as tests/test_wb15_click_through.py
VERBS = ("post", "patch", "put", "delete")


def _assert_lines(out):
    for key in ("access", "contract"):
        line = out[key]
        assert len(line.split()) <= 25, line
        assert "Nothing is written" in line, line
    assert "Contributor" in out["access"] and "Viewer" in out["access"] and "Member" in out["access"]
    assert "Admin" not in out["access"]
    assert "never set" in out["access"]
    assert "data_contract.draft" in out["contract"] and "ODCS v3.1.0" in out["contract"]


@pytest.fixture
def no_writes(monkeypatch):
    """Every write verb fails the test, at module level and on a Session; the list says what was tried."""
    tried = []

    def refuse(*a, **k):
        tried.append(a[:2])
        raise AssertionError(f"BL54: a write was attempted during the dry run: {a[:2]}")

    for verb in VERBS:
        monkeypatch.setattr(requests, verb, refuse)

    real = requests.Session.request

    def session_request(self, method, *a, **k):
        if str(method).upper() in {v.upper() for v in VERBS}:
            return refuse(method, *a)
        return real(self, method, *a, **k)
    monkeypatch.setattr(requests.Session, "request", session_request)
    return tried


def test_access_line_is_built_from_the_proposal_and_never_sets_a_label():
    outputs = [o for t, _, _ in sf.BUILDS for o in ts.TOOL_OUTPUTS[t]]
    line = wa.dry_run_line(outputs)
    for g in wa.propose(outputs)["groups"]:
        assert f"{g['group']} {g['role']}" in line
    assert "report inherits the model's" in line
    assert "inherits" not in wa.dry_run_line(["notebook", "pipeline"])
    assert wa.dry_run_line(["catalog_write"]).startswith("No workspace role proposed.")
    with pytest.raises(ValueError):
        wa.dry_run_line(["warehouse"])


def test_access_line_never_blocks(monkeypatch):
    monkeypatch.setattr(wa, "dry_run_line", lambda outputs: (_ for _ in ()).throw(ValueError("boom")))
    assert "Nothing is written" in sf._access_line()


@pytest.mark.parametrize("run", [False, True])
def test_shop_sample_dry_run_shows_both_lines(no_writes, run):
    out = json.loads(server.start(sample=True, step="dry_run", confirm=run))
    assert out["sample"] is True and out["stage"] == "dry_run"
    _assert_lines(out)
    assert no_writes == []


def test_shop_sample_other_steps_do_not_carry_them():
    for step in ("check", "decide", "create"):
        out = json.loads(server.start(sample=True, step=step))
        assert "access" not in out and "contract" not in out


def test_sap_demo_dry_run_shows_both_lines_and_writes_nothing(monkeypatch, no_writes):
    fake.install(monkeypatch)        # its own guard replaces the module-level verbs; the Session guard stays
    out = json.loads(server.start(**B, step="dry_run"))
    _assert_lines(out)
    assert out["needs"].startswith("Needs tenant settings:")                       # BL40's line stays
    everything = next(a for a in out["actions"] if a.get("kind") == "dry_run_all")
    for run in everything["runs"]:                                                # the dry runs the button makes
        res = fake.call(run["tool"], run["arguments"])
        assert not res.get("isError"), res["content"][0]["text"][:300]
    assert no_writes == [] and fake.WRITES == []


def test_the_write_guard_catches_a_write(no_writes):
    with pytest.raises(AssertionError):
        requests.post("https://api.fabric.microsoft.com/v1/workspaces/x/roleAssignments", json={})
    with pytest.raises(AssertionError):
        requests.Session().request("PATCH", "https://api.fabric.microsoft.com/v1/x")
    assert len(no_writes) == 2
