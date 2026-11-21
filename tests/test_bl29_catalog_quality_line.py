"""2026-11-21, round BL29 (sprint wave B, backlog P-15): a dated quality line and stable tags in the catalog draft.

Every description catalog.draft writes ends with one line from counts.summary (BL3): "Quality checked 2026-11-21: keys
6 of 6 hold; links 7 of 7 hold." An ISO date and the counts only: no row value, no column name. With no validation it
says "Quality: not checked yet." and never "hold". The tags come from a fixed, documented set (catalog.TAG_SET), are
the same in two runs on the same plan, and never carry a date."""
import json
import re

from fabric_backend import catalog, sap_demo, seed
from fabric_backend.infer import plan
from fabric_backend.schema import Column, Schema, Table

NAMES = {"create_silver_notebook": "silver_shop", "create_gold_views": "gold_shop", "create_drift_monitor": "drift_shop",
         "pipeline": "pipeline_shop"}
SCHEMAS = {"silver": "silver", "gold": "gold"}
MADE = [{"tool": "create_backend", "type": "GraphQLApi", "name": "shop_api"},
        {"tool": "create_semantic_model", "type": "SemanticModel", "name": "shop_model"},
        {"tool": "create_silver_notebook", "type": "Notebook", "name": "silver_shop"},
        {"tool": "create_views", "type": "T-SQL", "name": "krusgraph-sql"}]
ISO = re.compile(r"^Quality checked (\d{4}-\d{2}-\d{2}): keys \d+ of \d+ holds?(, [^;]+)?; links \d+ of \d+ holds?(, .+)?\.$")


def _info(name: str = "shop_lh", schema: str = "shop") -> dict:
    return {"workspace_id": "ws", "item_id": "item-1", "item_name": name, "item_kind": "Lakehouse", "schema": schema}


def _shop():
    return plan(seed.schema("shop"))


def _validation(p, bad_key: str | None = None, orphans_on: str | None = None) -> dict:
    """validate_plan's answer, made up from the plan: every key unique and every link without orphans, except the key of
    `bad_key` (2 duplicate rows) and the links from `orphans_on` (3 rows pointing at nothing)."""
    keys = []
    for t, (cols, _) in p.keys.items():
        dup = t == bad_key
        keys.append({"table": t, "columns": list(cols), "rows": 10, "distinct": 8 if dup else 10, "nulls": 0,
                     "verdict": "not unique: 2 duplicate rows" if dup else "unique in all 10 rows"})
    rels = [{"source": r.source, "columns": list(r.source_cols), "target": r.target, "rows_with_value": 10,
             "orphans": 3 if r.source == orphans_on else 0,
             "verdict": "3 rows point at nothing" if r.source == orphans_on else "holds: every value is found"}
            for r in p.relationships]
    return {"keys": keys, "relationships": rels}


def _draft(p, validation=None, **kw):
    return catalog.draft(p, _info(), MADE, NAMES, SCHEMAS, validation, **kw)


def _sap_plan():
    s = Schema(schema="sap")
    for name, (cols, types, _) in sap_demo.tables().items():
        t = sap_demo.PREFIX + name.lower()
        s.tables[t] = Table(t, [Column(c, ty) for c, ty in zip(cols, types)], schema="sap")
    return plan(s)


# ------------------------------------------------------------------ the line ---------------------------------------

def test_a_counted_plan_gets_one_dated_line_with_the_counts_on_every_item():
    p = _shop()
    out = _draft(p, _validation(p), checked_on="2026-11-21")
    k, n = len(p.keys), len(p.relationships)
    line = f"Quality checked 2026-11-21: keys {k} of {k} hold; links {n} of {n} hold."
    assert out["quality"]["line"] == line and out["quality"]["checked_on"] == "2026-11-21"
    assert out["quality"]["keys"] == {"total": k, "holds": k, "fails": 0, "no_rows": 0, "not_counted": 0}
    assert [i["type"] for i in out["items"]] == ["Lakehouse", "GraphQLApi", "SemanticModel", "Notebook"]
    for i in out["items"]:
        assert i["description"].endswith(" " + line) and i["description"].count("Quality") == 1
        assert len(i["description"]) == i["description_chars"] <= catalog.DESCRIPTION_MAX


def test_what_fails_is_said_and_not_folded_into_hold():
    p = _shop()
    bad = sorted(p.keys)[0]
    source = sorted({r.source for r in p.relationships})[0]
    line = _draft(p, _validation(p, bad_key=bad, orphans_on=source), checked_on="2026-11-21")["quality"]["line"]
    assert ISO.match(line), line
    k, n = len(p.keys), len(p.relationships)
    assert f"keys {k - 1} of {k} hold, 1 fails" in line
    assert re.search(rf"links \d of {n} hold, \d fails?\.$", line), line


def test_the_uncounted_case_says_not_checked_yet_and_never_hold():
    p = _shop()
    out = _draft(p)
    assert out["quality"] == {"checked_on": None, "keys": None, "links": None, "line": "Quality: not checked yet."}
    for i in out["items"]:
        assert i["description"].endswith(" Quality: not checked yet.")
        assert not re.search(r"\bholds?\b", i["description"]), i["description"]
        assert not re.search(r"\d{4}-\d{2}-\d{2}", i["description"])            # no date without a check
    assert catalog.CHECKED_TAG not in out["items"][0]["tags"]


def test_the_date_is_iso_from_the_argument_the_validation_or_today():
    p = _shop()
    v = _validation(p)
    assert catalog.checked_day(None, "2026-11-21") is None
    assert catalog.checked_day(v, "2026-11-21T20:05Z") == "2026-11-21"
    assert catalog.checked_day({**v, "checked_at": "2026-11-14T14:54Z"}) == "2026-11-14"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", catalog.checked_day(v))
    assert catalog.checked_day({**v, "checked_on": "yesterday"}, None) == catalog._today()


def test_the_line_has_no_row_value_and_no_column_name():
    p = _shop()
    out = _draft(p, _validation(p), checked_on="2026-11-21")
    line = out["quality"]["line"]
    words = set(re.findall(r"[a-z_]+", line.lower()))
    columns = {c.lower() for t in p.schema for c in t.column_names}
    assert not words & columns, words & columns
    values = {v for rows in seed.rows().values() for r in rows for v in r if isinstance(v, str) and len(v) >= 3}
    assert not [v for v in values if v in line]
    assert set(re.sub(r"\d{4}-\d{2}-\d{2}", "", line)) <= set("Quality checked: keys of hold; links fails no rows to "
                                                                "check have has not counted 0123456789,.")


def test_a_long_description_is_shortened_and_the_line_kept_whole():
    p = _shop()
    long = {**_info("a_lakehouse_with_a_rather_long_name_for_this"), "schema": "s" * 60}
    out = catalog.draft(p, long, MADE, NAMES, SCHEMAS, _validation(p), checked_on="2026-11-21")
    line = out["quality"]["line"]
    for i in out["items"]:
        assert len(i["description"]) <= catalog.DESCRIPTION_MAX
        assert i["description"].endswith(" " + line)


# ------------------------------------------------------------------ the tags ---------------------------------------

def _allowed(tag: str) -> bool:
    fixed = {t["tag"] for t in catalog.TAG_SET if not t["tag"].endswith("<name>")}
    return tag in fixed or tag.startswith(catalog.DOMAIN_TAG)


def test_two_runs_give_the_same_tags_and_no_tag_has_a_date():
    p = _shop()
    for v in (None, _validation(p)):
        first = _draft(p, v, checked_on="2026-11-21")
        second = _draft(_shop(), v, checked_on="2026-12-24")        # another day, the same plan: the same tags
        assert [i["tags"] for i in first["items"]] == [i["tags"] for i in second["items"]]
        assert first["tag_setup"] == second["tag_setup"]
        for t in first["items"][0]["tags"]:
            assert _allowed(t) and len(t) <= catalog.TAG_MAX and not re.search(r"\d{4}", t), t
    counted = _draft(p, _validation(p))["items"][0]["tags"]
    assert counted == ["Krusgraph", "krusgraph-checked", "domain: customers", "domain: products"]


def test_a_sap_plan_gets_the_sap_tag():
    p = _sap_plan()
    assert catalog.pack_ids(p) == ["sap"]
    out = catalog.draft(p, _info("sap_lh", "sap"), [], NAMES, SCHEMAS)
    tags = out["items"][0]["tags"]
    assert tags[:2] == ["Krusgraph", "krusgraph-sap"] and all(_allowed(t) for t in tags)
    assert catalog.pack_ids(_shop()) == []


def test_the_tag_set_is_documented_in_the_answer_and_the_doc():
    out = _draft(_shop())
    assert out["tag_set"] == catalog.TAG_SET
    doc = open("docs/CATALOG-ACCELERATOR.md", encoding="utf-8").read()
    for t in catalog.TAG_SET:
        assert f"`{t['tag']}`" in doc, t["tag"]
    assert json.dumps(out)                                            # the answer stays plain JSON
