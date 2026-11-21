"""2026-11-21, round BL2 (sprint item BL2, backlog C-29 and C-28): tenant settings per output, and /getting-started.

The module fabric_backend/tenant_settings.py is the one source; docs/GETTING-STARTED.md and the page /getting-started
must say the same. Every row has a Microsoft Learn link or is marked unverified. Nothing here reads or changes a
tenant setting, and no network is used.
"""
import html as _html
import re
from pathlib import Path

import pytest

from fabric_backend import discovery, tenant_settings as ts
from fabric_backend.pages import PAGES
from tests.test_site import client  # noqa: F401  (the site's test client)

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "GETTING-STARTED.md"
ITEMS = ("lakehouse", "notebook", "pipeline", "semantic model", "report", "ontology", "data agent", "graphql api",
         "catalog write")


def _plain(text: str) -> str:
    return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", text)))


# ------------------------------------------------------------------ the module ---------------------------------------

def test_every_output_of_the_brief_has_rows():
    assert list(ts.OUTPUTS) == [x.replace(" ", "_") for x in ITEMS]
    assert set(ts.REQUIRED) == set(ts.OUTPUTS)
    assert all(ts.REQUIRED[o] for o in ts.OUTPUTS)


def test_every_row_has_a_learn_link_and_a_read_date_or_is_unverified():
    for r in ts.rows():
        assert r["status"] in (ts.CONFIRMED, ts.UNVERIFIED), r
        assert r["read_on"] == ts.READ_ON
        if r["status"] == ts.CONFIRMED:
            assert r["learn"].startswith("https://learn.microsoft.com/"), r
        else:
            assert r["learn"].startswith("https://"), r
    for s in ts.SETTINGS.values():
        assert s["learn"].startswith("https://learn.microsoft.com/en-us/fabric/") and re.fullmatch(r"\d{4}-\d\d-\d\d", s["page_date"])


def test_the_live_value_is_never_claimed():
    for r in ts.rows():
        assert r["live"] == (ts.LIVE if r["setting_id"] else "nothing to read")
    for a in ts.for_outputs(list(ts.OUTPUTS)):
        assert a["live"] == "could not be read; ask your admin"
    src = (ROOT / "fabric_backend" / "tenant_settings.py").read_text(encoding="utf-8")
    assert "requests" not in src and "httpx" not in src and "/admin/tenantsettings" not in src.lower()


def test_for_outputs_orders_dedupes_and_rejects_unknown():
    asks = ts.for_outputs(["data agent", "lakehouse", "Lakehouse", "notebook"])
    names = [a["setting"] for a in asks]
    assert names[0] == "Users can create Fabric items" and len(names) == len(set(names)) == 5
    assert asks[0]["outputs"] == ["Data agent", "Lakehouse", "Notebook"] and asks[0]["status"] == ts.CONFIRMED
    assert ts.for_outputs(["report", "semantic_model"]) == []
    assert ts.no_setting(["report", "lakehouse"]) == ["Report"]
    with pytest.raises(ValueError):
        ts.for_outputs(["warehouse_of_dreams"])


def test_ontology_and_data_agent_name_their_own_settings():
    assert [a["setting"] for a in ts.for_outputs(["ontology"])] == ["Users can create Ontology (preview) items",
                                                                     "Users can create Fabric items"]
    agent = [a["setting"] for a in ts.for_outputs(["data_agent"])]
    assert "Users can use Copilot and other features powered by Azure OpenAI" in agent
    region = [a for a in ts.for_outputs(["data_agent"]) if a["setting"].startswith("Data sent to Azure OpenAI")]
    assert len(region) == 2 and all("outside the EU data boundary and the US" in a["when"] for a in region)


def test_markdown_lists_the_request_in_order():
    md = ts.markdown(["lakehouse", "ontology"])
    lines = [x for x in md.splitlines() if re.match(r"\d+\. ", x)]
    assert lines[0].startswith("1. **Users can create Fabric items**") and lines[1].startswith("2. **Users can create Ontology")
    assert "could not be read; ask your admin" in lines[0] and "**Unverified**" not in lines[0]
    assert "Nothing: these outputs need no tenant setting." in ts.markdown(["report"])


# ------------------------------------------------------------------ doc and page agree --------------------------------

def test_the_doc_is_the_generated_one():
    assert DOC.read_text(encoding="utf-8") == ts.getting_started_md(), \
        "docs/GETTING-STARTED.md is stale: run python -m fabric_backend.tenant_settings --write"
    assert DOC.read_text(encoding="utf-8").startswith("> 2026-11-21, round BL2.")


def test_page_is_routed_and_in_the_sitemap(client):  # noqa: F811
    assert "/getting-started" in PAGES and "/getting-started" in discovery.PUBLIC_PAGES
    r = client.get("/getting-started")
    assert r.status_code == 200 and "{{" not in r.text
    assert "https://krusgraph.test/getting-started</loc>" in client.get("/sitemap.xml").text


def test_page_doc_and_module_say_the_same(client):  # noqa: F811
    page = client.get("/getting-started").text
    body = _plain(page[page.index('<article class="wrap prose gs-page">'):page.index("</article>")])
    doc = _plain(DOC.read_text(encoding="utf-8").replace("**", "").replace("`", ""))
    for _, heading, _ in ts._sections():
        assert heading in body and f"## {heading}" in DOC.read_text(encoding="utf-8"), heading
    for r in ts.rows():
        for text in (r["output_label"], r["setting"] or "none", r["live"]):
            assert text in body and text in doc, text
        assert f'href="{r["learn"]}"' in page and f"<{r['learn']}>" in DOC.read_text(encoding="utf-8")
    for a in ts.for_outputs(list(ts.OUTPUTS)):
        assert a["setting"] in body and a["setting"] in doc
    # one row per (output, setting) in both tables
    assert page.count("<tr><td>") == len(ts.rows())
    assert len([x for x in DOC.read_text(encoding="utf-8").splitlines() if x.startswith("| ") and "---" not in x]) - 1 == len(ts.rows())


def test_page_has_one_h1_ordered_headings_and_a_captioned_table(client):  # noqa: F811
    page = client.get("/getting-started").text
    art = page[page.index('<article class="wrap prose gs-page">'):page.index("</article>")]
    assert art.count("<h1") == 1 and "<h3" not in art
    assert "<caption>" in art and art.count('scope="col"') == 6
    assert 'aria-current=page>Docs</a>' in page


def test_nothing_in_the_page_or_doc_claims_or_sells(client):  # noqa: F811
    text = (_plain(client.get("/getting-started").text) + DOC.read_text(encoding="utf-8")).lower()
    for banned in ("works with claude", "certified", "endorsed", "partner of", "compliant", "guarantee", "€", "price"):
        assert banned not in text, banned
