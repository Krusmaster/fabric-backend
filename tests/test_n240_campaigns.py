"""n240: campaign counts for /check without cookies or personal data, the operator's read-only view of them, and the
no-login sample path whose figures come from the engine (fabric_backend/usage.py, server.py, check.js, check.html)."""
import io
import json
import re
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from fabric_backend import pages, usage

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "n240-test-token-" + "x" * 24
CAMPAIGN = "/check?utm_source=tiktok&utm_medium=paid&utm_campaign=fabric_see_this_test1"


def lines(buf):
    return [json.loads(x) for x in buf.getvalue().splitlines() if x.startswith("{")]


@pytest.fixture()
def fresh(monkeypatch):
    c = usage.Campaigns(today=lambda: "2026-11-17")
    monkeypatch.setattr(usage, "campaigns", c)
    return c


def capture(monkeypatch):
    """The console lines, caught in the test body (pytest puts its own stdout back between setup and the call)."""
    buf = io.StringIO()
    monkeypatch.setattr(usage.sys, "stdout", buf)
    return buf


@pytest.fixture()
def client(monkeypatch, fresh):
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://krusgraph.test/mcp")
    monkeypatch.setenv("PRODUCT_NAME", "Krusgraph")
    monkeypatch.setenv("ENTRA_CLIENT_ID", "cid-123")
    monkeypatch.setenv("KRUSGRAPH_METRICS_TOKEN", TOKEN)
    from fabric_backend.server import build_app
    with TestClient(build_app()) as c:
        yield c


# ------------------------------------------------------------------ cleaning ---------------------------------------

def test_utm_values_are_cleaned_and_nothing_else_is_read():
    got = usage.utm_of({"utm_source": " TikTok ", "utm_medium": "paid", "utm_campaign": "fabric_see_this_test1",
                        "fbclid": "abc", "email": "a@b.c", "ttclid": "x"})
    assert got == {"utm_source": "tiktok", "utm_medium": "paid", "utm_campaign": "fabric_see_this_test1"}
    # free text, an e-mail address, something long: counted as "(other)", never written down as given
    assert usage.utm_of({"utm_source": "jane.doe@example.com"}) == {"utm_source": "(other)"}
    assert usage.utm_of({"utm_campaign": "a b"}) == {"utm_campaign": "(other)"}
    assert usage.utm_of({"utm_campaign": "x" * 65}) == {"utm_campaign": "(other)"}
    assert usage.utm_of({"utm_source": ""}) == {} and usage.utm_of({}) == {} and usage.utm_of(None) == {}


# ------------------------------------------------------------------ counting ---------------------------------------

def test_visits_checks_and_visits_with_a_check_are_counted_per_day_and_campaign(fresh, monkeypatch):
    c, buf = fresh, capture(monkeypatch)
    tt = {"utm_source": "tiktok", "utm_medium": "paid", "utm_campaign": "fabric_see_this_test1"}
    for _ in range(3):
        usage.page_view("/check", tt)
    usage.page_view("/check")
    usage.page_view("/", tt)                                         # only /check is counted per campaign
    usage.check_event("loaded", utm=tt)
    usage.check_event("done", kind="sample", first=True, utm=tt)
    usage.check_event("done", kind="real", utm=tt)                  # a second check on the same page load
    usage.check_event("done", kind="sample", first=True)
    usage.check_event("orders.csv", kind="sample", utm=tt)          # not a step: ignored
    rep = c.report()
    day = rep["days"][0]
    assert day["day"] == "2026-11-17" and len(rep["days"]) == 1
    rows = {(r["utm_source"], r["utm_medium"], r["utm_campaign"]): r for r in day["campaigns"]}
    t = rows[("tiktok", "paid", "fabric_see_this_test1")]
    assert (t["visits"], t["engine_loaded"], t["checks"], t["checks_sample"], t["checks_real"], t["visits_with_check"]) == (3, 1, 2, 1, 1, 1)
    n = rows[("(none)", "(none)", "(none)")]
    assert (n["visits"], n["checks"], n["visits_with_check"]) == (1, 1, 1)
    assert day["total"]["visits"] == 4 and day["total"]["checks"] == 3
    # the console lines carry the same fields and nothing else
    got = lines(buf)
    assert got[0] == {"event": "krusgraph.page_view", "path": "/check", **tt}
    assert got[3] == {"event": "krusgraph.page_view", "path": "/check"} and got[4] == {"event": "krusgraph.page_view", "path": "/"}
    assert {"event": "krusgraph.check", "step": "done", "kind": "sample", "first": True, **tt} in got
    allowed = {"event", "path", "step", "kind", "first", *usage.UTM_KEYS}
    assert all(set(x) <= allowed for x in got)


def test_the_counts_stay_bounded(monkeypatch):
    day = ["2026-11-01"]
    c = usage.Campaigns(today=lambda: day[0])
    monkeypatch.setattr(usage, "CAMPAIGN_KEYS", 3)
    monkeypatch.setattr(usage, "CAMPAIGN_DAYS", 2)
    for i in range(5):
        c.add("visits", {"utm_campaign": f"c{i}"})
    keys = {r["utm_campaign"] for r in c.report()["days"][0]["campaigns"]}
    assert keys == {"c0", "c1", "c2", "(other)"}
    for d in ("2026-11-02", "2026-11-03"):
        day[0] = d
        c.add("visits", None)
    assert [x["day"] for x in c.report()["days"]] == ["2026-11-03", "2026-11-02"]


# ------------------------------------------------------------------ the server -------------------------------------

def test_the_server_counts_a_campaign_visit_and_its_check_without_a_cookie(client, monkeypatch):
    buf = capture(monkeypatch)
    r = client.get(CAMPAIGN, headers={"X-Forwarded-For": "203.0.113.7", "User-Agent": "TikTok in-app"})
    assert r.status_code == 200 and "set-cookie" not in r.headers
    e = client.get("/check/event?e=done&k=sample&n=1&utm_source=tiktok&utm_medium=paid&utm_campaign=fabric_see_this_test1")
    assert e.status_code == 204 and "set-cookie" not in e.headers
    got = lines(buf)
    assert got == [{"event": "krusgraph.page_view", "path": "/check", "utm_source": "tiktok", "utm_medium": "paid", "utm_campaign": "fabric_see_this_test1"},
                   {"event": "krusgraph.check", "step": "done", "kind": "sample", "first": True, "utm_source": "tiktok", "utm_medium": "paid", "utm_campaign": "fabric_see_this_test1"}]
    assert "203.0.113.7" not in buf.getvalue() and "TikTok in-app" not in buf.getvalue()
    # the page's policy still lets it fetch nothing; the event is an image from this host
    assert "connect-src 'none'" in r.headers["content-security-policy"]


def test_the_admin_view_is_the_operators_only(client, monkeypatch):
    client.get(CAMPAIGN)
    client.get("/check/event?e=done&k=real&n=1&utm_source=tiktok&utm_medium=paid&utm_campaign=fabric_see_this_test1")
    assert client.get("/admin/campaigns").status_code == 401
    assert client.get("/admin/campaigns", headers={"Authorization": "Bearer wrong"}).status_code == 401
    r = client.get("/admin/campaigns", headers={"Authorization": "Bearer " + TOKEN})
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store" and "noindex" in r.headers["x-robots-tag"]
    row = r.json()["days"][0]["campaigns"][0]
    assert row == {"utm_source": "tiktok", "utm_medium": "paid", "utm_campaign": "fabric_see_this_test1", "visits": 1,
                   "engine_loaded": 0, "checks": 1, "checks_sample": 0, "checks_real": 1, "visits_with_check": 1}
    assert client.post("/admin/campaigns", headers={"Authorization": "Bearer " + TOKEN}).status_code == 405   # read-only
    monkeypatch.setenv("KRUSGRAPH_METRICS_TOKEN", "")
    assert client.get("/admin/campaigns", headers={"Authorization": "Bearer " + TOKEN}).status_code == 404


def test_the_page_sends_the_campaign_with_its_events_and_says_so():
    js = (ROOT / "fabric_backend/static/check.js").read_text()
    assert js.count('ping("') == 2 and '"/check/event?e=" + step' in js and '+ UTM' in js
    assert '"utm_source", "utm_medium", "utm_campaign"' in js and '"&k=" +' in js and '"&n=1"' in js
    assert "document.cookie" not in js and "localStorage" not in js
    md = pages.privacy_md()
    assert ("When you open `/check` from a link with campaign tags, we count per day and per tag (`utm_source`, `utm_medium`, "
            "`utm_campaign`) the visit and whether you ran a check, with no cookie, no IP address and nothing that identifies you.") in md
    html = (ROOT / "fabric_backend/page_templates/check.html").read_text()
    assert "campaign tags of this page's address" in html


# ------------------------------------------------------------------ the sample path --------------------------------

def test_the_one_tap_sample_runs_the_sap_shaped_example_and_its_figures_are_the_engines():
    html = (ROOT / "fabric_backend/page_templates/check.html").read_text()
    button = re.search(r'<button[^>]*id="check-try"[^>]*>', html).group(0)
    assert 'data-example="sap"' in button and "Try it on SAP-shaped sample data" in html
    assert html.index('id="check-try"') < html.index('id="check-drop"')
    # the figures the tiles show come from the run: nothing of them is written in the page or its script
    js = (ROOT / "fabric_backend/static/check.js").read_text()
    for fixed in ("1 950", "1,950", "1950", "16.7", "2.6", "17 of 17"):
        assert fixed not in html and fixed not in js, fixed
    # what the engine reports for that example, which the tiles read (r.health, the orphan finding, the amount)
    from fabric_backend import browser_check
    r = browser_check.analyze("sap")
    assert re.search(r"(\d+) of (\d+) keys unique", r["health"]).groups() == ("17", "17")
    orphan = [f for f in r["findings"] if f["check"] == "relationship" and "16.7%" in f["saw"]]
    assert orphan and "1 of 6 rows (16.7%) point at nothing" in orphan[0]["saw"] and orphan[0]["link"]["target"] == "sap_vbak"
    a = next(f["amount"] for f in r["findings"] if f["check"] == "amount_level" and f["amount"] and f["amount"]["wrong"] > f["amount"]["right"])
    assert (a["wrong"], a["right"], round(a["wrong"] / a["right"], 1)) == (1950, 750, 2.6)


def test_no_new_words_the_rules_forbid():
    js = (ROOT / "fabric_backend/static/check.js").read_text()
    added = ["Try it on SAP-shaped sample data", "One tap. No login, no files: synthetic rows, read in this browser.",
             re.search(r"// n240:.*?usage\.Campaigns\)\.", js, re.S).group(0)]
    for text in added:
        for word in ("works with claude", "certified", "partner", "endorsed", "faster", "compliant", "customer"):
            assert word not in text.lower(), (word, text)
