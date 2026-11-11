"""n220: running and scheduling the pipeline from the chat, and a report name already taken (the founder's chat of
11 November 2026).

a. The permission: DataPipeline.Execute.All is an opt-in permission of the hosted app (deploy switch pipeline_execute,
   server variable KRUSGRAPH_PIPELINE_EXECUTE), listed with why on /it and in docs/SCOPES.md; a token without it gets no
   bare 403 but the exact admin steps (app, permission, admin consent, reconnect) and "Run it in the Fabric portal".
b. Run once and Schedule from the chat: both off by default, each only after a dry run that shows it and the person's
   confirmation (the dry run's jobs.confirm passed back as confirm_jobs); the run is read by polling the job instance.
c. A report name taken: the next free name (checked), the existing report, whether Krusgraph made it from this model, and
   whether the name changed since the dry run; the name is checked again right before the create.
d. Each of these refusals ends with 1 to 3 next steps.
Fabric is the fake job of tests/test_n185_pipeline_jobs.py and the item list of tests/test_create_report.py."""
import base64
import importlib
import json

import pytest

from fabric_backend import access, pipeline_jobs as J, report, server
from test_create_pipeline import create, fabric as pipeline_fabric  # noqa: F401  (the fixture)
from test_create_report import ITEMS, MODEL_ID, WS as REPORT_WS, Resp, fabric  # noqa: F401
from test_drift_monitor import WS, lakehouse  # noqa: F401
from test_n185_pipeline_jobs import PL, FakeFabric, Clock, daily

APP_ID = "6b92ed27-66e7-4767-8e72-eeb4b66da277"


def jwt(scp: str) -> str:
    part = base64.urlsafe_b64encode(json.dumps({"scp": scp, "tid": "t"}).encode()).decode().rstrip("=")
    return f"eyJhbGciOiJub25lIn0.{part}.sig"


# ------------------------------------------------------------------ a. the permission --------------------------------

def test_the_scope_is_read_from_the_token_and_both_documented_names_count():
    assert J.token_scopes(jwt("Item.Read.All DataPipeline.ReadWrite.All")) == {"Item.Read.All", "DataPipeline.ReadWrite.All"}
    assert J.can_execute(J.token_scopes(jwt("DataPipeline.ReadWrite.All"))) is False
    assert J.can_execute(J.token_scopes(jwt("DataPipeline.Execute.All"))) is True
    assert J.can_execute(J.token_scopes(jwt("Item.Execute.All"))) is True
    assert J.token_scopes("fabric-token") is None and J.can_execute(None) is None      # unreadable: Fabric decides


def test_without_the_scope_nothing_is_sent_and_the_admin_steps_are_exact():
    fake = FakeFabric()
    clock = Clock()
    out = J.apply(fake, WS, PL, "pipeline_sap", True, daily(), wait_seconds=0, sleep=clock.sleep, clock=clock,
                  scopes={"DataPipeline.ReadWrite.All"}, app_id=APP_ID, consent_url="https://login/adminconsent")
    assert fake.calls == []                                                  # no 403 to read: nothing was asked
    run = out["run"]
    assert run["status"] == "NotStarted" and run["kind"] == "consent" and run["scope"] == "DataPipeline.Execute.All"
    steps = " ".join(run["admin"]["steps"])
    for said in (APP_ID, "API permissions", "Power BI Service", "Delegated permissions", "DataPipeline.Execute.All",
                 "Grant admin consent", "Reconnect Krusgraph in Claude"):
        assert said in steps, said
    assert run["alternative"]["label"] == "Run it in the Fabric portal" and PL in run["alternative"]["url"]
    assert 1 <= len(run["next_steps"]) <= 3 and run["next_steps"][0]["label"] == "Run it in the Fabric portal"
    assert out["schedule"]["kind"] == "consent"


def test_a_403_from_fabric_also_gets_the_steps_and_the_portal():
    fake = FakeFabric(refuse="/jobs/execute/instances")
    clock = Clock()
    run = J.apply(fake, WS, PL, "pipeline_sap", True, None, wait_seconds=0, sleep=clock.sleep, clock=clock, app_id=APP_ID)["run"]
    assert run["status"] == "NotStarted" and run["http"] == 403 and run["kind"] == "consent"
    assert APP_ID in run["admin"]["steps"][0] and run["alternative"]["url"].endswith(f"/pipelines/{PL}")


def test_the_scope_names_are_cited():
    assert "dataPipeline/swagger.json" in J.SCOPES_READ and "Run On Demand Item Job" in J.SCOPES_READ
    assert "11 November 2026" in J.SCOPES_READ


def test_it_and_the_trust_pack_list_the_opt_in_permission_with_why(monkeypatch):
    assert "DataPipeline.Execute.All" not in access.scopes()                 # not part of what the deploy check always demands
    md = access.table_md()
    assert "Opt-in: `DataPipeline.Execute.All`" in md and "Why:" in md and "off for this server" in md
    assert "it-opt-in" in access.table_html()
    monkeypatch.setenv("KRUSGRAPH_PIPELINE_EXECUTE", "1")
    assert access.pipeline_execute_on() and "on for this server" in access.table_md()


def test_the_deploy_check_demands_the_scope_only_with_the_switch():
    d = importlib.import_module("deploy.azure_containerapp")
    fabric_id = access.RESOURCE_IDS[access.FABRIC]
    assert "DataPipeline.Execute.All" not in d.required_scopes({})[fabric_id]
    assert "DataPipeline.Execute.All" in d.required_scopes({"pipeline_execute": True})[fabric_id]
    assert d.REQUIRED_SCOPES[fabric_id] == set(access.scopes(access.FABRIC))      # the base set is unchanged
    assert d.OPERATOR_FLAGS["pipeline_execute"] == access.PIPELINE_EXECUTE_ENV
    example = json.loads((d.ROOT / "deploy/krusgraph.example.json").read_text(encoding="utf-8"))
    assert example["pipeline_execute"] is False                                         # opt-in: off by default


# ------------------------------------------------------------------ b. run once and schedule from the chat ----------

def test_run_once_needs_the_dry_runs_code(pipeline_fabric):  # noqa: F811
    out = create(dry_run=False, run_once=True)
    assert out["kind"] == "needs_confirmation" and "Nothing was created" in out["error"]
    assert not any(c[0] == "POST" for c in pipeline_fabric["calls"])                     # nothing created, nothing run
    assert 1 <= len(out["next_steps"]) <= 3
    out = create(dry_run=False, run_once=True, confirm_jobs="run-0000000000")
    assert out["kind"] == "needs_confirmation" and "does not match" in out["error"]


def test_the_code_is_for_exactly_these_jobs(lakehouse):  # noqa: F811
    once = create(run_once=True)["jobs"]
    both = create(run_once=True, schedule={"every": "day", "at": "06:00"})["jobs"]
    assert once["confirm"] != both["confirm"] and once["confirm"].startswith("run-")
    assert "say yes" in once["ask"] and once["confirm"] in once["ask"]
    assert "confirm" not in create().get("jobs", {})                                     # nothing to confirm: no jobs


def test_the_dry_run_says_before_create_when_the_token_lacks_the_scope(lakehouse, monkeypatch):  # noqa: F811
    monkeypatch.setattr(server.auth, "fabric", lambda ctx: jwt("DataPipeline.ReadWrite.All Notebook.ReadWrite.All"))
    jobs = create(run_once=True)["jobs"]
    assert "DataPipeline.Execute.All" in jobs["permission"]["why"]
    assert jobs["permission"]["alternative"]["label"] == "Run it in the Fabric portal"


def test_create_with_the_code_but_no_scope_creates_the_items_and_says_what_the_admin_adds(pipeline_fabric, monkeypatch):  # noqa: F811
    code = create(run_once=True)["jobs"]["confirm"]
    monkeypatch.setattr(server.auth, "fabric", lambda ctx: jwt("DataPipeline.ReadWrite.All Notebook.ReadWrite.All"))
    out = create(dry_run=False, run_once=True, confirm_jobs=code)
    assert out["result"]["status"] == "Succeeded" and out["result"]["run"]["status"] == "NotStarted"
    assert out["kind"] == "consent" and out["scope"] == "DataPipeline.Execute.All" and "were created" in out["error"]
    assert not any("/jobs/" in u for _, u, _ in pipeline_fabric["calls"])
    assert out["alternative"]["label"] == "Run it in the Fabric portal" and 1 <= len(out["next_steps"]) <= 3


def test_create_with_the_code_runs_and_polls_the_job_instance(pipeline_fabric, monkeypatch):  # noqa: F811
    fake = FakeFabric(polls_to_end=1)
    monkeypatch.setattr(server.auth, "fabric", lambda ctx: jwt("DataPipeline.ReadWrite.All DataPipeline.Execute.All"))
    D = importlib.import_module("fabric_backend.deploy")
    real = D.send

    def send(method, url, headers, **kw):
        if "/jobs/" in url or "/queryactivityruns" in url or url.endswith(f"/items/{PL}"):
            return fake(method, url, **{k: v for k, v in kw.items() if k == "json"})
        return real(method, url, headers, **kw)
    monkeypatch.setattr(D, "send", send)
    token = server.PIPELINE_JOBS.set(None)
    try:
        code = create(run_once=True)["jobs"]["confirm"]
        monkeypatch.setattr(J, "RUN_WAIT_SECONDS", 0)
        out = create(dry_run=False, run_once=True, confirm_jobs=code)
    finally:
        server.PIPELINE_JOBS.reset(token)
    run = out["result"]["run"]
    assert run["run_id"] == "run-1" and run["status"] in ("Succeeded", "Running")
    assert any("/jobs/execute/instances/run-1" in u for _, u, _ in fake.calls)            # the job instance was read
    assert "error" not in out


# ------------------------------------------------------------------ c. a report name already taken ------------------

def test_the_next_free_name_counts_up_and_is_checked():
    assert report.next_free_name("demo_lh_report_2", {"demo_lh_report", "demo_lh_report_2"}) == "demo_lh_report_3"
    assert report.next_free_name("demo_lh_report_2", {"demo_lh_report_2", "DEMO_LH_REPORT_3"}) == "demo_lh_report_4"
    assert report.next_free_name("sales", {"sales"}) == "sales_2"


def test_provenance_reads_the_description_krusgraph_writes():
    mine = {"description": report.description_for("demo_lh_model")}
    assert report.provenance(mine, "demo_lh_model")["same_model"] is True
    other = report.provenance(mine, "another_model")
    assert other["by_krusgraph"] is True and other["same_model"] is False
    assert report.provenance({"description": "made by hand"}, "demo_lh_model")["by_krusgraph"] is False


def _with_items(monkeypatch, items):
    import requests
    inner = requests.get

    def get(url, **k):
        if "items?type=Report" in url:
            return Resp(200, {"value": items})
        return inner(url, **k)
    monkeypatch.setattr(requests, "get", get)


def test_a_taken_name_offers_the_next_free_name_and_the_existing_report(fabric, monkeypatch):  # noqa: F811
    _with_items(monkeypatch, [{"id": "rp-2", "displayName": "demo_lh_report_2", "type": "Report",
                               "description": report.description_for("shop_model")}])
    out = json.loads(server.create_report("Sales", "shop_model", "demo_lh_report_2", dry_run=True))
    assert out["kind"] == "already_exists" and out["free_name"] == "demo_lh_report_3"
    labels = [s["label"] for s in out["next_steps"]]
    assert labels[:2] == ["Use demo_lh_report_3", "Open the existing report"] and len(labels) <= 3
    use = out["next_steps"][0]
    assert use["tool"] == "create_report" and use["args"]["name"] == "demo_lh_report_3" and use["args"]["dry_run"] is True
    assert out["next_steps"][1]["url"].endswith(f"/groups/{REPORT_WS}/reports/rp-2")
    assert out["existing"]["by_krusgraph"] is True and out["existing"]["same_model"] is True
    assert "Krusgraph made it on the same semantic model shop_model" in out["error"]
    assert fabric["posts"] == []


def test_create_says_the_name_was_free_at_the_dry_run(fabric, monkeypatch):  # noqa: F811
    report._free_at.clear()
    dry = json.loads(server.create_report("Sales", "shop_model", "demo_lh_report_2", empty_page=True, dry_run=True))
    assert dry["name_check"]["free"] is True and "right before" in dry["name_check"]["again"]
    _with_items(monkeypatch, [{"id": "rp-2", "displayName": "demo_lh_report_2", "type": "Report", "description": "by hand"}])
    out = json.loads(server.create_report("Sales", "shop_model", "demo_lh_report_2", empty_page=True, dry_run=False))
    assert out["kind"] == "already_exists" and "was free at the dry run" in out["since_dry_run"]
    assert out["existing"]["by_krusgraph"] is False and "not made by Krusgraph" in out["error"]
    assert [s["label"] for s in out["next_steps"]][-1] == "Choose another name"
    assert fabric["posts"] == []


def test_the_name_is_checked_again_right_before_the_create(fabric, monkeypatch):  # noqa: F811
    import requests
    lists = []
    inner = requests.get

    def get(url, **k):
        if "items?type=Report" in url:
            lists.append(url)
            taken = len(lists) > 1                                    # free at the first look, taken by the second
            return Resp(200, {"value": [{"id": "rp-9", "displayName": "fresh", "type": "Report"}] if taken else []})
        return inner(url, **k)
    monkeypatch.setattr(requests, "get", get)
    out = json.loads(server.create_report("Sales", "shop_model", "fresh", empty_page=True, dry_run=False))
    assert out["kind"] == "already_exists" and len(lists) == 2 and fabric["posts"] == []


def test_a_name_taken_between_the_check_and_the_post_is_a_conflict_too(fabric, monkeypatch):  # noqa: F811
    import requests
    state = {"posted": False}
    inner = requests.get

    def get(url, **k):
        if "items?type=Report" in url:
            return Resp(200, {"value": [{"id": "rp-7", "displayName": "fresh", "type": "Report"}] if state["posted"] else []})
        return inner(url, **k)
    monkeypatch.setattr(requests, "get", get)

    def post(url, json):
        state["posted"] = True
        return Resp(409, {"errorCode": "ItemDisplayNameAlreadyInUse", "message": "taken"})
    fabric["post"] = post
    out = json.loads(server.create_report("Sales", "shop_model", "fresh", empty_page=True, dry_run=False))
    assert out["kind"] == "already_exists" and out["free_name"] == "fresh_2"


# ------------------------------------------------------------------ d. every error or refusal ends with next steps ---
from fabric_backend import mcp_apps, mcp_apps_build, mcp_apps_next as nxt, mcp_apps_review  # noqa: E402


def test_a_refusal_for_want_of_the_permission_gets_the_portal_link_and_what_to_ask():
    answer = {"error": "The run did not start", "kind": "consent", "scope": "DataPipeline.Execute.All",
              **{k: v for k, v in J.consent("why", APP_ID, None, "https://app.fabric.microsoft.com/groups/w/pipelines/p").items()
                 if k == "next_steps"}}
    steps = nxt.steps("create_pipeline", {"workspace": "Sales", "source": "lh", "name": "pipeline_sap"}, answer)
    assert 1 <= len(steps) <= 3
    assert steps[0] == {"label": "Run it in the Fabric portal", "url": "https://app.fabric.microsoft.com/groups/w/pipelines/p",
                        "say": "Run it in the Fabric portal: https://app.fabric.microsoft.com/groups/w/pipelines/p"}
    assert all(isinstance(s["say"], str) and s["say"] for s in steps)


def test_a_taken_report_name_becomes_a_dry_run_button_and_a_link(fabric, monkeypatch):  # noqa: F811
    _with_items(monkeypatch, [{"id": "rp-2", "displayName": "demo_lh_report_2", "type": "Report"}])
    args = {"workspace": "Sales", "model": "shop_model", "name": "demo_lh_report_2", "dry_run": False}
    answer = json.loads(server.create_report(**args))
    steps = nxt.steps("create_report", args, answer)
    use = steps[0]
    assert use["tool"] == "create_report" and use["arguments"]["name"] == "demo_lh_report_3"
    assert use["arguments"]["dry_run"] is True                                    # a step never writes
    assert steps[1]["label"] == "Open the existing report" and steps[1]["url"].startswith("https://")
    lead = nxt.lead("create_report", answer, steps)
    assert "Use demo_lh_report_3 (create_report, dry run)" in lead and "Open the existing report: https://" in lead


def test_any_other_error_gets_one_to_three_steps():
    for answer in ({"error": "Fabric timed out", "kind": "timeout"}, {"error": "odd", "kind": "bad_request"},
                   {"error": "no", "kind": "consent", "scope": "Item.ReadWrite.All"}):
        steps = nxt.steps("create_semantic_model", {"workspace": "Sales", "source": "lh", "name": "m", "dry_run": False}, answer)
        assert 1 <= len(steps) <= 3, answer
        assert all(s.get("arguments", {}).get("dry_run", True) is True for s in steps)   # never a write
    retry = nxt.steps("create_semantic_model", {"workspace": "Sales", "name": "m", "dry_run": False},
                      {"error": "Fabric timed out", "kind": "timeout"})
    assert retry[0]["label"] == "Try again" and retry[-1]["label"] == "Explain this and what to do"


def test_the_cards_draw_the_steps_of_an_error_too():
    js = nxt.js()
    assert "__DRY_TOOLS__" not in js and '"create_report"' in js and "ui/open-link" in js
    for html in (mcp_apps.card_html(), mcp_apps_review.card_html(), mcp_apps_build.card_html()):
        assert "n220" in html and "renderNext" in html


def test_a_taken_name_on_the_build_card_offers_the_next_free_name():
    acts, note = mcp_apps_build.actions_for("create_semantic_model", {"workspace": "Sales", "source": "lh", "name": "shop_model"},
                                            {"dry_run": True}, taken=["shop_model", "shop_model_2"])
    assert acts and acts[0]["kind"] == "dry_run" and acts[0]["arguments"]["name"] == "shop_model_3"
    assert acts[0]["arguments"]["dry_run"] is True and "nothing is overwritten" in note
