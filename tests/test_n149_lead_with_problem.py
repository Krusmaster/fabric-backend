"""n149: the home page and /check lead with the problem (the UX review of 7 November 2026, desktop and 375 px).

One primary and one secondary way in with the same labels everywhere ("Check my tables" for /check, "Connect to my
Fabric" for /start), the client chooser on /start, no floating demo button on the home page and /check, one guided-demo
button after the total that doubles, the test status said once by the tools list, a card after a /check result that
leads to /start, a jump to step 3 on /start for people coming from /check, and the blog in the main navigation."""
import json
import re
import subprocess

import pytest

from fabric_backend import pages
from fabric_backend.discovery import PUBLIC_PAGES
from tests.test_site import client  # noqa: F401  (the site's test client)
from test_browser import CHROMIUM, ROOT, _playwright_available, site  # noqa: F401

CHECK, CONNECT = "Check my tables", "Connect to my Fabric"
ARTICLE = "/blog/fabric-totals-double-after-join"


def _buttons(html):
    return re.findall(r'<a class="btn [^"]*" href="([^"#?]+)(?:#[^"]*)?">([^<]+)</a>', html)


def test_the_labels_are_constants_the_pages_render():
    assert (pages.CHECK_LABEL, pages.CONNECT_LABEL) == (CHECK, CONNECT)


@pytest.mark.parametrize("path", ["/", "/check", "/pricing"])
def test_the_two_ways_in_have_one_label_each(client, path):
    html = client.get(path).text
    main = html[html.index("<main"):html.index("</main>")]
    buttons = _buttons(main)
    assert ("/check", CHECK) in buttons or path == "/check"                       # /check itself has no button to /check
    assert ("/start", CONNECT) in buttons or ("/start", CONNECT + " →") in buttons
    for href, text in buttons:
        if href == "/check":
            assert text == CHECK, (path, text)
        if href == "/start":
            assert text.rstrip(" →") == CONNECT, (path, text)
    nav = re.search(r'<nav id="site-nav".*?</nav>', html, re.S).group(0)
    assert f'<a href="/check"{" aria-current=page" if path == "/check" else ""}>{CHECK}</a>' in nav
    foot = re.search(r'<nav class="footer-links".*?</nav>', html, re.S).group(0)
    assert f'<a href="/check">{CHECK}</a>' in foot and f'<a href="/start">{CONNECT}</a>' in foot and "#connect" not in foot


def test_the_hero_says_the_problem_and_shows_the_small_before_and_after(client):
    html = client.get("/").text
    hero = re.search(r'<section class="hero">.*?</section>', html, re.S).group(0)
    assert "<h1>Why is your total twice what finance says?</h1>" in hero
    assert ('<p class="lede">Krusgraph checks keys and joins in your Fabric tables, and shows the rule and the row counts '
            'behind every link.</p>') in hero
    ctas = re.search(r'<div class="ctas hero-ctas" id="connect">(.*?)</div>', hero, re.S).group(1)
    assert _buttons(ctas) == [("/check", CHECK), ("/start", CONNECT)] and "<details" not in ctas and "▾" not in hero
    mini = re.search(r'<p class="ba-mini">(.*?)</p>', hero, re.S).group(1)
    assert hero.index("hero-ctas") < hero.index("ba-mini")
    assert ">2 000<" in mini and ">1 000<" in mini and 'href="#example"' in mini        # seed.AMOUNT_DEMO's order
    assert '<figure class="session"' not in hero                                                    # the replay is further down
    assert html.index('id="how"') < html.index('<figure class="session"') < html.index('id="build-on"')


def test_one_guided_demo_button_after_the_total_that_doubles(client):
    html = client.get("/").text
    main = html[html.index("<main"):html.index("</main>")]
    demo = [m.start() for m in re.finditer(r'<a class="btn [^"]*" href="/check\?example=sample&amp;guide=1">Try the guided demo</a>', main)]
    assert len(demo) == 1 and main.index('id="example"') < demo[0] < main.index('id="paths"')


@pytest.mark.parametrize("path", ["/", "/check"])
def test_no_floating_demo_button_on_the_home_page_and_check(client, path):
    assert "kgc-launch" not in client.get(path).text


@pytest.mark.parametrize("path", ["/use-cases", "/docs", "/pricing", "/start"])
def test_deeper_pages_keep_the_floating_demo_button(client, path):
    assert 'class="kgc-launch"' in client.get(path).text


def test_the_status_is_said_once_by_the_tools_list(client):
    html = client.get("/").text
    main = html[html.index("<main"):html.index("</main>")]
    tools = main.index('id="build-on"')
    pitch = main[:tools]
    for word in ("xperimental", "Tested end to end on", "created live", "session-status", "status-tag"):
        assert word not in pitch, word
    status = re.findall(r'<p class="muted tiny build-status" id="status">(.*?)</p>', main, re.S)
    assert len(status) == 1 and "experimental" in status[0] and "Tested end to end on" in status[0]
    assert main.count("Tested end to end on") == 1


def test_the_client_chooser_is_on_start_in_the_step_that_adds_the_connector(client):
    home, start = client.get("/").text, client.get("/start").text
    assert "data-connect" not in home and "connect-pop" not in home
    step3 = start.split('data-pane="3" id="step-3"', 1)[1].split('<details id="access"', 1)[0]
    assert '<details class="connect connect-start" data-connect id="connect">' in step3
    assert "Open Claude’s connectors" in step3 and "Copy a note to your admin" in step3


def test_start_has_a_jump_for_people_coming_from_check_and_folds_the_requirements(client):
    html = client.get("/start").text
    hero = re.search(r'<section class="hero wrap".*?</section>', html, re.S).group(0)
    assert '<p class="start-from-check">Coming from /check? <a href="#step-3">' in hero
    assert 'id="step-3"' in html and "Add the connector" in html
    assert hero.index("start-from-check") < hero.index('<details class="start-needs"><summary>What you need</summary>')
    assert "Microsoft work account" in hero.split('<details class="start-needs">', 1)[1]


def test_check_offers_the_live_lakehouse_after_a_result(client):
    html = client.get("/check").text
    result = html[html.index('id="check-result"'):html.index("</section>\n\n<section", html.index('id="check-result"'))]
    card = re.search(r'<div class="card soft check-live" id="check-live">(.*?)\n  </div>', result, re.S).group(1)
    assert "Run the same check on your live lakehouse" in card and f'<a class="btn primary" href="/start">{CONNECT} →</a>' in card
    assert "Microsoft work account" in card and "admin approves" in card and 'href="/it"' in card
    assert ' hidden>' in html[html.index('id="check-result"') - 80:html.index('id="check-result"') + 80]   # shown with a result


def test_the_check_footer_has_a_text_link_to_run_locally_and_no_demo_button(client):
    html = client.get("/check").text
    foot = html[html.index('id="check-next-h"'):html.index("</section>", html.index('id="check-next-h"'))]
    assert '<a href="/local">Run it locally</a>' in foot and 'class="btn' not in foot.split("/local")[0][-60:]
    assert not re.search(r'<a class="btn[^"]*" href="/check\?example=sample', foot)


@pytest.mark.parametrize("path", PUBLIC_PAGES)
def test_blog_is_in_the_main_navigation(client, path):
    nav = re.search(r'<nav id="site-nav".*?</nav>', client.get(path).text, re.S).group(0)
    assert re.search(r'<a href="/blog"( aria-current=page)?>Blog</a>', nav), path


def test_the_article_is_linked_from_the_home_page_and_the_check_example(client):
    home = client.get("/").text
    example = home[home.index('id="example"'):home.index("</section>", home.index('id="example"'))]
    assert f'<a href="{ARTICLE}">Read the full walkthrough →</a>' in example
    check = client.get("/check").text
    examples = check[check.index('class="check-examples"'):check.index('class="check-box"')]
    assert 'data-example="sample"' in examples and f'href="{ARTICLE}"' in examples.split("</div>", 1)[1] and "A total that doubles" in examples
    assert client.get("/join-validation").status_code == 404          # no such page; nothing to link there
    assert client.get(ARTICLE).status_code == 200
    assert "/blog</loc>" in client.get("/sitemap.xml").text and ARTICLE + "</loc>" in client.get("/sitemap.xml").text
    llms = client.get("/llms.txt").text
    assert "/blog)" in llms and ARTICLE in llms


@pytest.mark.parametrize("path", ["/", "/pricing"])
def test_the_self_hosting_wording_is_n146s(client, path):
    from tests.test_site import DATA_STAYS
    html = client.get(path).text
    assert DATA_STAYS in html and "everything in your tenant" not in html.lower() and "stays in your tenant" not in html.lower()


@pytest.mark.skipif(not _playwright_available(), reason="node + playwright not available")
def test_in_a_browser_check_puts_the_drop_area_first_on_a_phone(site):
    out = subprocess.run(["node", str(ROOT / "tests" / "n149_browser.js"), site] + ([CHROMIUM] if CHROMIUM else []),
                         capture_output=True, text=True, timeout=300)
    assert out.returncode == 0, out.stderr[-2000:]
    r = json.loads(out.stdout.strip().splitlines()[-1])
    assert r["errors"] == []
    phone = r["check375"]
    assert phone["drop"] < phone["priv"] < phone["examples"] and phone["columns"] == 2 and phone["wide"] <= 375, phone
    desk = r["check1280"]
    assert desk["wide"] <= 1280, desk
    for w in ("375", "1280"):
        assert r["home" + w]["pill"] is False and r["home" + w]["wide"] <= int(w) and r["home" + w]["mini"], r["home" + w]
