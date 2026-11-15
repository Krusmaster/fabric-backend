"""Round E1 (docs/EVOLUTION.md): the gate that fails on a lower score, the evolution log that records what the gate
allows, and the case record that has no room for a customer's data. No network; synthetic numbers only."""
import copy
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EVO = ROOT / "tools" / "evolution"
sys.path.insert(0, str(EVO))
import case_record as cr  # noqa: E402
import log as evolog  # noqa: E402
import score_diff  # noqa: E402
import scores as score_file  # noqa: E402

DOC = (ROOT / "docs" / "EVOLUTION.md").read_text(encoding="utf-8")
TENANT = json.loads((EVO / "examples" / "case-leading-zeros.tenant.json").read_text(encoding="utf-8"))
SHARED = json.loads((EVO / "examples" / "case-leading-zeros.shared.json").read_text(encoding="utf-8"))


def _scores(**values):
    better = {"hits": "higher", "wrong": "lower", "declared": "same"}
    return {name: {"value": v, "better": better[name]} for name, v in values.items()}


def _file(tmp_path, name, scores):
    p = tmp_path / name
    p.write_text(json.dumps({"format": "krusgraph-scores", "version": 1, "scores": scores}), encoding="utf-8")
    return str(p)


# ---- the gate: scores must not go down ------------------------------------------------------------------------------

def test_the_scores_on_this_commit_are_not_below_the_baseline():
    """The gate in the ordinary suite: today's scores against tools/evolution/baseline/scores.json. An improvement
    passes (the weekly round moves the baseline up); a lower score fails here."""
    result = score_diff.diff(score_diff.load(score_file.BASELINE), score_diff.check_scores(score_file.collect()))
    assert result["ok"], score_diff.text(result)
    assert result["compared"] == 77       # 11 schemas, 7 numbers each; a smaller corpus would be a regression too


def test_each_direction_fails_only_the_wrong_way():
    base = _scores(hits=10, wrong=2, declared=13)
    assert score_diff.diff(base, base) == {"ok": True, "compared": 3, "unchanged": 3, "regressions": [], "improvements": [], "new": []}
    better = score_diff.diff(base, _scores(hits=11, wrong=1, declared=13))
    assert better["ok"] and [r["score"] for r in better["improvements"]] == ["hits", "wrong"]
    for worse in (_scores(hits=9, wrong=2, declared=13), _scores(hits=10, wrong=3, declared=13),
                  _scores(hits=10, wrong=2, declared=12), _scores(hits=10, wrong=2, declared=14)):
        result = score_diff.diff(base, worse)
        assert not result["ok"] and len(result["regressions"]) == 1


def test_a_gain_does_not_pay_for_a_loss_and_a_missing_score_is_a_loss():
    base = _scores(hits=10, wrong=2, declared=13)
    traded = score_diff.diff(base, _scores(hits=50, wrong=3, declared=13))
    assert not traded["ok"] and traded["regressions"][0]["score"] == "wrong" and traded["improvements"][0]["score"] == "hits"
    gone = score_diff.diff(base, _scores(hits=10, declared=13))
    assert not gone["ok"] and gone["regressions"][0]["why"] == "missing from the new file"
    flipped = score_diff.diff(base, {**base, "wrong": {"value": 2, "better": "higher"}})
    assert not flipped["ok"] and "direction changed" in flipped["regressions"][0]["why"]
    added = score_diff.diff(base, {**base, "extra": {"value": 1, "better": "higher"}})
    assert added["ok"] and added["new"] == [{"score": "extra", "current": 1}]


def test_the_command_exits_1_on_a_regression_and_2_on_a_bad_file(tmp_path):
    base = _file(tmp_path, "base.json", _scores(hits=10, wrong=2, declared=13))
    same = _file(tmp_path, "same.json", _scores(hits=10, wrong=2, declared=13))
    worse = _file(tmp_path, "worse.json", _scores(hits=9, wrong=2, declared=13))
    run = lambda *a: subprocess.run([sys.executable, str(EVO / "score_diff.py"), *a], capture_output=True, text=True)  # noqa: E731
    assert run(base, same).returncode == 0
    failed = run(base, worse)
    assert failed.returncode == 1 and "hits: 10 -> 9" in failed.stdout and "FAILED" in failed.stdout
    assert json.loads(run(base, worse, "--json").stdout)["ok"] is False
    (tmp_path / "bad.json").write_text('{"scores": {}}', encoding="utf-8")
    assert run(base, str(tmp_path / "bad.json")).returncode == 2
    assert run(base, str(tmp_path / "absent.json")).returncode == 2
    assert score_diff.main([base, same]) == 0 and score_diff.main([base, worse]) == 1


def test_a_score_file_with_a_bad_score_is_refused():
    for bad in ({"hits": {"value": "10", "better": "higher"}}, {"hits": {"value": 10, "better": "up"}},
                {"hits": {"value": True, "better": "higher"}}, {"hits": {"value": 10}}, {}):
        with pytest.raises(score_diff.ScoreFileError):
            score_diff.check_scores({"format": "krusgraph-scores", "version": 1, "scores": bad})


def test_the_baseline_is_what_scores_py_writes_today():
    """The committed baseline is the script's own output, byte for byte, so nobody edits a number by hand unnoticed.
    A round that raises a score regenerates the file: python tools/evolution/scores.py --out tools/evolution/baseline/scores.json"""
    committed = json.loads(score_file.BASELINE.read_text(encoding="utf-8"))
    current = score_file.collect()
    lower = score_diff.diff(current["scores"], committed["scores"])       # the baseline may lag behind, never lead
    assert not [r for r in lower["improvements"]], "the baseline claims a better score than the code gives"
    assert score_file.BASELINE.read_text(encoding="utf-8") == score_file.dumps(committed)


# ---- the record: the evolution log ----------------------------------------------------------------------------------

REPORT = {
    "date": "2026-11-15", "round": "E1", "title": "A synthetic entry for the tests", "status": "shipped",
    "signals": [{"kind": "regression_score", "ref": "tools/evolution/baseline/scores.json"}],
    "proposal": "Compare scores before every push.",
    "gate": {"scores": "no_regression", "scores_ref": "77 compared, 0 worse", "evidence": ["tests/test_e1_evolution.py"],
             "others_code": False, "founder_yes": "not_needed"},
    "shipped": ["8066dd0"],
    "measure": {"scores_before": "77 scores", "scores_after": "77 scores, none changed"},
    "next": ["Add the larger corpus when it exists"],
}


def test_a_report_is_appended_once_and_rendered_the_same_every_time(tmp_path):
    log = tmp_path / "log" / "LOG.jsonl"
    e = evolog.append(REPORT, log)
    assert e["id"].startswith("2026-11-15-E1-") and e["format"] == "krusgraph-evolution-log"
    assert evolog.read(log) == [e]
    with pytest.raises(ValueError, match="already in the log"):
        evolog.append(REPORT, log)
    second = evolog.append({**REPORT, "title": "A correction", "corrects": e["id"]}, log)
    assert len(log.read_text(encoding="utf-8").splitlines()) == 2
    md = evolog.render(evolog.read(log))
    assert md == evolog.render(list(reversed(evolog.read(log))))
    assert "(corrected by a later entry)" in md and f"corrects `{e['id']}`" in md and second["id"] in md
    assert "scores no_regression (77 compared, 0 worse)" in md
    with pytest.raises(ValueError, match="not in the log"):
        evolog.append({**REPORT, "title": "Another", "corrects": "nothing"}, log)


@pytest.mark.parametrize("change, message", [
    ({"gate": {**REPORT["gate"], "scores": "not_run"}}, "shipped needs gate.scores 'no_regression'"),
    ({"gate": {**REPORT["gate"], "scores": "regression"}}, "shipped needs gate.scores 'no_regression'"),
    ({"gate": {**REPORT["gate"], "evidence": []}}, "at least one line of evidence"),
    ({"shipped": []}, "at least one commit"),
    ({"gate": {**REPORT["gate"], "others_code": True, "founder_yes": "pending"}}, "founder_yes 'yes'"),
    ({"status": "measured", "gate": {**REPORT["gate"], "scores": "regression"}}, "never as shipped or measured"),
    ({"signals": []}, "at least one signal"),
    ({"signals": [{"kind": "a hunch", "ref": "x"}]}, "each signal is"),
    ({"date": "15 November"}, "YYYY-MM-DD"),
    ({"customer": "someone"}, "unknown field 'customer'"),
    ({"shipped": ["not a commit"]}, "commit ids"),
])
def test_the_log_refuses_what_the_gate_forbids(change, message):
    assert any(message in p for p in evolog.problems({**REPORT, **change})), evolog.problems({**REPORT, **change})


def test_the_log_takes_what_the_gate_allows(tmp_path):
    assert evolog.problems(REPORT) == []
    rejected = {**REPORT, "status": "rejected", "shipped": [], "gate": {**REPORT["gate"], "scores": "regression", "evidence": []}}
    assert evolog.problems(rejected) == []
    reused = {**REPORT, "gate": {**REPORT["gate"], "others_code": True, "founder_yes": "yes"}}
    assert evolog.problems(reused) == []
    report = tmp_path / "report.json"
    report.write_text(json.dumps(REPORT), encoding="utf-8")
    log = tmp_path / "LOG.jsonl"
    assert evolog.main(["append", str(report), "--log", str(log)]) == 0
    assert evolog.main(["append", str(report), "--log", str(log)]) == 1
    assert evolog.main(["render", "--log", str(log), "--out", str(tmp_path / "LOG.md")]) == 0
    assert (tmp_path / "LOG.md").read_text(encoding="utf-8").startswith("# Evolution log")
    assert evolog.main(["append", str(tmp_path / "absent.json"), "--log", str(log)]) == 2


def test_the_signal_kinds_are_the_ones_the_design_lists():
    for kind in evolog.SIGNALS:
        assert f"`{kind}`" in DOC, kind


# ---- the case record ------------------------------------------------------------------------------------------------

def _rehash(record):
    record["case_id"] = cr.case_id(record)
    return record


def _with(base, **changes):
    r = copy.deepcopy(base)
    for path, value in changes.items():
        target = r
        *parents, last = path.split("__")
        for p in parents:
            target = target[int(p) if p.isdigit() else p]
        if value is KeyError:
            del target[last]
        else:
            target[last] = value
    return _rehash(r)


def test_the_synthetic_examples_are_valid_and_one_is_the_other_shared():
    assert cr.problems(TENANT) == [] and cr.problems(SHARED) == []
    assert cr.to_shared(TENANT, contributor=SHARED["contributor"], share_id=SHARED["share_id"], consent=SHARED["consent"]) == SHARED


def test_what_leaves_the_tenant_has_bands_and_no_date_reference_or_name():
    text = json.dumps(SHARED)
    for exact in ("48210", "3120", "2026-11-15", "orders", "customers", "customer_no"):
        assert exact not in text, exact
    assert not {"local_ref", "created", "names", "names_opt_in"} & set(SHARED) and "date" not in SHARED["decision"]
    assert SHARED["before"] == {"rows": "1e4-1e5", "distinct": "1e3-1e4", "nulls": "0", "orphans": "1e4-1e5", "matched": "0",
                                "orphan_ratio": "100%", "match_ratio": "0"}
    assert SHARED["after"]["orphans"] == "0" and SHARED["after"]["match_ratio"] == "100%"
    assert SHARED["columns"][1]["length"] == 10 and SHARED["columns"][1]["leading_zeros"] is True     # the shape stays


@pytest.mark.parametrize("field, value", [
    ("sample", ["0000104711"]), ("values", {"c1": "0000104711"}), ("note", "Anna said the numbers come from the old system"),
    ("who", "00000000-0000-0000-0000-000000000000"), ("tenant_id", "00000000-0000-0000-0000-000000000000"),
    ("workspace", "Finance"), ("query", "SELECT 1"),
])
def test_there_is_no_field_for_a_row_value_a_text_or_a_person(field, value):
    for base in (TENANT, SHARED):
        assert any(f"unknown field {field!r}" in p for p in cr.problems(_with(base, **{field: value})))
    assert any("unknown field" in p for p in cr.problems(_with(TENANT, **{f"columns__0__{field}": value})))
    assert any("unknown field" in p for p in cr.problems(_with(TENANT, **{f"before__{field}": value})))


def test_names_need_the_opt_in_and_must_be_names():
    named = _with(TENANT, names={"t1": "VBAK", "t1.c1": "KUNNR"})
    assert any("names_opt_in is missing" in p for p in cr.problems(named))
    assert any("names_opt_in: must be true" in p for p in cr.problems(_with(named, names_opt_in=False)))
    opted = _with(named, names_opt_in=True)
    assert cr.problems(opted) == []
    shared = cr.to_shared(opted, contributor="a" * 16, share_id="b" * 32, consent="c-1")
    assert shared["names"] == {"t1": "VBAK", "t1.c1": "KUNNR"} and shared["names_opt_in"] is True
    assert any("does not match" in p for p in cr.problems(_with(opted, names={"t1": "Anna Andersson, Storgatan 1"})))
    assert any("does not match" in p for p in cr.problems(_with(opted, names={"t1": "0000104711"})))
    assert any("field name" in p for p in cr.problems(_with(opted, names={"orders": "VBAK"})))
    assert any("is not a table or column of this case" in p for p in cr.problems(_with(opted, names={"t3": "KNA1"})))


def test_a_shared_record_cannot_carry_what_only_the_tenant_keeps():
    for change in ({"before__rows": 48210}, {"created": "2026-11-15"}, {"local_ref": "rel:a.b->c"},
                   {"decision__date": "2026-11-15"}, {"contributor": KeyError}, {"share_id": KeyError}, {"consent": KeyError},
                   {"contributor": "00000000-0000-0000-0000-000000000000"}):
        assert cr.problems(_with(SHARED, **change)), change
    for change in ({"before__rows": "1e4-1e5"}, {"contributor": "a" * 16}, {"share_id": "b" * 32}, {"consent": "c-1"}):
        assert cr.problems(_with(TENANT, **change)), change


def test_what_the_schema_cannot_say_is_checked_too():
    assert any("case_id" in p for p in cr.problems({**TENANT, "engine": "9.9.9"}))            # changed without rehash
    assert any("needs after.orphans to be 0" in p for p in cr.problems(_with(TENANT, after__orphans=3)))
    assert any("without a fix" in p for p in cr.problems(_with(TENANT, fix={"id": "none"})))
    assert any("not listed" in p for p in cr.problems(_with(TENANT, columns__0__table="t3")))
    assert any("repeats" in p for p in cr.problems(_with(TENANT, columns__1__table="t1")))
    assert any("must be one of" in p for p in cr.problems(_with(TENANT, kind="something new")))
    assert any("does not match" in p for p in cr.problems(_with(TENANT, rule_ids=["trim it"])))
    with pytest.raises(ValueError, match="not a valid tenant case record"):
        cr.to_shared(SHARED, contributor="a" * 16, share_id="b" * 32, consent="c-1")


def test_the_bands():
    assert [cr.count_band(n) for n in (0, 1, 9, 10, 999, 1000, 99_999, 9_999_999, 10**7)] == \
        ["0", "1-9", "1-9", "10-99", "100-999", "1e3-1e4", "1e4-1e5", "1e6-1e7", "1e7+"]
    assert [cr.ratio_band(p, 1000) for p in (0, 1, 9, 10, 99, 100, 499, 500, 999, 1000)] == \
        ["0", "0-1%", "0-1%", "1-10%", "1-10%", "10-50%", "10-50%", "50-100%", "50-100%", "100%"]
    assert [cr.sum_ratio_band(r) for r in (0.5, 1, 1.5, 2, 3, 5)] == ["below 1", "1", "1-2", "2", "2-5", "5+"]
    doubled = _with(TENANT, kind="amount_repeated_on_lines", fix={"id": "sum_at_header_level"},
                    before={"rows": 900, "sum_ratio": 2.0}, after={"rows": 900, "sum_ratio": 1.0})
    shared = cr.to_shared(doubled, contributor="a" * 16, share_id="b" * 32, consent="c-1")
    assert shared["before"] == {"rows": "100-999", "sum_ratio": "2"} and shared["after"]["sum_ratio"] == "1"


def _shares(organisations, per_organisation=1):
    out = []
    for o in range(organisations):
        for i in range(per_organisation):
            out.append(cr.to_shared(_with(TENANT, before__rows=48210 + o, after__rows=48210 + o),
                                    contributor=f"{o:016x}", share_id=f"{o:016x}{i:016x}", consent="c-1"))
    return out


def test_a_pattern_is_counted_only_at_k_organisations_and_only_in_bands():
    four = cr.aggregate(_shares(4, per_organisation=9))
    assert four == {"k": 5, "patterns": [], "held_back": 1}                    # 36 cases at 4 organisations: nothing is said
    five = cr.aggregate(_shares(5))
    assert five["held_back"] == 0 and len(five["patterns"]) == 1
    p = five["patterns"][0]
    assert p["organisations"] == "5+" and p["cases"] == "5+"
    assert p["source_line"] == "learned from 5+ customer cases at 5+ organisations"
    assert set(p) == {"signature", "organisations", "cases", "source_line"}
    assert not re.search(r"[0-9a-f]{16}", json.dumps(p))                        # no contributor, share or case id
    nine = cr.aggregate(_shares(9))["patterns"][0]
    assert nine["organisations"] == "5+"                                        # 6, 7, 8 and 9 read the same as 5
    assert cr.aggregate(_shares(10))["patterns"][0]["organisations"] == "10+"


def test_one_organisation_cannot_carry_a_count_and_k_cannot_be_lowered():
    heavy = cr.aggregate(_shares(5, per_organisation=40))["patterns"][0]        # 200 cases, counted as 5 x 3
    assert heavy["cases"] == "10+" and heavy["organisations"] == "5+"
    with pytest.raises(ValueError, match="k must be at least 5"):
        cr.aggregate(_shares(3), k=3)
    assert cr.aggregate(_shares(9), k=10) == {"k": 10, "patterns": [], "held_back": 1}
    with pytest.raises(ValueError, match="not a valid shared case record"):
        cr.aggregate([TENANT])
    other = cr.to_shared(_with(TENANT, fix={"id": "trim"}), contributor="f" * 16, share_id="e" * 32, consent="c-1")
    mixed = cr.aggregate(_shares(5) + [other])
    assert mixed["held_back"] == 1 and len(mixed["patterns"]) == 1 and mixed["patterns"][0]["signature"]["fix"] == "strip_leading_zeros"


def test_the_package_agrees_with_the_validator_written_here():
    """Where the `jsonschema` package is installed (CI: it comes with the server's pins), it gives the same verdict
    on the schema's own rules as tools/evolution/case_record.py does."""
    jsonschema = pytest.importorskip("jsonschema")
    schema = cr.schema()
    jsonschema.Draft202012Validator.check_schema(schema)
    validator = jsonschema.Draft202012Validator(schema)
    own: list = []
    for record in (TENANT, SHARED):
        assert list(validator.iter_errors(record)) == []
    bad = [_with(TENANT, sample=["x"]), _with(TENANT, names={"t1": "VBAK"}), _with(SHARED, before__rows=5),
           _with(SHARED, contributor=KeyError), _with(TENANT, contributor="a" * 16), _with(TENANT, kind="new"),
           _with(TENANT, columns__0__length=0), _with(TENANT, rule_ids=[]), _with(SHARED, created="2026-11-15"),
           _with(TENANT, columns__0__char_class="hex"), _with(TENANT, tables=[]), _with(TENANT, rule_ids=["R1", "R1"])]
    for record in bad:
        own.clear()
        cr._check(record, schema, schema, "case", own)
        assert own and list(validator.iter_errors(record)), record


def test_the_command_checks_and_shares(tmp_path, capsys):
    good, bad = EVO / "examples" / "case-leading-zeros.tenant.json", tmp_path / "bad.json"
    bad.write_text(json.dumps({**TENANT, "sample": ["x"]}), encoding="utf-8")
    assert cr.main(["validate", str(good), str(EVO / "examples" / "case-leading-zeros.shared.json")]) == 0
    assert cr.main(["validate", str(good), str(bad)]) == 1
    capsys.readouterr()
    assert cr.main(["share", str(good), "--contributor", SHARED["contributor"], "--share-id", SHARED["share_id"],
                    "--consent", SHARED["consent"]]) == 0
    assert json.loads(capsys.readouterr().out) == SHARED
    assert cr.main(["share", str(bad), "--contributor", "a" * 16, "--share-id", "b" * 32, "--consent", "c-1"]) == 1
    assert cr.main(["validate", str(tmp_path / "absent.json")]) == 2


# ---- the tools themselves, and the document --------------------------------------------------------------------------

def test_the_tools_open_no_connection_and_need_no_package():
    """The open-source version sends nothing: the evolution tools read and write local files only."""
    stdlib = {"__future__", "argparse", "copy", "hashlib", "json", "re", "sys", "pathlib"}
    for path in sorted(EVO.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        imported = set(re.findall(r"^\s*(?:from|import)\s+([A-Za-z_][\w]*)", source, re.M))
        own = {"test_inference_quality"} if path.name == "scores.py" else set()
        assert imported <= stdlib | own, (path.name, imported - stdlib)
        for word in ("urllib", "requests", "socket", "http.client", "subprocess", "os.environ"):
            assert word not in source, (path.name, word)


def test_the_document_says_what_exists_and_claims_nothing_it_cannot_back():
    for path in ("tools/evolution/score_diff.py", "tools/evolution/scores.py", "tools/evolution/log.py",
                 "tools/evolution/case_record.py", "tools/evolution/case-record.schema.json",
                 "tools/evolution/examples/case-leading-zeros.tenant.json", "tools/evolution/baseline/scores.json",
                 "tests/test_e1_evolution.py"):
        assert f"`{path}`" in DOC and (ROOT / path).exists(), path
    for part in ("signals", "proposals", "gate", "ship", "measure", "record"):
        assert part in DOC.lower()
    flat = re.sub(r"\s+", " ", DOC.replace("*", ""))
    assert "Nothing in this document is switched on" in flat
    assert f"at least {cr.K_DEFAULT} organisations" in flat
    low = flat.lower()
    for word in ("gdpr compliant", "gdpr-compliant", "fully anonymous", "certified", "endorsed", "faster than", "guarantee"):
        assert word not in low, word
