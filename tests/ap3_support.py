"""AP3: the doubles behind the caretaker in /app (tests/test_ap3_care*.py). Invented names and ids only.

On top of AP2's (tests/ap2_support.py: the synthetic SAP demo behind the tools, Fabric's REST in memory for the source
workspace `demo` and the build workspace `build`), this adds what the caretaker reads:

- Fabric's job list (JobScheduler_ListItemJobInstances) for any item: `fabric.jobs[item_id]` is its job instances, as
  Fabric returns them; Run On Demand (POST .../jobs/instances) answers 202 with a Location and is recorded.
- Power BI's refresh history of a semantic model: `fabric.refreshes` (newest first); a refresh request is recorded.
- the health table the pipeline's check notebook writes, answered where the SQL analytics endpoint is asked
  (`health_rows(monkeypatch, rows)`): rows as health.read_sql selects them.
- a Krusgraph Model item with its definition (outputs.json, source.json, review.json), as the Fabric workload stores it.
"""
from __future__ import annotations

import base64
import json
import uuid
from urllib.parse import urlsplit

import ap2_support as s2

MODEL_TYPE = "Krusgraph.Modeler.Model"


class Fabric(s2.Workspaces):
    """AP2's in-memory Fabric, with job lists, Run On Demand and Power BI's refresh history."""

    def __init__(self, lakehouse_get):
        super().__init__(lakehouse_get)
        self.jobs: dict[str, list[dict]] = {}
        self.refreshes: list[dict] = [{"status": "Completed", "refreshType": "ViaApi", "endTime": "2026-11-24T06:10:00Z"}]
        self.started_runs: list[str] = []
        self.refresh_requests: list[str] = []

    def route(self, method: str, url: str, body=None):
        parts = urlsplit(str(url))
        path = parts.path
        if parts.netloc == "api.powerbi.com" and path.endswith("/refreshes"):
            self.calls.append((method, path))
            if method == "POST":
                self.refresh_requests.append(path)
                self.refreshes.insert(0, {"status": "Completed", "requestId": "r-new", "refreshType": "ViaApi"})
                return s2.Response(202, None, {"x-ms-request-id": "r-new", "location": "x"})
            return s2.Response(200, {"value": list(self.refreshes)})
        seg = [x for x in path.split("/") if x]
        if "jobs" in seg and seg[-1] == "instances" and parts.netloc == "api.fabric.microsoft.com":
            item = seg[seg.index("items") + 1] if "items" in seg else ""
            if method == "GET":
                self.calls.append((method, path))
                return s2.Response(200, {"value": list(self.jobs.get(item, []))})
            if method == "POST":
                self.calls.append((method, path))
                self.started_runs.append(item)
                run = str(uuid.uuid4())
                return s2.Response(202, None, {"Location": f"https://api.fabric.microsoft.com/v1/workspaces/x/items/{item}/jobs/instances/{run}",
                                                "Retry-After": "0"})
        return super().route(method, url, body)

    def item(self, name: str) -> dict:
        return next(it for ws in self.items.values() for it in ws if it.get("displayName") == name)

    def add_model(self, workspace: str, name: str, outputs: dict, source: dict, review: dict) -> dict:
        """A Krusgraph Model item and its definition parts, as the workload saves them."""
        iid = str(uuid.uuid4())
        it = {"id": iid, "displayName": name, "type": MODEL_TYPE, "workspace": workspace}
        self.items[workspace].append(it)
        self.definitions[iid] = {"parts": [{"path": p, "payload": base64.b64encode(json.dumps(v).encode()).decode(), "payloadType": "InlineBase64"}
                                           for p, v in (("outputs.json", outputs), ("source.json", source), ("review.json", review),
                                                        ("item.json", {"version": 1}))]}
        return it


def data(monkeypatch) -> Fabric:
    """AP2's doubles with this Fabric in place of AP2's."""
    import requests
    s2.data(monkeypatch)
    import wb15_fake
    fake = Fabric(wb15_fake._get)
    for verb in ("get", "post", "patch", "put", "delete"):
        monkeypatch.setattr(requests, verb, getattr(fake, verb))
    return fake


def run(status: str, start: str = "2026-11-24T06:00:00", end: str | None = "2026-11-24T06:04:12", message: str | None = None) -> dict:
    """One job instance as Fabric lists it."""
    out = {"id": str(uuid.uuid4()), "status": status, "jobType": "Pipeline", "invokeType": "Manual", "startTimeUtc": start,
           "endTimeUtc": end}
    if message:
        out["failureReason"] = {"errorCode": "UserError", "message": message, "requestId": "req-1"}
    return out


def health_rows(monkeypatch, rows: list[dict]) -> list[str]:
    """The SQL analytics endpoint answers the health table's two queries (health.exists_sql, health.read_sql) with
    `rows`; every other query goes to the synthetic demo as before. Returns the SQL it was asked, for the tests."""
    from fabric_backend import server
    factory = server._execute_factory
    asked: list[str] = []

    def execute_factory(item, token):
        inner = factory(item, token)

        def execute(sql, *a, **kw):
            if "INFORMATION_SCHEMA.TABLES" in sql and "health" in sql:
                asked.append(sql)
                return [{"n": 1 if rows else 0}]
            if "[krusgraph].[health]" in sql or "krusgraph_health" in sql:
                asked.append(sql)
                return [dict(r) for r in rows]
            return inner(sql, *a, **kw)
        execute.close = getattr(inner, "close", lambda: None)
        return execute
    monkeypatch.setattr(server, "_execute_factory", execute_factory)
    return asked


def health_row(plan_id: str, check: str, obj: str, status: str, count: int = 0, at: str = "2026-11-24 06:04:00") -> dict:
    return {"run_id": "run-1", "checked_at": at, "plan_id": plan_id, "check": check, "object": obj, "rule": check,
            "status": status, "count": count, "baseline": None}
