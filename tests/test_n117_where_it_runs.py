"""n117: the Concepts page "Where it runs": four places (the browser, your own computer, your own Azure tenant, hosted)
by three tasks (check, draft, create and review). Every status comes from tool_status and the code, the facts the code
cannot give are in one place with their date, and the engine itself calls no language model."""
import re
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from fabric_backend import concepts, discovery, pages, server, tool_status as ts

PATH = "/docs/concepts/where-it-runs"
ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PRODUCT_NAME", "Krusgraph")
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://krusgraph.test/mcp")
    monkeypatch.setenv("CONTACT_EMAIL", "hello@krusgraph.test")
    monkeypatch.setenv("ENTRA_CLIENT_ID", "cid-123")
    with TestClient(server.build_app()) as c:
        yield c


def _main(text: str) -> str:
    return text[text.index('<article class="prose docs">'):text.index("</article>")]


def _plain(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)).replace("&#x27;", "'").replace("&amp;", "&")


def test_the_page_sits_in_concepts_before_the_vision_and_is_linked_from_the_menu_llms_and_the_sitemap(client):
    paths = [x["path"] for x in pages.docs_pages()]
    assert paths.index(PATH) == paths.index("/docs/concepts/vision") - 1
    menu = re.search(r'<nav class="docs-menu"[^>]*>(.*?)</nav>', client.get("/docs").text, re.S).group(1)
    for href in re.findall(r'href="([^"#]+)"', menu):                  # every link in the docs menu answers 200
        assert client.get(href).status_code == 200, href
    assert f'href="{PATH}"' in menu
    assert "### Where it runs" in client.get("/docs.md").text
    llms = client.get("/llms.txt").text
    assert f"{PATH})" in llms and "where it runs" in llms
    assert PATH in client.get("/sitemap.xml").text and PATH in discovery.sitemap_xml()
    assert "### Where it runs" in client.get("/llms-full.txt").text


def test_the_table_has_four_places_three_tasks_and_a_text_version(client):
    html = _main(client.get(PATH).text)
    table = re.search(r'<table class="wr-table"[^>]*>(.*?)</table>', html, re.S).group(1)
    heads = re.findall(r'<th scope="col">(.*?)</th>', table)
    assert heads == ["In the browser", "On your own computer", "In your own Azure tenant", "Hosted by Krusgraph"]
    rows = [re.sub(r"<span.*", "", h) for h in re.findall(r'<th scope="row">(.*?)</th>', table)]
    assert rows == ["Where it is", "Status", "Check", "Draft", "Create and review"]
    assert all(len(re.findall(r"<td data-label=", tr)) == 4 for tr in re.findall(r"<tr class=\"wr-[a-z]+\">(.*?)</tr>", table))
    said = re.search(r'<p class="visually-hidden" id="wr-said">(.*?)</p>', html, re.S).group(1)
    assert 'aria-describedby="wr-said"' in html and "Create and review" in said and "Hosted by Krusgraph" in said
    plain = _plain(html)
    for fact in ("Azure, Sweden Central", "deploy/krusgraph.sh", "Your files are read in this browser and are not uploaded",
                 "Cannot write to Fabric", "dry_run=false", "fabric-backend-mcp"):
        assert fact in plain, fact


def test_every_status_comes_from_tool_status(client):
    plain = _plain(_main(client.get(PATH).text))
    assert f"validate_plan : {ts.task_status(['validate_plan'])}" in plain or f"validate_plan: {ts.task_status(['validate_plan'])}" in plain
    for t in ("semantic_model_draft", "ontology_draft", "dbt_schema", "silver_notebook_draft", "gold_views_draft", "drift_monitor_draft"):
        assert re.sub(r"[`\s]", "", f"{t}:{ts.phrase(t)}") in re.sub(r"\s", "", plain), t
    for t in ts.STATUS:
        if ts.STATUS[t].kind == ts.CREATES:
            assert re.sub(r"\s", "", f"{t}:{concepts.mark(t)[1]}") in re.sub(r"\s", "", plain), t
    word, _at, what = next((w, a, x) for n, w, a, x in ts.FUNCTIONS if n == "`fabric-backend-mcp`")
    assert f"{word.lower()}; {what}" in plain
    claude = next(c for c in ts.CLIENTS if c.name == "Claude")
    assert f"since {claude.works_since}" in plain
    # the local tools are the ones the local server has
    local = (ROOT / "fabric_backend" / "mcp_server.py").read_text()
    for t in ("semantic_model_draft", "ontology_draft", "dbt_schema", "silver_notebook_draft"):
        assert t in ts.LOCAL_TOOLS and f"def {t}(" in local
    for t in ("gold_views_draft", "drift_monitor_draft"):
        assert t not in ts.LOCAL_TOOLS


def test_status_words_sit_next_to_their_own_tool_and_no_sales_words(client):
    from tests.test_site import SALES, WORDS, _claim_named, _claim_sentences
    for path in (PATH, "/docs.md"):
        text = client.get(path).text
        assert not [w for w in SALES if w in text.lower()]
        for sentence in _claim_sentences(_main(text) if path == PATH else text):
            low = sentence.lower()
            used = {w for w in WORDS if w in low}
            other = any(f.replace("`", "") in sentence for f, *_ in ts.FUNCTIONS)
            tools = [] if other else _claim_named(sentence, ts.STATUS)
            if used and len(tools) == 1:
                own = ts.label(tools[0]).lower()
                assert all(w in own for w in used), sentence


def test_the_facts_the_code_cannot_give_are_in_one_place_with_their_date(client):
    html = re.sub(r'<p class="visually-hidden" id="wr-said">.*?</p>', "", _main(client.get(PATH).text), flags=re.S)
    plain = _plain(html)                                # the text version for screen readers repeats the table; not counted
    for key, fact in concepts.WHERE_NOT_IN_CODE.items():
        assert plain.lower().count(fact.lower()) == 1, key
        i = plain.lower().index(fact.lower())
        assert concepts.WHERE_AS_OF in plain[i - 160:i + len(fact) + 40], key
    assert "Copilot Studio and Azure AI Foundry have not been tried" in plain
    assert "no packaging per region and none per agent tier" in plain
    assert "not a Microsoft product" in plain
    for claim in ("cheaper", "as good as", "faster", "minutes", "seconds"):
        assert claim not in plain.lower(), claim


# Model SDKs and model API hosts: the engine imports none and calls none, which is what lets the page say it calls no
# language model. A hit here means the page's sentence has to change.
MODEL_SDKS = ("anthropic", "openai", "azure.ai.inference", "azure.ai.projects", "google.generativeai", "google.genai",
              "mistralai", "cohere", "ollama", "langchain", "litellm", "transformers", "huggingface_hub", "vertexai", "boto3")
MODEL_HOSTS = ("api.anthropic.com", "api.openai.com", "openai.azure.com", "cognitiveservices.azure.com",
               "services.ai.azure.com", "generativelanguage.googleapis.com", "api.mistral.ai", "api.cohere",
               "bedrock-runtime", "inference.ai.azure.com", "/chat/completions", "/v1/messages")


def test_the_engine_calls_no_language_model(client):
    src = [p for p in (ROOT / "fabric_backend").rglob("*") if p.suffix in (".py", ".js") and "pyodide" not in p.parts]
    for p in src:
        text = p.read_text(encoding="utf-8", errors="ignore")
        for sdk in MODEL_SDKS:
            assert not re.search(rf"^\s*(import|from)\s+{re.escape(sdk)}\b", text, re.M), (p, sdk)
        for host in MODEL_HOSTS:
            assert host not in text, (p, host)
    deps = (ROOT / "pyproject.toml").read_text() + (ROOT / "deploy" / "constraints.txt").read_text()
    for sdk in MODEL_SDKS:
        assert not re.search(rf"^\s*\"?{re.escape(sdk.split('.')[0])}[\"=<>\[ ]", deps, re.M | re.I), sdk
    assert "itself calls no language model; the checks are counted with SQL, so a smaller model can drive them" in _plain(
        _main(client.get(PATH).text))
