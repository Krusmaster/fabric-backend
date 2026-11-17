"""Q2: the Qlik reader on public load scripts (tests/fixtures/qlik/, with SOURCES.md).

The fixtures come from four public repositories under the MIT licence, each licence file read at the commit that
SOURCES.md names. No Qlik engine ran these scripts: "read" means the reader applied a statement or knows that it leaves
the tables as they are, not that the result equals what Qlik loads. The numbers here are the ones SOURCES.md states.
"""
import re
from pathlib import Path

import pytest

from fabric_backend import migration_read as mr, qlik
from fabric_backend.qlik import star

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "tests" / "fixtures" / "qlik"
FOLDERS = {"qdf": 34, "core-data-loading": 16, "corectl": 7, "butler": 1}
FILES = sorted(CORPUS.rglob("*.qvs"))


def _read(rel: str) -> dict:
    return qlik.read_script((CORPUS / rel).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def coverage():
    total: dict = {}
    for f in FILES:
        total = star.add_coverage(total, star.statement_coverage(qlik.read_script(f.read_text(encoding="utf-8"))))
    return total


# ------------------------------------------------------------------ attribution --------------------------------------

def test_every_fixture_names_its_source_and_every_folder_keeps_its_licence():
    assert {d.name: len(list(d.glob("*.qvs"))) for d in CORPUS.iterdir() if d.is_dir()} == FOLDERS
    sources = (CORPUS / "SOURCES.md").read_text(encoding="utf-8")
    for folder in FOLDERS:
        licence = list((CORPUS / folder).glob("LICENSE-*.txt"))
        assert len(licence) == 1, folder
        text = licence[0].read_text(encoding="utf-8")
        assert "MIT License" in text and "Permission is hereby granted, free of charge" in text, folder
        assert f"{folder}/{licence[0].name}" in sources
    for f in FILES:
        first = f.read_text(encoding="utf-8").splitlines()[0]
        m = re.match(r"// Test fixture of Krusgraph, copied from github\.com/([\w.-]+/[\w.-]+) at commit ([0-9a-f]{40}), file (.+?)\. "
                     r"Licence: MIT, see (LICENSE-[\w.-]+\.txt) in this folder\.", first)
        assert m, f.name
        assert (f.parent / m.group(4)).exists() and m.group(2) in sources
        assert f"`{f.parent.name}/{f.name}`" in sources, f.name


def test_sources_say_what_was_left_out_and_what_the_corpus_does_not_cover():
    sources = (CORPUS / "SOURCES.md").read_text(encoding="utf-8")
    for said in ("16 November 2026", "Lesser General Public License", "help.qlik.com", "not exercised by this corpus",
                 "trademarks of QlikTech International AB", "not affiliated", "No Qlik engine ran these scripts"):
        assert said in sources, said


def test_no_address_credential_or_server_path_in_the_fixtures():
    bad = re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b|\\\\[A-Za-z0-9]|\b[A-Za-z]:\\[A-Za-z]|[\w.-]+@[\w-]+\.[a-z]{2,}"
                     r"|\b(password|pwd|secret|apikey|api_key)\s*=|xpassword|xuserid|Bearer\s+[A-Za-z0-9]", re.I)
    found = {f.name: m.group(0) for f in FILES if (m := bad.search(f.read_text(encoding="utf-8")))}
    assert not found, found


# ------------------------------------------------------------------ coverage -----------------------------------------

def test_every_script_is_read_without_an_error_and_every_statement_is_accounted_for():
    for f in FILES:
        text = f.read_text(encoding="utf-8")
        rd = qlik.read_script(text)
        statements, _ = mr._statements(text)
        assert len(rd["statements"]) == len(statements), f.name
        assert all(n["line"] and n["why"] for n in rd["not_read"]), f.name
        qlik.map_associations(rd)                                    # the mapping takes every reading


def test_the_coverage_is_the_one_sources_md_states(coverage):
    assert {k: v for k, v in coverage.items() if k != "by_type"} == {
        "total": 1856, "read": 1092, "control_flow": 722, "include": 29, "not_read": 13}
    by = coverage["by_type"]
    assert by["load"] == {"total": 64, "read": 64} and by["select"] == {"total": 20, "read": 20}
    assert by["set"] == {"total": 535, "read": 535} and by["let"] == {"total": 303, "read": 303}
    assert by["control"] == {"total": 722, "read": 0, "control_flow": 722}
    assert by["include"] == {"total": 29, "read": 0, "include": 29}
    assert by["drop"] == {"total": 42, "read": 31, "not_read": 11} and by["other"] == {"total": 2, "read": 0, "not_read": 2}
    sources = (CORPUS / "SOURCES.md").read_text(encoding="utf-8")
    assert "| **All** | **1856** | **1092** | **722** | **29** | **13** |" in sources
    for name, row in by.items():
        assert f"| {name} | {row['total']} | {row.get('read', 0)} | {row.get('control_flow', 0)} | {row.get('include', 0)} | {row.get('not_read', 0)} |" in sources


def test_what_is_not_read_in_the_corpus_is_what_sources_md_says():
    left = []
    for f in FILES:
        left += [(f.name, n["statement"].split()[0].lower()) for n in qlik.read_script(f.read_text(encoding="utf-8"))["not_read"]]
    words = sorted(w for _, w in left)
    assert words.count("drop") == 12 and len(words) == 14           # one statement drops two tables: 13 statements
    assert {f for f, _ in left} <= {n for n in (p.name for p in FILES) if n.startswith("3.Include_4.Sub_")}


# ------------------------------------------------------------------ the small scripts, table by table ----------------

def test_qlik_core_examples_give_the_tables_their_scripts_describe():
    def tables(rel):
        return {t["name"]: t["fields"] for t in _read(rel)["tables"]}
    assert tables("core-data-loading/resident-load.qvs") == {"TotalNumber": ["Country", "Number"]}      # Countries is dropped
    assert tables("core-data-loading/concat-tables-auto.qvs") == {"cars1": ["Brand", "RegNo", "Year"]}  # same fields: one table
    assert tables("core-data-loading/concat-tables-forced.qvs") == {"cars1": ["Brand", "RegNo", "Year"]}
    assert tables("core-data-loading/preceding-load-reuse-calc.qvs") == {"EvenOrOddness": ["KeyId", "EvenOrOdd"]}
    assert tables("core-data-loading/rename-fields.qvs") == {"Airports": ["ID", "Name", "City"]}
    assert tables("core-data-loading/split-field.qvs") == {"Locations": ["LetterCode", "NumericCode", "HexCode", "Location"]}
    assert tables("corectl/test_projects_presedence_script.qvs") == {"Numbers": ["Number", "English", "Swedish"]}
    assert tables("corectl/test_projects_using-entities_script.qvs") == {"TableA": ["A"], "TableB": ["B"]}
    auto = _read("core-data-loading/concat-tables-auto.qvs")["tables"][0]
    assert auto["concatenated"][0]["automatic"] is True
    taxes = _read("core-data-loading/preceding-load-calc-field.qvs")["tables"][0]
    assert taxes["name"] == "Taxes" and taxes["fields"] == ["Tax"] and "fields_unknown" in taxes      # `*` over a file


def test_crosstable_is_applied():
    rd = _read("core-data-loading/crosstable.qvs")
    t = rd["tables"][0]
    assert t["fields"] == ["Country", "Month", "Number"] and "fields_unknown" not in t
    assert t["loads"][0]["crosstable"] == {"attribute": "Month", "data": "Number", "qualifiers": 1}
    assert rd["not_read"] == []
    two = mr.read_qvs("T:\nCrossTable(Month, Sales, 2) LOAD Region, Product, Jan, Feb FROM [lib://X/t.csv];")
    assert two["tables"][0]["fields"] == ["Region", "Product", "Month", "Sales"]
    star_file = mr.read_qvs("T:\nCrossTable(Month, Sales) LOAD * FROM [lib://X/t.csv];")["tables"][0]
    assert star_file["fields"] == ["Month", "Sales"] and "fields_unknown" in star_file


# ------------------------------------------------------------------ what the corpus taught the reader ----------------

def test_control_statements_are_listed_on_their_own_and_their_loads_are_read():
    rd = mr.read_qvs("Sub Fill(vName)\n  T:\n  LOAD a, b FROM [lib://X/t.qvd] (qvd);\nEnd Sub\nIf 1 = 1 then\n  Call Fill('x');\nEnd If")
    assert [c["word"] for c in rd["control_statements"]] == ["sub", "end sub", "if", "call", "end if"]
    assert rd["not_read"] == [] and [t["name"] for t in rd["tables"]] == ["T"]
    assert star.statement_coverage(rd) == {"total": 6, "read": 1, "control_flow": 5, "include": 0, "not_read": 0,
                                           "by_type": {"control": {"total": 5, "read": 0, "control_flow": 5},
                                                       "load": {"total": 1, "read": 1}}}


def test_an_include_is_listed_as_a_file_that_was_not_given():
    rd = mr.read_qvs("$(Include=lib://Scripts/common.qvs);\n$(Must_Include=$(vPath)\\calendar.qvs);\nT:\nLOAD a FROM [lib://X/t.qvd] (qvd);")
    assert [(i["kind"], i["file"]) for i in rd["includes"]] == [("include", "lib://Scripts/common.qvs"),
                                                                 ("must_include", "$(vPath)\\calendar.qvs")]
    assert rd["not_read"] == [] and star.statement_coverage(rd)["include"] == 2


def test_variables_with_a_built_name_without_a_value_and_without_let():
    rd = mr.read_qvs("SET vG.$(vPrefix)Path='$(vBase)\\';\nset vEmpty;\nset vNone=;\nvTotal = 13 - vMonths;\nLET vX = 1;")
    assert [(v["name"], v["kind"]) for v in rd["variables"]] == [("vG.$(vPrefix)Path", "set"), ("vEmpty", "set"), ("vNone", "set"),
                                                                 ("vTotal", "let"), ("vX", "let")]
    assert rd["not_read"] == []
    secret = mr.read_qvs("SET vApiToken = abc123;")["variables"][0]
    assert secret["value"] == "(not shown: the name looks like a secret)"


def test_a_label_built_by_dollar_sign_expansion_and_noconcatenate_before_the_label():
    rd = mr.read_qvs("$(vTable):\nLOAD a, b FROM [lib://X/t.qvd] (qvd);\nNoConcatenate $(vOther):\nLOAD a, b FROM [lib://X/u.qvd] (qvd);")
    assert [t["name"] for t in rd["tables"]] == ["$(vTable)", "$(vOther)"] and rd["not_read"] == []


def test_partial_reload_and_row_limiting_prefixes_are_noted_and_the_load_is_read():
    rd = mr.read_qvs("T:\nREPLACE LOAD a, b FROM [lib://X/t.qvd] (qvd);\nU:\nADD ONLY LOAD c FROM [lib://X/u.qvd] (qvd);\n"
                     "V:\nFIRST 10 LOAD d FROM [lib://X/v.qvd] (qvd);\nLeft Join (T) ADD LOAD a, e FROM [lib://X/w.qvd] (qvd);")
    by = {t["name"]: t for t in rd["tables"]}
    assert by["T"]["fields"] == ["a", "b", "e"] and by["T"]["loads"][0]["prefixes_not_applied"] == ["replace"]
    assert by["U"]["loads"][0]["prefixes_not_applied"] == ["add"] and by["V"]["loads"][0]["prefixes_not_applied"] == ["first"]
    assert by["T"]["joins"][0]["prefixes_not_applied"] == ["add"] and rd["not_read"] == []


def test_execute_has_no_effect_on_the_tables_and_a_prefix_that_reshapes_is_still_listed():
    rd = mr.read_qvs("EXECUTE cmd.exe /C dir;\nT:\nGENERIC LOAD k, attr, val FROM [lib://X/t.qvd] (qvd);\n"
                     "H:\nHIERARCHY (id, parent, name) LOAD id, parent, name FROM [lib://X/h.qvd] (qvd);")
    assert rd["other_statements"] == {"execute": 1}
    assert [n["statement"].split()[1] for n in rd["not_read"]] == ["GENERIC", "HIERARCHY"]
    assert rd["tables"] == []


def test_a_drop_of_a_table_this_text_never_loads_says_why():
    rd = mr.read_qvs("Call MakeTable('Tmp');\nDROP TABLE Tmp;")
    assert len(rd["not_read"]) == 1 and "a subroutine of another file" in rd["not_read"][0]["why"]
