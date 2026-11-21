"""Round DBT1: dbt_schema(project=true) writes singular dbt tests from what Krusgraph checked (fabric_backend/dbt_checks.py)
to tests/krusgraph_checks/: a duplicate test per composite key and an orphan test per relationship over several columns,
on the sources, and per header amount that validate_plan's amount_levels found (and the pack trap with check
amount_level that names it) a sum test on the header's mart or a grain test on the line's mart.

On the synthetic SAP, Salesforce and Dynamics 365 demos: golden files of the new tests, every one T-SQL that parses, with
no CTE and no dbt-utils, starting with the check or pack rule it comes from; then their SQL is run on the demo rows in
SQLite (tests/dbt1_support.py) and fails on the planted errors and passes otherwise. The rest of the project is the same
as before apart from one README line (the n114/n156 golden files show it). Nothing runs dbt."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import dbt1_support as support
from fabric_backend import dbt, dbt_checks
from test_n139_sql_parses import parse_error, without_jinja

GOLDEN = Path(__file__).parent / "golden"
UPDATE = os.environ.get("KRUSGRAPH_UPDATE_GOLDEN") == "1"
FOLDER = dbt_checks.FOLDER + "/"


@pytest.fixture(scope="module", params=sorted(support.DEMOS))
def demo(request):
    out, p, v = support.project(request.param)
    return request.param, out, p, v


def _checks(files: dict[str, str]) -> dict[str, str]:
    return {k: v for k, v in files.items() if k.startswith(FOLDER)}


def _sql(text: str) -> str:
    return "\n".join(x for x in text.lower().splitlines() if not x.startswith("--"))


# ------------------------------------------------------------------ the files ---------------------------------------

def test_the_new_tests_match_the_golden_file_and_parse_as_tsql(demo):
    name, out, _, _ = demo
    checks = _checks(out["files"])
    assert checks
    for k, v in checks.items():
        assert v.startswith("-- From Krusgraph's "), k                     # which check it comes from, first
        assert parse_error(without_jinja(v)) is None, k
        assert "with " not in _sql(v) and "dbt_utils" not in _sql(v), k     # no CTE, no package
    line = dbt_checks.readme_line(out["files"])
    assert line in out["files"]["README.md"].splitlines() and f"({len(checks)})" in line
    golden = GOLDEN / f"dbt_project_checks_{name}.json"
    if UPDATE:
        golden.write_text(json.dumps(checks, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    assert json.loads(golden.read_text(encoding="utf-8")) == checks, f"{golden.name} differs; KRUSGRAPH_UPDATE_GOLDEN=1 rewrites it"


def test_one_test_per_composite_key_and_composite_relationship(demo):
    _, out, p, _ = demo
    checks = _checks(out["files"])
    dups = {k for k in checks if "__duplicate_" in k}
    orphans = {k for k in checks if "__orphans_" in k}
    assert len(dups) == sum(1 for t, (key, _) in p.keys.items() if len(key) > 1)
    assert len(orphans) == sum(1 for r in p.relationships if len(r.source_cols) > 1)
    for k in dups:
        assert checks[k].startswith("-- From Krusgraph's key check (validate_plan, keys): ")
    for k in orphans:
        assert checks[k].startswith("-- From Krusgraph's relationship check (validate_plan, relationships): ")


def test_the_sap_example_names_its_check_and_its_pack_trap():
    out, _, _ = support.project("sap")
    files = out["files"]
    s = files[FOLDER + "fct_sap_vbak__netwr_summed_once.sql"]
    assert s.splitlines()[0].startswith("-- From Krusgraph's amount check (validate_plan, amount_levels): sap_vbak.NETWR")
    assert "-- Pack rule: sap trap amount_levels (Header amounts and item amounts are different levels)." in s
    assert "from {{ ref('fct_sap_vbak') }}" in s and "from {{ ref('stg_sap__sap_vbak') }}" in s
    o = files[FOLDER + "sap__sap_vbap__orphans_mandt_vbeln__in_sap_vbak.sql"]
    assert "counted: 1 of 6 rows (16.7%) point at nothing" in o and "ltrim(rtrim(c.[VBELN])) <> ''" in o
    assert "ltrim(rtrim(c.[MANDT]))" not in o                              # the client is never blank-tested
    d = files[FOLDER + "sap__sap_vbak__duplicate_mandt_vbeln.sql"]
    assert "from {{ source('sap', 'sap_vbak') }}" in d and "group by [MANDT], [VBELN]" in d
    g = files[FOLDER + "fct_sap_vbap__one_row_per_sap_vbap_row.sql"]
    assert "leaves sap_vbak.NETWR out" in g


def test_nothing_counted_gives_key_and_reference_tests_but_no_mart_tests():
    from fabric_backend import sap_demo
    from fabric_backend.infer import plan
    s, _ = sap_demo.sqlite()
    files = dbt.project(plan(s), "sap", "sap", "lh", None)["files"]
    checks = _checks(files)
    assert checks and all("__duplicate_" in k or "__orphans_" in k for k in checks)
    assert all("not counted (dbt_schema with check_rows=true counts it)" in v.splitlines()[0] for v in checks.values())


# ------------------------------------------------------------------ run on the rows ---------------------------------

def test_on_the_demo_rows_only_the_planted_orphans_fail(demo):
    name, out, p, v = demo
    w = support.Warehouse(name, out["files"])
    failing = w.failing()
    planted = {(x["source"], tuple(x["columns"]), x["target"]) for x in v["relationships"]
               if x.get("orphans") and len(x["columns"]) > 1}
    want = {f"{FOLDER}{name}__{dbt._slug(s)}__orphans_{'_'.join(dbt._slug(c) for c in cols)}__in_{dbt._slug(t)}.sql"
            for s, cols, t in planted}
    assert set(failing) == want
    if name == "sap":                                                       # VBAP 0000000009: an item of no order
        assert failing == {f"{FOLDER}sap__sap_vbap__orphans_mandt_vbeln__in_sap_vbak.sql": [("100", "0000000009")]}


def test_a_planted_duplicate_fails_its_key_test_on_the_source_where_staging_hides_it(demo):
    name, out, p, _ = demo
    w = support.Warehouse(name, out["files"])
    tested = 0
    for t, (key, _) in p.keys.items():
        if len(key) < 2:
            continue
        w.con.execute(f"INSERT INTO {w.schema}.[{t}] SELECT * FROM {w.schema}.[{t}] LIMIT 1")
        try:
            dup = {k: r for k, r in w.failing().items() if "__duplicate_" in k}
            assert list(dup) == [f"{FOLDER}{name}__{dbt._slug(t)}__duplicate_{'_'.join(dbt._slug(c) for c in key)}.sql"], t
            assert dup[next(iter(dup))][0][-1] == 2                         # the key values, and the 2 rows that share them
            stg = [k for k in out["files"] if k.startswith(f"tests/stg_") and f"__{dbt._slug(t)}__unique_" in k]
            assert all(w.run(k) == [] for k in stg)                         # after staging's de-duplication: not visible
            tested += 1
        finally:
            w.con.execute(f"DELETE FROM {w.schema}.[{t}] WHERE rowid = (SELECT MAX(rowid) FROM {w.schema}.[{t}])")
    assert tested == sum(1 for key, _ in p.keys.values() if len(key) > 1)


def _one(w, sql: str):
    return w.con.execute(w.lite(sql)).fetchone()[0]


def test_a_mart_that_sums_the_header_amount_over_its_lines_fails(demo):
    """The mistake the amount check names: the header joined to its lines, the header amount carried on each line. The
    test fails exactly when that changes the total (a header with more than one line and an amount on it)."""
    name, out, p, v = demo
    w = support.Warehouse(name, out["files"])
    sums = sorted(k for k in _checks(out["files"]) if k.endswith("_summed_once.sql"))
    assert sums and all(w.run(k) == [] for k in sums)                      # the drafted marts pass
    stg = dict(zip([x.name for x in p.schema], out["models"]["staging"]))
    broken = 0
    for k in sums:
        mart, col = k[len(FOLDER):-len("_summed_once.sql")].split("__")
        h = next(m for m in out["marts"] if m["model"] == mart)["fact"]
        col = next(c for c in dbt.renames(p, h).values() if dbt._slug(c) == col)
        for f in (f for f in v["amount_levels"]["findings"] if f["header"] == h):
            rh, rl = dbt.renames(p, h), dbt.renames(p, f["line"])
            on = " and ".join(f"h.[{rh[b]}] = l.[{rl[a]}]" for a, b in zip(f["line_columns"], f["header_columns"]))
            wrong = f"select h.* from {{{{ ref('{stg[h]}') }}}} as h left join {{{{ ref('{stg[f['line']]}') }}}} as l on {on}"
            w.models({mart: wrong})
            try:
                total = _one(w, f"select sum(cast([{col}] as decimal(38, 4))) from [{mart}]") or 0
                own = _one(w, f"select sum(cast([{col}] as decimal(38, 4))) from [{stg[h]}]") or 0
                rows = w.run(k)
                assert bool(rows) == (abs(total - own) >= 0.01), (k, f["line"])
                if rows:
                    assert rows[0][0] > rows[0][1], k                      # the mart's total is larger than the header's
                    broken += 1
            finally:
                w.models()
    assert broken
    if name == "sap":                                                       # the demo's numbers: 1 950 against 750
        w.models({"fct_sap_vbak": "select h.* from {{ ref('stg_sap__sap_vbak') }} as h left join {{ ref('stg_sap__sap_vbap') }} as l "
                                  "on h.[mandt] = l.[mandt] and h.[vbeln] = l.[vbeln]"})
        assert w.run(FOLDER + "fct_sap_vbak__netwr_summed_once.sql") == [(1950, 750)]


def test_a_line_mart_that_multiplies_its_rows_fails_its_grain_test(demo):
    """The lines joined to their header's other lines (a many-to-many join over the header's key): the test fails exactly
    when a header has more than one line."""
    name, out, p, v = demo
    w = support.Warehouse(name, out["files"])
    grains = sorted(k for k in _checks(out["files"]) if "__one_row_per_" in k)
    assert grains and all(w.run(k) == [] for k in grains)
    stg = dict(zip([x.name for x in p.schema], out["models"]["staging"]))
    broken = 0
    for k in grains:
        mart = k[len(FOLDER):].split("__")[0]
        line = next(m for m in out["marts"] if m["model"] == mart)["fact"]
        for f in (f for f in v["amount_levels"]["findings"] if f["line"] == line):
            rl = dbt.renames(p, line)
            on = " and ".join(f"a.[{rl[c]}] = b.[{rl[c]}]" for c in f["line_columns"])
            w.models({mart: f"select a.* from {{{{ ref('{stg[line]}') }}}} as a left join {{{{ ref('{stg[line]}') }}}} as b on {on}"})
            try:
                rows = w.run(k)
                assert bool(rows) == (_one(w, f"select count(*) from [{mart}]") != _one(w, f"select count(*) from [{stg[line]}]")), k
                if rows:
                    assert rows[0][0] > rows[0][1], k
                    broken += 1
            finally:
                w.models()
    assert broken


def test_the_demo_script_names_every_singular_test_that_fails_on_the_sap_rows():
    """docs/demo/DBT-DEMO.md, step 4: the tests that fail on purpose on the SAP demo, and nothing else."""
    out, _, _ = support.project("sap")
    failing = support.Warehouse("sap", out["files"]).failing("tests/")
    assert sorted(failing) == [f"{FOLDER}sap__sap_vbap__orphans_mandt_vbeln__in_sap_vbak.sql",
                               "tests/stg_sap__sap_vbap__references_sap_vbak.sql",
                               "tests/stg_sap__sap_vbpa__references_sap_kna1.sql",     # n156: a blank counted as a reference
                               "tests/stg_sap__sap_vbpa__references_sap_knvk.sql"]
    doc = (Path(__file__).parent.parent / "docs" / "demo" / "DBT-DEMO.md").read_text(encoding="utf-8")
    for k in failing:
        assert f"`{k}`" in doc, k
