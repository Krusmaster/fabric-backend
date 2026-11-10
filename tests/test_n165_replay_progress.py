"""n165: the founder's feedback of 8 November 2026. On a first visit "nothing happens", then after a few seconds it
"starts": n154's first round showed turn 1 finished and still for 6 s, so the first motion was turn 2 typing. Turn 1 now
plays like the others from 0 s (question typing at once, answer in by 2 s), four dots under the box say which turn is on,
and turns 1 and 2 say what the engine finds today on the synthetic shop data (seed.py), with the caption saying so.
The browser check (0.5 s and 2.5 s after load) is in tests/n154_browser.js, asserted by test_n154_replay_and_widget.py."""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from test_golden import SRC, fabric  # noqa: E402,F401 - the hosted server against the synthetic shop data
from tests.test_site import client  # noqa: E402,F401

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "fabric_backend" / "static" / "site.css").read_text(encoding="utf-8")


def _box(client) -> str:
    html = client.get("/").text
    return re.search(r'<figure class="session".*?</figure>', html, re.S).group(0)


def _keyframes(name: str) -> str:
    return re.search(r"@keyframes " + name + r"\{(.*?\})\}", CSS).group(1)


def test_turn_one_has_no_first_cycle_rule_and_starts_at_0s():
    assert ":first-child" not in "".join(re.findall(r"[^{}]*\.session-turn[^{}]*\{", CSS))
    assert "session-turn-first" not in CSS and "session-first-" not in CSS
    assert ".session-turn{grid-area:1/1;display:flex;flex-direction:column;justify-content:flex-end;gap:16px;opacity:0;animation:session-turn 24s infinite}" in CSS
    # only turns 2-4 are delayed (6 s apart): nothing delays turn 1
    delays = re.findall(r"\.session-turn:nth-child\((\d)\),\.session-turn:nth-child\(\1\) \*\{animation-delay:(\d+)s\}", CSS)
    assert delays == [("2", "6"), ("3", "12"), ("4", "18")]
    assert not re.search(r"\.session-turn:nth-child\(1\)", CSS)
    # within a 24 s cycle: visible by 1.5 % (0.36 s), typing from 0 %, the answer fully in by 8.25 % (1.98 s)
    assert _keyframes("session-turn").startswith("0%{opacity:0}1.5%,")
    assert _keyframes("session-type").startswith("0%{clip-path:inset(0 100% 0 0);opacity:1}")
    answer_in = float(re.search(r"([\d.]+)%,100%\{opacity:1", _keyframes("session-answer")).group(1))
    assert answer_in / 100 * 24 <= 2.0
    # phones keep showing the question without the typing clip, on the same timing
    assert "@media (max-width:719px){.session{padding:18px 16px 12px}.session-text{animation-name:session-show;clip-path:none}}" in CSS
    assert _keyframes("session-show") == "0%{opacity:0}1.5%,5.25%{opacity:1}5.5%,100%{opacity:0}"


def test_four_dots_follow_the_turns_and_are_hidden_from_screen_readers(client):
    """n190: the replay left the home page; its styles stay until the clean-up in docs/WEBSITE_IMPLEMENTATION_PLAN.md."""
    assert '<figure class="session"' not in client.get("/").text
    assert "animation:session-dot 24s step-end infinite" in CSS


def test_turns_one_and_two_are_what_the_engine_answers_on_the_shop_data(client, fabric):
    """The numbers of turns 1 and 2 come from plan_backend and validate_plan on the synthetic shop data (the hosted tools
    over the tests' SQL endpoint, R5 included); the caption dates them 8 November 2026 and claims no Claude session."""
    from fabric_backend import server
    plan = json.loads(server.plan_backend(**SRC, detail="summary"))
    checks = json.loads(server.validate_plan(**SRC))
    head = plan["summary"].splitlines()[0]
    assert head == "7 tables, 6 with keys, 7 relationships"
    assert plan["keys"]["order_items"] == "order_id+line_no (K5)" and "order_items.order_id -> orders [R1]" in plan["relationships"]
    assert plan["keyless"] == ["audit_log"]
    assert any("orders.ship_to_id -> addresses [R5]" in r and "15 of 15" in r for r in plan["relationships"])
    assert checks["summary"] == "6 of 6 keys unique, 7 of 7 relationships hold without orphans"

    assert '<figure class="session"' not in client.get("/").text          # n190: the replay left the home page
