"""Round n79: a pack other than SAP is named by its own name wherever a person reads the rule (the /check map, panel
and findings, the data dictionary, the Power BI README, the data contracts, the Rayfin comments), while the `rule`
fields of the plan and of the MCP answers keep "SAP pack" and the SAP example reads exactly as before."""
from __future__ import annotations

import json

import pytest

from fabric_backend import browser_check as bc, dictionary, domains, evidence, infer, rayfin, semantic_model, younium_demo as yd
from fabric_backend.infer import plan
from tests import sap_support

LABEL = "Younium + Salesforce pack"


@pytest.fixture(scope="module")
def billing():
    schema, execute = yd.sqlite()
    p = plan(schema)
    return p, evidence.validate(p, execute, max_items=200)


def _strip(o):
    """The result without timings, which differ from run to run."""
    if isinstance(o, dict):
        return {k: _strip(v) for k, v in o.items() if k != "ms"}
    if isinstance(o, list):
        return [_strip(v) for v in o]
    return o


def test_rule_label():
    assert infer.rule_label("SAP pack", {"pack": "younium_salesforce"}) == LABEL
    assert infer.rule_label("SAP pack", "younium_salesforce") == LABEL
    assert infer.rule_label("SAP pack", {"pack": "sap"}) == "SAP pack" and infer.rule_label("SAP pack", None) == "SAP pack"
    assert infer.rule_label("R1", {"pack": "younium_salesforce"}) == "R1" and infer.rule_label("K2", "younium_salesforce") == "K2"


def test_the_plan_and_validate_plan_keep_the_rule_field(billing):
    p, v = billing
    assert {r.rule for r in p.relationships} == {"SAP pack"} and p.pack["rule"] == "SAP pack"
    assert {r["rule"] for r in v["relationships"]} == {"SAP pack"} and {k["rule"] for k in v["keys"]} == {"SAP pack"}
    assert LABEL in p.summary() and "SAP pack" not in p.summary() and "SAP pack" not in p.mermaid()


def test_subscription_billing_on_check_never_says_sap_pack():
    r = bc.analyze("billing")
    shown = _strip({k: v for k, v in r.items() if k != "domains"})
    shown["domains"] = {k: v for k, v in r["domains"].items() if k != "method"}       # the weight table lists rule codes
    text = json.dumps(shown, ensure_ascii=False)
    assert "SAP pack" not in text and text.count(LABEL) > 30
    assert {t["key_rule"] for t in r["tables"]} == {LABEL} and {x["rule"] for x in r["relationships"]} == {LABEL}
    orphan = next(f for f in r["findings"] if f["check"] == "relationship")
    assert f"(rule {LABEL})" in orphan["saw"] and orphan["rules"] == [LABEL]
    assert all(i["rule"] == LABEL for i in r["domains"]["interfaces"])
    assert all(LABEL in c for c in r["domains"]["contracts"].values())


@pytest.mark.parametrize("kind", ["sap", "sample", "crm"])
def test_the_other_examples_read_as_before(kind, monkeypatch):
    now = _strip(bc.analyze(kind))
    monkeypatch.setattr(infer, "rule_label", lambda rule, pack=None: rule)            # the text before round n79
    assert now == _strip(bc.analyze(kind))
    if kind == "sap":
        assert "SAP pack" in json.dumps(now) and LABEL not in json.dumps(now)


def test_dictionary_power_bi_contracts_and_rayfin_name_the_pack(billing):
    p, v = billing
    md = dictionary.data_dictionary(p, "billing", "billing", validation=v)
    assert "SAP pack" not in md and f"| {LABEL} |" in md and f'(rule "{LABEL}")' in md
    sm = semantic_model.draft(p, {"schema": "billing", "item_kind": "Lakehouse"}, "billing_model")
    readme = next(t for n, t in sm["parts"].items() if n.endswith("README.generated.md")) if "parts" in sm else json.dumps(sm)
    assert "SAP pack" not in readme and LABEL in readme
    contracts = domains.draft(p, "billing", "billing", v)["contracts"]
    assert all("SAP pack" not in c and f"key by rule {LABEL}" in c for c in contracts.values())
    files = rayfin.rayfin_files(p)
    assert not any("SAP pack" in t for t in files.values()) and any(f"by rule {LABEL}" in t for t in files.values())


def test_the_sap_texts_are_the_ones_before(monkeypatch):
    p = plan(sap_support.schema())
    md, files = dictionary.data_dictionary(p, "sap", "sap"), rayfin.rayfin_files(p)
    sm = json.dumps(semantic_model.draft(p, {"schema": "sap", "item_kind": "Lakehouse"}, "m"), sort_keys=True)
    monkeypatch.setattr(infer, "rule_label", lambda rule, pack=None: rule)
    assert md == dictionary.data_dictionary(p, "sap", "sap") and files == rayfin.rayfin_files(p)
    assert sm == json.dumps(semantic_model.draft(p, {"schema": "sap", "item_kind": "Lakehouse"}, "m"), sort_keys=True)
    assert '(rule "SAP pack")' in md
