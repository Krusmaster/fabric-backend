"""The regression corpus with published scores (round F2, SCOPE-REVIEW section 6, mechanism 5).

Every corpus of tests/f2_corpus.py is planned three ways (names; names and R5, as main did before round F2; with the
row profile) and scored against its ground truth. The scores, the plan with the profile and what the rows say about
that plan are asserted exactly against tests/corpus/<name>.json, and SCORES here pins the numbers a second time, typed
by hand, so a regenerated expected file cannot move a score unnoticed.

A number here is never changed to make a test pass. A rule change that moves one is a decision: say it in the commit,
regenerate with `python tests/f2_corpus.py --write-expected` and `--write-docs`, and read the diff of every file.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import f2_corpus as corpus

ROOT = Path(__file__).resolve().parent.parent

# (keys right, wrong, missed, extra; links found, wrong) of (true keys, true links), per corpus:
# names only | names and R5, main at 8066dd0 | with the row profile of round F2
SCORES = {
    "adventureworks": {"true": (71, 90), "names": (47, 4, 20, 0, 62, 17), "before": (47, 4, 20, 0, 62, 17), "after": (62, 6, 3, 0, 87, 6)},
    "shop":           {"true": (6, 7),   "names": (6, 0, 0, 0, 6, 0),     "before": (6, 0, 0, 0, 7, 0),     "after": (6, 0, 0, 0, 7, 0)},
    "sap_sd":         {"true": (12, 18), "names": (10, 0, 2, 0, 17, 2),   "before": (10, 0, 2, 0, 17, 2),   "after": (12, 0, 0, 0, 17, 2)},
    "sap_mm":         {"true": (8, 7),   "names": (7, 0, 1, 0, 7, 1),     "before": (7, 0, 1, 0, 7, 1),     "after": (8, 0, 0, 0, 7, 1)},
    "sap_renamed":    {"true": (12, 18), "names": (0, 0, 12, 0, 0, 0),    "before": (0, 0, 12, 0, 0, 0),    "after": (11, 0, 1, 0, 13, 2)},
    "nordic_erp":     {"true": (8, 9),   "names": (0, 0, 8, 0, 0, 0),     "before": (0, 0, 8, 0, 0, 0),     "after": (8, 0, 0, 0, 5, 0)},
    "bc_like":        {"true": (10, 12), "names": (3, 4, 3, 0, 0, 0),     "before": (3, 4, 3, 0, 0, 0),     "after": (8, 2, 0, 0, 10, 1)},
    # PK1: rows written from the salesforce pack, so the pack's own links are the truth; 2 of 53 links hold with orphans
    # (the archived price book), as planted
    "salesforce":     {"true": (21, 53), "names": (21, 0, 0, 0, 53, 0),   "before": (21, 0, 0, 0, 53, 0),   "after": (21, 0, 0, 0, 53, 0)},
}


@pytest.fixture(scope="module")
def results():
    return {n: corpus.run(n) for n in corpus.ORDER}


def _six(s: dict) -> tuple:
    return (s["keys_right"], s["keys_wrong"], s["keys_missed"], s["keys_extra"], s["links_found"], s["links_wrong"])


@pytest.mark.parametrize("name", corpus.ORDER)
def test_the_scores_are_the_published_ones(results, name):
    r = results[name]
    assert (r["after"]["keys_true"], r["after"]["links_true"]) == SCORES[name]["true"]
    for way in ("names", "before", "after"):
        assert _six(r[way]) == SCORES[name][way], (name, way, r[way])


@pytest.mark.parametrize("name", corpus.ORDER)
def test_the_plan_and_the_row_results_are_the_expected_ones(results, name):
    exp = corpus.expected(name)
    got = json.loads(json.dumps(results[name], ensure_ascii=False))
    assert got["plan"] == exp["plan"]                              # every key and link with its rule, and what was proposed
    assert got["row_results"] == exp["row_results"]                # evidence.validate's verdicts, word for word
    assert got == exp


def test_no_corpus_gets_worse_with_the_profile(results):
    """Fewer right keys or fewer found links than before would be a regression; every new wrong one is named below."""
    for n, r in results.items():
        assert r["after"]["keys_right"] >= r["before"]["keys_right"], n
        assert r["after"]["links_found"] >= r["before"]["links_found"], n
        assert r["after"]["keys_extra"] == 0, n                     # no key on a table that has none (the shop's audit_log)
    # wrong links the profile adds where it finds links at all (before: none found, none wrong), each named:
    new_wrong = {n: sorted(set(r["after"]["links_wrong_list"]) - set(r["before"]["links_wrong_list"])) for n, r in results.items()}
    bc = lambda t: f"{corpus.BC}{t}{corpus.BC_APP}"
    assert {n: v for n, v in new_wrong.items() if v} == {
        # an identity key of the same name in a smaller table reads as a subtype: the known limit of R6's own-key case
        "adventureworks": ["TransactionHistoryArchive.transactionid -> TransactionHistory"],
        # the two links by name (R3) the unrenamed sample has too, once the pack knows the tables
        "sap_renamed": ["order_extension.mandt+vbeln -> billing_header", "order_extension.mandt+vbeln -> delivery_header"],
        # the rows fit (every ledger entry's document is a sales order here); the source declares no such link
        "bc_like": [f"{bc('Cust_ Ledger Entry')}.document no_ -> {bc('Sales Header')}"],
    }
    # the keys that are wrong after and were not wrong before, each a key the rows do count unique but the source declares wider
    aw = results["adventureworks"]
    assert sorted(set(aw["after"]["keys_wrong_list"]) - set(aw["before"]["keys_wrong_list"])) == [
        "BusinessEntityContact", "EmployeeDepartmentHistory"]


def test_adventureworks_names_only_is_the_inference_benchmark():
    """The same 47 of 71 keys and 62 of 90 links as tests/test_inference_quality.py, which this corpus does not replace."""
    import test_inference_quality as q
    e = q.EXPECTED["adventureworks"]
    assert (e["key_hits"], e["key_wrong"], e["key_missed"], 0, e["rel_hits"], e["rel_wrong"]) == SCORES["adventureworks"]["names"]


def test_the_published_page_is_what_the_corpus_writes():
    exp = {n: corpus.expected(n) for n in corpus.ORDER}
    assert (ROOT / "docs" / "SCORES.md").read_text(encoding="utf-8") == corpus.scores_md(exp)
    assert json.loads((ROOT / "docs" / "scores.json").read_text(encoding="utf-8")) == corpus.scores_json(exp)


def test_the_published_page_carries_the_pinned_numbers_and_says_what_the_rows_are():
    md = (ROOT / "docs" / "SCORES.md").read_text(encoding="utf-8")
    js = json.loads((ROOT / "docs" / "scores.json").read_text(encoding="utf-8"))
    assert [c["name"] for c in js["corpora"]] == list(corpus.ORDER)
    for c in js["corpora"]:
        for way in ("names", "before", "after"):
            assert _six(c[way]) == SCORES[c["name"]][way]
    assert "| AdventureWorks (OLTP) (`adventureworks`) | 71 | 71 | 47 / 4 / 20 / 0 | 47 / 4 / 20 / 0 | 62 / 6 / 3 / 0 |" in md
    assert "| AdventureWorks (OLTP) (`adventureworks`) | 90 | 62 / 17 | 62 / 17 | 87 / 6 |" in md
    assert "The rows are synthetic in every corpus" in md and "not a measurement on the sample's own rows" in md
    assert "sap_cds" in js["not_present"] and "`sap_cds`" in md
    low = md.lower()
    for word in ("certified", "fastest", "faster", "best-in-class", "world-class", "seamless", "blazing"):
        assert word not in low, word


def test_the_rows_are_the_same_on_every_run():
    a, b = corpus.adventureworks(), corpus.adventureworks()
    assert a[1] == b[1] and sum(len(r) for r in a[1].values()) == 14890
    assert corpus.nordic_erp()[1] == corpus.nordic_erp()[1] and corpus.bc_like()[1] == corpus.bc_like()[1]


def test_the_planted_cases_are_in_the_rows(results):
    n = results["nordic_erp"]
    assert any("fh.kundnr -> kus [R6]" in x and "158 of 158 rows with a value match after stripping leading zeros (0 as written)" in x
               for x in n["plan"]["proposed"])
    assert not any(x.startswith("fh.kundnr") for x in n["plan"]["links"])           # proposed with the counts, never applied
    assert any(x.startswith("orp.ordernr -> oh [R6]: 3 of 491 value(s)") for x in n["plan"]["proposed"])
    s = results["sap_sd"]["row_results"]["links"]
    assert s["VBAP.MANDT+VBELN -> VBAK"].startswith("3 of 844 rows (0.4%) point at nothing | re-count: 841 of 844 rows with a value match as written")
