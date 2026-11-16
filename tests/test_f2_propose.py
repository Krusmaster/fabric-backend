"""Count before claiming, and let the data propose (round F2, fabric_backend/propose.py; SCOPE-REVIEW section 6, #4).

Small schemas in SQLite, read with the SQL the engine writes. What the rules do on whole sources is in
tests/test_f2_corpus.py; here each rule is pinned on a case of its own, with the cases it must leave alone.
"""
from __future__ import annotations

import pytest

import f2_corpus as corpus
from fabric_backend import budget, coverage, evidence, profile, propose
from fabric_backend.dialects import DATABRICKS, TSQL
from fabric_backend.infer import RULES, plan


def db(tables: dict, rows: dict, name: str = "s"):
    schema, execute, _close = corpus.database(name, tables, rows)
    return schema, execute


def counting(execute):
    seen = []

    def run(sql):
        seen.append(sql)
        return execute(sql)
    return run, seen


def links(p):
    return sorted(f"{r.source}.{'+'.join(r.source_cols)} -> {r.target} [{r.rule}]" for r in p.relationships)


# ------------------------------------------------------------------ the plan without the profile is unchanged -------

def test_without_profile_nothing_is_counted_and_the_plan_is_the_plan_by_names_and_r5():
    schema, execute = db({"kus": [("ftgnr", "nvarchar"), ("namn", "nvarchar")], "oh": [("ordernr", "int"), ("ftgnr", "nvarchar")]},
                         {"kus": [("001", "a"), ("002", "b")], "oh": [(1, "001"), (2, "002")]})
    run, seen = counting(execute)
    p = plan(schema, execute=run)
    assert p.profile is None and p.keys == {} and seen == []
    assert plan(schema).profile is None
    assert "K6" in RULES and "R6" in RULES and "never linked" in RULES["R6"]


# ------------------------------------------------------------------ 1. keys counted in the same call ----------------

def test_a_key_by_name_is_counted_in_the_same_call_and_its_state_says_so():
    schema, execute = db({"customers": [("customer_id", "int"), ("name", "nvarchar")],
                          "orders": [("order_id", "int"), ("customer_id", "int")]},
                         {"customers": [(1, "a"), (2, "b"), (2, "c")], "orders": [(10, 1), (11, 2)]})
    by_name = plan(schema)
    assert coverage.states(by_name)["key:customers"] == coverage.BY_NAME
    p = plan(schema, execute=execute, profile=True)
    st = coverage.states(p)
    assert st["key:orders"] == coverage.COUNTED_UNIQUE and st["key:customers"] == coverage.COUNTED_NOT_UNIQUE
    assert p.keys["customers"] == (["customer_id"], "K2")          # one duplicate row is a data fault: the key stays
    assert p.profile["key_counts"]["customers"] == {"columns": ["customer_id"], "rows": 3, "nulls": 0, "distinct": 2, "unique": False}
    assert p.profile["not_unique"] == {"customers": "customer_id: 3 rows, 2 distinct, 0 NULL"}
    assert "counted in this call: 2 key(s), 1 unique; not unique in the rows: customers" in p.summary()
    head = coverage.coverage(p)["headline"]
    assert "1 with a counted key" in head and "1 with a key the rows show is not unique" in head and "0 with a key by name only" in head


def test_the_keys_most_links_point_at_are_counted_first():
    schema, execute = db({"a": [("a_id", "int")], "b": [("b_id", "int")], "c": [("c_id", "int"), ("b_id", "int")],
                          "d": [("d_id", "int"), ("b_id", "int")]},
                         {"a": [(1,)], "b": [(1,), (2,)], "c": [(1, 1)], "d": [(1, 2)]})
    run, seen = counting(execute)
    p = plan(schema, execute=run, profile=True, profile_queries=1)
    assert list(p.profile["key_counts"]) == ["b"] and "[s].[b]" in seen[0]
    assert p.profile["not_checked"]["not counted: the statements allowed in this call were used up"] == ["key:a", "key:c", "key:d"]


# ------------------------------------------------------------------ 2. K6 -------------------------------------------

def k6(tables, rows):
    schema, execute = db(tables, rows)
    return plan(schema, execute=execute, profile=True)


def test_k6_takes_the_column_named_like_an_identifier():
    p = k6({"kus": [("namn", "nvarchar"), ("ftgnr", "nvarchar"), ("ort", "nvarchar")]},
           {"kus": [("A", "001", "x"), ("B", "002", "x"), ("C", "003", "y")]})
    assert p.keys == {"kus": (["ftgnr"], "K6")} and p.keyless == []
    assert p.profile["keys_from_rows"]["kus"] == ("ftgnr is unique and never NULL in all 3 rows, and is named like an identifier; "
                                                  "also unique: namn")
    assert coverage.states(p)["key:kus"] == coverage.COUNTED_UNIQUE


def test_k6_takes_the_first_column_when_no_name_says_identifier():
    p = k6({"vg": [("varugrupp", "nvarchar"), ("beskr", "nvarchar")]}, {"vg": [("V1", "a"), ("V2", "b")]})
    assert p.keys == {"vg": (["varugrupp"], "K6")}
    assert "is the table's first column" in p.profile["keys_from_rows"]["vg"]


def test_k6_lists_but_does_not_take_a_unique_column_that_is_neither():
    p = k6({"log": [("event", "nvarchar"), ("rowguid", "uniqueidentifier"), ("at", "datetime")]},
           {"log": [("a", "g1", "2026-01-01"), ("a", "g2", "2026-01-02"), ("b", "g3", "2026-01-03")]})
    assert p.keys == {} and p.keyless == ["log"]
    assert [c["columns"] for c in p.profile["key_candidates"]["log"]] == [["rowguid"]]


def test_k6_never_takes_a_decimal_a_date_or_a_column_with_a_null():
    p = k6({"t": [("amount", "decimal"), ("day", "date"), ("ref_no", "nvarchar")]},
           {"t": [(1.5, "2026-01-01", "a"), (2.5, "2026-01-02", None)]})
    assert p.keys == {} and "no column and no combination" in p.profile["key_candidates"]["t"][0]["reason"]


def test_k6_says_too_few_rows_for_a_table_of_one_row():
    p = k6({"version": [("build", "nvarchar"), ("built", "date")]}, {"version": [("7.1", "2026-01-01")]})
    assert p.keys == {} and p.profile["key_candidates"]["version"] == [{"reason": "1 row(s): too few to tell a key from the rows"}]


def test_k6_takes_the_shortest_unique_combination_of_the_leading_columns():
    p = k6({"lagsaldo": [("lagplats", "nvarchar"), ("artnr", "nvarchar"), ("saldo", "int")]},
           {"lagsaldo": [("H1", "A", 1), ("H1", "B", 1), ("H2", "A", 1)]})
    assert p.keys == {"lagsaldo": (["lagplats", "artnr"], "K6")}
    assert p.profile["keys_from_rows"]["lagsaldo"].startswith("no single column is taken; the first 2 columns together are unique")


def test_k6_puts_a_leading_client_column_into_the_key():
    p = k6({"zext": [("MANDT", "string"), ("VBELN", "string"), ("ZZ_REGION", "string")]},
           {"zext": [("100", "0001", "N"), ("100", "0002", "N"), ("100", "0003", "S")]})
    assert p.keys == {"zext": (["MANDT", "VBELN"], "K6")}
    assert "after the client column MANDT, which is part of the key" in p.profile["keys_from_rows"]["zext"]


def test_a_key_named_after_its_table_stays_when_the_rows_have_duplicates():
    p = k6({"customers": [("customer_id", "int"), ("name", "nvarchar")]}, {"customers": [(1, "a"), (2, "b"), (2, "c"), (2, "d")]})
    assert p.keys == {"customers": (["customer_id"], "K2")} and "keys_from_rows" not in p.profile
    assert p.profile["not_unique"] == {"customers": "customer_id: 4 rows, 2 distinct, 0 NULL"}


def test_a_key_by_name_the_rows_refute_gives_way_to_a_key_from_the_rows():
    """`No_` in a line table is the item number, not the line's key: 2 distinct values in 4 rows."""
    p = k6({"Sales Line": [("Document No_", "nvarchar"), ("Line No_", "int"), ("No_", "nvarchar")],
            "Item": [("No_", "nvarchar"), ("Description", "nvarchar")]},
           {"Sales Line": [("S1", 1, "100"), ("S1", 2, "200"), ("S2", 1, "100"), ("S2", 2, "200")], "Item": [("100", "a"), ("200", "b")]})
    assert plan(p.schema).keys["Sales Line"] == (["No_"], "K2")
    assert p.keys["Sales Line"] == (["Document No_", "Line No_"], "K6")
    assert "the key by name (No_, K2) is not unique in the rows and gives way" in p.profile["keys_from_rows"]["Sales Line"]
    assert "Sales Line.No_ -> Item [R6]" in links(p)


# ------------------------------------------------------------------ 3. R6 -------------------------------------------

def test_r6_links_a_text_reference_the_names_cannot_place():
    schema, execute = db({"kus": [("ftgnr", "nvarchar"), ("namn", "nvarchar")], "ar": [("artnr", "nvarchar"), ("namn", "nvarchar")],
                          "oh": [("ordernr", "int"), ("ftgnr", "nvarchar")]},
                         {"kus": [("001", "a"), ("002", "b"), ("003", "c")], "ar": [("X1", "p"), ("X2", "q")],
                          "oh": [(1, "001"), (2, "002"), (3, "001")]})
    assert links(plan(schema, execute=execute)) == []
    p = plan(schema, execute=execute, profile=True)
    assert links(p) == ["oh.ftgnr -> kus [R6]"]
    r = p.relationships[0]
    assert r.note == "R6 (reference), counted in the rows: 3 of 3 value(s) of oh.ftgnr are in kus.ftgnr"
    assert coverage.states(p)["rel:oh.ftgnr>kus"] == coverage.HOLDS
    assert "1 link(s) from the rows (R6)" in p.summary()


def test_r6_never_compares_a_whole_number_the_name_does_not_support():
    """quantity 1..3 fits any dense id: it is not even compared."""
    schema, execute = db({"products": [("product_id", "int"), ("name", "nvarchar")],
                          "lines": [("line_id", "int"), ("quantity", "int"), ("error_number", "int")]},
                         {"products": [(1, "a"), (2, "b"), (3, "c")], "lines": [(1, 1, 2), (2, 2, 3), (3, 3, 1)]})
    run, seen = counting(execute)
    p = plan(schema, execute=run, profile=True)
    assert links(p) == [] and p.proposed == []
    assert not any("quantity" in s or "error_number" in s for s in seen if "LEFT JOIN" in s)


def test_r6_proposes_and_does_not_apply_what_the_rows_fit_without_a_name():
    schema, execute = db({"salj": [("sign", "nvarchar"), ("namn", "nvarchar")], "kus": [("ftgnr", "nvarchar"), ("saljare", "nvarchar")]},
                         {"salj": [("AB", "x"), ("CD", "y")], "kus": [("1", "AB"), ("2", "CD"), ("3", "AB")]})
    p = plan(schema, execute=execute, profile=True)
    assert links(p) == []
    assert [(x["source"], x["source_cols"], x["target"], x["rule"], x["reason"]) for x in p.proposed] == [
        ("kus", ["saljare"], "salj", "R6",
         "3 of 3 value(s) of kus.saljare are in salj.sign, but the name gives no support: confirm it to apply it")]
    assert p.proposed[0]["confirmed"] == {"source": "kus", "source_cols": ["saljare"], "target": "salj", "target_cols": ["sign"]}
    assert "1 link(s) proposed by R6 from the rows, not applied" in p.summary()
    confirmed = plan(schema, confirmed=[p.proposed[0]["confirmed"]], execute=execute, profile=True)
    assert links(confirmed) == ["kus.saljare -> salj [confirmed]"]


SUBTYPES = ({"entity": [("entity_id", "int"), ("kind", "nvarchar")], "person": [("entity_id", "int"), ("first_name", "nvarchar")],
             "employee": [("entity_id", "int"), ("title", "nvarchar")], "email": [("email_no", "int"), ("entity_id", "int")]},
            {"entity": [(i, "x") for i in range(1, 41)], "person": [(i, "p") for i in range(1, 21)],
             "employee": [(i, "e") for i in range(1, 6)],
             # e-mail rows of persons 1..20: the first values are all employees, the later ones are not
             "email": [(100 + i, i) for i in range(1, 21)]})


def test_r6_finds_the_subtype_chain_and_the_nearest_key():
    schema, execute = db(*SUBTYPES)
    before = plan(schema, execute=execute)
    assert before.keys["entity"] == (["entity_id"], "K2") and "person" not in before.keys
    assert links(before) == ["email.entity_id -> entity [R1]", "employee.entity_id -> entity [R1]", "person.entity_id -> entity [R1]"]
    p = plan(schema, execute=execute, profile=True)
    assert p.keys["person"] == (["entity_id"], "K6") and p.keys["employee"] == (["entity_id"], "K6")
    assert links(p) == ["email.entity_id -> person [R6]", "employee.entity_id -> person [R6]", "person.entity_id -> entity [R1]"]
    note = next(r.note for r in p.relationships if r.source == "email")
    assert note == ("R6 (by name it pointed at entity), counted in the rows: 20 of 20 value(s) of email.entity_id are in "
                    "person.entity_id; they fit entity too, and person has fewer rows: it is the nearest")


def test_the_nearest_key_is_decided_over_every_value_never_over_a_sample():
    """The first 5 distinct values of email.entity_id are all employees; over all 20 they are not."""
    schema, execute = db(*SUBTYPES)
    p = plan(schema, execute=execute, profile=True, sample=5)
    assert "email.entity_id -> person [R6]" in links(p) and "email.entity_id -> employee [R6]" not in links(p)
    assert "a sample" not in next(r.note for r in p.relationships if r.source == "email")


def test_two_keys_of_one_name_with_the_same_values_are_proposed_not_linked():
    schema, execute = db({"history": [("transaction_id", "int"), ("qty", "int")], "archive": [("transaction_id", "int"), ("qty", "int")]},
                         {"history": [(1, 1), (2, 1), (3, 1)], "archive": [(1, 1), (2, 1), (3, 1)]})
    p = plan(schema, execute=execute, profile=True)
    assert links(p) == []
    assert sorted((x["source"], x["target"]) for x in p.proposed) == [("archive", "history"), ("history", "archive")]
    assert "whether one table extends the other is for a person to say" in p.proposed[0]["reason"]


def test_an_ambiguous_column_is_decided_by_the_rows():
    tables = {"dim_customer": [("customer_key", "int"), ("name", "nvarchar")], "stg_customer": [("customer_key", "int"), ("name", "nvarchar")],
              "sales": [("sale_id", "int"), ("customer_key", "int")]}
    rows = {"dim_customer": [(1, "a"), (2, "b"), (3, "c")], "stg_customer": [(7, "x"), (8, "y")], "sales": [(1, 1), (2, 3), (3, 1)]}
    schema, execute = db(tables, rows)
    assert [a["column"] for a in plan(schema).ambiguous] == ["customer_key"]
    p = plan(schema, execute=execute, profile=True)
    assert p.ambiguous == [] and links(p) == ["sales.customer_key -> dim_customer [R6]"]
    assert p.relationships[0].note.startswith("R6 (ambiguous), counted in the rows: 3 of 3 value(s)")


# ------------------------------------------------------------------ 4. the re-count ---------------------------------

ZEROS = ({"kus": [("ftgnr", "nvarchar"), ("namn", "nvarchar")], "fh": [("faktnr", "int"), ("kundnr", "nvarchar")]},
         {"kus": [("000101", "a"), ("000102", "b"), ("000103", "c")], "fh": [(1, "101"), (2, "102"), (3, "101"), (4, "103")]})


def test_a_link_that_holds_only_without_leading_zeros_is_proposed_with_the_counts():
    schema, execute = db(*ZEROS)
    p = plan(schema, execute=execute, profile=True)
    assert links(p) == []
    assert [x["reason"] for x in p.proposed] == [
        "fh.kundnr fits no key as written; 4 of 4 rows with a value match after stripping leading zeros (0 as written) in kus.ftgnr: "
        "the link holds only with that conversion, so it is proposed, not applied (the join needs the same conversion on both sides)"]
    assert p.proposed[0]["kind"] == "conversion"


@pytest.mark.parametrize("source, target, step, sentence", [
    (["101", "102", "999"], ["000101", "000102"], "zeros_stripped", "2 of 3 rows with a value match after stripping leading zeros (0 as written)"),
    ([" A1", "a2 "], ["A1", "A2"], "case_folded", "2 of 2 rows with a value match after trimming spaces and folding case (0 as written)"),
    (["A1 ", " A2"], ["A1", "A2"], "trimmed", "2 of 2 rows with a value match after trimming spaces (0 as written)"),
    (["A1", "A2", "A3"], ["A1", "A2"], "as_written",
     "2 of 3 rows with a value match as written; trimming spaces, folding case and stripping leading zeros match no more"),
    (["000", "0"], ["0000", "x"], "zeros_stripped", "2 of 2 rows with a value match after stripping leading zeros (0 as written)"),
])
def test_recount_says_which_conversion_matches(source, target, step, sentence):
    schema, execute = db({"t": [("k", "nvarchar")], "s": [("c", "nvarchar")]}, {"t": [(v,) for v in target], "s": [(v,) for v in source]})
    rc = propose.recount("s", "s", ["c"], "t", ["k"], execute)
    assert rc["sentence"] == sentence and rc["helps"] == (step != "as_written")
    assert max(rc["match"], key=lambda s: (rc["match"][s], -propose.STEPS.index(s))) == step


def test_recount_casts_a_number_and_a_text_to_the_same_writing():
    schema, execute = db({"t": [("k", "nvarchar")], "s": [("c", "int")]}, {"t": [("0000012345",), ("0000012346",)], "s": [(12345,), (12346,), (5,)]})
    rc = propose.recount("s", "s", ["c"], "t", ["k"], execute)
    assert rc["match"] == {"as_written": 0, "trimmed": 0, "case_folded": 0, "zeros_stripped": 2} and rc["rows_with_value"] == 3


def test_recount_never_raises_and_says_why_it_did_not_count():
    def broken(sql):
        raise RuntimeError("the secret value 4711")
    rc = propose.recount("s", "a", ["c"], "b", ["k"], broken)
    assert rc == {"not_counted": "not counted: the re-count could not run (RuntimeError)"}
    with budget.call(seconds=10, clock=iter([0, 11, 12, 13, 14]).__next__):
        assert propose.recount("s", "a", ["c"], "b", ["k"], broken) == {"not_counted": budget.NOT_CHECKED}


def test_the_recount_statements_are_sql_both_platforms_parse():
    sqlglot = pytest.importorskip("sqlglot")
    for dialect, name in ((TSQL, "tsql"), (DATABRICKS, "databricks")):
        for sql in (propose.recount_sql("dbo", "VBAK", ["MANDT", "KUNNR"], "KNA1", ["MANDT", "KUNNR"], dialect, blank_is_none=True),
                    propose.normalized_inclusion_sql("dbo", "fh", "kundnr", [("kus", "ftgnr"), ("lev", "levnr")], dialect),
                    propose.inclusion_sql("dbo", "oh", "ftgnr", [("kus", "ftgnr"), ("lev", "levnr")], dialect, sample=200, text=True)):
            assert sqlglot.parse_one(sql, read=name) is not None
    t = propose.recount_sql("dbo", "a", ["c"], "b", ["k"], TSQL)
    assert "PATINDEX('%[^0]%'" in t and "NVARCHAR(4000)" in t and "SELECT DISTINCT" in t and t.count("LEFT JOIN") == 4
    d = propose.recount_sql("dbo", "a", ["c"], "b", ["k"], DATABRICKS)
    assert "REGEXP_REPLACE(" in d and "AS STRING" in d and "PATINDEX" not in d


def test_validate_recounts_a_relationship_with_orphans_once():
    schema, execute = db({"customers": [("customer_id", "nvarchar"), ("name", "nvarchar")],
                          "orders": [("order_id", "int"), ("customer_id", "nvarchar")]},
                         {"customers": [("0001", "a"), ("0002", "b")], "orders": [(1, "0001"), (2, "2"), (3, "0002"), (4, "9")]})
    p = plan(schema)
    run = profile.Counting(execute)
    out = evidence.validate(p, run)
    r = out["relationships"][0]
    assert r["orphans"] == 2 and r["verdict"] == "2 of 4 rows (50.0%) point at nothing"         # the verdict is the count as written
    assert r["recount"] == "3 of 4 rows with a value match after stripping leading zeros (2 as written)"
    assert r["recount_match"] == {"as_written": 2, "trimmed": 2, "case_folded": 2, "zeros_stripped": 3}
    assert out["recount_queries"] == 1 and run.statements == 4
    assert profile.items_used(out, run.statements) == 3                                            # the re-count is no item of max_items
    assert coverage.states(p, out)["rel:orders.customer_id>customers"] == coverage.FAILS


def test_validate_does_not_recount_what_holds():
    schema, execute = db({"customers": [("customer_id", "int")], "orders": [("order_id", "int"), ("customer_id", "int")]},
                         {"customers": [(1,), (2,)], "orders": [(1, 1), (2, 2)]})
    run, seen = counting(execute)
    out = evidence.validate(plan(schema), run)
    assert "recount" not in out["relationships"][0] and "recount_queries" not in out and len(seen) == 3


# ------------------------------------------------------------------ the limits --------------------------------------

def test_the_profile_stops_at_its_share_of_the_calls_time():
    schema, execute = db(*ZEROS)
    run, seen = counting(execute)
    ticks = iter([0.0] + [30.0] * 50)                               # the call started; every later look is 30 s in, of 45
    with budget.call(seconds=45, clock=lambda: next(ticks)):
        p = plan(schema, execute=run, profile=True)
    assert seen == [] and p.keys == {} and p.profile["queries"] == 0
    assert p.profile["not_checked"] == {budget.NOT_CHECKED: ["table:fh", "table:kus"]}
    assert "the profile did not reach everything" in p.summary()
    assert propose.PROFILE_SHARE == 0.5


def test_a_statement_that_fails_leaves_its_item_not_counted_and_the_plan_stands():
    schema, execute = db(*ZEROS)

    def flaky(sql):
        if "[fh]" in sql and "c1_nulls" in sql:
            raise RuntimeError("boom")
        return execute(sql)
    p = plan(schema, execute=flaky, profile=True)
    assert p.keys == {"kus": (["ftgnr"], "K6")} and p.profile["failed"] == 1
    assert p.profile["not_checked"] == {"not counted: the statement could not run": ["table:fh"]}


def test_the_hosted_cap_and_its_switch(monkeypatch):
    assert propose.max_queries() == propose.PROFILE_MAX_QUERIES == 60
    monkeypatch.setenv("KRUSGRAPH_PROFILE_QUERIES", "0")
    assert propose.max_queries() == 0
    monkeypatch.setenv("KRUSGRAPH_PROFILE_QUERIES", "not a number")
    assert propose.max_queries() == 60


def test_the_hosted_plan_turns_the_profile_on_and_the_switch_turns_it_off(monkeypatch):
    from fabric_backend import server
    schema, execute = db(*ZEROS)
    p = server._hosted_plan(schema, None, None, execute)
    assert p.keys["kus"] == (["ftgnr"], "K6") and p.profile["max_queries"] == 60 and p.profile["sample"] == server.R5_SAMPLE
    monkeypatch.setenv("KRUSGRAPH_PROFILE_QUERIES", "0")
    off = server._hosted_plan(schema, None, None, execute)
    assert off.profile is None and off.keys == {}


def test_no_statement_of_the_profile_selects_a_row_value():
    schema, execute = db(*SUBTYPES)
    run, seen = counting(execute)
    plan(schema, execute=run, profile=True)
    schema2, execute2 = db(*ZEROS)
    run2, seen2 = counting(execute2)
    plan(schema2, execute=run2, profile=True)
    assert seen and seen2
    for sql in seen + seen2:
        head = sql.split(" FROM ", 1)[0]
        assert head.startswith("SELECT COUNT_BIG(*) AS ") and all(
            part.strip().startswith(("COUNT_BIG(", "COUNT(DISTINCT ", "SUM(CASE WHEN", "(SELECT COUNT_BIG(*)")) for part in head[len("SELECT "):].split(", ")), sql


# ------------------------------------------------------------------ a pack table by its key columns -----------------

def test_a_renamed_sap_table_is_recognised_by_its_key_columns():
    tables, rows, _truth = corpus.sap("sap_sd", corpus.RENAMED)
    schema, execute = db(tables, rows, "sap_renamed")
    p = plan(schema)                                                # no rows needed: the columns say it
    assert {t: v["pack_table"] for t, v in p.pack["by_signature"].items()} == {
        "material_master": "MARA", "sales_doc_header": "VBAK", "sales_doc_item": "VBAP", "delivery_header": "LIKP",
        "delivery_item": "LIPS", "billing_header": "VBRK", "billing_item": "VBRP"}
    assert p.keys["sales_doc_item"] == (["MANDT", "VBELN", "POSNR"], "SAP pack")
    assert "sales_doc_item.MANDT+VBELN -> sales_doc_header [SAP pack]" in links(p)
    assert p.pack["tables"]["sales_doc_header"] == "VBAK"           # the schema's name, the pack's name
    assert "the key of VBAK (VBELN)" in p.pack["by_signature"]["sales_doc_header"]["why"]
    assert coverage.states(p)["key:sales_doc_header"] == coverage.PACK
    counted = plan(schema, execute=execute, profile=True)           # still a candidate until counted, in the same call
    assert coverage.states(counted)["key:sales_doc_header"] == coverage.COUNTED_UNIQUE


def test_the_signature_leaves_alone_what_it_cannot_tell_apart():
    """An extension table keyed like VBAK, and a table that merely has a KUNNR column, are not pack tables."""
    tables, rows, _truth = corpus.sap("sap_sd", corpus.RENAMED)
    schema, _execute = db(tables, rows, "sap_renamed")
    found, unresolved = propose.signature_aliases(schema)
    assert "order_extension" not in found and "customer_master" not in found and "kam_assignment" not in found
    assert unresolved["order_extension"].startswith("its first columns are the key of VBAK, VBUK, LIKP, VBRK")
    plain = plan(corpus.database("shop", *corpus.shop()[:2])[0])
    assert plain.pack is None


def test_a_schema_the_pack_knows_by_name_is_planned_as_before():
    from fabric_backend import sap_sample
    s = sap_sample.schema("sap_sd")
    p = plan(s)
    assert "by_signature" not in p.pack and len(p.pack["tables"]) == 10
    assert p.pack.get("signature_unresolved", {}).keys() <= {"ZSD_ORDER_EXT"}


def test_type_classes():
    assert [propose.type_class(t) for t in ("int", "BIGINT", "nvarchar", "varchar(20)", "STRING", "uniqueidentifier")] == [
        "integer", "integer", "string", "string", "string", "guid"]
    assert [propose.type_class(t) for t in ("decimal(18,2)", "date", "float", "bit", "text", "xml", "money", "", None)] == [None] * 9
