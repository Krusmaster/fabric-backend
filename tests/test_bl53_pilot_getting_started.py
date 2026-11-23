"""2026-11-23, round BL53 (backlog C-28): /getting-started opens with the steps for a first pilot tenant.

The steps live in fabric_backend/tenant_settings.py (`steps()`), next to the tenant settings they point at, so the
page and docs/GETTING-STARTED.md cannot drift apart (tests/test_bl2_tenant_settings.py keeps those equal). Here: the
steps are in order on both, each names who does it and the error kinds that point at it, every kind and tool named
exists in the code, the permissions are the ones access.py grants, the page is linked from the home page and the docs
menu, and every link on it answers. No network.
"""
import asyncio
import html as _html
import inspect
import re
from pathlib import Path

from fabric_backend import access, errors, server, tenant_settings as ts
from tests.test_site import client  # noqa: F401  (the site's test client)

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "GETTING-STARTED.md"


def _plain(text: str) -> str:
    return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", text)))


def _article(page: str) -> str:
    return page[page.index('<article class="wrap prose gs-page">'):page.index("</article>")]


def test_steps_name_who_and_point_at_real_error_kinds():
    st = ts.steps()
    assert len(st) == 6
    assert [x["who"] for x in st] == ["Entra administrator", "Fabric administrator", "Fabric administrator",
                                      "Data lead", "Data lead", "Data lead"]
    for x in st:
        assert x["kinds"] and set(x["kinds"]) <= set(errors.HINTS), x["title"]


def test_every_tool_named_is_an_mcp_tool_and_sample_is_a_start_argument():
    tools = {t.name for t in asyncio.run(server.mcp.list_tools())}
    named = set()
    for x in ts.steps():
        named |= set(re.findall(r"`([a-z_]+)`", x["text"]))
    for sid, _, paras in ts._sections():
        if sid in ("paths", "steps", "never"):                               # the sections BL53 wrote
            for p in paras:
                named |= set(re.findall(r"`([a-z_]+)`", p))
    named -= {"user_impersonation", "kind", "hint"}                          # a permission and the error fields
    assert {"start", "plan_backend", "validate_plan", "verify_build", "sample_rows", "query_graphql"} <= named
    assert named <= tools, named - tools
    assert "sample" in inspect.signature(server.start).parameters


def test_the_permissions_are_the_ones_access_py_grants():
    first = ts.steps()[0]["text"]
    for scope in access.scopes():
        assert f"`{scope}`" in first, scope
    assert "delegated" in first and "/it#permissions" in first


def test_step_three_names_the_settings_from_the_table():
    third = ts.steps()[2]["text"]
    for a in ts.for_outputs(ts.FIRST_OUTPUTS):
        assert a["setting"] in third
    assert "Tenant settings per output" in third and any(h == "Tenant settings per output" for _, h, _ in ts._sections())


def test_steps_are_in_order_on_the_page_and_in_the_doc(client):  # noqa: F811
    page = client.get("/getting-started").text
    art = _article(page)
    doc = DOC.read_text(encoding="utf-8")
    assert art.count('<ol class="gs-steps">') == 1
    pos_page = [art.index(f'<li id="step-{i}"><strong>{_html.escape(x["title"])}</strong>') for i, x in enumerate(ts.steps(), 1)]
    pos_doc = [doc.index(f"{i}. **{x['title']}** ({x['who']}).") for i, x in enumerate(ts.steps(), 1)]
    assert pos_page == sorted(pos_page) and pos_doc == sorted(pos_doc)
    body = _plain(art)
    for x in ts.steps():
        for k in x["kinds"]:
            assert k in body
    # the steps come before the long reference sections, after the two paths
    assert art.index('id="paths"') < art.index('id="steps"') < art.index('id="never"') < art.index('id="settings"')


def test_both_paths_and_what_it_never_does(client):  # noqa: F811
    body = _plain(_article(client.get("/getting-started").text))
    assert "The hosted MCP server, available now." in body
    paths = next(p for sid, _, p in ts._sections() if sid == "paths")
    hub = paths[1]
    assert "Workload Hub is pending" in hub
    assert not re.search(r"\b20\d\d\b|January|February|March|April|May|June|July|August|September|October|November|December", hub)
    assert not re.search(r"\b(Microsoft|they|we) (has|have) not\b|waiting for|blocked by|delay", hub, re.I)
    for words in ("Shows no row values unless you ask.", "Deletes nothing.", "Uses only your permissions.",
                  "Creates nothing on its own.", "Leaves your settings alone."):
        assert words in body, words
    assert "sample=true" in body and "verify_build" in body


def test_linked_from_home_and_docs_menu_and_every_link_answers(client):  # noqa: F811
    assert 'href="/getting-started"' in client.get("/").text
    docs = client.get("/docs").text
    menu = re.search(r'<nav class="docs-menu"[^>]*>(.*?)</nav>', docs, re.S).group(1)
    assert 'href="/getting-started"' in menu
    page = client.get("/getting-started").text
    for href in set(re.findall(r'href="(/[^"#]*)(?:#([^"]*))?"', _article(page))):
        path, frag = href
        r = client.get(path)
        assert r.status_code == 200, path
        if frag:
            assert f'id="{frag}"' in r.text, (path, frag)


def test_no_prices_names_or_claims(client):  # noqa: F811
    text = (_plain(_article(client.get("/getting-started").text)) + DOC.read_text(encoding="utf-8")).lower()
    for banned in ("price", "€", "sek", "kr ", "certified", "endorsed", "partner of", "guarantee", "faster"):
        assert banned not in text, banned
