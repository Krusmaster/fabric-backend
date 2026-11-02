"""Round n79: masking goes through the pack the engine reads (sap_pack.match_any), so the personal columns the
Younium + Salesforce pack names (Contact's names, e-mail, telephone, address and birth date; the account names,
e-mail and telephone numbers) are masked like the SAP pack's; schemas without a pack and SAP schemas flag what they
flagged before."""
from __future__ import annotations

import json

import pytest

from fabric_backend import browser_check as bc, privacy, sap_pack, seed
from fabric_backend.schema import Schema
from tests import sap_support

COLS = {"sf_contact": ["Id", "AccountId", "FirstName", "LastName", "Email", "Phone", "MobilePhone", "MailingStreet", "Birthdate"],
        "sf_account": ["Id", "Name", "Phone", "BillingStreet"],
        "younium_accounts": ["id", "name", "invoiceEmail", "phone", "externalCrmId"],
        "younium_subscriptions": ["id", "accountId"], "younium_subscription_versions": ["id", "subscriptionId"]}
VALUE = {"FirstName": "Zq-first", "LastName": "Zq-last", "Email": "zq.contact@example.invalid", "Phone": "+46 70 000 00 01",
         "MobilePhone": "+46 70 000 00 02", "MailingStreet": "Zq-gatan 1", "Birthdate": "1970-01-01", "Name": "Zq Holding",
         "BillingStreet": "Zq-vagen 2", "name": "Zq Account", "invoiceEmail": "zq.billing@example.invalid", "phone": "+46 8 000 00 03"}


def _schema() -> Schema:
    rows = [("b", t, c, "nvarchar", i) for t, cs in COLS.items() for i, c in enumerate(cs, 1)]
    return Schema.from_information_schema(rows, schema="b")


def _old_pack_columns(schema, wanted):
    """privacy._pack_columns as it was before round n79: sap_pack.match (SAP alone), columns compared upper-cased."""
    m = sap_pack.match(schema)
    if m is None:
        return {}
    out = {}
    for table, name in m.tables.items():
        if wanted is not None and table.lower() not in wanted:
            continue
        have = {c.upper(): c for c in schema[table].column_names}
        for p in sap_pack.table_info(name, m.pack).get("personal", []):
            col = have.get(p["column"])
            if col:
                out[(table, col)] = {"rule": p["rule"], "what": privacy.RULES[p["rule"]],
                                     "why": f"the {m.pack} pack names {name}.{p['column']} {privacy.RULES[p['rule']]}"}
    return out


def test_the_pack_names_the_personal_columns_in_the_landings_spelling():
    got = privacy._pack_columns(_schema(), None)
    assert set(got) == {("sf_contact", c) for c in ("FirstName", "LastName", "Email", "Phone", "MobilePhone", "MailingStreet", "Birthdate")} | \
        {("sf_account", c) for c in ("Name", "Phone", "BillingStreet")} | {("younium_accounts", c) for c in ("name", "invoiceEmail", "phone")}
    assert got[("sf_contact", "Email")]["rule"] == "P2" and "younium_salesforce pack names CONTACT.EMAIL" in got[("sf_contact", "Email")]["why"]
    assert got[("younium_accounts", "name")]["rule"] == "P1" and got[("sf_account", "Name")]["rule"] == "P1"
    assert not any(c.lower() in ("id", "accountid", "externalcrmid") for _, c in got)


@pytest.mark.parametrize("name_rules", [True, False])
def test_no_personal_value_leaks_from_a_masked_sample(name_rules, monkeypatch):
    """The values go through mask_rows the way sample_rows sends them; with the name rules switched off the pack alone
    still masks every one of them."""
    if not name_rules:
        monkeypatch.setattr(privacy, "classify", lambda table, column: None)
    schema = _schema()
    for table, cols in COLS.items():
        rows = [{c: VALUE.get(c, f"{table}-{c}-1") for c in cols}]
        flagged = privacy.personal_columns(schema, [table])
        masked, names = privacy.mask_rows(table, rows, flagged)
        text = json.dumps(masked)
        for c in cols:
            if c in VALUE:
                assert VALUE[c] not in text and masked[0][c] == privacy.MASK, (table, c, name_rules)
        assert set(names) == {c for c in cols if c in VALUE}, table
        assert masked[0][cols[0]] == rows[0][cols[0]]                            # the key is not personal data


@pytest.mark.parametrize("schema", [seed.schema("shop"), sap_support.schema(), sap_support.schema(style="prefix"),
                                    sap_support.schema(style="lower")], ids=["shop", "sap", "sap_prefix", "sap_lower"])
def test_schemas_without_a_pack_and_sap_schemas_flag_what_they_flagged(schema, monkeypatch):
    now = privacy.personal_columns(schema)
    monkeypatch.setattr(privacy, "_pack_columns", _old_pack_columns)
    assert now == privacy.personal_columns(schema)


def test_the_check_examples_flag_what_they_flagged_except_billing(monkeypatch):
    srcs = {k: bc._source(k, None, "")[0] for k in ("sample", "sap", "crm", "billing")}
    now = {k: privacy.personal_columns(s.schema) for k, s in srcs.items()}
    monkeypatch.setattr(privacy, "_pack_columns", _old_pack_columns)
    before = {k: privacy.personal_columns(s.schema) for k, s in srcs.items()}
    assert {k: now[k] for k in ("sample", "sap", "crm")} == {k: before[k] for k in ("sample", "sap", "crm")}
    assert set(now["billing"]) >= set(before["billing"])                     # the name rules' findings stay; the pack adds its own
    for s in srcs.values():
        s.close()
