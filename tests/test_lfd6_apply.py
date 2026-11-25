"""Round LFD6 (25 November 2026): round LFD4's counted numbers in propose_change, and apply_change through Update, both
behind KRUSGRAPH_CHANGES, off by default (docs/CHANGES.md, "Applying a change (LFD6)").

The fake Fabric below is the hosted server's outer seams only, as tests/wb15_fake.py has them: the workspace `demo`, the
lakehouse `shop_lh` with the synthetic shop_lfd sample in the schema `shop` (SQLite), and Fabric's REST API answered from
an item store in memory (list, create, getDefinition, updateDefinition, the description PATCH, a pipeline run, a Power BI
refresh). A DELETE or a PUT fails the test. The data product is built first by the creating tools themselves
(create_pipeline and create_semantic_model with dry_run=false), so apply_change meets the items as they make them.

Scenario A5 is scenario A applied: remove the test customers (A2), region from addresses (A3), order value per customer
(A4), each proposed with propose_change and applied with apply_change and its confirm, one after the other.
"""
from __future__ import annotations

import base64
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from fabric_backend import change_apply, change_diff, lfd_demo, server, tool_listing, tool_status, workload_api
from fabric_backend.platforms.local import _sqlite_execute
from test_n123_switches import _LIST

ROOT = Path(__file__).resolve().parents[1]
WS = "w-demo"
LH = {"id": "aaaaaaaa-0000-0000-0000-00000000lfd6", "displayName": "shop_lh", "type": "Lakehouse", "schemas_enabled": True}
SRC = {"workspace": "demo", "source": "shop_lh", "schema": "shop"}
IS_TEST = {"column": "is_test", "op": "is_true"}
A2 = {"type": "filter_rows", "table": "customers", "drop_where": IS_TEST,
      "cascade": ["orders", "order_items", "addresses", "audit_log"]}
SHIP_TO = {"from": {"table": "orders", "columns": ["ship_to_id"]}, "to": {"table": "addresses", "columns": ["address_id"]}}
A3 = {"type": "add_column", "table": "orders", "from": "addresses", "columns": ["region"], "via": [SHIP_TO]}
A4 = {"type": "add_measure", "name": "Order value per customer",
      "measure": {"form": "ratio", "numerator": {"measure": "Order amount"},
                  "denominator": {"form": "distinct_count", "table": "orders", "column": "customer_id"}}}


# ------------------------------------------------------------------ the fake Fabric ------------------------------------

class _Response:
    def __init__(self, status: int = 200, body=None, headers: dict | None = None):
        self.status_code, self._body, self.headers = status, body, headers or {}
        self.ok = status < 400
        self.text = json.dumps(body) if body is not None else ""
        self.content = self.text.encode()

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def _decode(parts: list[dict]) -> dict[str, str]:
    return {p["path"]: base64.b64decode(p["payload"]).decode("utf-8") for p in parts}


class FakeFabric:
    """Items in memory: {id: {id, displayName, type, description, parts}}. calls: every request (method, path)."""

    def __init__(self, db: sqlite3.Connection):
        self.db, self.items, self.calls, self.n = db, {}, [], 0
        self.runs: list[str] = []
        self.refreshes: list[str] = []

    def writes(self) -> list[tuple[str, str]]:
        return [(m, p) for m, p in self.calls if m != "GET" and not p.endswith("/getDefinition")]

    def by_name(self, name: str) -> dict:
        return next(i for i in self.items.values() if i["displayName"] == name)

    def _route(self, method: str, url: str, body=None) -> _Response:
        parts = urlsplit(url)
        self.calls.append((method, parts.path))
        if method in ("DELETE", "PUT"):
            raise AssertionError(f"LFD6: a {method} was sent: {url}")
        if parts.netloc == "api.powerbi.com":
            if method == "POST" and parts.path.endswith("/refreshes"):
                self.refreshes.append(parts.path.split("/datasets/")[1].split("/")[0])
                return _Response(202, None, {"x-ms-request-id": "rq-1"})
            return _Response(200, {"value": [{"requestId": "rq-1", "status": "Completed"}]})
        seg = [s for s in parts.path.split("/") if s][1:]
        rest = seg[2:] if seg[:2] == ["workspaces", WS] else None
        if rest is None:
            return _Response(200, {"value": []})
        if method == "GET" and rest == ["items"]:
            want = (dict(x.split("=", 1) for x in parts.query.split("&") if "=" in x)).get("type")
            return _Response(200, {"value": [{k: v for k, v in i.items() if k != "parts"} for i in self.items.values()
                                             if want in (None, i["type"])]})
        if method == "GET" and rest[:1] == ["items"] and len(rest) == 2:
            i = self.items.get(rest[1])
            return _Response(200, {k: v for k, v in i.items() if k != "parts"}) if i else _Response(404, {"errorCode": "EntityNotFound"})
        if method == "PATCH" and rest[:1] == ["items"] and len(rest) == 2:
            self.items[rest[1]]["description"] = (body or {}).get("description", self.items[rest[1]]["description"])
            return _Response(200, {})
        if method == "POST" and len(rest) == 1 and rest[0] in ("notebooks", "dataPipelines", "semanticModels"):
            self.n += 1
            typ = {"notebooks": "Notebook", "dataPipelines": "DataPipeline", "semanticModels": "SemanticModel"}[rest[0]]
            iid = f"{typ.lower()}-{self.n}"
            self.items[iid] = {"id": iid, "displayName": body["displayName"], "type": typ,
                               "description": body.get("description", ""), "parts": _decode(body["definition"]["parts"])}
            return _Response(201, {"id": iid, "displayName": body["displayName"]})
        if method == "POST" and len(rest) == 3 and rest[2] == "getDefinition":
            return _Response(200, {"definition": {"parts": [
                {"path": k, "payload": base64.b64encode(v.encode()).decode(), "payloadType": "InlineBase64"}
                for k, v in self.items[rest[1]]["parts"].items()]}})
        if method == "POST" and len(rest) == 3 and rest[2] == "updateDefinition":
            self.items[rest[1]]["parts"] = _decode(body["definition"]["parts"])
            return _Response(200, None)
        if rest[:1] == ["dataPipelines"] and rest[2:4] == ["jobs", "execute"]:
            if method == "POST":
                self.runs.append(rest[1])
                self._run()
                return _Response(202, None, {"Location": f"https://api.fabric.microsoft.com/v1/workspaces/{WS}/items/{rest[1]}"
                                                         "/jobs/instances/run-1", "Retry-After": "0"})
            return _Response(200, {"status": "Completed", "startTimeUtc": "2026-11-25T10:00:00Z", "endTimeUtc": "2026-11-25T10:01:00Z"})
        if method == "POST" and "queryactivityruns" in parts.path:
            return _Response(200, {"value": []})
        return _Response(404, {"errorCode": "EntityNotFound", "message": f"no route {method} {parts.path}"})

    def _run(self) -> None:
        """The pipeline's run: the silver tables as the silver notebook leaves them (shop_lfd without its test
        customers, which is what the filter of A2 keeps, as tests/test_lfd4_numbers.py checks against silver.simulate)."""
        if not any(r[1] == "silver" for r in self.db.execute("PRAGMA database_list")):
            self.db.execute("ATTACH DATABASE ':memory:' AS silver")
        data = lfd_demo.shop_rows(include_test=False)
        for name, ddl in lfd_demo.SHOP_SCHEMAS.items():
            self.db.execute(f"DROP TABLE IF EXISTS silver.[{name}]")
            self.db.execute(f"CREATE TABLE silver.[{name}] ({ddl})")
            rows = [tuple(v.isoformat() if hasattr(v, "isoformat") else v for v in r) for r in data[name]]
            self.db.executemany(f"INSERT INTO silver.[{name}] VALUES ({','.join('?' * len(rows[0]))})", rows)

    def get(self, url, headers=None, params=None, timeout=None, **kw):
        return self._route("GET", url)

    def post(self, url, headers=None, json=None, data=None, timeout=None, **kw):
        return self._route("POST", url, json)

    def patch(self, url, headers=None, json=None, timeout=None, **kw):
        return self._route("PATCH", url, json)

    def delete(self, url, *a, **k):
        return self._route("DELETE", url)

    def put(self, url, *a, **k):
        return self._route("PUT", url)


@pytest.fixture
def fabric(monkeypatch):
    import requests
    schema, _ = lfd_demo.sqlite("shop_lfd")
    con = sqlite3.connect(":memory:", check_same_thread=False)
    con.execute("ATTACH DATABASE ':memory:' AS shop")
    data = lfd_demo.shop_rows(True)
    for name, ddl in lfd_demo.SHOP_SCHEMAS.items():
        con.execute(f"CREATE TABLE shop.[{name}] ({ddl})")
        rows = [tuple(v.isoformat() if hasattr(v, "isoformat") else v for v in r) for r in data[name]]
        con.executemany(f"INSERT INTO shop.[{name}] VALUES ({','.join('?' * len(rows[0]))})", rows)
    execute = _sqlite_execute(con)
    fake = FakeFabric(con)
    for verb in ("get", "post", "patch", "delete", "put"):
        monkeypatch.setattr(requests, verb, getattr(fake, verb))
    monkeypatch.setattr(server.auth, "fabric", lambda ctx: "fabric-token")
    monkeypatch.setattr(server.auth, "sql", lambda ctx: "sql-token")
    monkeypatch.setattr(server.auth, "powerbi", lambda ctx: "powerbi-token", raising=False)
    monkeypatch.setattr(server, "limiter", None)
    monkeypatch.setattr(server, "REFRESH_PAUSE", 0)
    monkeypatch.setattr(server, "_workspace_id", lambda workspace, headers: WS)
    monkeypatch.setattr(server, "_resolve_source", lambda workspace, source, headers: dict(LH))
    monkeypatch.setattr(server, "_lakehouse_csn", lambda *a, **k: None)
    monkeypatch.setattr(server, "_execute_factory", lambda item, token: execute)
    monkeypatch.setattr(server._fabric.PLATFORM, "read_schema", lambda ex, name: schema)
    monkeypatch.setattr(change_apply, "pause", lambda seconds: None)
    return fake


def _build(fake) -> None:
    """The data product as the creating tools build it: the pipeline (three notebooks) and the semantic model."""
    out = json.loads(server.create_pipeline(name="pipeline_shop", dry_run=False, **SRC))
    assert out["result"]["status"] == "Succeeded", out
    out = json.loads(server.create_semantic_model(name="shop_model", dry_run=False, **SRC))
    assert (out.get("result") or {}).get("status") == "Succeeded", out
    assert {i["displayName"] for i in fake.items.values()} == {"silver_shop", "gold_shop", "pipeline_shop_check", "pipeline_shop",
                                                              "shop_model"}
    fake.calls.clear()


def _propose(change, applied=()) -> dict:
    return json.loads(server._propose_change(change=change, applied=list(applied), **SRC))


def _apply(change, applied=(), **kw) -> dict:
    return json.loads(server._apply_change(change=change, applied=list(applied), **SRC, **kw))


def _numbers(answer: dict) -> dict:
    out = {}
    for c in answer["diff"]["numbers"]["counted"]["changes"]:
        for n in c["numbers"]:
            out[n["item"]] = (n.get("before"), n.get("after"))
    return out


# ------------------------------------------------------------------ the flag and the listings ------------------------

def _env(**extra) -> dict:
    return {k: v for k, v in os.environ.items() if not k.startswith("KRUSGRAPH_")} | {"PYTHONPATH": str(ROOT)} | extra


def _listing(module: str, **env) -> dict:
    return json.loads(subprocess.run([sys.executable, "-c", _LIST, module], env=_env(**env), cwd=ROOT, capture_output=True,
                                     text=True, check=True).stdout)


def test_flag_off_apply_change_is_not_registered_anywhere():
    if tool_listing.changes_on():
        pytest.skip("KRUSGRAPH_CHANGES is on in this environment")
    assert not hasattr(server, "apply_change") and "apply_change" not in tool_status.STATUS
    assert "apply_change" not in tool_status.LOCAL_TOOLS and tool_listing.default_names({}) == tool_listing.DEFAULT
    off = _listing("server", KRUSGRAPH_ADVANCED_TOOLS="1")
    assert "apply_change" not in [t["name"] for t in off["tools"]] and "propose_change" not in [t["name"] for t in off["tools"]]
    assert len(_listing("server", KRUSGRAPH_ADVANCED_TOOLS="0")["tools"]) == 16
    assert "apply_change" not in [t["name"] for t in _listing("mcp_server")["tools"]]


def test_flag_on_apply_change_is_a_creating_tool_and_the_read_only_listing_stays_under_23_500():
    on = _listing("server", KRUSGRAPH_CHANGES="1", KRUSGRAPH_ADVANCED_TOOLS="0")
    off = _listing("server", KRUSGRAPH_ADVANCED_TOOLS="0")
    names = [t["name"] for t in on["tools"]]
    assert sorted(names) == sorted((*tool_listing.DEFAULT, "propose_change", "apply_change"))
    tool = next(t for t in on["tools"] if t["name"] == "apply_change")
    assert tool["annotations"]["read_only_hint"] is False and tool["annotations"]["destructive_hint"] is True
    assert set(tool["input_schema"]["properties"]) == {"workspace", "source", "change", "schema", "applied", "confirmed", "confirm",
                                                        "dry_run"}
    assert tool["input_schema"]["properties"]["dry_run"]["default"] is True
    assert all(p.get("description") for p in tool["input_schema"]["properties"].values())
    # LFD6, 25 November 2026: 21 583 characters off, 23 364 on; apply_change is not read-only, so it adds nothing here
    assert off["ro_size"] <= on["ro_size"] <= 23_500
    ro = _listing("server", KRUSGRAPH_CHANGES="1", KRUSGRAPH_READ_ONLY="1", KRUSGRAPH_ADVANCED_TOOLS="1")
    listed = [t["name"] for t in ro["tools"]]
    assert "propose_change" in listed and "apply_change" not in listed            # KRUSGRAPH_READ_ONLY leaves it out
    assert "apply_change" not in [t["name"] for t in _listing("mcp_server", KRUSGRAPH_CHANGES="1")["tools"]]   # hosted only
    status = json.loads(subprocess.run([sys.executable, "-c", "import json; from fabric_backend import tool_status as t; "
                                        "s = t.STATUS['apply_change']; print(json.dumps([s.kind, 'apply_change' in t.LOCAL_TOOLS]))"],
                                       env=_env(KRUSGRAPH_CHANGES="1"), cwd=ROOT, capture_output=True, text=True, check=True).stdout)
    assert status == [tool_status.CREATES, False]


# ------------------------------------------------------------------ the plan marker's change list --------------------

def test_an_old_mark_without_changes_reads_as_zero_changes_and_a_new_one_carries_the_list():
    old = "Created by Krusgraph [Krusgraph plan plan-0123456789ab, schema shop (sha256:00112233aabbccdd), 7 links]"
    mark = workload_api.mark_of_description(old)
    assert mark == {"plan_id": "plan-0123456789ab", "schema": "shop", "schema_fingerprint": "sha256:00112233aabbccdd", "links": 7}
    assert change_apply.changes_of(mark)["changes"] == 0 and change_apply.changes_of(mark)["digest"] == change_apply.digest([])
    assert change_apply.changes_of(None)["changes"] is None
    new = change_apply.new_mark({"plan_id": "plan-0123456789ab", "schema_fingerprint": "sha256:00112233aabbccdd"}, "shop", 7,
                                ["chg-1", "chg-2"])
    text = workload_api.with_mark("Created by Krusgraph", new)
    assert text.endswith(f", 7 links, 2 changes ({change_apply.digest(['chg-1', 'chg-2'])})]") and len(text) <= 256
    back = workload_api.mark_of_description(text)
    assert back["changes"] == 2 and change_apply.changes_of(back)["digest"] == change_apply.digest(["chg-1", "chg-2"])
    assert workload_api.same_plan(back, mark)                       # the plan is the same; the change list is apart
    from fabric_backend import after_create
    assert after_create.same_plan(text, mark) and after_create.MARK.search(old)


# ------------------------------------------------------------------ the numbers layer (task 0) -----------------------

def test_a2_propose_change_shows_the_counted_numbers(fabric):
    out = _propose(A2)
    assert out["result"] == "ok" and out["diff"]["numbers"]["status"] == "counted"
    n = _numbers(out)
    assert n["rows:customers"] == (12, 10) and n["rows:orders"] == (66, 60) and n["rows:order_items"] == (146, 134)
    assert n["sum:Order amount"] == ("56834.70", "51296.70")
    counted = out["diff"]["numbers"]["counted"]
    assert counted["receipt"]["rows"] > 0 and "change_numbers.statements" in counted["receipt"]["said"]
    assert all(x.get("after_sql") for c in counted["changes"] for x in c["numbers"] if x["what"] == "rows")
    assert out["pipeline_run"]["needed"] is True and out["writes"].startswith("Nothing was written")
    assert fabric.writes() == []


_LOCAL = r"""
import json
from fabric_backend import mcp_server as m, lfd_demo, server
schema, ex = lfd_demo.sqlite("shop_lfd")
m._execute_factory = lambda s: ex                                  # the local server's connection: SQLite over shop_lfd
m._plan_on = lambda execute, s, keys=None, confirmed=None, decisions=True: server._hosted_plan(schema, keys, confirmed, ex)
out = json.loads(m.propose_change(json.loads(__import__("sys").argv[1]), schema="shop"))
n = {x["item"]: [x.get("before"), x.get("after")] for c in out["diff"]["numbers"]["counted"]["changes"] for x in c["numbers"]}
print(json.dumps([out["result"], n["rows:customers"], n["rows:orders"], n["sum:Order amount"], out["pipeline_run"]["needed"]]))
"""


def test_a2_the_local_server_counts_the_numbers_too():
    got = subprocess.run([sys.executable, "-c", _LOCAL, json.dumps(A2)], env=_env(KRUSGRAPH_CHANGES="1"), cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout
    assert json.loads(got) == ["ok", [12, 10], [66, 60], ["56834.70", "51296.70"], True]


def test_a_long_answer_drops_the_sql_of_each_number_first_and_keeps_the_numbers():
    schema, execute = lfd_demo.sqlite("shop_lfd")
    p = server._hosted_plan(schema, None, None, execute)
    info = dict(workspace_id=WS, item_id="lh-1", item_name="shop_lh", item_kind="Lakehouse", schema="shop", schemas_enabled=True)
    ok = change_diff.propose(A4, p, info, [A2], numbers=change_apply.numbers(execute))
    whole = json.loads(change_apply.answer(ok, 10**6))
    assert "sql_omitted" not in whole["diff"]["numbers"]["counted"]
    limit = len(json.dumps(whole, indent=2)) - 2000
    cut = json.loads(change_apply.answer(ok, limit))
    counted = cut["diff"]["numbers"]["counted"]
    assert counted["sql_omitted"] and not any(k.endswith("sql") for c in counted["changes"] for x in c["numbers"] for k in x)
    assert [(x["item"], x.get("before"), x.get("after")) for c in counted["changes"] for x in c["numbers"]] == \
           [(x["item"], x.get("before"), x.get("after")) for c in whole["diff"]["numbers"]["counted"]["changes"] for x in c["numbers"]]
    assert "diff" in next(x for x in cut["diff"]["items"] if x["item"] == "semantic_model")   # the diffs stay while the SQL goes


# ------------------------------------------------------------------ apply_change: what is never written ------------

def test_dry_run_is_the_default_and_writes_nothing(fabric):
    _build(fabric)
    out = _apply(A4)
    assert out["result"] == "ok" and out["dry_run"] is True and out["written"] == []
    assert [s["action"] for s in out["steps"]] == ["update definition", "refresh once"]
    assert out["confirm"] == _propose(A4)["confirm"] and out["pipeline_run"]["needed"] is False
    assert out["writes"].startswith("Nothing was written: a dry run")
    assert fabric.writes() == [] and fabric.refreshes == []


def test_a_wrong_or_old_token_writes_nothing_and_answers_the_new_diff_and_token(fabric):
    _build(fabric)
    old = _propose(A4)["confirm"]                                   # the token of another list: A4 before A2
    for confirm, kind in (("", "needs_confirmation"), ("upd-0000000000000000", "confirm_mismatch"), (old, "confirm_mismatch")):
        out = _apply(A4, [A2], confirm=confirm, dry_run=False)
        assert out["result"] == "not_applied" and out["kind"] == kind and out["writes"].startswith("Nothing was written")
        assert out["confirm"] == _propose(A4, [A2])["confirm"] != old and out["diff"]["items"]
    assert fabric.writes() == []


def test_an_item_someone_else_made_is_never_written(fabric):
    _build(fabric)
    fabric.by_name("shop_model")["description"] = "The finance team's model"
    out = _apply(A4, confirm=_propose(A4)["confirm"], dry_run=False)
    assert out["result"] == "not_applied" and out["kind"] == "not_ours" and "shop_model" in out["reason"]
    assert fabric.writes() == []


def test_an_item_changed_in_fabric_since_it_was_built_is_not_written(fabric):
    _build(fabric)
    nb = fabric.by_name("silver_shop")
    nb["parts"]["notebook-content.py"] += "\n# CELL ********************\n\nprint('edited by hand')\n"
    out = _apply(A2, confirm=_propose(A2)["confirm"], dry_run=False)
    assert out["result"] == "not_applied" and out["kind"] == "items_differ"
    row = next(c for c in out["checks"] if c["item"] == "silver_notebook")
    assert row["now"] == "differs from the diff's now" and row["differences"]
    assert fabric.writes() == [] and fabric.runs == []


# ------------------------------------------------------------------ apply_change: what is written ------------------

def test_only_the_items_in_the_diff_are_written_and_an_old_mark_reads_as_zero_changes(fabric):
    _build(fabric)
    model = fabric.by_name("shop_model")
    assert change_apply.changes_of(workload_api.mark_of_description(model["description"]))["changes"] == 0   # create's own mark
    before = {i["id"]: dict(i["parts"]) for i in fabric.items.values()}
    prop = _propose(A4)
    out = _apply(A4, confirm=prop["confirm"], dry_run=False)
    assert out["result"] == "ok" and out["written"] == ["shop_model"]
    check = next(c for c in out["checks"] if c["item"] == "semantic_model")
    assert check["recorded"]["changes"] == 0 and check["now"] == "as the diff's now"
    assert [(m, p.rsplit("/", 2)[-2]) for m, p in fabric.writes() if p.endswith("updateDefinition")] == [("POST", model["id"])]
    assert all(m in ("POST", "PATCH") for m, _ in fabric.writes())                       # never a DELETE or a PUT
    assert {i["id"] for i in fabric.items.values()} == set(before)                       # nothing deleted, nothing new
    changed = [i["displayName"] for i in fabric.items.values() if i["parts"] != before[i["id"]]]
    assert changed == ["shop_model"]
    assert "Order value per customer" in "".join(model["parts"].values())
    mark = workload_api.mark_of_description(model["description"])
    assert mark["changes"] == 1 and mark["changes_digest"] == change_apply.digest([prop["id"]])
    assert fabric.runs == [] and fabric.refreshes == [model["id"]]
    assert out["verify"]["definition"]["state"] == "verified"
    assert out["verify"]["numbers_after_run"]["state"] == "not checked" and "no run was needed" in out["verify"]["numbers_after_run"]["said"]


def test_a5_scenario_a_applied_updates_the_definitions_in_order_and_verify_build_says_verified(fabric):
    _build(fabric)
    ids = {i["displayName"]: i["id"] for i in fabric.items.values()}
    applied: list = []
    seen = {}
    for name, change in (("A2", A2), ("A3", A3), ("A4", A4)):
        prop = _propose(change, applied)
        assert prop["result"] == "ok", prop
        marked = [x["name"] for x in prop["diff"]["items"] if x["status"] == change_diff.UPDATE]
        fabric.calls.clear()
        out = _apply(change, applied, confirm=prop["confirm"], dry_run=False)
        assert out["result"] == "ok", out
        seen[name] = out
        written = [p.rsplit("/", 2)[-2] for m, p in fabric.writes() if p.endswith("updateDefinition")]
        assert written == [ids[n] for n in out["written"]]
        assert set(out["written"]) <= set(marked) and "pipeline_shop" not in out["written"]        # the pipeline as the diff says
        assert out["verify"]["definition"]["state"] == "verified", out["verify"]
        applied = out["applied_next"]
    a2, a3, a4 = seen["A2"], seen["A3"], seen["A4"]
    # A2: the silver notebook, then the run (rows change), then the refresh; the model's README is no part of the item
    assert a2["written"] == ["silver_shop"] and a2["pipeline_run"]["needed"] is True
    assert [(s["action"], s["name"], s["status"]) for s in a2["steps"]] == [
        ("update definition", "silver_shop", "written"), ("run once", "pipeline_shop", "Succeeded"),
        ("refresh once", "shop_model", "refreshed")]
    numbers = a2["verify"]["numbers_after_run"]
    assert numbers["state"] == "verified"
    rows = {r["table"]: (r["expected"], r["counted"]) for r in numbers["rows"]}
    assert rows.items() >= {"customers": (10, 10), "orders": (60, 60), "order_items": (134, 134)}.items()
    # A3 (the plan counted orders.ship_to_id, R5): the gold views notebook as the diff says, then a run and a refresh
    assert a3["written"] == ["gold_shop"] and a3["pipeline_run"]["needed"] is True
    assert [s["action"] for s in a3["steps"]] == ["update definition", "run once", "refresh once"]
    assert fabric.runs == [ids["pipeline_shop"]] * 2                                     # A2 and A3; A4 needs no run
    # A4: the semantic model only, no run, one refresh
    assert a4["written"] == ["shop_model"] and a4["pipeline_run"]["needed"] is False
    model = fabric.by_name("shop_model")
    assert "DIVIDE([Order amount], DISTINCTCOUNT('orders'[customer_id]))" in "".join(model["parts"].values())
    assert workload_api.mark_of_description(model["description"])["changes"] == 3
    assert "exclude_rows" in fabric.by_name("silver_shop")["parts"]["notebook-content.py"]
    assert "addresses_region" in fabric.by_name("gold_shop")["parts"]["notebook-content.py"]
    assert not [c for c in fabric.calls if c[0] in ("DELETE", "PUT")]
    # applying the same list again writes nothing: every item is already as the change makes it
    again = _propose(A4, applied[:2])
    fabric.calls.clear()
    repeat = _apply(A4, applied[:2], confirm=again["confirm"], dry_run=False)
    assert repeat["written"] == [] and not [p for m, p in fabric.writes() if p.endswith("updateDefinition")]
