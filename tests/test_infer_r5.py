"""Rule R5 (round n62): code and role columns linked only where the rows support it, otherwise proposed with a reason."""
from fabric_backend import browser_check as bc
from fabric_backend.infer import RULES, plan


def src(tables):
    return bc._sqlite_source("folder", "synthetic", "t", tables, "synthetic")


def base():
    return {"countries": (["code", "name"], [("SE", "Sweden"), ("NO", "Norway"), ("FI", "Finland")]),
            "currencies": (["code", "name"], [("SEK", "Krona"), ("NOK", "Krone"), ("EUR", "Euro")]),
            "users": (["user_id", "name"], [(i, f"User {i}") for i in range(1, 6)]),
            "invoices": (["invoice_id", "currency_code", "country_code", "created_by"],
                         [(i, ["SEK", "NOK", "EUR"][i % 3], ["SE", "NO", "FI"][i % 3], 1 + i % 5) for i in range(1, 10)])}


def rels(p):
    return {(r.source, r.source_cols[0]): (r.target, r.target_cols[0], r.rule) for r in p.relationships}


def test_code_and_role_columns_are_planned_when_the_rows_support_them():
    s = src(base())
    try:
        p = plan(s.schema, execute=s.execute)
    finally:
        s.close()
    r = rels(p)
    assert r[("invoices", "currency_code")] == ("currencies", "code", "R5")
    assert r[("invoices", "country_code")] == ("countries", "code", "R5")
    assert r[("invoices", "created_by")] == ("users", "user_id", "R5")
    assert p.keys["countries"] == (["code"], "R5") and p.keys["currencies"] == (["code"], "R5")
    # the trap: two tables with `code` and `name` are never linked to each other
    assert not any({x.source, x.target} == {"countries", "currencies"} for x in p.relationships)
    assert not p.proposed and "counted in the rows" in next(x.note for x in p.relationships if x.rule == "R5")


def test_without_rows_the_plan_is_the_plan_by_names():
    s = src(base())
    try:
        named, counted = plan(s.schema), plan(s.schema, execute=s.execute)
    finally:
        s.close()
    assert not any(x.rule == "R5" for x in named.relationships) and not named.proposed
    assert len(counted.relationships) == len(named.relationships) + 3


def test_values_outside_the_key_wrong_type_or_too_few_values_are_proposed_not_planned():
    t = base()
    t["invoices"] = (["invoice_id", "currency_code", "country_code", "created_by"],
                     [(i, ["SEK", "XXX", "EUR"][i % 3], "SE", f"u{i}") for i in range(1, 10)])
    s = src(t)
    try:
        p = plan(s.schema, execute=s.execute)
    finally:
        s.close()
    assert not any(x.rule == "R5" for x in p.relationships)
    why = {(x["source_cols"][0], x["target"]): x["reason"] for x in p.proposed}
    assert "3 of 9 value(s) of invoices.currency_code are not in currencies.code" in why[("currency_code", "currencies")]
    assert "too few to tell" in why[("country_code", "countries")]
    assert "is text, users.user_id is number" in why[("created_by", "users")]
    assert all(x["confirmed"]["target"] == x["target"] for x in p.proposed)


def test_a_code_column_that_is_not_unique_in_the_target_is_no_key():
    t = base()
    t["countries"] = (["code", "name"], [("SE", "Sweden"), ("SE", "Sverige"), ("NO", "Norway"), ("FI", "Finland")])
    s = src(t)
    try:
        p = plan(s.schema, execute=s.execute)
    finally:
        s.close()
    assert "countries" not in p.keys and ("invoices", "country_code") not in rels(p)
    assert any("is not unique" in x["reason"] for x in p.proposed if x["target"] == "countries")


def test_a_role_name_that_fits_two_tables_is_proposed_for_both():
    t = base()
    t["employees"] = (["employee_id", "name"], [(i, f"Employee {i}") for i in range(1, 9)])
    s = src(t)
    try:
        p = plan(s.schema, execute=s.execute)
    finally:
        s.close()
    assert ("invoices", "created_by") not in rels(p)
    assert {x["target"] for x in p.proposed if x["source_cols"] == ["created_by"]} == {"users", "employees"}


def test_salesforce_custom_field_and_words_before_the_stem():
    t = {"Account": (["Id", "Name", "ERP_Customer_No__c"], [(f"A{i}", f"Acct {i}", f"C{i}") for i in range(1, 6)]),
         "customers": (["customer_no", "name"], [(f"C{i}", f"Cust {i}") for i in range(1, 8)])}
    s = src(t)
    try:
        p = plan(s.schema, execute=s.execute)
    finally:
        s.close()
    assert rels(p)[("Account", "ERP_Customer_No__c")] == ("customers", "customer_no", "R5")


def test_r5_is_documented_like_the_other_rules():
    assert "R5" in RULES and "proposed" in RULES["R5"]
