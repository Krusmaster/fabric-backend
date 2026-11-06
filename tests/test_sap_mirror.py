"""SAP mirror metadata (round n129): keys from a mirrored source's `_metadata.json` win over the SAP pack and the name
rules, and say so per key and per link; the drafted source-to-mirror check. Synthetic SAP-like tables only: column
lists as a SQL analytics endpoint shows them (INFORMATION_SCHEMA rows) and `_metadata.json` files in the format of the
open mirroring landing zone page (`{"keyColumns": [...]}`). No rows and no names from any real SAP system."""
from __future__ import annotations

import json

import pytest

from fabric_backend import dictionary, sap_mirror, sap_pack
from fabric_backend.infer import plan as infer_plan
from fabric_backend.sap_pack import MIRROR_RULE, RULE
from fabric_backend.schema import Column, Schema
from tests import sap_support

O2C = ["VBAK", "VBAP", "VBEP", "KNA1"]


def _files(**keys) -> dict:
    """`_metadata.json` per table folder, written and parsed as the landing zone holds them."""
    return {t: json.loads(json.dumps({"keyColumns": k})) for t, k in keys.items()}


def test_read_takes_both_spellings_and_rejects_what_is_not_a_key_list():
    md = sap_mirror.read({"VBAK": {"keyColumns": ["MANDT", "VBELN"]}, "VBAP": {"KeyColumns": ["MANDT", "VBELN", "POSNR"]},
                          "KNA1": {"FileExtension": "csv"}})
    assert md["VBAK"]["keys"] == ["MANDT", "VBELN"] and md["VBAP"]["keys"] == ["MANDT", "VBELN", "POSNR"]
    assert md["VBAK"]["key_from"] == sap_mirror.KEY_FROM and "KNA1" not in md
    for bad in ({"keyColumns": []}, {"keyColumns": "VBELN"}, {"keyColumns": [""]}):
        with pytest.raises(ValueError):
            sap_mirror.read({"VBAK": bad})


def test_without_mirror_metadata_the_pack_and_the_engine_are_unchanged():
    s = sap_support.schema(O2C)
    m = sap_pack.match(s, "sap")
    assert set(m.key_rules.values()) == {RULE} and all("decided_by" not in r for r in m.relationships)
    assert not m.mirror and not m.mirror_problems
    p = infer_plan(s)
    assert {rule for _, rule in p.keys.values()} == {RULE} and MIRROR_RULE not in {r.rule for r in p.relationships}


def test_mirror_keys_win_and_each_link_says_which_rule_decided_its_target():
    s = sap_support.schema(O2C)
    md = sap_mirror.read(_files(VBAK=["MANDT", "VBELN"], VBAP=["MANDT", "VBELN", "POSNR"]))
    m = sap_pack.match(s, "sap", mirror=md)
    assert m.key_rules == {"VBAK": MIRROR_RULE, "VBAP": MIRROR_RULE, "VBEP": RULE, "KNA1": RULE}
    decided = {(r["source"], r["target"]): r["decided_by"] for r in m.relationships}
    assert decided == {("VBAP", "VBAK"): MIRROR_RULE, ("VBEP", "VBAP"): MIRROR_RULE, ("VBAK", "KNA1"): RULE}
    p, _ = sap_mirror.plan(s, md)
    assert p.keys["VBAK"] == (["MANDT", "VBELN"], MIRROR_RULE) and p.keys["KNA1"] == (["MANDT", "KUNNR"], RULE)
    rules = {(r.source, r.target): (r.rule, r.note) for r in p.relationships}
    assert rules[("VBAP", "VBAK")][0] == MIRROR_RULE and "keyColumns" in rules[("VBAP", "VBAK")][1]
    assert rules[("VBAK", "KNA1")][0] == RULE and "from the pack" in rules[("VBAK", "KNA1")][1]


def test_a_mirror_key_that_differs_from_the_pack_wins_and_the_pack_link_is_listed_with_why():
    # a synthetic mirror that declares VBAK without its client: the pack's VBAP.MANDT+VBELN -> VBAK no longer joins on the key
    s = sap_support.schema(O2C)
    md = sap_mirror.read(_files(VBAK=["VBELN"]))
    m = sap_pack.match(s, "sap", mirror=md)
    assert m.keys["VBAK"] == ["VBELN"]
    assert ("VBAP", "VBAK") not in {(r["source"], r["target"]) for r in m.relationships}
    why = next(r["why"] for r in m.not_applied if (r["source"], r["target"]) == ("VBAP", "VBAK"))
    assert why.startswith(MIRROR_RULE) and "VBELN" in why
    p, _ = sap_mirror.plan(s, md)
    assert p.keys["VBAK"] == (["VBELN"], MIRROR_RULE)
    assert ("VBAP", "VBAK") not in {(r.source, r.target) for r in p.relationships if r.rule in (RULE, MIRROR_RULE)}


def test_mirror_keys_win_over_the_name_rules_on_a_table_no_pack_knows():
    rows = [("sap", "orders", c, "nvarchar(10)", i) for i, c in enumerate(["mandt", "order_no", "order_id"], 1)]
    rows += [("sap", "order_lines", c, "nvarchar(10)", i) for i, c in enumerate(["mandt", "order_id", "line_no"], 1)]
    s = Schema.from_information_schema(rows, schema="sap")
    assert infer_plan(s).keys["orders"][0] == ["order_no"]               # what the name rules read: no client
    p, m = sap_mirror.plan(s, sap_mirror.read(_files(orders=["mandt", "order_no"])))
    assert m is None and p.keys["orders"] == (["mandt", "order_no"], MIRROR_RULE)


def test_mirror_keys_match_a_table_whose_pack_key_columns_are_not_all_there():
    s = sap_support.schema(["VBAK", "KNA1"])
    t = s["VBAK"]
    t.columns = [c for c in t.columns if c.name not in ("MANDT", "VBELN")]  # a landing without the pack's key columns...
    t.columns.insert(0, Column("SALES_DOC", "nvarchar(10)"))              # ...and a key under a name the pack cannot know
    assert sap_pack.match(s, "sap") is None
    m = sap_pack.match(s, "sap", mirror=sap_mirror.read(_files(VBAK=["SALES_DOC"])))
    assert m is not None and m.keys["VBAK"] == ["SALES_DOC"] and m.key_rules["VBAK"] == MIRROR_RULE


def test_metadata_naming_columns_the_table_lacks_is_reported_and_the_pack_key_used():
    s = sap_support.schema(O2C)
    m = sap_pack.match(s, "sap", mirror=sap_mirror.read(_files(VBAK=["MANDT", "NO_SUCH"])))
    assert m.key_rules["VBAK"] == RULE and m.keys["VBAK"] == ["MANDT", "VBELN"]
    assert m.mirror_problems and "NO_SUCH" in m.mirror_problems[0]["why"]


def test_caller_keys_still_win_over_the_mirror():
    s = sap_support.schema(O2C)
    p, _ = sap_mirror.plan(s, sap_mirror.read(_files(VBAK=["MANDT", "VBELN"])), keys={"VBAK": ["VBELN"]})
    assert p.keys["VBAK"] == (["VBELN"], "K1")


def test_descriptions_given_with_the_metadata_win_in_the_draft_and_say_where_they_come_from():
    s = sap_support.schema(O2C)
    md = sap_mirror.read(_files(VBAK=["MANDT", "VBELN"]),
                         descriptions={"VBAK": {"table": "Synthetic order header", "columns": {"VBELN": "Synthetic document number"}}})
    p, _ = sap_mirror.plan(s, md)
    d = sap_pack.draft(p, mirror=md)
    rows = {t["table"]: t for t in d["tables"]}
    assert rows["VBAK"]["description"] == "Synthetic order header" and rows["VBAK"]["description_rule"] == MIRROR_RULE
    assert rows["VBAK"]["description_from"] == sap_mirror.DESCRIPTION_FROM
    assert rows["VBAK"]["column_descriptions"]["VBELN"]["rule"] == MIRROR_RULE
    assert rows["KNA1"]["description_rule"] == RULE and rows["KNA1"]["key_rule"] == RULE
    assert {r["decided_by"] for r in d["relationships"]} == {MIRROR_RULE, RULE}
    assert "mirror_rule" in d and "mirror_rule" not in sap_pack.draft(infer_plan(s))
    assert "SAP mirror metadata" in dictionary.data_dictionary(p, "sap", "sap")


def test_check_draft_for_one_table():
    s = sap_support.schema(O2C)
    c = sap_mirror.check_draft(s, sap_mirror.read(_files(VBAK=["MANDT", "VBELN"])), client="001", tables=["VBAK"])
    [t] = c["tables"]
    assert t["key_rule"] == MIRROR_RULE and t["group_by"] == "VKORG"
    assert t["sap"]["row_count"] == "SELECT COUNT(*) AS row_count FROM \"VBAK\" WHERE \"MANDT\" = '001'"
    assert t["mirror"]["row_count"] == "SELECT COUNT(*) AS row_count FROM [sap].[VBAK] WHERE [MANDT] = '001'"
    assert t["mirror"]["distinct_keys"] == ("SELECT COUNT(*) AS distinct_keys FROM (SELECT DISTINCT [MANDT], [VBELN] "
                                            "FROM [sap].[VBAK] WHERE [MANDT] = '001') AS d")
    assert set(t["sap"]) == set(t["mirror"]) == set(t["compare"])
    assert "connects to neither side" in c["how"] and c["status"].startswith("a draft")


def test_check_draft_uses_the_pack_key_without_metadata_and_a_placeholder_client():
    s = sap_support.schema(["VBAK", "VBAP"], style="prefix")
    c = sap_mirror.check_draft(s)
    t = {x["table"]: x for x in c["tables"]}["sap_vbap"]
    assert t["key_rule"] == RULE and t["sap_table"] == "VBAP"
    assert '"VBAP" WHERE "MANDT" = \'<client>\'' in t["sap"]["row_count"]
    assert "[sap].[sap_vbap] WHERE [mandt] = '<client>'" in t["mirror"]["row_count"]


def test_compare_finds_differences_and_incomplete_answers():
    s = sap_support.schema(O2C)
    c = sap_mirror.check_draft(s, sap_mirror.read(_files(VBAK=["MANDT", "VBELN"])), client="001", tables=["VBAK", "VBAP", "KNA1"])
    sap = {"VBAK": {"row_count": 10, "distinct_keys": 10, "null_keys": 0, "rows_by_group": {"S1": 6, "S2": 4}},
           "VBAP": {"row_count": 25, "distinct_keys": 25}}
    mirror = {"VBAK": {"row_count": 10, "distinct_keys": 10, "null_keys": 0, "duplicate_keys": 0, "rows_by_group": {"S1": 6, "S2": 4}},
              "VBAP": {"row_count": 26, "distinct_keys": 25, "duplicate_keys": 1}}
    r = sap_mirror.compare(c, sap, mirror)
    by = {x["table"]: x for x in r["tables"]}
    assert by["VBAK"]["verdict"] == "equal" and by["KNA1"]["verdict"] == "incomplete"
    assert by["VBAP"]["verdict"] == "different"
    assert "row_count: SAP 25, mirror 26" in by["VBAP"]["differences"] and "duplicate_keys on mirror: 1" in by["VBAP"]["differences"]
    mirror["VBAK"]["rows_by_group"] = {"S1": 6}
    assert "group S2: SAP 4, mirror none" in sap_mirror.compare(c, sap, mirror)["tables"][0]["differences"]
