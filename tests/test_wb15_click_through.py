"""Round WB15: Gustav's second phone test of 19 November 2026 (claude.ai Android, about 390 px, dark mode, demo / demo_lh /
dbo, the SAP order-to-cash tables). His verdict: "several boxes replacing each other: a new Krusgraph box after every
choice. And you don't see the mascots, and there is honestly a lot of unnecessary information."

The end-to-end test here is a required check (CONTRIBUTING.md, "The guided path is clicked through"): it runs in CI's
test job with the other browser tests, and it fails instead of skipping there when Chromium is missing. It clicks only
the card's buttons on the synthetic SAP demo (tests/wb15_fake.py: the hosted tools, the outer seams faked, no write
possible) from step 1 to the confirmation step, at 390 px, light and dark, and checks:

- each click advances inside the same card (no message to the chat, the step number in the same card goes up);
- one total (9) and monotonic numbering; the header matches what the step shows;
- the mascot is visible (at least 60 px) at the top of every step;
- every step except the map fits in 390 x 800 without scrolling;
- Accept, Reject, Accept, Reject tapped as fast as the card lets end as rejected everywhere: the card, the next steps,
  the shared state and the dry runs; the buttons are off while a decision call runs;
- the rejected link is absent from the dry runs that follow ("23 relationships", "1 relationship left out by your
  decision"); the pipeline dry run still says "runs silver_dbo, then gold_dbo, then demo_lh_pipeline_check";
- on a host that runs no tool from the card, a button puts plain words in the chat (never a tool's name with its
  arguments) and the card folds to one line ("Moved on: step 1"), with no blank space under it.

SM2 (docs/SMOOTH/PLAN.md, row 1) changed the path on purpose, in the same pull request as this test: five steps
(Your data, Check, Decide, Dry run, Create) instead of nine. The first card is "demo › demo_lh › dbo ✓" (one usable
option each, chosen by the start tool); Check has run the map, the row check and the doubled totals on its own and says
them in one line each, the map under Details; one "Dry run everything" button runs the three dry runs; after Create a
closing step offers Open in Fabric, Add a source and Schedule it. Every step fits 390 x 800, the dry run included.

ED1 (Gustav's editor test of 21 November 2026, which showed the editor's six old steps Source, Keys and links, Choose,
Dry run, Built, Data product beside this card's five) pins one set of names on purpose: the Fabric editor's step row
says the same five words as this card, and Data product is the result shown after Create, not a step of its own
(test_ed1_the_editor_and_this_card_name_the_same_five_steps).

The unit tests below pin the parts: preselecting the one usable option, the shared state's latest-tap rule, the
decisions flowing into the building tools, one numbering in the coach, and the plain-words guard.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from fabric_backend import coach, flow_state, mcp_apps_start, server, start_flow as sf

import wb15_fake as fake

TESTS = Path(__file__).parent
VBAP = "rel:sap_vbap.MANDT+VBELN>sap_vbak"
B = {"workspace": "demo", "source": "demo_lh", "schema": "dbo"}
FN_SAID = re.compile(r"\b[a-z_]+=(?:\"|'|\[|\{|true\b|false\b|\d)|\brun [a-z]+_[a-z_]+\b|\b[a-z]+_[a-z_]+\(", re.I)


# ------------------------------------------------------------------ the end-to-end click-through (required) -----------

def _browser_ready() -> bool:
    if not shutil.which("node"):
        return False
    r = subprocess.run(["node", "-e", "require('playwright').chromium.launch().then(b => b.close())"],
                       capture_output=True, cwd=TESTS.parent, timeout=60)
    return r.returncode == 0


@pytest.fixture(scope="module")
def tools_server():
    """The real hosted tools on the synthetic SAP demo, answered over HTTP for the fake host in Chromium."""
    mp = pytest.MonkeyPatch()
    fake.install(mp)
    flow_state.clear()
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):                                   # noqa: N802
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            with lock:                                       # one call at a time, like one MCP session
                out = fake.call(body["name"], body.get("arguments") or {})
            data = json.dumps(out).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield httpd.server_address[1]
    httpd.shutdown()
    mp.undo()
    flow_state.clear()


@pytest.fixture(scope="module", params=["light", "dark"])
def run(request, tools_server, tmp_path_factory):
    if not _browser_ready():
        if os.environ.get("CI"):
            pytest.fail("WB15: the click-through test is required in CI, and Chromium did not start")
        pytest.skip("Chromium (playwright) is not available here; CI runs this test")
    flow_state.clear()
    folder = tmp_path_factory.mktemp("wb15")
    card = folder / "card.html"
    card.write_text(mcp_apps_start.card_html(), encoding="utf-8")
    shots = os.environ.get("WB15_SHOTS", "")
    if shots:
        Path(shots).mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["node", str(TESTS / "wb15_click_through.js"), str(card), str(tools_server), request.param, shots],
                       capture_output=True, text=True, timeout=600, cwd=TESTS.parent)
    assert r.returncode == 0, r.stderr[-3000:]
    out = json.loads(r.stdout)
    out["scheme"] = request.param
    out["state"] = flow_state.state(flow_state.who_of(None, "fabric-token"), "demo", "demo_lh", "dbo") or \
        flow_state.state("local", "demo", "demo_lh", "dbo")
    return out


def test_every_click_advances_inside_the_same_card(run):
    assert run["errors"] == []
    assert run["messages"] == []                             # nothing went to the chat: no new card was needed
    keys = [s["key"] for s in run["steps"]]
    assert keys == ["data", "check", "decide", "dry_run", "dry_runs_done", "create", "confirmed", "done"]
    assert [c["name"] for c in run["calls"]].count("start") >= 8


def test_one_total_and_the_numbers_only_go_up(run):
    ns = [s["n"] for s in run["steps"]]
    assert ns == [1, 2, 3, 4, 4, 5, 5, 5]
    assert {s["of"] for s in run["steps"]} == {5}


def test_the_header_matches_what_the_step_shows(run):
    by = {s["key"]: s for s in run["steps"]}
    for key in ("data", "check", "decide", "dry_run", "create"):
        assert by[key]["short"] == sf.SHORT[key], key
    assert by["data"]["chosen"] == "demo › demo_lh › dbo ✓" and by["data"]["choices"] == 0
    assert "Change" in by["data"]["buttons"] and "Mascots: on" not in by["data"]["buttons"]
    assert not any(s["map"] for s in run["steps"])                # the map is under Details, on tap
    assert "17 tables, 24 links, 1 needs you." in run["checkText"]
    assert "header amounts would count twice" in run["checkText"]
    assert by["decide"]["decisions"] == 1 and by["check"]["decisions"] == 0
    assert by["dry_run"]["dryButtons"] == ["Dry run everything"]
    assert run["dryLines"] == ["✓ demo_lh_pipeline", "✓ demo_lh_model", "✓ demo_lh_agent"]
    assert by["create"]["confirm"] and not by["dry_run"]["confirm"]
    assert by["confirmed"]["creates"] and all(c.startswith("Create demo_lh_") for c in by["confirmed"]["creates"])
    assert by["done"]["buttons"] == ["Open in Fabric", "Add a source", "Schedule it"]


def test_sm2_two_or_three_buttons_plus_next_on_every_step(run):
    for s in run["steps"]:
        rest = [b for b in s["buttons"] if not b.startswith("Next") and b != "Details"]
        assert len(rest) <= 3, (s["key"], s["buttons"])


def test_the_mascot_is_visible_at_the_top_of_every_step(run):
    for s in run["steps"]:
        assert s["mascot"], (s["key"], run["scheme"])
        assert s["line"] and len(s["line"]) <= 120, s["line"]   # one short sentence


def test_every_step_fits_on_one_phone_screen_the_dry_run_included(run):
    for s in run["steps"]:
        assert not s["scroll"], (s["key"], s["bottom"], run["scheme"])


def test_rapid_alternating_decisions_end_in_the_last_tap_everywhere(run):
    assert [t["label"] for t in run["tapStates"]] == ["Accept", "Change to Reject", "Change to Accept", "Change to Reject"]
    assert all(t["offWhileRunning"] for t in run["tapStates"])
    assert run["decisionShown"] == "rejected"                 # the card
    assert "sap_vbap.MANDT+VBELN → sap_vbak: rejected" in run["dryDetails"]   # the next step
    assert run["state"]["decisions"][-1] == {"item": VBAP, "review": "rejected", "reason": "decided on the start card"}


def test_a_rejected_link_is_absent_from_the_dry_runs(run):
    d = run["dryRuns"]
    assert "runs silver_dbo, then gold_dbo, then demo_lh_pipeline_check" in d["Dry run: silver and gold"]
    model = d["Dry run: semantic model"]
    assert "23 relationships" in model and "24 relationships" not in model
    for label, text in d.items():
        assert "1 relationship left out by your decision" in text, label


def test_no_button_puts_function_call_syntax_in_the_chat(run):
    h = run["handoff"]
    assert h["errors"] == []
    sent = [m["content"][0]["text"] for m in h["messages"]]
    assert sent == ["Next: Check."]
    for text in sent + h["said"]:
        assert not FN_SAID.search(text), text


def test_a_card_that_hands_off_folds_to_one_line_without_blank_space(run):
    h = run["handoff"]
    assert h["moved"].startswith("Moved on: step 1")
    assert h["visible"] == 1
    assert h["reported"] is not None and h["reported"] <= h["bottom"] + 8 and h["bottom"] < 120


# ------------------------------------------------------------------ unit tests -----------------------------------------

def test_one_usable_source_or_workspace_is_preselected_and_next_works():
    a = sf.guide(workspace="demo", options={"step": "source", "items": [{"name": "demo_lh", "hint": "lakehouse"}]})
    assert "next_waits" not in a
    assert a["after"]["arguments"] == {"workspace": "demo", "source": "demo_lh"}     # SM2: the schema is read next
    assert [x.get("selected") for x in a["actions"] if x["kind"] == "choose"] == [True]
    w = sf.guide(options={"step": "workspace", "items": [{"name": "demo", "hint": "1 lakehouse"},
                                                         {"name": "old", "hint": "no capacity: nothing can run here"}]})
    assert w["choices"]["preselected"] == "demo" and w["after"]["arguments"]["workspace"] == "demo"
    two = sf.guide(workspace="demo", options={"step": "source", "items": [{"name": "a"}, {"name": "b"}]})
    assert "after" not in two and two["next_waits"]["why"] == "Choose a source first."
    s = sf.guide(workspace="demo", source="demo_lh", options={"step": "schema", "items": [
        {"name": "dbo", "tables": 17}, {"name": "empty", "tables": 0}]})
    assert s["after"]["arguments"]["schema"] == "dbo" and s["after"]["arguments"]["step"] == "check"
    assert sf.only_choice("schema", {"step": "schema", "items": [{"name": "dbo", "tables": 17}, {"name": "e", "tables": 0}]}) == "dbo"
    assert sf.only_choice("source", {"step": "source", "items": [{"name": "a"}, {"name": "b"}]}) is None


def test_the_latest_tap_wins_and_older_arguments_never_undo_it():
    who = "u1"
    acc = [{"item": VBAP, "review": "accepted"}]
    rej = [{"item": VBAP, "review": "rejected"}]
    link = [{"source": "sap_vbap", "source_cols": ["MANDT", "VBELN"], "target": "sap_vbak", "target_cols": ["MANDT", "VBELN"]}]
    flow_state.record(who, "demo", "demo_lh", "dbo", "decide", acc, link, tapped=True)
    s = flow_state.record(who, "demo", "demo_lh", "dbo", "decide", rej, None, tapped=True)
    assert s["decisions"][0]["review"] == "rejected" and s["confirmed"] is None
    s = flow_state.record(who, "demo", "demo_lh", "dbo", "totals", acc, link, tapped=False)   # an older card's Next
    assert s["decisions"][0]["review"] == "rejected" and s["confirmed"] is None
    s = flow_state.record(who, "demo", "demo_lh", "dbo", "decide", acc, link, tapped=True)
    assert s["decisions"][0]["review"] == "accepted" and s["confirmed"] == link
    assert flow_state.state("someone else", "demo", "demo_lh", "dbo") is None
    assert s["seq"] > 0


def test_a_new_card_from_typed_text_continues_from_the_shared_state(monkeypatch):
    fake.install(monkeypatch)
    a = json.loads(server.start(**B, step="decide", plan={"decisions": [{"item": VBAP, "review": "rejected"}]}))
    assert a["found"]["decisions"][0]["state"] == "rejected"
    b = json.loads(server.start(**B, step="dry_run"))            # Claude's call: no plan in its arguments
    assert b["decided"] == ["sap_vbap.MANDT+VBELN → sap_vbak: rejected: the next steps leave it out."]
    assert b["step"]["n"] == 4 and b["seq"] > a["seq"]


def test_decisions_flow_into_every_building_tool(monkeypatch):
    fake.install(monkeypatch)
    server.start(**B, step="decide", plan={"decisions": [{"item": VBAP, "review": "rejected"}]})
    for tool in ("create_semantic_model", "create_data_agent", "create_pipeline", "semantic_model_draft"):
        args = {**B, "name": f"x_{tool}"}
        if tool.startswith("create_"):
            args["dry_run"] = True
        d = json.loads(getattr(server, tool)(**args))
        assert not d.get("error"), (tool, d.get("error"))
        assert d["your_decisions"]["left_out"] == ["sap_vbap.MANDT+VBELN → sap_vbak"], tool
    model = json.loads(server.semantic_model_draft(**B))
    assert model["your_decisions"]["note"] == "1 relationship left out by your decision."
    flow_state.clear()
    plain = json.loads(server.semantic_model_draft(**B))
    assert "your_decisions" not in plain


def test_an_accepted_link_is_passed_as_confirmed(monkeypatch):
    fake.install(monkeypatch)
    start = json.loads(server.start(**B, step="decide"))
    accept = [x for x in start["actions"] if x.get("decision") == "accepted"][0]
    server.start(**accept["arguments"])
    seen = {}
    real = server._plan

    def spy(workspace, source, schema, keys, confirmed, ctx, *a, **k):
        seen["confirmed"] = confirmed
        return real(workspace, source, schema, keys, confirmed, ctx, *a, **k)
    monkeypatch.setattr(server, "_plan", spy)
    d = json.loads(server.create_data_agent(**B, name="demo_lh_agent", dry_run=True))
    assert seen["confirmed"] and seen["confirmed"][0]["source"] == "sap_vbap"
    assert "accepted by your decision" in d["your_decisions"]["note"]


def test_one_numbering_for_the_coach_the_card_and_claudes_text():
    for step, n, key in (("data", 1, "data"), ("map", 2, "check"), ("check", 2, "check"), ("decide", 3, "decide"),
                         ("totals", 2, "check"), ("dry_run", 4, "dry_run"), ("create", 5, "create"), ("done", 5, "create")):
        a = sf.guide(**B, step=step)
        c = coach.coach("start", {**B, "step": step}, a)
        assert (c["n"], c["of"], c["title"]) == (n, 5, sf.SHORT[key])
        assert f"step {n} of 5" in c["text"]
        from fabric_backend import mcp_apps_next as nxt
        assert f"Step {n} of 5: {sf.SHORT[key]}" in nxt.start_lead(a)
        assert "of 9" not in c["text"] + nxt.start_lead(a)
    # other tools sit on the same five steps, and the build stages never go back below the decisions
    assert coach.coach("validate_plan", B, {"totals": {}})["of"] == 5
    assert coach.coach("create_data_agent", {**B, "name": "a", "dry_run": True}, {"would_create": []})["n"] == 4
    assert coach.coach("list_sources", {"workspace": "demo"}, {"sources": []})["n"] == 1


def test_the_step_sentences_are_short_and_the_lead_asks_for_one_sentence():
    for step in sf.KEYS:
        a = sf.guide(**B, step=step)
        assert len(a["say"]) <= 120, (step, a["say"])
        assert a["who"] in ("onto", "thinker", "builder")
    from fabric_backend import mcp_apps_next as nxt
    lead = nxt.start_lead(sf.guide(**B))
    assert "the card already shows this step" in lead and "The step's question for the user" in lead   # DIR1: facts


def test_step_9_is_never_a_dead_end():
    a = sf.guide(**B, step="create")
    confirm = [x for x in a["actions"] if x["kind"] == "confirm"]
    assert len(confirm) == 1 and confirm[0]["arguments"]["confirm"] is True
    assert confirm[0]["arguments"]["create"] == ["demo_lh_pipeline", "demo_lh_model", "demo_lh_agent"]
    assert not FN_SAID.search(confirm[0]["ask"])
    b = sf.guide(**B, step="create", create=confirm[0]["arguments"]["create"], confirm=True)
    assert [x["label"] for x in b["actions"]] == ["Create demo_lh_pipeline", "Create demo_lh_model", "Create demo_lh_agent"]
    assert b["after"]["arguments"]["step"] == "done"              # SM2: what now, after Create
    d = sf.guide(**B, step="done")
    assert [x["label"] for x in d["actions"]] == ["Open in Fabric", "Add a source", "Schedule it"]
    assert d["actions"][0]["url"].startswith("https://") and d["actions"][1]["arguments"]["step"] == "source"


def test_the_cards_send_plain_words_only():
    from fabric_backend import mcp_apps_next as nxt
    js = nxt.js()
    assert "function plainAsk" in js and "plainAsk(text).slice(0, 8000)" in js
    assert "sayInChat(s.say" not in js
    assert "sayInChat(plainAsk(askOf(s))" in js


def test_sm1_each_sample_step_says_its_own_sentence():
    """SM1 (docs/SMOOTH/AUDIT.md): on the synthetic shop the card fell back to the coach's line, which was the step
    before's: step 7 said "A few links need you" and step 9 "Try a dry run". Each step now has its own sentence."""
    said = {}
    for key in ("check", "decide", "dry_run", "create"):
        said[key] = sf.guide(sample=True, step=key)["say"]
        assert said[key] and len(said[key].split()) <= 15, (key, said[key])
    assert len(set(said.values())) == len(said)
    assert "decision" not in said["check"] and "dry run" not in said["create"]


def test_sm2_the_sample_has_the_same_dry_run_button():
    """SM2 (AUDIT.md D2): the sample's dry run is a button, as on your own data, and its answer is one line each."""
    a = sf.guide(sample=True, step="dry_run")
    allb = [x for x in a["actions"] if x["kind"] == "dry_run_all"]
    assert len(allb) == 1 and allb[0]["arguments"]["confirm"] is True and allb[0]["primary"]
    b = sf.guide(**allb[0]["arguments"])
    assert b["lines"] == ["✓ shop_pipeline", "✓ shop_model", "✓ shop_agent"]
    assert not [x for x in b["actions"] if x["kind"] == "dry_run_all"]
    # from the sample's start: Next, Next and the dry run's button
    s = sf.guide(sample=True)
    assert s["step"]["n"] == 2 and s["after"]["arguments"]["step"] == "decide"
    assert sf.guide(**s["after"]["arguments"])["after"]["arguments"]["step"] == "dry_run"


def test_ed1_the_editor_and_this_card_name_the_same_five_steps():
    model = Path(__file__).resolve().parent.parent / "workload" / "Workload" / "app" / "items" / "ModelItem"
    steps = (model / "stepWords.ts").read_text(encoding="utf-8")
    words = re.search(r"export const STEP_WORDS = \[([^\]]*)\]", steps).group(1)
    editor = re.findall(r'"([^"]+)"', words)
    card = [sf.SHORT[k] for k in sf.KEYS]
    assert editor == card == ["Your data", "Check", "Decide", "Dry run", "Create"]
    # five rows in the editor's step row, each labelled from STEP_WORDS; Data product is shown under Create's step
    assert len(re.findall(r"\{ view: \"\w+\", label: STEP_WORDS\[\d\]", steps)) == 5
    assert 'label: STEP_WORDS[4], also: ["product"]' in steps
    for old in ("Source", "Keys and links", "Choose", "Built", "Data product"):
        assert not re.search(rf'label: "{old}"', steps), old
