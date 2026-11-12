"""n224: the site's sentences that S1 (docs/SCOPE-REVIEW.md, sections 3.2 and 4) found promising more than the evidence.

Site only: /check loses the seconds measured on a local server and the "two minutes"; /use-cases/build loses "about N
minutes"; the ten industry cards on /use-cases each say they are illustrative, not run on customer data; the headline
(USP), the server card's description, the three points and llms.txt say "the rule behind every proposed link" instead of
"the proof", count "up to 60 keys and links per call (200 at most)" instead of "every", give each built item its status,
and say an SAP pack link cites a public SAP page rather than resting on a verified source. The body text's qualifiers stay.
"""
import re

import pytest
from starlette.testclient import TestClient

from fabric_backend import claims, discovery, offering, server, use_cases


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PRODUCT_NAME", "Krusgraph")
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://krusgraph.test/mcp")
    with TestClient(server.build_app()) as c:
        yield c


def _text(html: str) -> str:
    html = re.sub(r"<script\b.*?</script>|<style\b.*?</style>", " ", html, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


OLD = ("really connect", "proof behind every link", "with its public source", "checks every key", "Count every link",
       "counts from all rows", "Each builds the same items")


@pytest.mark.parametrize("path", ["/", "/check", "/use-cases", "/use-cases/build", "/sap", "/docs", "/choose", "/llms.txt",
                                  "/llms-full.txt", "/docs.md", "/choose.md", "/use-cases.md"])
def test_the_overreaching_sentences_are_gone(client, path):
    r = client.get(path)
    if r.status_code == 404:
        pytest.skip(f"{path} is not served")
    for s in OLD:
        assert s not in r.text, (path, s)


def test_check_has_no_measured_seconds_and_no_two_minutes(client):
    t = _text(client.get("/check").text)
    for s in ("Measured on", "13.5 s", "5.5 s", "2.5 s", "two minutes", "Mbit/s"):
        assert s not in t, s
    assert "This page sets no file or row limit of its own; it is meant for samples" in t
    assert "Drop CSV or Excel exports (meant for samples), or paste a list of columns." in t


def test_use_cases_build_has_no_minutes_estimate(client):
    t = _text(client.get("/use-cases/build").text)
    assert not re.search(r"about \d+ minutes", t) and "minutes are the budget" not in t
    assert "it is a script, not a measured time on your schema" in t


def test_each_industry_card_says_it_is_illustrative(client):
    html = client.get("/use-cases").text
    cards = re.findall(r'<li class="card soft uc-ind" id="([\w-]+)">(.*?)</li>', html, re.S)
    assert len(cards) == len(use_cases.INDUSTRIES) == 10
    for slug, body in cards:
        assert "Illustrative, not run on customer data" in body, slug
    md = client.get("/use-cases.md").text
    assert md.count("*Illustrative, not run on customer data.*") == 10


def test_the_headline_and_llms_txt_promise_the_rule_not_proof(client):
    assert discovery.USP == "See how your tables connect: the rule behind every proposed link, and the row counts once you run the check."
    assert len(discovery.DESCRIPTION) <= 100 and "proof" not in discovery.DESCRIPTION
    llms = client.get("/llms.txt").text
    assert discovery.USP in llms
    assert "up to 60 keys and links per call (200 at most)" in llms
    assert "each citing a public SAP page" in llms
    point = discovery.USP_POINTS[2]
    assert "(each created live on synthetic data)" in point and "experimental" in point and "Krusgraph for Fabric only" in point


def test_the_home_diagram_gives_each_built_item_its_status(client):
    html = client.get("/").text
    built = re.search(r'<div class="off-built">.*?<ul>(.*?)</ul>', html, re.S).group(1)
    items = re.findall(r'<li>([^<]+?) <span class="off-src-st">([^<]+)</span></li>', built)
    got = dict(items)
    for b in offering.BUILT:
        assert got.get(b) in claims.CHIPS, (b, got.get(b))
    assert got["Data agent"] == "Experimental" and got["App (Rayfin, preview)"] == "Preview"


def test_no_speed_certification_partnership_or_endorsement_in_the_new_words():
    new = " ".join([discovery.USP, discovery.DESCRIPTION, discovery.USP_POINTS[2], use_cases.ILLUSTRATIVE]).lower()
    for w in ("fast", "second", "minute", "certif", "partner", "endorse", "guarantee", "customer:"):
        assert w not in new, w
