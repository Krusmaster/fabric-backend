"""The change-by-chat demo end to end, offline (round LFD9, 25 November 2026; docs/demo/CHANGE-BY-CHAT.md).

Scenario A on the synthetic shop_lfd sample and scenario B on sap_lfd (fabric_backend/lfd_demo.py, docs/SAMPLE-LFD.md),
run through the hosted tools' own functions: create_pipeline and create_semantic_model build the data product (a dry run,
then dry_run=false), then every change goes through server._propose_change and server._apply_change, the functions the
tools propose_change and apply_change call. Nothing else decides anything here.

Fabric is an in-memory stand-in (FakeFabric): the workspace `demo` with one lakehouse, its rows in SQLite, and Fabric's
REST API answered from an item store (list, create, getDefinition, updateDefinition, the description PATCH, a pipeline
run, a Power BI refresh). A pipeline run writes the silver tables as the silver notebook in the store would leave them:
its change list read back (silver.read_changes) and silver.simulate on the source rows. A DELETE or a PUT raises. The
network is not used: `offline()` replaces the HTTP verbs of `requests` and the sign-in for the duration of the run, and
puts everything back afterwards.

The plan is made as the hosted tools make it, except that R5 (counting the code and role columns the names left
unlinked) is off, so the shop's plan has no orders.ship_to_id link and step A3 asks for it, as a source would where R5
did not count it. On a lakehouse where R5 counts it (shop_lfd does: 60 of 60), A3 is ok at once and A3a and A3b are
not shown.

    run("shop_lfd") / run("sap_lfd")   -> {"scenario", "sample", "steps": [...], "seconds"}
    lines(result)                      -> the steps as they read in the chat, one string per line
"""
from __future__ import annotations

import base64
import contextlib
import datetime as _dt
import json
import sqlite3
import time
from urllib.parse import urlsplit

from . import lfd_demo

WS = "w-demo"
WORKSPACE = "demo"
SOURCES = {
    "shop_lfd": {"workspace": WORKSPACE, "source": "shop_lh", "schema": "shop"},
    "sap_lfd": {"workspace": WORKSPACE, "source": "sap_lh", "schema": "sap"},
}
LAKEHOUSE_IDS = {"shop_lfd": "aaaaaaaa-0000-0000-0000-00000000lfd9", "sap_lfd": "bbbbbbbb-0000-0000-0000-00000000lfd9"}

IS_TEST = {"column": "is_test", "op": "is_true"}
CASCADE = ["orders", "order_items", "addresses", "audit_log"]
A2 = {"type": "filter_rows", "table": "customers", "drop_where": IS_TEST, "cascade": CASCADE}
A3 = {"type": "add_column", "table": "orders", "from": "addresses", "columns": ["region"]}
SHIP_TO = {"from": {"table": "orders", "columns": ["ship_to_id"]}, "to": {"table": "addresses", "columns": ["address_id"]}}
A4 = {"type": "add_measure", "name": "Order value per customer",
      "measure": {"form": "ratio", "numerator": {"measure": "Order amount"},
                  "denominator": {"form": "distinct_count", "table": "orders", "column": "customer_id"}}}
CANCELLED = {"any": [{"column": "FKSTO", "op": "equals", "value": "X"}, {"column": "SFAKN", "op": "is_not_empty"}]}
B1 = {"type": "filter_rows", "table": "sap_vbrk", "drop_where": CANCELLED, "cascade": ["sap_vbrp"]}

# The amount the numbers layer counts on the source, summed over the silver tables after a run (whole cents).
SILVER_AMOUNT = {
    "shop_lfd": "SELECT SUM(CAST(ROUND(i.[quantity] * p.[list_price] * 100, 0) AS INTEGER)) FROM silver.[order_items] AS i "
                "JOIN silver.[products] AS p ON p.[product_id] = i.[product_id]",
    "sap_lfd": "SELECT SUM(CAST(ROUND([NETWR] * 100, 0) AS INTEGER)) FROM silver.[sap_vbrk]",
}

# What the person types in the chat, per step (docs/demo/CHANGE-BY-CHAT.md has the same sentences).
SAID = {
    "build": "Build the data product for shop_lh: the pipeline and the semantic model.",
    "build_sap": "Build the data product for sap_lh: the pipeline and the semantic model.",
    "A2": "Remove the test customers.",
    "A3": "Add region from addresses to orders.",
    "A4": "Add a measure: order value per customer.",
    "A6": "Undo removing the test customers.",
    "B1": "Leave out cancelled billing documents and their cancellations.",
}


# ------------------------------------------------------------------ the in-memory Fabric ------------------------------

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


def _plain(v):
    return v.isoformat() if isinstance(v, (_dt.date, _dt.datetime)) else v


def connection(sample: str) -> tuple[sqlite3.Connection, list[str]]:
    """The sample's rows in an in-memory SQLite database, in the schema the source names (as lfd_demo.sqlite), and
    the table names."""
    schema = SOURCES[sample]["schema"]
    con = sqlite3.connect(":memory:", check_same_thread=False)
    con.execute(f"ATTACH DATABASE ':memory:' AS {schema}")
    names = []
    if sample == "shop_lfd":
        data = lfd_demo.shop_rows(True)
        for name, ddl in lfd_demo.SHOP_SCHEMAS.items():
            con.execute(f"CREATE TABLE {schema}.[{name}] ({ddl})")
            rows = [tuple(_plain(v) for v in r) for r in data[name]]
            con.executemany(f"INSERT INTO {schema}.[{name}] VALUES ({','.join('?' * len(rows[0]))})", rows)
            names.append(name)
    else:
        from . import sap_demo
        for name, (cols, _kinds, rows) in lfd_demo.sap_tables().items():
            t = sap_demo.PREFIX + name.lower()
            con.execute(f"CREATE TABLE {schema}.[{t}] ({', '.join(f'[{c}]' for c in cols)})")
            con.executemany(f"INSERT INTO {schema}.[{t}] VALUES ({','.join('?' * len(cols))})", rows)
            names.append(t)
    return con, names


class FakeFabric:
    """Fabric's REST API in memory. items: {id: {id, displayName, type, description, parts}}; calls: every request
    (method, path); runs: the pipeline ids run; refreshes: the semantic model ids refreshed."""

    def __init__(self, sample: str, con: sqlite3.Connection, tables: list[str], plan_of):
        self.sample, self.con, self.tables, self.plan_of = sample, con, tables, plan_of
        self.items: dict[str, dict] = {}
        self.calls: list[tuple[str, str]] = []
        self.runs: list[str] = []
        self.refreshes: list[str] = []
        self.n = 0

    def writes(self) -> list[tuple[str, str]]:
        return [(m, p) for m, p in self.calls if m != "GET" and not p.endswith("/getDefinition")]

    def by_name(self, name: str) -> dict:
        return next(i for i in self.items.values() if i["displayName"] == name)

    def silver_count(self, table: str) -> int:
        return self.con.execute(f"SELECT COUNT(*) FROM silver.[{table}]").fetchone()[0]

    def _route(self, method: str, url: str, body=None) -> _Response:
        parts = urlsplit(url)
        self.calls.append((method, parts.path))
        if method in ("DELETE", "PUT"):
            raise AssertionError(f"change_demo: a {method} was sent to {parts.path}; the demo never deletes or replaces")
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
            want = dict(x.split("=", 1) for x in parts.query.split("&") if "=" in x).get("type")
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
        """The pipeline's run: the silver tables as the silver notebook in the store leaves them. Its change list is
        read back from the notebook (silver.read_changes) and silver.simulate runs its steps on the source rows."""
        from . import changes, silver
        schema = SOURCES[self.sample]["schema"]
        nb = next((i for i in self.items.values() if i["displayName"] == f"silver_{schema}"), None)
        listed = silver.read_changes(nb["parts"].get("notebook-content.py", "")) if nb else []
        plan = self.plan_of()
        applied = changes.apply([x["change"] for x in listed], plan)
        info = {"workspace_id": WS, "item_id": LAKEHOUSE_IDS[self.sample], "item_name": SOURCES[self.sample]["source"],
                "item_kind": "Lakehouse", "schema": schema, "schemas_enabled": True}
        cur = self.con.cursor()
        data = {}
        for t in self.tables:
            cur.execute(f"SELECT * FROM {schema}.[{t}]")
            cols = [d[0] for d in cur.description]
            data[t] = [dict(zip(cols, r)) for r in cur.fetchall()]
        out = silver.simulate(silver.spec(plan, info, changes=applied if applied.get("result") == "ok" else None), data)["silver"]
        if not any(r[1] == "silver" for r in self.con.execute("PRAGMA database_list")):
            self.con.execute("ATTACH DATABASE ':memory:' AS silver")
        for t in self.tables:
            cols = list(data[t][0]) if data[t] else []
            self.con.execute(f"DROP TABLE IF EXISTS silver.[{t}]")
            self.con.execute(f"CREATE TABLE silver.[{t}] ({', '.join(f'[{c}]' for c in cols)})")
            rows = [tuple(r.get(c) for c in cols) for r in out.get(t, [])]
            if rows:
                self.con.executemany(f"INSERT INTO silver.[{t}] VALUES ({','.join('?' * len(cols))})", rows)

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


_MISSING = object()


@contextlib.contextmanager
def offline(sample: str = "shop_lfd"):
    """The hosted server's outer seams pointed at a FakeFabric of `sample` for the duration: the HTTP verbs of
    `requests`, the sign-in, the workspace and lakehouse lookups, the SQL connection (SQLite over the sample), the
    pauses, and R5 off (the module's docstring). Everything is put back afterwards. Yields the FakeFabric."""
    import requests

    from . import change_apply, server, usage
    from .platforms.local import _sqlite_execute
    if sample not in SOURCES:
        raise ValueError(f"unknown sample {sample!r}; one of {', '.join(SOURCES)}")
    schema_obj = lfd_demo.sqlite(sample)[0]
    con, tables = connection(sample)
    execute = _sqlite_execute(con)
    src = SOURCES[sample]
    lakehouse = {"id": LAKEHOUSE_IDS[sample], "displayName": src["source"], "type": "Lakehouse", "schemas_enabled": True}
    fake = FakeFabric(sample, con, tables, lambda: server._hosted_plan(schema_obj, None, None, execute))
    patches = [(requests, verb, getattr(fake, verb)) for verb in ("get", "post", "patch", "delete", "put")]
    patches += [
        (server.auth, "fabric", lambda ctx: "fabric-token"),
        (server.auth, "sql", lambda ctx: "sql-token"),
        (server.auth, "powerbi", lambda ctx: "powerbi-token"),
        (server, "limiter", None),
        (server, "REFRESH_PAUSE", 0),
        (server, "R5_MAX_QUERIES", 0),
        (server, "_workspace_id", lambda workspace, headers: WS),
        (server, "_resolve_source", lambda workspace, source, headers: dict(lakehouse)),
        (server, "_lakehouse_csn", lambda *a, **k: None),
        (server, "_execute_factory", lambda item, token: execute),
        (server._fabric.PLATFORM, "read_schema", lambda ex, name: schema_obj),
        (change_apply, "pause", lambda seconds: None),
        (usage, "_log_on", lambda: False),                       # no usage line on stdout between the answers
    ]
    saved = [(obj, name, getattr(obj, name, _MISSING)) for obj, name, _ in patches]
    try:
        for obj, name, value in patches:
            setattr(obj, name, value)
        yield fake
    finally:
        for obj, name, value in reversed(saved):
            if value is _MISSING:
                delattr(obj, name)
            else:
                setattr(obj, name, value)
        con.close()


# ------------------------------------------------------------------ the scenarios ------------------------------------

def _call(fn, **kw) -> dict:
    return json.loads(fn(**kw))


def _counted(answer: dict, change_id: str | None = None) -> dict:
    """{item: (before, after)} of the numbers layer, for the change `change_id` (default: the answer's own)."""
    out = {}
    counted = ((answer.get("diff") or {}).get("numbers") or {}).get("counted") or {}
    cid = change_id or answer.get("id")
    for c in counted.get("changes") or []:
        if cid and c.get("id") != cid:
            continue
        for n in c.get("numbers") or []:
            out[n["item"]] = n.get("value") if n.get("what") == "measure" else (n.get("before"), n.get("after"))
    return out


class _Scenario:
    def __init__(self, sample: str, fake: FakeFabric):
        from . import server
        self.server, self.fake, self.src = server, fake, SOURCES[sample]
        self.applied: list = []
        self.confirmed: list | None = None
        self.steps: list[dict] = []

    def _args(self, change) -> dict:
        return {**self.src, "change": change, "applied": list(self.applied), "confirmed": self.confirmed}

    def build(self, said: str) -> None:
        s = self.server
        step = {"step": "build", "said": said, "kind": "build", "dry_run": {}, "created": {}}
        for name, fn in (("pipeline_" + self.src["schema"], s.create_pipeline), (self.src["schema"] + "_model", s.create_semantic_model)):
            seen = len(self.fake.writes())
            dry = _call(fn, name=name, dry_run=True, **self.src)
            step["dry_run"][name] = dry
            if len(self.fake.writes()) != seen:
                raise RuntimeError(f"change_demo: the dry run of {name} wrote to Fabric")
            made = _call(fn, name=name, dry_run=False, **self.src)
            step["created"][name] = made
        step["items"] = sorted(i["displayName"] for i in self.fake.items.values())
        self.steps.append(step)

    def propose(self, label: str, said: str | None, change) -> dict:
        args = self._args(change)
        call = {k: v for k, v in args.items() if v is not None}
        seen = len(self.fake.writes())
        answer = _call(self.server._propose_change, **args)
        from . import mcp_apps_change
        card = mcp_apps_change.card(answer, call) if answer.get("result") in ("ok", "question", "denied", "replan") else None
        if card is not None and answer.get("result") == "question" and not card.get("choices"):
            # the card lists its buttons only while propose_change is listed (KRUSGRAPH_CHANGES=1); the demo shows them
            card["choices"] = mcp_apps_change.choices(answer, call)
        self.steps.append({"step": label, "said": said, "kind": "propose", "change": change, "answer": answer,
                           "card": card, "writes": self.fake.writes()[seen:]})
        return answer

    def apply(self, label: str, change, proposal: dict) -> dict:
        args = self._args(change)
        before = len(self.fake.calls)
        dry = _call(self.server._apply_change, **args, confirm=proposal.get("confirm", ""), dry_run=True)
        if [c for c in self.fake.calls[before:] if c[0] != "GET" and not c[1].endswith("/getDefinition")]:
            raise RuntimeError("change_demo: apply_change's dry run wrote to Fabric")
        out = _call(self.server._apply_change, **args, confirm=proposal.get("confirm", ""), dry_run=False)
        self.steps.append({"step": label, "said": "Yes, apply it.", "kind": "apply", "change": change, "dry_run": dry,
                           "answer": out, "runs": len(self.fake.runs), "refreshes": len(self.fake.refreshes),
                           "silver": self._silver(), "silver_amount": self._amount()})
        if out.get("result") == "ok":
            self.applied = out["applied_next"]
            if proposal.get("confirmed") is not None:
                self.confirmed = proposal["confirmed"] or None
        return out

    def _silver(self) -> dict:
        try:
            return {t: self.fake.silver_count(t) for t in self.fake.tables}
        except sqlite3.Error:
            return {}

    def _amount(self) -> str | None:
        """The order value (shop) or the billed amount (SAP) over the silver tables, in cents and back, as
        lfd_demo.numbers sums them; None before the first run."""
        sql = SILVER_AMOUNT[self.fake.sample]
        try:
            cents = self.fake.con.execute(sql).fetchone()[0]
        except sqlite3.Error:
            return None
        return None if cents is None else f"{cents // 100}.{cents % 100:02d}"


def scenario_a(sc: _Scenario) -> None:
    sc.build(SAID["build"])
    # A2: remove the test customers; the client's model fills in the answers to Krusgraph's two questions
    sc.propose("A2a", SAID["A2"], {"type": "filter_rows", "table": "customers"})
    sc.propose("A2b", "is_test", {"type": "filter_rows", "table": "customers", "drop_where": IS_TEST})
    a2 = sc.propose("A2c", "Yes, from all 4.", A2)
    sc.apply("A2 applied", A2, a2)
    # A3: region from addresses: the link question, the link, then the column over it
    q = sc.propose("A3a", SAID["A3"], A3)
    link = (q.get("candidates") or [{}])[0].get("change") if q.get("result") == "question" else None
    if link:
        a3_link = sc.propose("A3b", "orders.ship_to_id → addresses", link)
        sc.apply("A3b applied", link, a3_link)
        col = {**A3, "via": [SHIP_TO]}
        a3 = sc.propose("A3c", "Now add region.", col)
    else:                                                         # R5 counted the link: A3 is ok at once
        col = A3
        a3 = q
    sc.apply("A3 applied", col, a3)
    # A4: the measure; no pipeline run
    a4 = sc.propose("A4", SAID["A4"], A4)
    sc.apply("A4 applied", A4, a4)
    # A6: undo the filter of A2 with a revert. The id is the filter's id in the list as it stands now (the last answer's
    # `changes`): a change's id names the plan it was checked on (`base`), so after A3's link it is not A2c's id.
    at = next(i for i, c in enumerate(sc.applied) if c.get("type") == "filter_rows")
    undo = {"type": "revert", "change": a4["changes"][at]}
    a6 = sc.propose("A6", SAID["A6"], undo)
    sc.apply("A6 applied", undo, a6)


def scenario_b(sc: _Scenario) -> None:
    sc.build(SAID["build_sap"])
    b1 = sc.propose("B1", SAID["B1"], B1)
    sc.apply("B1 applied", B1, b1)


def run(sample: str = "shop_lfd") -> dict:
    """Scenario A (shop_lfd) or B (sap_lfd), end to end against the in-memory Fabric. Every step's answer is the
    tool's own JSON."""
    started = time.perf_counter()
    with offline(sample) as fake:
        sc = _Scenario(sample, fake)
        (scenario_a if sample == "shop_lfd" else scenario_b)(sc)
        result = {"scenario": "A" if sample == "shop_lfd" else "B", "sample": sample, "source": dict(SOURCES[sample]),
                  "steps": sc.steps, "items": {i["displayName"]: i["type"] for i in fake.items.values()},
                  "runs": len(fake.runs), "refreshes": len(fake.refreshes),
                  "deletes_or_puts": [c for c in fake.calls if c[0] in ("DELETE", "PUT")]}
    result["seconds"] = round(time.perf_counter() - started, 2)
    return result


# ------------------------------------------------------------------ the chat, as text ---------------------------------

def _spaced(v) -> str:
    from .mcp_apps_change import _amount
    return str(_amount(v)) if isinstance(v, str) else (f"{v:,}".replace(",", " ") if isinstance(v, int) else str(v))


def _build_lines(step: dict) -> list[str]:
    out = []
    for name, dry in step["dry_run"].items():
        n = len(dry.get("would_create") or dry.get("items") or []) if isinstance(dry, dict) else 0
        out.append(f"  dry run {name}: nothing written" + (f" ({n} items)" if n else ""))
    for name, made in step["created"].items():
        status = (made.get("result") or {}).get("status") or made.get("status") or made.get("result")
        out.append(f"  created {name}: {status}")
    out.append("  in the workspace: " + ", ".join(step["items"]))
    return out


def _card_lines(step: dict) -> list[str]:
    a, card = step["answer"], step.get("card") or {}
    out = [f"  Krusgraph: {card.get('sentence') or a.get('result')}"]
    r = a.get("result")
    if r == "question":
        for c in card.get("choices") or []:
            out.append(f"    [{c['label']}]")
        return out
    if r != "ok":
        if a.get("reason"):
            out.append(f"    why: {a['reason']}")
        return out
    d = a.get("diff") or {}
    out.append("  Plan:    " + "; ".join(card.get("plan") or []))
    upd = [x for x in d.get("items") or [] if x.get("status") == "update in place"]
    out.append("  Items:   " + ("; ".join(f"{x['name']}: {x.get('summary', '')}" for x in upd) if upd else "no item changes"))
    rows = (card.get("numbers") or {}).get("rows") or []
    if rows:
        out.append("  Numbers:")
        for x in rows:
            b, f = x.get("before"), x.get("after")
            diff = f" ({x['difference']})" if x.get("difference") not in ("", None, "+0", "0", "0.00", "+0.00") else ""
            arrow = f"{b} → {f}" if b not in ("", None) and f not in ("", None) and b != f else (f if f not in ("", None) else b)
            out.append(f"    {x['label']}: {arrow}{diff if b not in ('', None) and b != f else ''}")
        layer = d.get("numbers") or {}
        if layer.get("reverts"):
            out.append("    (the undone change's numbers: the undo takes each one from after back to before)")
        mine = [c for c in (layer.get("counted") or {}).get("changes") or [] if c.get("id") == a.get("id")]
        for check in (mine[0].get("doubling") or []) if mine else []:
            if check.get("what") == "sum" and check.get("state") == "counted":
                verdict = "the same" if check.get("before") == check.get("after") else "DOUBLED"
                out.append(f"    doubling check, {check['name']} over the join: {_spaced(check['before'])} → "
                           f"{_spaced(check['after'])} ({verdict})")
    elif (a.get("change") or {}).get("type") == "add_link":
        out.append("  Numbers: none: a link changes no row (validate_plan counts it against the rows)")
    else:
        out.append("  Numbers: " + str((d.get("numbers") or {}).get("status", "none")))
    run = (a.get("pipeline_run") or {}).get("needed")
    out.append(f"  Pipeline run needed: {'yes' if run else 'no'}.  [Yes]  [No]" + ("  [Undo the last change]" if card.get("undo") else ""))
    return out


def _apply_lines(step: dict) -> list[str]:
    a = step["answer"]
    out = []
    if a.get("result") != "ok":
        return [f"  apply_change: {a.get('result')} ({a.get('kind')}): {a.get('reason', '')}"]
    for s in a.get("steps") or []:
        out.append(f"  {s['step']}. {s['action']} {s['name']}: {s.get('status', '')}")
    v = a.get("verify") or {}
    out.append(f"  definition: {(v.get('definition') or {}).get('state')}; numbers after the run: "
               f"{(v.get('numbers_after_run') or {}).get('state')}")
    for r in (v.get("numbers_after_run") or {}).get("rows") or []:
        if "counted" in r:
            out.append(f"    silver {r['table']}: {_spaced(r['counted'])} rows (expected {_spaced(r['expected'])})")
    out.append("  " + a.get("writes", ""))
    return out


def lines(result: dict) -> list[str]:
    """The run as the chat shows it: what the person types, Krusgraph's sentence, the diff per layer, the numbers
    before → after (amounts with a space between thousands) and what apply_change did."""
    head = (f"krusgraph demo change: scenario {result['scenario']} on {result['sample']} (synthetic), against an "
            "in-memory Fabric. Nothing leaves this machine.")
    out = [head, ""]
    for step in result["steps"]:
        if step["kind"] == "build":
            out.append(f"[build] You: {step['said']}")
            out += _build_lines(step)
        elif step["kind"] == "propose":
            out.append(f"[{step['step']}] You: {step['said']}")
            out += _card_lines(step)
        else:
            out.append(f"[{step['step']}] You: {step['said']}")
            out += _apply_lines(step)
        out.append("")
    out.append(f"{result['runs']} pipeline run(s), {result['refreshes']} refresh(es), "
               f"{len(result['deletes_or_puts'])} delete(s); {result['seconds']} s.")
    return out


def summary(result: dict) -> dict:
    """The run without the tools' whole answers (the diffs and SQL): per step what was said, the answer, the card's
    sentence, plan lines and numbers, the items updated, and what apply_change wrote and verified."""
    steps = []
    for s in result["steps"]:
        row = {"step": s["step"], "said": s["said"], "kind": s["kind"]}
        if s["kind"] == "build":
            row["created"] = {k: (v.get("result") or {}).get("status") if isinstance(v.get("result"), dict) else v.get("result")
                              for k, v in s["created"].items()}
            row["items"] = s["items"]
        elif s["kind"] == "propose":
            a, card = s["answer"], s.get("card") or {}
            row.update(result=a.get("result"), kind_of_answer=a.get("kind"), sentence=card.get("sentence"), id=a.get("id"))
            if a.get("result") == "question":
                row["choices"] = [c["label"] for c in card.get("choices") or []]
            if a.get("result") == "ok":
                row.update(plan=card.get("plan"), numbers=(card.get("numbers") or {}).get("rows"),
                           items=[{"name": x["name"], "summary": x.get("summary")} for x in a["diff"]["items"]
                                  if x.get("status") == "update in place"],
                           pipeline_run=(a.get("pipeline_run") or {}).get("needed"), confirm=a.get("confirm"))
        else:
            a = s["answer"]
            v = a.get("verify") or {}
            row.update(result=a.get("result"), written=a.get("written"),
                       steps=[{k: x.get(k) for k in ("step", "action", "name", "status")} for x in a.get("steps") or []],
                       definition=(v.get("definition") or {}).get("state"),
                       numbers_after_run=(v.get("numbers_after_run") or {}).get("state"),
                       silver_rows={r["table"]: r.get("counted") for r in (v.get("numbers_after_run") or {}).get("rows") or []
                                    if "counted" in r},
                       writes=a.get("writes"))
        steps.append(row)
    return {"scenario": result["scenario"], "sample": result["sample"], "source": result["source"], "steps": steps,
            "runs": result["runs"], "refreshes": result["refreshes"], "deletes_or_puts": len(result["deletes_or_puts"]),
            "seconds": result["seconds"],
            "note": "Synthetic rows; Fabric is an in-memory stand-in (fabric_backend/change_demo.py). The tools' own "
                    "functions answered every step. Nothing left this machine."}
