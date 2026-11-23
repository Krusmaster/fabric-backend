"""Round BL47 (23 November 2026): issue #104, second part, the card fold.

WB15 folded a Start Krusgraph card to "Moved on: step N" when it handed a step to the chat itself. When the user typed
instead and Claude opened a newer card, the older card learnt of it only over a BroadcastChannel, and whether two
frames of one claude.ai conversation share one is not known (docs/CHAT-TEST-2026-11-19.md); where they do not, the
older card kept its height. The issue proposed a read-only "is this card still the latest?" check through the start
tool. This round adds it: `start(..., step="latest")` answers the flow's newest sequence number and step
(flow_state.latest), records nothing and reads nothing from Fabric, and the card asks it when its first answer is drawn,
when it comes back into view and when the page is shown again, and folds when the path has moved on.

The browser test runs the card under the same fake host as the WB15 click-through (tests/wb15_fake.py, the real hosted
tools on the synthetic SAP demo), each card in its own page so no BroadcastChannel reaches it.
"""
from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from fabric_backend import flow_state, mcp_apps, mcp_apps_start, server, start_flow as sf

import wb15_fake as fake
from test_wb15_click_through import _browser_ready, tools_server  # noqa: F401  (the module's HTTP tools server)

TESTS = Path(__file__).parent
B = {"workspace": "demo", "source": "demo_lh", "schema": "dbo"}
VBAP = "rel:sap_vbap.MANDT+VBELN>sap_vbak"


@pytest.fixture(autouse=True)
def _clean():
    flow_state.clear()
    yield
    flow_state.clear()


# ------------------------------------------------------------------ the read-only check -------------------------------

def test_latest_answers_the_flows_newest_number_and_step(monkeypatch):
    fake.install(monkeypatch)
    a = json.loads(server.start(**B, step="check"))
    got = json.loads(server.start(**B, step="latest"))
    assert got["latest"] == {"seq": a["seq"], "step": "check"} and got["changes_nothing"] is True
    b = json.loads(server.start(**B, step="decide"))               # Claude's call from typed text: a newer card
    got = json.loads(server.start(**B, step="latest"))
    assert got["latest"] == {"seq": b["seq"], "step": "decide"} and b["seq"] > a["seq"]


def test_latest_records_nothing_and_never_moves_the_number(monkeypatch):
    fake.install(monkeypatch)
    server.start(**B, step="decide", plan={"decisions": [{"item": VBAP, "review": "rejected"}]})
    who = server._flow_who(None)
    before = flow_state.state(who, *B.values())
    assert before and before["decisions"][0]["review"] == "rejected"
    for _ in range(3):
        server.start(**B, step="latest", plan={"decisions": [{"item": VBAP, "review": "accepted"}]})
    assert flow_state.state(who, *B.values()) == before            # no decision taken from it, no number taken
    nxt = json.loads(server.start(**B, step="dry_run"))
    assert nxt["seq"] == before["seq"] + 1


def test_latest_reads_nothing_from_fabric(monkeypatch):
    fake.install(monkeypatch)
    server.start(**B, step="check")
    for seam in ("_start_options", "_start_review", "_start_combine", "_start_targets", "_plan"):
        monkeypatch.setattr(server, seam, lambda *a, **k: pytest.fail("step latest reached " + seam))
    assert json.loads(server.start(**B, step="latest"))["latest"]["step"] == "check"


def test_latest_without_a_flow_or_on_the_sample_is_none(monkeypatch):
    fake.install(monkeypatch)
    assert json.loads(server.start(**B, step="latest"))["latest"] is None              # nothing kept yet
    assert json.loads(server.start(workspace="demo", step="latest"))["latest"] is None  # no source, no schema
    assert json.loads(server.start(sample=True, step="latest"))["latest"] is None
    assert json.loads(server.start(**B, step=" LATEST "))["latest"] is None             # same word, any case


def test_latest_is_per_person():
    flow_state.record("local", *B.values(), "check", None, None, False)
    assert flow_state.latest("local", *B.values())["step"] == "check"
    assert flow_state.latest("someone else", *B.values()) is None


def test_latest_holds_across_two_replicas():
    """BL44's shared store: a card served by one replica sees the number the other replica took."""
    from fabric_backend import registration_store as rs
    store = rs.MemoryStore()
    a = importlib.import_module("fabric_backend.flow_state")
    spec = importlib.util.spec_from_file_location("flow_state_b", a.__file__)
    b = importlib.util.module_from_spec(spec)
    sys.modules["flow_state_b"] = b
    spec.loader.exec_module(b)
    try:
        a.use_store(store)
        b.use_store(store)
        s1 = a.record("u", *B.values(), "check", None, None, False)
        assert b.latest("u", *B.values()) == {"seq": s1["seq"], "step": "check"}
        s2 = b.record("u", *B.values(), "decide", None, None, False)
        assert a.latest("u", *B.values()) == {"seq": s2["seq"], "step": "decide"} and s2["seq"] > s1["seq"]
        got = store.get("flow", a._rk(a._key("u", *B.values())))[0]
        assert a.latest("u", *B.values()) and store.get("flow", a._rk(a._key("u", *B.values())))[0] == got   # read only
    finally:
        a.use_store(None)
        sys.modules.pop("flow_state_b", None)


def test_latest_in_memory_does_not_renew_the_time_to_live(monkeypatch):
    flow_state.record("u", *B.values(), "check", None, None, False)
    k = flow_state._key("u", *B.values())
    at = flow_state._FLOWS[k]["at"]
    flow_state.latest("u", *B.values())
    assert flow_state._FLOWS[k]["at"] == at
    flow_state._FLOWS[k]["at"] = at - flow_state.TTL - 1
    assert flow_state.latest("u", *B.values()) is None


def test_the_hosted_answer_has_no_coach_no_step_and_no_row_value(monkeypatch):
    fake.install(monkeypatch)
    fake.call("start", {**B, "step": "check"})
    r = fake.call("start", {**B, "step": "latest"})
    d = r["structuredContent"]
    assert set(d) == {"latest", "changes_nothing", "note"}
    assert set(d["latest"]) == {"seq", "step"}
    assert r["content"][0]["text"] == mcp_apps.LATEST_LEAD
    assert "Coach" not in json.dumps(r) and "step 1 of 5" not in json.dumps(r)


def test_the_listing_names_the_new_word():
    from fabric_backend import tool_params
    assert '"latest" is the card' in str(tool_params.StartStep.__metadata__)
    assert sf.LATEST == "latest" and sf.LATEST not in sf.KEYS


# ------------------------------------------------------------------ the card -------------------------------------------

def test_the_card_asks_only_through_start_and_keeps_the_card_rules():
    html = mcp_apps_start.card_html()
    assert 'step: "latest"' in html and 'callTool("start", { workspace: myFlow.workspace' in html
    assert "new IntersectionObserver" in html and '"visibilitychange"' in html
    assert "setTimeout(checkLatest, 1200)" in html
    low = html.lower()
    for banned in ("navigator.", "url(", "innerhtml", "outerhtml", "insertadjacenthtml", "fetch(", "xmlhttprequest",
                   "localstorage", "sessionstorage", "document.cookie", "eval(", "new function", "http://"):
        assert banned not in low, banned
    # a card's own call makes any check that crossed it void; never while a call of its own runs
    assert "busy = true; setBusy(true); ownCalls++;" in html
    assert "calls === ownCalls && !busy" in html
    assert "if (moved || busy || checking || !myFlow || !lastSeq || !canCallTools()) return;" in html


# ------------------------------------------------------------------ in a browser ---------------------------------------

@pytest.fixture(scope="module", params=["light", "dark"])
def run(request, tools_server, tmp_path_factory):  # noqa: F811
    if not _browser_ready():
        if os.environ.get("CI"):
            pytest.fail("BL47: the card-fold browser test runs in CI, and Chromium did not start")
        pytest.skip("Chromium (playwright) is not available here; CI runs this test")
    flow_state.clear()
    card = tmp_path_factory.mktemp("bl47") / "card.html"
    card.write_text(mcp_apps_start.card_html(), encoding="utf-8")
    r = subprocess.run(["node", str(TESTS / "bl47_card_fold.js"), str(card), str(tools_server), request.param],
                       capture_output=True, text=True, timeout=600, cwd=TESTS.parent)
    assert r.returncode == 0, r.stderr[-3000:]
    out = json.loads(r.stdout)
    for k, v in out.items():
        assert v["errors"] == [], (k, v["errors"])
        assert v["messages"] == 0, k                                 # never a word to the chat
    return out


def test_a_card_that_is_still_the_latest_stays_as_it_is(run):
    live = run["live"]
    assert live["moved"] == "" and live["title"].startswith("Step 2 of 5")
    assert live["latestCalls"] == [{**B, "step": "latest"}]          # one check, when its answer was drawn


def test_an_older_card_folds_when_the_user_typed_and_a_newer_card_moved_on(run):
    t = run["typed"]
    assert t["moved"].startswith("Moved on: step 2. The path goes on in the newest Krusgraph card.")
    assert t["visible"] == 1 and t["bottom"] < 120
    assert t["reported"] is not None and t["reported"] <= t["bottom"] + 8   # the frame is told to shrink
    assert len(t["latestCalls"]) == 2                                # on the first answer, and back in view


def test_a_reloaded_old_card_folds_when_it_is_drawn(run):
    r = run["reloaded"]
    assert r["moved"].startswith("Moved on: step 2") and r["visible"] == 1
    assert r["startCalls"] == 1 and len(r["latestCalls"]) == 1       # the check only: nothing tapped, nothing recorded


def test_a_cards_own_taps_never_fold_it(run):
    o = run["own"]
    assert o["moved"] == "" and o["title"].startswith("Step 4 of 5")
    assert len(o["latestCalls"]) == 2 and o["startCalls"] == 3       # the check, Next, the check back in view


def test_a_host_without_tools_and_the_sample_send_no_check(run):
    assert run["noTools"]["latestCalls"] == [] and run["noTools"]["moved"] == ""
    assert run["sample"]["latestCalls"] == [] and run["sample"]["moved"] == ""
