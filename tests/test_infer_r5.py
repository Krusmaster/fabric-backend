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


def test_a_sample_and_a_query_budget_bound_r5_and_say_what_was_left():
    """plan_backend's R5 (round n71): the first `sample` distinct values of a column, one counting query per candidate target
    (two when the target has no key yet), at most `max_queries`; what is left over is proposed, and plan.counted says so."""
    s = src(base())
    log = []

    def execute(sql):
        log.append(sql)
        return s.execute(sql)
    try:
        p = plan(s.schema, execute=execute, sample=2, max_queries=4)
    finally:
        s.close()
    # currency_code and country_code need a key check of their target (2 queries each): 4 queries, then created_by is not counted
    assert p.counted == {"sample": 2, "max_queries": 4, "rule": "R5", "candidates": 3, "queries": 4, "not_counted": 1}
    assert len(log) == 4 and all("TOP (2)" in q for q in log if "with_value" in q)
    r = rels(p)
    assert r[("invoices", "currency_code")] == ("currencies", "code", "R5") and r[("invoices", "country_code")] == ("countries", "code", "R5")
    note = next(x.note for x in p.relationships if x.source_cols == ["currency_code"])
    assert "2 of 2 of the first 2 distinct values of invoices.currency_code are in currencies.code" in note and "a sample" in note
    assert ("invoices", "created_by") not in r
    left = [x for x in p.proposed if x["source_cols"] == ["created_by"]]
    assert len(left) == 1 and left[0]["reason"].startswith("not counted: the counting queries allowed in this call were used up")
    assert left[0]["confirmed"] == {"source": "invoices", "source_cols": ["created_by"], "target": "users", "target_cols": ["user_id"]}
    assert "R5 counted 3 code or role column(s) in the rows: 4 counting query(ies), at most 2 distinct values of a column each; " \
           "1 candidate(s) left for validate_plan or suggest_relationships (limit 4 queries)" in p.summary()
    assert "1 code or role column(s) proposed by R5, not applied" in p.summary()


def test_without_a_sample_the_whole_column_is_counted_and_the_note_says_so():
    s = src(base())
    try:
        p = plan(s.schema, execute=s.execute)
    finally:
        s.close()
    assert p.counted == {"sample": None, "max_queries": None, "rule": "R5", "candidates": 3, "queries": 5, "not_counted": 0}
    assert "a sample" not in next(x.note for x in p.relationships if x.source_cols == ["currency_code"])
    assert "R5 counted 3 code or role column(s) in the rows: 5 counting query(ies)" in p.summary()
    assert plan(s.schema).counted is None                               # no rows read, nothing counted


def test_r5_is_documented_like_the_other_rules():
    assert "R5" in RULES and "proposed" in RULES["R5"]
