"""Decision rules (round L1): a team's accept or reject of a proposed key or link becomes a rule for that tenant, the
next plan proposes the right thing directly and says why, rows still outrank rules, a decision can be undone, and
nothing crosses tenants. On the synthetic shop seed in SQLite, so the counts are real; no network, no AI."""
import ast
import json
import pathlib
import sqlite3

import pytest

from fabric_backend import decisions, mcp_server, seed
from fabric_backend.infer import RULES, plan
from fabric_backend.schema import Column, Schema, Table

from test_stdio_server import sqlite_execute

SHIP_TO = {"source": "orders", "source_cols": ["ship_to_id"], "target": "addresses", "target_cols": ["address_id"]}
AUDIT = "rel:audit_log.customer_id>customers"
SCOPE = decisions.scope_of("fabric-odbc", "shop_lh", "shop")
AT = "2026-11-16T09:30:00Z"


def _planner(s, keys, confirmed):
    return plan(s, keys, confirmed)


def _rels(p) -> dict:
    return {(r.source, tuple(r.source_cols), r.target): r for r in p.relationships}


def _renamed(old: str, new: str) -> Schema:
    """The shop schema with one table renamed, its columns unchanged."""
    s = seed.schema("shop")
    t = s.tables.pop(old)
    s.tables[new] = Table(new, list(t.columns), schema="shop")
    return s


@pytest.fixture
def local(monkeypatch, tmp_path):
    """The local MCP server over the seed rows, with its decision file in a temporary folder; `use(schema)` swaps the
    schema the source reports (a renamed table)."""
    execute = sqlite_execute()
    current = {"schema": seed.schema("shop")}
    monkeypatch.setattr(mcp_server, "_execute_factory", lambda schema: execute)
    monkeypatch.setattr(Schema, "from_sql", classmethod(lambda cls, execute, schema="dbo", with_keys=True: current["schema"]))
    monkeypatch.setattr(mcp_server, "plan_from", lambda **kw: plan(current["schema"], kw.get("keys"), kw.get("confirmed")))
    monkeypatch.setenv("FABRIC_ODBC", "Driver={ODBC Driver 18 for SQL Server};Server=x.datawarehouse.fabric.microsoft.com;"
                                      "Database=shop_lh;Authentication=ActiveDirectoryInteractive")
    monkeypatch.setenv(decisions.ENV, str(tmp_path / "decisions.sqlite"))
    monkeypatch.delenv(decisions.TENANT_ENV, raising=False)
    monkeypatch.delenv("KRUSGRAPH_CSN", raising=False)
    monkeypatch.delenv("FABRIC_SOURCE_KIND", raising=False)

    def use(s):
        current["schema"] = s
    use.path = tmp_path / "decisions.sqlite"
    return use


def _call(fn, **kw) -> dict:
    out = json.loads(fn(**kw))
    assert "error" not in out, out
    return out


def _plan_rels(**kw) -> dict:
    out = _call(mcp_server.plan_backend, schema="shop", detail="full", **kw)
    return out, {(r["source"], tuple(r["source_cols"]), r["target"]): r for r in out["relationships"]}


# ---- accepted: proposed directly, said why -------------------------------------------------------------------------

def test_an_accepted_link_is_proposed_directly_and_says_your_team_decided_it(local):
    _, rels = _plan_rels()
    assert ("orders", ("ship_to_id",), "addresses") not in rels                 # the name rules alone do not find it
    rec = _call(mcp_server.record_decision, schema="shop", decision="accepted", link=SHIP_TO, role="steward",
                reason="ship_to_id holds address ids")
    assert rec["recorded"]["evidence"] == {"rows_with_value": 60, "orphans": 0, "verdict": "holds for all 60 rows with a value"}
    assert rec["recorded"]["role"] == "steward" and rec["rule"].startswith("decided by your team on ")
    out, rels = _plan_rels()
    r = rels[("orders", ("ship_to_id",), "addresses")]
    assert r["rule"] == "decided" and r["note"].startswith("decided by your team on ") and "steward" in r["note"]
    assert r["evidence"] == "given, not counted"                                 # rows outrank rules: not "counted" yet
    assert out["decisions"]["applied"][0]["item"] == "rel:orders.ship_to_id>addresses"
    assert any("decided by your team" in line for line in out["decisions"]["lines"])
    assert "decision(s) of your team applied as rules" in out["summary"]
    assert "decided" in RULES and "validate_plan" in RULES["decided"]


def test_an_accepted_key_goes_in_with_the_rule_decided():
    store = decisions.Store()
    p0 = plan(seed.schema("shop"))
    assert "audit_log" in p0.keyless
    decisions.record(store, "t1", SCOPE, p0, "accepted", "owner", key={"table": "audit_log", "columns": ["EVENT", "happened_at"]}, at=AT)
    p = decisions.plan(seed.schema("shop"), store.active("t1", SCOPE), _planner)
    assert p.keys["audit_log"] == (["event", "happened_at"], "decided") and "audit_log" not in p.keyless
    assert p.decisions["applied"][0]["provenance"] == "decided by your team on 16 November 2026 (owner): accepted"


def test_the_callers_own_arguments_still_win_over_a_decision():
    store = decisions.Store()
    p0 = plan(seed.schema("shop"))
    decisions.record(store, "t1", SCOPE, p0, "accepted", "steward", link=SHIP_TO, at=AT)
    other = {"source": "orders", "source_cols": ["ship_to_id"], "target": "customers", "target_cols": ["customer_id"]}
    p = decisions.plan(seed.schema("shop"), store.active("t1", SCOPE), _planner, confirmed=[other])
    assert _rels(p)[("orders", ("ship_to_id",), "customers")].rule == "confirmed"
    assert ("orders", ("ship_to_id",), "addresses") not in _rels(p)
    assert p.decisions["not_applied"][0]["why"] == "the call confirms this column itself"


# ---- rejected: not proposed, reason shown, undone ------------------------------------------------------------------

def test_a_rejected_link_is_not_proposed_with_the_reason_and_can_be_undone(local):
    rec = _call(mcp_server.record_decision, schema="shop", decision="rejected", item=AUDIT, role="analyst",
                reason="audit_log keeps ids of deleted customers too")
    out, rels = _plan_rels()
    assert ("audit_log", ("customer_id",), "customers") not in rels
    assert ("orders", ("customer_id",), "customers") in rels                     # the same column elsewhere is untouched
    s = out["decisions"]["suppressed"][0]
    assert s["how"] == "exact" and s["decision"] == rec["recorded"]["id"]
    assert "audit_log keeps ids of deleted customers too" in s["provenance"] and "analyst" in s["provenance"]
    undone = _call(mcp_server.record_decision, schema="shop", undo=rec["recorded"]["id"], role="steward")
    assert undone["undone"]["undone_at"] and undone["undone"]["undone_role"] == "steward"
    out, rels = _plan_rels()
    assert rels[("audit_log", ("customer_id",), "customers")]["rule"] == "R1" and "decisions" not in out
    hist = _call(mcp_server.list_decisions, schema="shop")
    assert len(hist["decisions"]) == 1 and hist["not_undone"] == 0                 # history kept, no longer a rule
    with pytest.raises(decisions.DecisionError, match="already undone"):
        decisions.Store(local.path).undo("local", rec["recorded"]["id"], "steward")


def test_a_later_decision_on_the_same_item_replaces_the_earlier_one():
    store = decisions.Store()
    p0 = plan(seed.schema("shop"))
    decisions.record(store, "t1", SCOPE, p0, "rejected", "analyst", item=AUDIT, at=AT)
    decisions.record(store, "t1", SCOPE, p0, "accepted", "steward", item=AUDIT, at="2026-11-17T08:00:00Z")
    assert [d["decision"] for d in store.active("t1", SCOPE)] == ["accepted"]
    p = decisions.plan(seed.schema("shop"), store.active("t1", SCOPE), _planner)
    assert _rels(p)[("audit_log", ("customer_id",), "customers")].rule == "decided"


def test_a_rejected_key_takes_the_links_into_it_with_it():
    store = decisions.Store()
    p0 = plan(seed.schema("shop"))
    decisions.record(store, "t1", SCOPE, p0, "rejected", "engineer", item="key:products", reason="reloads duplicate it", at=AT)
    p = decisions.plan(seed.schema("shop"), store.active("t1", SCOPE), _planner)
    assert "products" not in p.keys and "products" in p.keyless
    assert ("order_items", ("product_id",), "products") not in _rels(p)
    assert {s["how"] for s in p.decisions["suppressed"]} == {"exact", "key rejected"}


def test_a_rejection_the_call_contradicts_is_kept_and_shown_as_a_conflict():
    store = decisions.Store()
    p0 = plan(seed.schema("shop"))
    decisions.record(store, "t1", SCOPE, p0, "rejected", "analyst", item=AUDIT, at=AT)
    again = {"source": "audit_log", "source_cols": ["customer_id"], "target": "customers", "target_cols": ["customer_id"]}
    p = decisions.plan(seed.schema("shop"), store.active("t1", SCOPE), _planner, confirmed=[again])
    assert _rels(p)[("audit_log", ("customer_id",), "customers")].rule == "confirmed"
    assert p.decisions["conflicts"][0]["kept_because"] == "the call confirms this link"


# ---- name patterns: only when deterministic, and shown -------------------------------------------------------------

def test_a_rejected_link_follows_its_table_renamed_and_says_so(local):
    _call(mcp_server.record_decision, schema="shop", decision="rejected", item=AUDIT, role="analyst", count_rows=False)
    local(_renamed("audit_log", "audit_events"))
    out, rels = _plan_rels()
    assert ("audit_events", ("customer_id",), "customers") not in rels
    assert ("orders", ("customer_id",), "customers") in rels and ("addresses", ("customer_id",), "customers") in rels
    s = out["decisions"]["suppressed"][0]
    assert s["how"] == "pattern" and s["item"] == "rel:audit_events.customer_id>customers"
    assert "audit_log is not in the schema now and audit_events has exactly the columns audit_log had" in s["pattern"]


def test_no_pattern_when_the_renamed_table_is_not_recognisable():
    store = decisions.Store()
    decisions.record(store, "t1", SCOPE, plan(seed.schema("shop")), "rejected", "analyst", item=AUDIT, at=AT)
    s = _renamed("audit_log", "audit_events")
    s.tables["audit_events"].columns.append(Column("source_system", "varchar"))  # other columns: not read as a rename
    p = decisions.plan(s, store.active("t1", SCOPE), _planner)
    assert ("audit_events", ("customer_id",), "customers") in _rels(p)
    assert p.decisions["not_applied"][0]["why"] == "table audit_log is not in the schema now"
    two = _renamed("audit_log", "audit_a")                                       # two tables with those columns: none
    two.tables["audit_b"] = Table("audit_b", list(two.tables["audit_a"].columns), schema="shop")
    p = decisions.plan(two, store.active("t1", SCOPE), _planner)
    assert {("audit_a", ("customer_id",), "customers"), ("audit_b", ("customer_id",), "customers")} <= set(_rels(p))


# ---- rows outrank rules --------------------------------------------------------------------------------------------

def test_validate_plan_flags_an_accepted_link_the_rows_contradict(local):
    wrong = {"source": "orders", "source_cols": ["ship_to_id"], "target": "customers", "target_cols": ["customer_id"]}
    rec = _call(mcp_server.record_decision, schema="shop", decision="accepted", link=wrong, role="reviewer")
    assert rec["warning"].startswith("The rows do not support this link now: 25 of 60 rows")
    out = _call(mcp_server.validate_plan, schema="shop")
    c = out["decisions"]["contradicted_by_rows"]
    assert len(c) == 1 and c[0]["item"] == "rel:orders.ship_to_id>customers" and c[0]["now"].startswith("25 of 60 rows")
    assert "Your team accepted this link, but the rows now say" in c[0]["what"]
    ok = _call(mcp_server.record_decision, schema="shop", decision="accepted", link=SHIP_TO, role="reviewer")
    assert "warning" not in ok                                                   # replaces the earlier link of that column
    assert [d["item"] for d in decisions.Store(local.path).active("local", SCOPE)] == ["rel:orders.ship_to_id>addresses"]
    assert [x["item"] for x in _call(mcp_server.validate_plan, schema="shop")["decisions"]["contradicted_by_rows"]] == []


def test_a_decision_on_a_changed_table_says_so_and_a_gone_column_is_not_applied():
    store = decisions.Store()
    decisions.record(store, "t1", SCOPE, plan(seed.schema("shop")), "accepted", "steward", link=SHIP_TO, at=AT)
    s = seed.schema("shop")
    s.tables["orders"].columns.append(Column("channel", "varchar"))
    p = decisions.plan(s, store.active("t1", SCOPE), _planner)
    assert p.decisions["applied"][0].get("changed_since") is True
    s.tables["orders"].columns[:] = [c for c in s.tables["orders"].columns if c.name != "ship_to_id"]
    p = decisions.plan(s, store.active("t1", SCOPE), _planner)
    assert p.decisions["not_applied"][0]["why"] == "column orders.ship_to_id is not in the schema now"


# ---- per tenant, and nothing else ----------------------------------------------------------------------------------

def test_nothing_crosses_tenants(tmp_path):
    store = decisions.Store(tmp_path / "d.sqlite")
    p0 = plan(seed.schema("shop"))
    a = decisions.record(store, "tenant-a", SCOPE, p0, "rejected", "analyst", item=AUDIT, at=AT)
    decisions.record(store, "tenant-a", SCOPE, p0, "accepted", "steward", link=SHIP_TO, at=AT)
    assert len(store.active("tenant-a", SCOPE)) == 2
    assert store.active("tenant-b", SCOPE) == [] and store.history("tenant-b") == []
    assert store.get("tenant-b", a["id"]) is None
    with pytest.raises(decisions.DecisionError, match="no decision"):
        store.undo("tenant-b", a["id"], "steward")                             # another tenant's id: as if it did not exist
    assert store.get("tenant-a", a["id"])["undone_at"] is None
    pb = decisions.plan(seed.schema("shop"), store.active("tenant-b", SCOPE), _planner)
    assert ("audit_log", ("customer_id",), "customers") in _rels(pb) and ("orders", ("ship_to_id",), "addresses") not in _rels(pb)
    assert store.active("tenant-a", decisions.scope_of("fabric-odbc", "other_lh", "shop")) == []   # nor across sources
    raw = sqlite3.connect(tmp_path / "d.sqlite").execute("SELECT tenant FROM decisions").fetchall()
    assert {r[0] for r in raw} == {decisions.tenant_key("tenant-a")} and all("tenant-a" not in r[0] for r in raw)


def test_the_local_server_keeps_each_tenant_apart(local, monkeypatch):
    monkeypatch.setenv(decisions.TENANT_ENV, "tenant-a")
    _call(mcp_server.record_decision, schema="shop", decision="rejected", item=AUDIT, role="analyst", count_rows=False)
    assert ("audit_log", ("customer_id",), "customers") not in _plan_rels()[1]
    monkeypatch.setenv(decisions.TENANT_ENV, "tenant-b")
    out, rels = _plan_rels()
    assert ("audit_log", ("customer_id",), "customers") in rels and "decisions" not in out
    assert _call(mcp_server.list_decisions)["decisions"] == []


def test_a_role_is_kept_never_a_name_and_the_reason_is_short():
    store = decisions.Store()
    p0 = plan(seed.schema("shop"))
    with pytest.raises(decisions.DecisionError, match="a role, never a person's name"):
        decisions.record(store, "t1", SCOPE, p0, "accepted", "Firstname Lastname", link=SHIP_TO)
    with pytest.raises(decisions.DecisionError, match="decision is one of"):
        decisions.record(store, "t1", SCOPE, p0, "maybe", "steward", link=SHIP_TO)
    with pytest.raises(decisions.DecisionError, match="no such link"):
        decisions.record(store, "t1", SCOPE, p0, "accepted", "steward", item="rel:orders.ghost>customers")
    d = decisions.record(store, "t1", SCOPE, p0, "accepted", "steward", link=SHIP_TO, reason="x " * 400)
    assert len(d["reason"]) <= decisions.REASON_LIMIT and set(d) >= {"role", "at", "evidence", "fingerprint", "names"}


def test_no_decision_file_means_no_rules_and_nothing_written(local, monkeypatch, tmp_path):
    monkeypatch.setenv(decisions.ENV, str(tmp_path / "none" / "decisions.sqlite"))
    assert "decisions" not in _plan_rels()[0]
    assert not (tmp_path / "none").exists()
    monkeypatch.setenv(decisions.ENV, "off")
    out = json.loads(mcp_server.record_decision(schema="shop", link=SHIP_TO))
    assert "switched off" in out["error"]


# ---- deterministic, no AI ------------------------------------------------------------------------------------------

def test_the_same_decisions_give_the_same_plan():
    store = decisions.Store()
    p0 = plan(seed.schema("shop"))
    decisions.record(store, "t1", SCOPE, p0, "accepted", "steward", link=SHIP_TO, at=AT)
    decisions.record(store, "t1", SCOPE, p0, "rejected", "analyst", item=AUDIT, at=AT)
    one, two = (decisions.plan(seed.schema("shop"), store.active("t1", SCOPE), _planner) for _ in range(2))
    assert [r.__dict__ for r in one.relationships] == [r.__dict__ for r in two.relationships]
    assert one.decisions == two.decisions and one.keys == two.keys


def test_decision_rules_use_no_model_and_no_network():
    src = pathlib.Path(decisions.__file__).read_text()
    imported = {n.split(".")[0] for node in ast.walk(ast.parse(src)) if isinstance(node, (ast.Import, ast.ImportFrom))
                for n in ([a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or "."])}
    assert imported <= {"__future__", "hashlib", "json", "os", "sqlite3", "threading", "datetime", "pathlib", ""}
    for word in ("openai", "anthropic", "sklearn", "torch", "numpy", "embedding", "requests", "urllib", "http"):
        assert word not in src.lower(), word


def test_the_docs_say_cross_tenant_learning_is_not_built():
    doc = (pathlib.Path(__file__).parent.parent / "docs" / "DECISION-RULES.md").read_text()
    assert "Cross-tenant learning" in doc and "not built" in doc.lower()
    for word in ("opt-in", "anonymised", "DPA"):
        assert word in doc
