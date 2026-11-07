"""Round n143: lineage with runs= reads a pipeline's or notebook's latest runs, per activity, with Fabric's error text and
a heuristic category from run_results.CATALOG. Fabric's REST API is a test double: requests.get answers from a recorded
fixture, every write method fails the test, and the pipeline definition is the one create_pipeline sends."""
import copy
import json
from pathlib import Path

import pytest
import requests

from fabric_backend import pipeline, run_results, server, tool_status

FIX = json.loads((Path(__file__).parent / "fixtures" / "run_results" / "pipeline_shop.json").read_text(encoding="utf-8"))
WS = "11111111-1111-1111-1111-111111111111"
PIPE, SILVER, GOLD, CHECK = (f"aaaaaaaa-0000-4000-8000-00000000000{i}" for i in range(1, 5))
LIVE = FIX["live_import_error"]


class _Resp:
    def __init__(self, status: int, body: dict):
        self.status_code, self._body, self.headers, self.text = status, body, {}, json.dumps(body)

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"{self.status_code} Client Error", response=self)


@pytest.fixture
def fabric(monkeypatch):
    """The test double. `state["jobs"]` is {item id: instances}, `state["denied"]` item ids that answer 403."""
    state = {"jobs": copy.deepcopy(FIX["jobs"]), "denied": set(), "gets": [], "definition_reads": []}

    def get(url, headers=None, **kw):
        state["gets"].append(url)
        assert url.startswith(f"https://api.fabric.microsoft.com/v1/workspaces/{WS}/items/") and url.endswith("/jobs/instances"), url
        item = url.split("/items/")[1].split("/")[0]
        if item in state["denied"]:
            return _Resp(403, {"errorCode": "InsufficientPrivileges", "message": "The caller does not have permission"})
        return _Resp(200, {"value": state["jobs"].get(item, [])})

    def no_write(*a, **k):
        raise AssertionError("run results must not write to Fabric")

    monkeypatch.setattr(requests, "get", get)
    for m in ("post", "put", "patch", "delete"):
        monkeypatch.setattr(requests, m, no_write)
    monkeypatch.setattr(server, "_headers", lambda ctx: {"Authorization": "Bearer test-only"})
    monkeypatch.setattr(server, "_workspace_id", lambda workspace, headers: WS)
    monkeypatch.setattr(server, "_workspace_items", lambda ws, headers: FIX["items"])
    content = pipeline.pipeline_content("silver_shop", "gold_shop", "pipeline_shop_check", "shop_lh.shop",
                                        ids={"silver_shop": SILVER, "gold_shop": GOLD, "pipeline_shop_check": CHECK}, workspace_id=WS)

    def parts(ws, route, item_id, headers, fmt=None):
        state["definition_reads"].append((route, item_id))
        assert route == "dataPipelines" and item_id == PIPE
        return {"pipeline-content.json": json.dumps(content)}
    monkeypatch.setattr(server, "_item_definition_parts", parts)

    def no_sql(*a, **k):
        raise AssertionError("runs= opens no SQL connection")
    monkeypatch.setattr(server, "_connected", no_sql)
    return state


def _runs(name="pipeline_shop"):
    return json.loads(server.lineage("Sales", "shop_lh", runs=name))


CASES = [
    ("import_error", LIVE),
    ("import_error", "ModuleNotFoundError: No module named 'great_expectations'"),
    ("table_not_found", "[TABLE_OR_VIEW_NOT_FOUND] The table or view `silver`.`orders` cannot be found."),
    ("table_not_found", "AnalysisException: Table or view not found: gold.vw_orders"),
    ("table_not_found", "Invalid object name 'krusgraph.vw_order_items'."),
    ("permission_denied", "Operation failed: \"This request is not authorized to perform this operation.\", 403"),
    ("permission_denied", "PermissionDenied: the caller does not have permission to write to the lakehouse"),
    ("capacity_paused_or_throttled", "CapacityNotActive: The capacity is paused."),
    ("capacity_paused_or_throttled", "[TooManyRequestsForCapacity] This spark job can't be run because you have hit a spark "
                                     "compute or API rate limit."),
    ("timeout", "Livy session has failed. Session state: Dead. The session timed out."),
    ("timeout", "Activity exceeded the maximum execution time"),
]


@pytest.mark.parametrize("category,text", CASES)
def test_every_catalog_entry_matches_its_kind_of_error(category, text):
    d = run_results.classify(text)
    assert d["category"] == category and d["next_step"] and d["heuristic"].startswith("heuristic")
    assert d["matched"].lower() in text.lower()


def test_every_catalog_entry_has_a_case_and_the_order_puts_narrow_before_generic():
    assert {c for c, _ in CASES} == {name for name, *_ in run_results.CATALOG}
    assert run_results.classify(LIVE + "\n  ... while waiting, the session timeout was 20 minutes")["category"] == "import_error"
    unknown = run_results.classify("ZeroDivisionError: division by zero")
    assert unknown["category"] == "unknown" and "monitoring hub" in unknown["next_step"]
    assert run_results.classify(None) == {}


def test_the_live_import_error_of_7_november_is_classified_and_kept_word_for_word(fabric):
    out = _runs()
    first = next(r for r in out["runs"] if r["status"] == "Failed")
    assert first["failure"]["message"] == LIVE and first["diagnosis"]["category"] == "import_error"
    acts = {a["activity"]: a for a in first["activities"]}
    assert [a["status"] for a in first["activities"]] == ["Completed", "Completed", "Failed"]
    check = first["activities"][2]
    assert check["notebook"] == "pipeline_shop_check" and check["failure"]["message"] == LIVE
    assert check["diagnosis"]["category"] == "import_error" and "heuristic" in check["matched_by"]
    assert all(a["created_by_krusgraph"] for a in acts.values())


def test_the_latest_run_comes_first_and_the_answer_says_scope_limits_and_that_it_changes_nothing(fabric):
    out = _runs()
    assert out["item"] == {"name": "pipeline_shop", "id": PIPE, "type": "DataPipeline", "created_by_krusgraph": True}
    assert [r["status"] for r in out["runs"]] == ["Completed", "Failed"]
    assert all(a["status"] == "Completed" for a in out["runs"][0]["activities"]) and "diagnosis" not in out["runs"][0]
    assert out["summary"].startswith("pipeline_shop: latest run Completed")
    assert "Item.Read.All" in out["scopes"]["needs"][0] and "hosted app has these" in out["scopes"]["hosted_app"]
    assert tool_status.STATUS["lineage"].available == tool_status.HOSTED
    assert out["changes"].startswith("nothing") and {x["is"] for x in out["limits"]} >= {"a heuristic", "a person's decision", "never"}
    assert "not yet run against a live workspace" in out["note"]
    # only GETs on the job-instance list and one definition read; every write method would have failed the test
    assert len(fabric["gets"]) == 4 and fabric["definition_reads"] == [("dataPipelines", PIPE)]


def test_a_failed_first_step_leaves_the_later_ones_not_run_from_the_definition(fabric):
    silver = fabric["jobs"][SILVER][0]
    silver.update(status="Failed", failureReason={"errorCode": "UserError", "message": "[TABLE_OR_VIEW_NOT_FOUND] shop.orders"})
    fabric["jobs"][GOLD] = fabric["jobs"][GOLD][1:]
    fabric["jobs"][CHECK] = fabric["jobs"][CHECK][1:]
    failed = next(r for r in _runs()["runs"] if r["status"] == "Failed")
    assert [a["status"] for a in failed["activities"]] == ["Failed", "NotRun", "NotRun"]
    assert failed["activities"][0]["diagnosis"]["category"] == "table_not_found"
    assert "dependsOn" in failed["activities"][1]["why"]


def test_a_notebook_whose_runs_cannot_be_read_is_skipped_and_the_pipeline_runs_still_shown(fabric):
    fabric["denied"].add(CHECK)
    out = _runs()
    assert [r["status"] for r in out["runs"]] == ["Completed", "Failed"]
    check = out["runs"][1]["activities"][2]
    assert check["status"] == "unknown" and check["skipped"]["item"] == "pipeline_shop_check"


def test_a_notebook_by_name_and_an_item_someone_else_made(fabric):
    fabric["jobs"]["aaaaaaaa-0000-4000-8000-000000000005"] = [
        {"id": "x", "status": "Failed", "startTimeUtc": "2026-11-07T08:00:00", "failureReason": {"message": "CapacityNotActive"}}]
    out = _runs("SOMEONE_ELSES")
    assert out["item"]["type"] == "Notebook" and out["item"]["created_by_krusgraph"] is False
    assert out["runs"][0]["diagnosis"]["category"] == "capacity_paused_or_throttled" and "activities" not in out["runs"][0]
    assert len(out["scopes"]["needs"]) == 1


def test_an_unknown_name_and_a_permission_error_on_the_item_itself(fabric):
    out = _runs("nope")
    assert out["kind"] == "not_found" and "pipeline_shop" in out["hint"] and "shop_lh" not in out["hint"]
    fabric["denied"].add(PIPE)
    denied = _runs()
    assert "error" in denied and denied["kind"] != "not_found"


def test_a_long_message_is_cut_and_marked_never_reworded():
    msg = LIVE + " " + "x" * 5000
    f = run_results.failure({"failureReason": {"message": msg, "errorCode": "UserError"}})
    assert f["message"] == msg[:run_results.MESSAGE_CAP] and f"of {len(msg)} characters" in f["message_cut"]


def test_create_pipeline_says_it_ran_live_on_7_november_and_nothing_more():
    note = tool_status.answer_note("create_pipeline")
    assert "7 November 2026" in note and "9de8bc49" in note and "all three steps succeeded" in note
    assert "Not yet run" not in note
    s = tool_status.STATUS["create_pipeline"]
    # n146: a dated live run is not Experimental; the run is in the tool's fields, not in a free-text note
    assert "9de8bc49" in tool_status.label("create_pipeline") and not s.live and tool_status.word("create_pipeline") == "Tried live"


def test_the_docs_limits_table_has_a_row_for_every_limit_the_answer_gives():
    doc = (Path(__file__).parents[1] / "docs" / "RUN-RESULTS.md").read_text(encoding="utf-8")
    table = doc.split("## Know the limits", 1)[1].split("##", 1)[0]
    rows = {line.split("|")[1].strip() for line in table.splitlines() if line.startswith("| ") and "---" not in line} - {"Area"}
    assert rows == {x["what"] for x in run_results.LIMITS}
    assert {name for name, *_ in run_results.CATALOG} | {"unknown"} <= set(
        line.split("`")[1] for line in doc.split("## The catalog", 1)[1].split("##", 1)[0].splitlines() if line.startswith("| `"))
