"""BL40 (backlog C-29, B-26), 23 November 2026: the dry run names the tenant settings its outputs need, and Schedule in
the closing step shows the schedule it would send.

On the synthetic SAP demo behind tests/wb15_fake.py (no Fabric, no write possible): the dry-run step carries one line
of at most 25 words naming the settings (from tenant_settings.py) and saying they could not be checked; it never blocks.
After Create, "Schedule it" carries schedules.draft's preview (the pipeline daily, the model's refresh as its last step,
not sent) and its sentence stays within 25 words."""
import json

import wb15_fake as fake

from fabric_backend import server, start_flow as sf, tenant_settings as ts

B = {"workspace": "demo", "source": "demo_lh", "schema": "dbo"}     # as tests/test_wb15_click_through.py


def test_the_line_names_the_settings_within_25_words():
    for tools in (["create_pipeline", "create_semantic_model", "create_data_agent"], ["create_ontology"],
                  ["create_semantic_model"], list(ts.TOOL_OUTPUTS)):
        line = sf._settings_line(tools)
        assert len(line.split()) <= 25, line
    assert sf._settings_line(["create_semantic_model"]) == "Needs no tenant setting."
    line = sf._settings_line(["create_pipeline", "create_data_agent"])
    assert line.startswith("Needs tenant settings: Fabric items, Copilot") and "Not checked" in line
    assert "Ontology (preview)" in sf._settings_line(["create_ontology"])


def test_an_unknown_output_says_could_not_check_and_never_raises(monkeypatch):
    monkeypatch.setattr(ts, "dry_run_line", lambda outputs: (_ for _ in ()).throw(ValueError("boom")))
    assert sf._settings_line(["create_pipeline"]) == "Tenant settings: could not check them."


def test_the_dry_run_step_carries_the_line(monkeypatch):
    fake.install(monkeypatch)
    out = json.loads(server.start(**B, step="dry_run"))
    assert out["needs"].startswith("Needs tenant settings:") and len(out["needs"].split()) <= 25
    assert any(a.get("kind") == "dry_run_all" for a in out.get("actions", []))         # the dry run is still offered


def test_schedule_in_the_closing_step_previews_and_sends_nothing():
    c = {"workspace": "ws", "source": "sap_lh", "schema": "sap"}
    out = sf._closing(c)
    sched = next(a for a in out["actions"] if a["label"] == "Schedule it")
    p = sched["schedule"]
    assert p["dry_run"] is True and p["sent"] == []
    kinds = [s["what"] for s in p["schedules"]]
    assert kinds == ["pipeline", "model refresh"] and p["schedules"][0]["body"]["configuration"]["type"] == "Daily"
    assert len(sched["say"].split()) <= 25 and "Nothing is created" in sched["say"]
    assert len(out["actions"]) == 3                                                    # still three buttons
