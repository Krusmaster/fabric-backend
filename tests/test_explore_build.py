"""The cards "What you can build automatically from a plan" (round n31; on /use-cases since n55, when /explore became a redirect; on /use-cases/build since n59): every card is engine output on the synthetic shop plan,
its status word comes from tool_status, and the page loads no script from elsewhere."""
import re

import pytest
from fabric_backend import demo, pages, seed, tool_status


def _clear():
    for f in (demo._demo_db, demo.demo_validation, demo.demo_validation_json, demo.demo_suggestions, demo.build_cards):
        f.cache_clear()


@pytest.fixture
def fresh():
    _clear()
    yield
    _clear()


def _section(html: str) -> str:
    return html.split('id="build"', 1)[1].split("</section>", 1)[0]


def test_the_chart_is_the_seed_rows_summed_along_the_safest_path(fresh):
    c = demo.build_cards()["chart"]
    assert c["path"] == ["order_items", "products", "categories"] and all(s["direction"] == "many-to-one" for s in c["steps"])
    # the same sum, done by hand over the seed rows
    r = seed.rows()
    cat = {p[0]: p[2] for p in r["products"]}
    name = {k[0]: k[1] for k in r["categories"]}
    want: dict[str, float] = {}
    for line in r["order_items"]:
        want[name[cat[line[2]]]] = want.get(name[cat[line[2]]], 0) + line[3]
    assert {b["label"]: b["value"] for b in c["bars"]} == want
    assert c["question"] in _section(pages.render("/use-cases/build"))


def test_changing_the_seed_rows_changes_the_chart(fresh, monkeypatch):
    before = demo.build_cards()["chart"]["bars"]
    real = seed.rows()
    changed = dict(real, order_items=[(o, n, p, q * 10) for o, n, p, q in real["order_items"]])
    monkeypatch.setattr(seed, "rows", lambda: changed)
    monkeypatch.setattr(demo, "rows", lambda: changed)
    _clear()
    after = demo.build_cards()["chart"]["bars"]
    assert [b["value"] * 10 for b in before] == [b["value"] for b in after]
    assert f'{after[0]["value"]:g}' in _section(pages.render("/use-cases/build"))


def test_changing_the_plan_changes_every_card(fresh, monkeypatch):
    before = demo.build_cards()
    real = seed.schema
    def without_categories(name="shop"):
        s = real(name)
        del s.tables["categories"]
        return s
    monkeypatch.setattr(demo, "schema", without_categories)
    _clear()
    after = demo.build_cards()
    assert after["chart"]["target"] != "categories"
    assert not any("categories" in r["to"] for r in after["model"]["relationships"])
    assert "Categories" not in {e["class"] for e in after["rayfin"]["entities"]} and "Categories" in {e["class"] for e in before["rayfin"]["entities"]}
    assert "categories" not in after["app"]["prompt"] and "categories" in before["app"]["prompt"]


def test_the_cards_show_the_engine_output(fresh):
    c = demo.build_cards()
    html = _section(pages.render("/use-cases/build"))
    for r in c["model"]["relationships"]:
        assert f"<code>{r['from']}</code> → <code>{r['to']}</code>" in html
    for m in c["model"]["measures"]:
        assert m["expression"].replace("'", "&#x27;") in html
    ad = c["model"]["amount_demo"]
    assert (ad["before"], ad["after"], ad["lines_total"]) == (2000.0, 1000.0, 1000.0)       # seed.AMOUNT_DEMO, run by amounts.demo()
    assert f"gives {ad['before']:g}" in html and c["model"]["amount_check"] in html
    for e in c["rayfin"]["entities"]:
        assert f"<code>{e['class']}</code> ← <code>{e['table']}</code>" in html
    assert c["app"]["query"]["query"] in html and "Build a small internal web app" in html


def test_status_words_come_from_tool_status(fresh, monkeypatch):
    html = _section(pages.render("/use-cases/build"))
    found = re.findall(r'data-tool="(\w+)">.*?<span class="build-status">([^<]+)</span>', html)
    assert [t for t, _ in found] == ["join_path", "semantic_model_draft", "rayfin_connector", "app_starter"]
    assert all(word == tool_status.label(t) for t, word in found)
    monkeypatch.setattr(tool_status, "label", lambda name: f"STATUS-OF-{name}")
    html = _section(pages.render("/use-cases/build"))
    assert all(f"STATUS-OF-{t}" in html for t, _ in found)


def test_each_card_links_to_a_docs_section_that_exists():
    docs = pages.docs_html()
    for tool in pages.BUILD_DOCS:
        anchor = pages.build_doc_anchor(tool).split("#", 1)[1]
        assert f'id="{anchor}"' in docs, tool
        assert f'href="/docs#{anchor}"' in _section(pages.render("/use-cases/build"))


def test_the_build_section_loads_no_external_script():
    html = pages.render("/use-cases/build")
    srcs = re.findall(r"<script[^>]*\bsrc=\"([^\"]+)\"", html)
    assert srcs and all(s.startswith("/") and not s.startswith("//") for s in srcs)
    assert "<svg" in _section(html) and not re.search(r"<script|<link|(src|href)=\"(https?:)?//", _section(html))


def test_the_path_is_counted_from_the_tools_and_the_demo_budget():
    from fabric_backend.demo_app import STEPS
    path = pages.build_path()
    assert all(t in tool_status.STATUS for s in path for t in s["tools"])
    assert path[-1]["tools"] == tuple(t for _, t in tool_status.BUILDS)
    html = _section(pages.render("/use-cases/build"))
    assert html.count('<li><span class="path-n"') == len(path)
    assert f"{sum(len(s['tools']) for s in path[:-1])} tool calls" in html and f"{len(path[-1]['tools'])} parts in all" in html
    assert f"to a checked plan in about {sum(s['minutes'] for s in STEPS)} minutes; each part after that is one call" in html and 'href="/local#the-20-minute-demo"' in html
    assert "What you can build automatically from a plan" in html and "when you ask for it" in html
