"""Round n136: the site's mascots on the two MCP Apps cards (validate_plan's, n119, and review_plan's, n124).

Checked here: the figures are inline SVG built from the package's own `static/mascots.js` and the cards still load
nothing; they exist only with KRUSGRAPH_MCP_APPS=1 (the flag off means no card at all); each card has a visible switch
that hides them; Onto says the counts, the Thinker what needs attention, the Builder the next step, each sentence word
for word from the text answer and also on the card; nobody is glad about a check that failed; the text answers are what
they were; the listing keeps its tool count and cap; and a copy of only the files the Docker image holds renders the
same cards.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

import pytest

from fabric_backend import mcp_apps, mcp_apps_mascots, mcp_apps_review, server

from test_golden import SRC, fabric  # noqa: F401  (the hosted server against the synthetic shop workspace)

ROOT = Path(__file__).resolve().parents[1]
CARDS = {"validate_plan": mcp_apps.card_html, "review_plan": mcp_apps_review.card_html}


class _Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags, self.attrs = [], []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attrs += [(tag, k, v) for k, v in attrs]


def _strings(x) -> set[str]:
    """Every string in a JSON answer (keys left out)."""
    if isinstance(x, str):
        return {x}
    if isinstance(x, dict):
        return set().union(*(_strings(v) for v in x.values())) if x else set()
    if isinstance(x, list):
        return set().union(*(_strings(v) for v in x)) if x else set()
    return set()


# ------------------------------------------------------------------ the figures in the HTML ---------------------------

def test_the_figures_come_from_the_package_file():
    assert mcp_apps_mascots.SOURCE == ROOT / "fabric_backend" / "static" / "mascots.js"
    k = mcp_apps_mascots.kinds()
    for kind in mcp_apps_mascots.KINDS:
        svg = mcp_apps_mascots.svg(kind)
        assert k[kind]["body"] in svg and k[kind]["fill"] in svg            # the site's shape and colour
        assert 'aria-hidden="true"' in svg                                   # decoration: the words are in the text


@pytest.mark.parametrize("tool", sorted(CARDS))
def test_no_external_loads_with_the_mascots(tool):
    html = CARDS[tool]()
    p = _Tags()
    p.feed(html)
    assert p.tags.count("svg") >= 3
    assert not {"img", "image", "use", "link", "iframe", "object", "embed", "foreignobject", "feimage"} & set(p.tags)
    assert not [a for a in p.attrs if a[1] in ("src", "href", "xlink:href", "action", "srcset", "poster", "data",
                                               "filter", "clip-path", "mask")]
    figures = "".join(re.findall(r"<svg class=\"mascot.*?</svg>", html, re.S))
    assert figures.count("<svg") == 3
    for banned in ("http", "url(", "data:", "@import", "href", "#"):
        assert banned not in figures.replace("fill=\"#", "").replace("stroke=\"#", ""), banned
    low = html.lower()
    for banned in ("url(", "data:image", "localstorage", "sessionstorage", "innerhtml", "@keyframes", "animation:"):
        assert banned not in low.replace("animation: none !important", ""), banned


@pytest.mark.parametrize("tool", sorted(CARDS))
def test_each_card_has_a_visible_switch(tool):
    html = CARDS[tool]()
    assert html.count('id="kg-toggle"') == 1 and 'aria-pressed="true"' in html and ">Mascots: on</button>" in html
    assert 'aria-controls="kg-mascots"' in html and html.count('id="kg-mascots"') == 1
    switch = re.search(r'<button id="kg-toggle"[^>]*>', html).group(0)
    assert "hidden" not in switch                                           # the switch is always on the card


def test_mascots_only_with_the_flag():
    code = r"""
import asyncio, json
from fabric_backend import server
async def go():
    out = []
    for r in await server.mcp.list_resources():
        c = await server.mcp.read_resource(r.uri)
        out.append([str(r.uri), "".join(getattr(x, "content", "") or getattr(x, "text", "") for x in c)])
    return out
tools = asyncio.run(server.mcp.list_tools())
print(json.dumps({"cards": asyncio.run(go()), "listing": json.dumps([t.model_dump(mode="json") for t in tools])}))
"""
    env = {k: v for k, v in os.environ.items() if k != mcp_apps.FLAG}
    on = json.loads(subprocess.run([sys.executable, "-c", code], env=env | {mcp_apps.FLAG: "1"}, cwd=ROOT,
                                   capture_output=True, text=True, check=True).stdout)
    off = json.loads(subprocess.run([sys.executable, "-c", code], env=env, cwd=ROOT,
                                    capture_output=True, text=True, check=True).stdout)
    assert off["cards"] == [] and "mascot" not in off["listing"].lower()
    assert [u for u, _ in on["cards"]] == [mcp_apps.CARD_URI, mcp_apps_review.CARD_URI]
    for _, html in on["cards"]:
        assert html.count('<svg class="mascot ') == 3 and 'id="kg-toggle"' in html
    assert "mascot" not in on["listing"].lower()                            # nothing about them in the tool listing


# ------------------------------------------------------------------ the text answers ----------------------------------

def _app_server():
    from mcp.server.mcpserver import MCPServer
    m = MCPServer("n136", extensions=mcp_apps.extensions(on=True))
    m.add_tool(server.validate_plan, annotations=server.RO, meta=mcp_apps.tool_meta(on=True))
    m.add_tool(server.review_plan, annotations=server.RO, meta=mcp_apps_review.tool_meta(on=True))
    return m


def test_the_text_answers_are_unchanged(fabric):  # noqa: F811
    from mcp import Client
    plain = {"validate_plan": server.validate_plan(**SRC), "review_plan": server.review_plan(**SRC)}

    async def go():
        async with Client(_app_server()) as c:
            return {t: await c.call_tool(t, SRC) for t in plain}
    for tool, r in asyncio.run(go()).items():
        [part] = r.content
        assert part.type == "text" and json.loads(part.text) == json.loads(plain[tool]), tool
        assert "mascot" not in part.text.lower() and "Onto" not in part.text


def test_the_listing_keeps_its_tool_count_and_cap():
    code = r"""
import asyncio, inspect, json
from fabric_backend import server
tools = asyncio.run(server.mcp.list_tools())
ro = [t.model_dump(by_alias=True, exclude_none=True, mode="json") for t in tools if t.annotations and t.annotations.read_only_hint]
for t in ro:
    t["description"] = inspect.cleandoc(t.get("description", ""))
print(json.dumps({"n": len(tools), "ro_size": len(json.dumps({"tools": ro}, separators=(",", ":"), ensure_ascii=False))}))
"""
    env = {k: v for k, v in os.environ.items() if k != mcp_apps.FLAG}
    on = json.loads(subprocess.run([sys.executable, "-c", code], env=env | {mcp_apps.FLAG: "1"}, cwd=ROOT,
                                   capture_output=True, text=True, check=True).stdout)
    off = json.loads(subprocess.run([sys.executable, "-c", code], env=env, cwd=ROOT,
                                    capture_output=True, text=True, check=True).stdout)
    assert on["n"] == off["n"] and on["ro_size"] <= 64_500 and on["ro_size"] - off["ro_size"] < 400


# ------------------------------------------------------------------ only the image's files ----------------------------

def _image_copy(dest: Path) -> Path:
    """The files the Dockerfile copies, as .dockerignore lets them through: pyproject.toml, README.md,
    deploy/constraints.txt and fabric_backend/ without caches."""
    dest.mkdir()
    for name in ("pyproject.toml", "README.md"):
        shutil.copy2(ROOT / name, dest / name)
    (dest / "deploy").mkdir()
    shutil.copy2(ROOT / "deploy" / "constraints.txt", dest / "deploy" / "constraints.txt")
    shutil.copytree(ROOT / "fabric_backend", dest / "fabric_backend",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".env*", "*.pem", "*.key", ".entra-secret"))
    return dest


def test_the_cards_render_from_a_copy_of_only_the_image_files(tmp_path):
    app = _image_copy(tmp_path / "app")
    code = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
import fabric_backend
from fabric_backend import mcp_apps, mcp_apps_review, mcp_apps_mascots
assert fabric_backend.__file__.startswith(sys.argv[1]), fabric_backend.__file__
assert str(mcp_apps_mascots.SOURCE).startswith(sys.argv[1])
print(json.dumps({"validate_plan": mcp_apps.card_html(), "review_plan": mcp_apps_review.card_html()}))
"""
    run = subprocess.run([sys.executable, "-c", code, str(app)], cwd=tmp_path, capture_output=True, text=True,
                         env={k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", mcp_apps.FLAG)})
    assert run.returncode == 0, run.stderr
    out = json.loads(run.stdout)
    for tool, card in CARDS.items():
        assert out[tool] == card() and out[tool].count('<svg class="mascot ') == 3, tool


# ------------------------------------------------------------------ in a browser --------------------------------------

def _playwright() -> bool:
    if not shutil.which("node"):
        return False
    return subprocess.run(["node", "-e", "require('playwright')"], capture_output=True, cwd=ROOT).returncode == 0


def _browse(tmp_path, tool: str, args: dict, answer: str, width: int = 480, scheme: str = "light"):
    (tmp_path / "card.html").write_text(CARDS[tool]())
    (tmp_path / "input.json").write_text(json.dumps(args))
    (tmp_path / "result.json").write_text(json.dumps({"content": [{"type": "text", "text": answer}]}))
    shot = os.environ.get("KRUSGRAPH_CARD_SHOT")
    run = subprocess.run(["node", str(Path(__file__).parent / "mcp_apps_mascots_browser.js"),
                          *(str(tmp_path / f) for f in ("card.html", "input.json", "result.json")), str(width), scheme,
                          *([f"{shot}-n136-{tool}-{width}-{scheme}.png"] if shot else [])],
                         capture_output=True, text=True, cwd=ROOT, timeout=60)
    assert run.returncode == 0, run.stderr
    out = json.loads(run.stdout)
    assert out["requests"] == [] and out["errors"] == [] and out["violations"] == []
    assert not [m for m in out["log"] if m.get("method") == "tools/call"]   # the switch calls nothing
    return out


def _check_words_and_switch(out: dict, answer: str):
    """Every sentence a figure says is a string of the answer and is on the card with the mascots off; the switch
    hides every figure and keeps every word; pressed again, they are back."""
    strings = _strings(json.loads(answer))
    shown = [f for f in out["on"]["figures"] if f["shown"]]
    assert shown and out["on"]["boxShown"]
    for f in shown:
        assert f["text"] and f["text"] in strings, f
        assert f["text"] in out["off"]["text"], f                           # on the card without the figures
        assert f["who"] == mcp_apps_mascots.NAMES[f["kind"]]
    for f in out["on"]["figures"]:
        if not f["shown"]:
            assert f["text"] == ""                                           # nothing to say: not shown
    assert out["on"]["toggle"] == {"shown": True, "text": "Mascots: on", "pressed": "true"}
    assert out["off"]["toggle"] == {"shown": True, "text": "Mascots: off", "pressed": "false"}
    assert not out["off"]["boxShown"] and not any(f["shown"] for f in out["off"]["figures"])
    assert [f["shown"] for f in out["again"]["figures"]] == [f["shown"] for f in out["on"]["figures"]]
    return {f["kind"]: f for f in shown}


def _not_glad(out: dict):
    for f in out["on"]["figures"]:
        assert f["pose"] not in mcp_apps_mascots.GLAD and not f["glad"], f
        assert f["confetti"] == "0" and f["heart"] == "0", f


@pytest.mark.skipif(not _playwright(), reason="node + playwright not available")
def test_validate_plan_card_says_counts_attention_and_next_step(tmp_path, fabric):  # noqa: F811
    answer = server.validate_plan(**SRC)
    data = json.loads(answer)
    assert data["needs_attention"] == 1                                      # the shop's header amount
    out = _browse(tmp_path, "validate_plan", SRC, answer)
    said = _check_words_and_switch(out, answer)
    assert set(said) == {"onto", "thinker", "builder"}
    assert said["onto"]["text"] == data["summary"]                          # the counts
    [finding] = data["attention"]["amount_levels"]
    assert said["thinker"]["text"] == finding["do_instead"]                 # what needs attention
    assert said["builder"]["text"] == data["next_steps"][0]["why"]          # the next step
    _not_glad(out)                                                           # something needs attention: nobody celebrates


@pytest.mark.skipif(not _playwright(), reason="node + playwright not available")
def test_no_celebration_on_a_failed_validate_plan_narrow_and_dark(tmp_path, fabric):  # noqa: F811
    args = {**SRC, "keys": {"order_items": ["order_id"]}}                    # a key that does not hold
    answer = server.validate_plan(**args)
    data = json.loads(answer)
    assert data["totals"]["keys"]["failed"] >= 1
    out = _browse(tmp_path, "validate_plan", args, answer, width=340, scheme="dark")
    _check_words_and_switch(out, answer)
    _not_glad(out)
    on = out["on"]
    assert on["docWidth"] <= on["viewWidth"]                                 # no sideways scroll at 340 px
    assert on["colors"]["body"] != "rgb(255, 255, 255)"                     # dark card in a dark host
    for f in on["figures"]:
        if f["shown"]:
            assert f["bubble"] != "rgb(255, 255, 255)" and f["ink"] != "rgb(27, 27, 31)" and f["right"] <= on["viewWidth"]


@pytest.mark.skipif(not _playwright(), reason="node + playwright not available")
def test_glad_only_when_the_validate_plan_check_passed(tmp_path):
    passed = {"summary": "6 of 6 keys unique, 7 of 7 relationships hold without orphans", "needs_attention": 0,
              "totals": {"keys": {"checked": 6, "passed": 6, "failed": 0},
                         "relationships": {"checked": 7, "passed": 7, "failed": 0}},
              "next_steps": [{"tool": "review_plan", "arguments": {"validate": True},
                              "why": "keeps the plan, its checks and the decisions made about it as one file."}]}
    answer = json.dumps(passed)
    out = _browse(tmp_path, "validate_plan", SRC, answer)
    said = _check_words_and_switch(out, answer)
    assert set(said) == {"onto", "builder"}                                  # nothing needs attention: no Thinker
    assert said["onto"]["pose"] == "celebrate" and said["onto"]["glad"] and said["onto"]["confetti"] == "1"
    # the same answer with one failed check: nobody is glad
    failed = json.loads(answer)
    failed["totals"]["keys"].update(passed=5, failed=1)
    _not_glad(_browse(tmp_path, "validate_plan", SRC, json.dumps(failed)))
    # an error answer: no figure at all
    err = _browse(tmp_path, "validate_plan", SRC, json.dumps({"error": "No such workspace.", "kind": "not_found",
                                                               "hint": "Call list_workspaces."}))
    assert not err["on"]["boxShown"] and not any(f["shown"] for f in err["on"]["figures"])


@pytest.mark.skipif(not _playwright(), reason="node + playwright not available")
def test_review_plan_card_says_counts_attention_and_next_step(tmp_path, fabric):  # noqa: F811
    args = {**SRC, "validate": True, "keys": {"order_items": ["order_id"]}}  # a failed key check
    answer = server.review_plan(**args)
    data = json.loads(answer)
    out = _browse(tmp_path, "review_plan", args, answer, width=340, scheme="dark")
    said = _check_words_and_switch(out, answer)
    assert said["onto"]["text"] == data["summary"]
    assert said["thinker"]["text"] == data["attention"][0] and said["thinker"]["text"].startswith("Accepted, but the check failed")
    assert said["builder"]["text"] == data["note"]
    _not_glad(out)
    assert out["on"]["docWidth"] <= out["on"]["viewWidth"]


@pytest.mark.skipif(not _playwright(), reason="node + playwright not available")
def test_glad_only_when_the_review_passed(tmp_path, fabric):  # noqa: F811
    data = json.loads(server.review_plan(**SRC, validate=True))
    data["attention"] = []                                                   # as if nothing were open
    rv = data["review"]
    rv["open_questions"] = []
    assert all(it["check"]["status"] == "passed" for it in rv["items"])
    out = _browse(tmp_path, "review_plan", SRC, json.dumps(data))
    said = _check_words_and_switch(out, json.dumps(data))
    assert said["onto"]["pose"] == "celebrate" and said["onto"]["glad"]
    assert "thinker" not in said
    rv["items"][0]["check"]["status"] = "stale"                              # one stale check: nobody is glad
    _not_glad(_browse(tmp_path, "review_plan", SRC, json.dumps(data)))
