"""n146: one source for permissions, data flow and test status (the outside review of 7 November 2026).

Fails when two pages state different permission lists, when a page says a permission the app has is not requested,
when two pages give the same tool different status words, or when they give Claude Code different connect advice.
The permissions come from fabric_backend/access.py, which must equal what the deploy check demands; the status words
from fabric_backend/tool_status.py.

PENDING is empty: the texts in page_templates/DOCS.md and README.md that contradicted the source were fixed in the
second part of round n146. A page that cannot be fixed at once may be listed there as a strict xfail with its reason.
"""
import html
import importlib
import re
from pathlib import Path

import pytest

from fabric_backend import access, tool_status as ts
from fabric_backend.discovery import PUBLIC_PAGES
from tests.test_site import client  # noqa: F401  (the site's test client)

ROOT = Path(__file__).resolve().parents[1]
MD_PAGES = ["/docs.md", "/start.md", "/privacy.md", "/lovable.md", "/local.md", "/use-cases.md", "/llms.txt", "/llms-full.txt"]
# n146, second part: DOCS.md and README.md were fixed and the strict xfails removed. A text that cannot be fixed in the
# same round goes here as {test: {page: reason}}, and becomes a strict xfail.
PENDING: dict[str, dict[str, str]] = {"permissions": {}, "claude_code": {}}


def _docs_subpages():
    from fabric_backend.pages import docs_pages
    return [x["path"] for x in docs_pages()[1:]]


def _all_paths():
    return list(PUBLIC_PAGES) + MD_PAGES + _docs_subpages()


def _params(test, names):
    pending = PENDING[test]
    return [pytest.param(n, marks=pytest.mark.xfail(strict=True, reason=pending[n])) if n in pending else n for n in names]


def _text(client, name):  # noqa: F811
    raw = (ROOT / name).read_text(encoding="utf-8") if name.endswith("README.md") else client.get(name).text
    plain = html.unescape(re.sub(r"<[^>]+>", " ", raw)).replace("`", "")
    return raw, re.sub(r"[ \t]+", " ", plain)


def _blocks(plain):
    """Paragraphs, list items and table rows: the units a permission list or a status is stated in."""
    return [b for b in re.split(r"\n\s*\n|\n(?=\s*[-|*])|(?<=[.!?])\s+(?=[A-Z])", plain) if b.strip()]


GRANTED = set(access.scopes())
NOT_REQUESTED = {x for a, b, _ in access.NOT_REQUESTED for x in (a, b) if x}
SCOPE_RX = re.compile(r"(?<![\w.])(" + "|".join(re.escape(s) for s in sorted(GRANTED | NOT_REQUESTED, key=len, reverse=True))
                      + r")(?!\w|\.\w)")
FABRIC = set(access.scopes(access.FABRIC))
NEG = re.compile(r"does not ask for|doesn't ask for|not asked for|not requested|does not request|not granted|"
                 r"which the (?:hosted )?app does not have", re.I)


# ------------------------------------------------------------------ the source itself ---------------------------------

def test_access_is_what_the_deploy_check_demands():
    deploy = importlib.import_module("deploy.azure_containerapp")
    for resource, scopes in deploy.REQUIRED_SCOPES.items():
        name = next(n for n, rid in access.RESOURCE_IDS.items() if rid == resource)
        assert set(access.scopes(name)) == scopes, name
    assert GRANTED == set().union(*deploy.REQUIRED_SCOPES.values())
    assert not GRANTED & NOT_REQUESTED


def test_scopes_md_carries_the_generated_table():
    doc = (ROOT / "docs/SCOPES.md").read_text(encoding="utf-8")
    inside = doc.split("<!-- access:table -->\n", 1)[1].split("\n<!-- /access:table -->", 1)[0]
    assert inside == access.table_md()


def test_the_token_lifetimes_come_from_the_code():
    from fabric_backend import registration as reg, registration_flow, registration_store
    rows = access.tokens_md(True, "X")
    assert (reg.TXN_TTL, reg.CODE_TTL, reg.FAMILY_TTL, registration_flow.REFRESH_OVERLAP, registration_store.PURGE_EVERY) == \
           (600, 60, 90 * 86400, 60, 600)
    for said in ("10 minutes", "60 seconds, deleted when the client collects them", "at most 90 days",
                 "reused for at most 60 seconds", "it is never opened", "120 seconds before the expiry"):
        assert said in rows, said
    src = (ROOT / "fabric_backend/entra.py").read_text(encoding="utf-8")
    assert "hit[1] - 120 > time.time()" in src                    # the reuse margin the table states


# ------------------------------------------------------------------ permissions: one list everywhere -----------------

@pytest.mark.parametrize("name", _params("permissions", _all_paths() + ["README.md"]))
def test_every_page_states_the_same_permissions(client, name):  # noqa: F811
    _raw, plain = _text(client, name)
    bad = []
    for block in _blocks(plain):
        named = set(SCOPE_RX.findall(block))
        granted = named & GRANTED
        if NEG.search(block) and granted and not named & NOT_REQUESTED:
            bad.append(("says a granted permission is not requested", block.strip()[:200]))
        fabric = granted & FABRIC
        if len(fabric) >= 4 and fabric != FABRIC and "|" not in block:          # a list of the app's Fabric permissions
            bad.append(("lists a different set", sorted(FABRIC - fabric), block.strip()[:200]))
        if re.search(r"permission the hosted (?:app|service) does not ask for today", block) and re.search(
                r"(?<![\w-])(?:" + _TOOL + r")(?![\w-])", block) and not any(ts.STATUS[t].available == ts.OPERATOR for t in ts.STATUS):
            bad.append(("names an operator permission no tool needs", block.strip()[:200]))
    assert not bad, bad[:3]


@pytest.mark.parametrize("path", ["/start", "/it", "/privacy", "/docs/hosting-and-permissions/what-it-accesses"])
def test_the_permission_table_is_the_generated_one(client, path):  # noqa: F811
    page = client.get(path).text
    listed = re.findall(r"<tr><td><code>([\w.]+)</code> \(", page)
    assert listed == access.scopes(), path
    assert f"read from the code on {access.AS_OF}" in page and "Runs or schedules anything?" in page


# ------------------------------------------------------------------ status words: one word per tool ------------------

_TOOL = "|".join(sorted(map(re.escape, ts.STATUS), key=len, reverse=True))
_BASE = sorted(ts.WORDS, key=len, reverse=True)
_STATED = [re.compile(r"^\|\s*(" + _TOOL + r")\s*\|\s*([^|]+)\|", re.M),                        # a Markdown table row
           re.compile(r"(?<![\w-])(" + _TOOL + r")(?:\s*:|\s+\()\s*((?:" + "|".join(map(re.escape, _BASE)) + r")[^|\n]{0,60})", re.I)]


def _base(phrase):
    low = phrase.strip().lower()
    return next((w for w in _BASE if low.startswith(w.lower())), None)


def _statements(client, name):  # noqa: F811
    raw, plain = _text(client, name)
    md = re.sub(r"`", "", raw) if name.endswith((".md", ".txt")) else ""
    out = []
    for rx in _STATED:
        for text in filter(None, (md, plain)):
            out += [(m.group(1), m.group(2).strip()) for m in rx.finditer(text) if _base(m.group(2))]
    for m in re.finditer(r"<tr><td><code>(" + _TOOL + r")</code></td><td>(.*?)</td>", raw):    # an HTML table row
        cell = html.unescape(re.sub(r"<[^>]+>", "", m.group(2)))
        if _base(cell):
            out.append((m.group(1), cell))
    return out


def _wrong(tool, phrase):
    """The stated word is not the tool's, or drops the qualifier that limits it (as a dry run, as an update in place)."""
    want, base, low = ts.word(tool), _base(phrase), phrase.lower()
    if base != _base(want):
        return True
    return any(q in want.lower() and q not in low and not low.startswith(base.lower() + " on")
               for q in (" as a dry run", " as an update in place"))


@pytest.mark.parametrize("name", _all_paths())
def test_every_page_gives_each_tool_the_status_word_of_tool_status(client, name):  # noqa: F811
    wrong = sorted({(t, p[:80]) for t, p in _statements(client, name) if _wrong(t, p)})
    assert not wrong, wrong[:5]


def test_two_pages_never_give_one_tool_two_status_words(client):  # noqa: F811
    seen: dict = {}
    for name in _all_paths():
        for tool, phrase in _statements(client, name):
            seen.setdefault(tool, set()).add(_base(phrase))
    two = {t: w for t, w in seen.items() if len(w) > 1}
    assert not two, two
    assert seen.get("create_pipeline") == {"Tried live"}                        # run live on 7 November 2026, not Experimental


def test_experimental_means_never_tried_live():
    for t in ts.STATUS:
        date, _op, _result = ts.live_fields(t)
        assert (ts.word(t) == "Experimental") is (not date and ts.STATUS[t].kind != ts.DRAFT), t
        assert (ts.word(t) == ts.TRIED) <= bool(date), t
    assert ts.LIVE["create_pipeline"][0] == "7 November 2026" and "9de8bc49" in ts.LIVE["create_pipeline"][1]


# ------------------------------------------------------------------ data flow, analytics, Claude Code ----------------

def test_the_data_flows_and_the_analytics_line_agree(client):  # noqa: F811
    it, privacy = client.get("/it").text, client.get("/privacy").text
    flows = html.unescape(re.sub(r"<[^>]+>", "", access.flows_html("Krusgraph", "krusgraph.test")))
    for page in (it, privacy):
        plain = html.unescape(re.sub(r"<[^>]+>", "", page))
        assert flows in plain or all(line.split(":** ", 1)[1] in plain for line in access.flows_md("Krusgraph", "krusgraph.test").splitlines())
        assert "keep everything in your tenant" not in page
    assert "no analytics or tracking" not in privacy and "no third-party analytics or tracking" in privacy
    for path in ("/", "/pricing", "/it"):
        assert "keep everything in your tenant" not in client.get(path).text, path


@pytest.mark.parametrize("name", _params("claude_code", _all_paths() + ["README.md"]))
def test_claude_code_gets_one_connect_instruction(client, monkeypatch, name):  # noqa: F811
    monkeypatch.setenv("KRUSGRAPH_CLIENT_REGISTRATION", "1")
    from fabric_backend.pages import _vars
    want = re.search(r"claude mcp add --transport http \S+ (\S+?)`", _vars()["CLAUDE_CODE_CONNECT"]).group(1)
    _raw, plain = _text(client, name)
    urls = set(re.findall(r"claude mcp add --transport http \S+ (https?://[^\s`<)]+?)[.,;:]?(?=[\s`)<]|$)", plain))
    assert urls <= {want}, urls


def test_the_start_page_step_links_land_on_a_step(client):  # noqa: F811
    start = client.get("/start").text
    for n in "123":
        assert f'id="step-{n}"' in start
    assert 'href="#step-1"' in start
    js = (ROOT / "fabric_backend/static/site.js").read_text(encoding="utf-8")
    assert "hashchange" in js
