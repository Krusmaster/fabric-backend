"""The case record: check one, turn a tenant's record into the form that may be shared, and count shared records
into patterns no single organisation can be recognised in (round E1, docs/EVOLUTION.md part 2).

A case is a schema-level pattern with its outcome, for example "a link had orphans; they fell to 0 after stripping
leading zeros on a 10-character customer number". The record holds rule ids, column shapes and types, counts, the fix
and a person's decision by role. It has no field for a row value, a sample, a free text, a person or a token, and real
table and column names are present only when the tenant opted in (case-record.schema.json).

    problems(record)                 everything wrong with a record, [] when it is valid
    to_shared(record, ...)           the tenant's record as the only form that may leave the tenant: counts and
                                     ratios as bands, no date, no reference into the plan, names only on opt-in
    aggregate(shared_records, k=5)   patterns seen at k or more organisations, with banded numbers and the source
                                     line a rule learned from them may carry; everything below k is held back

    python tools/evolution/case_record.py validate FILE [FILE ...]
    python tools/evolution/case_record.py share FILE --contributor HEX16 --share-id HEX32 --consent ID

The schema is read by a small validator written here for the keywords the schema uses, so the check needs no package;
tests/test_e1_evolution.py also runs the `jsonschema` package over the same records where it is installed and expects
the same verdicts. Standard library only; no network. This is the development tool and the contract; the product's
own writer of case records is a later round's work in the engine.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parent / "case-record.schema.json"
K_DEFAULT = 5                       # organisations a pattern must be seen at before it is counted in public
CAP_PER_CONTRIBUTOR = 3             # cases one organisation can add to a pattern's count
N_BANDS = (5, 10, 25, 50, 100)      # a published number is the highest of these that is not above the count

_TYPES = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}


def schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _is(value, name: str) -> bool:
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, _TYPES[name])


def _same(a, b) -> bool:
    return type(a) is type(b) and a == b if isinstance(a, bool) or isinstance(b, bool) else a == b


def _check(value, sch, root: dict, path: str, out: list) -> None:
    """The JSON Schema keywords case-record.schema.json uses, and no others."""
    if sch is True:
        return
    if sch is False:
        out.append(f"{path}: not allowed here")
        return
    if "$ref" in sch:
        target = root
        for part in sch["$ref"].lstrip("#/").split("/"):
            target = target[part]
        _check(value, target, root, path, out)
    if "type" in sch:
        names = sch["type"] if isinstance(sch["type"], list) else [sch["type"]]
        if not any(_is(value, n) for n in names):
            out.append(f"{path}: must be {' or '.join(names)}")
            return
    if "const" in sch and not _same(value, sch["const"]):
        out.append(f"{path}: must be {json.dumps(sch['const'])}")
    if "enum" in sch and not any(_same(value, e) for e in sch["enum"]):
        out.append(f"{path}: must be one of {json.dumps(sch['enum'])}")
    if isinstance(value, str):
        if "pattern" in sch and not re.search(sch["pattern"], value):
            out.append(f"{path}: does not match {sch['pattern']}")
    if _is(value, "number"):
        if "minimum" in sch and value < sch["minimum"]:
            out.append(f"{path}: below {sch['minimum']}")
        if "maximum" in sch and value > sch["maximum"]:
            out.append(f"{path}: above {sch['maximum']}")
    if isinstance(value, list):
        if len(value) < sch.get("minItems", 0):
            out.append(f"{path}: fewer than {sch['minItems']} items")
        if "maxItems" in sch and len(value) > sch["maxItems"]:
            out.append(f"{path}: more than {sch['maxItems']} items")
        if sch.get("uniqueItems") and len({json.dumps(v, sort_keys=True) for v in value}) != len(value):
            out.append(f"{path}: items repeat")
        if "items" in sch:
            for i, v in enumerate(value):
                _check(v, sch["items"], root, f"{path}[{i}]", out)
    if isinstance(value, dict):
        props = sch.get("properties", {})
        for name in sch.get("required", []):
            if name not in value:
                out.append(f"{path}: {name} is missing")
        if len(value) < sch.get("minProperties", 0):
            out.append(f"{path}: fewer than {sch['minProperties']} fields")
        for name, v in value.items():
            if "propertyNames" in sch:
                _check(name, sch["propertyNames"], root, f"{path} (field name {name!r})", out)
            if name in props:
                _check(v, props[name], root, f"{path}.{name}", out)
            elif "additionalProperties" in sch:
                if sch["additionalProperties"] is False:
                    out.append(f"{path}: unknown field {name!r}")
                else:
                    _check(v, sch["additionalProperties"], root, f"{path}.{name}", out)
    for sub in sch.get("allOf", []):
        _check(value, sub, root, path, out)
    if "if" in sch:
        probe: list = []
        _check(value, sch["if"], root, path, probe)
        branch = sch.get("then") if not probe else sch.get("else")
        if branch is not None:
            _check(value, branch, root, path, out)


def case_id(record: dict) -> str:
    body = {k: v for k, v in record.items() if k != "case_id"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def problems(record) -> list[str]:
    """Everything wrong with a case record: the schema first, then what a schema cannot say."""
    out: list[str] = []
    _check(record, schema(), schema(), "case", out)
    if out:
        return out
    tables = [t["ref"] for t in record["tables"]]
    columns = [(c["table"], c["ref"]) for c in record["columns"]]
    if len(set(tables)) != len(tables):
        out.append("case.tables: a table reference repeats")
    if len(set(columns)) != len(columns):
        out.append("case.columns: a column reference repeats within a table")
    out += [f"case.columns: {c} is in table {t}, which is not listed" for t, c in columns if t not in tables]
    known = set(tables) | {f"{t}.{c}" for t, c in columns}
    out += [f"case.names: {n} is not a table or column of this case" for n in sorted(record.get("names", {})) if n not in known]
    zero = (0, "0")
    after = record["after"]
    if record["outcome"] == "holds":
        if record["kind"] == "orphans" and after.get("orphans") not in zero:
            out.append("case.outcome: 'holds' for an orphans case needs after.orphans to be 0")
        if record["kind"] == "key_not_unique" and after.get("duplicates") not in zero:
            out.append("case.outcome: 'holds' for a key case needs after.duplicates to be 0")
    if record["fix"]["id"] == "none" and record["outcome"] in ("holds", "improved", "worse"):
        out.append("case.outcome: without a fix the outcome is 'unchanged' or 'not_counted'")
    if record["case_id"] != case_id(record):
        out.append(f"case.case_id: is not the hash of the record (expected {case_id(record)})")
    return out


def count_band(n: int) -> str:
    if n == 0:
        return "0"
    for top, name in ((10, "1-9"), (100, "10-99"), (1000, "100-999"), (10**4, "1e3-1e4"), (10**5, "1e4-1e5"),
                      (10**6, "1e5-1e6"), (10**7, "1e6-1e7")):
        if n < top:
            return name
    return "1e7+"


def ratio_band(part: int, whole: int) -> str:
    if part == 0 or whole == 0:
        return "0"
    if part >= whole:
        return "100%"
    r = part / whole
    return "0-1%" if r < 0.01 else "1-10%" if r < 0.10 else "10-50%" if r < 0.50 else "50-100%"


def sum_ratio_band(r: float) -> str:
    return "below 1" if r < 1 else "1" if r == 1 else "1-2" if r < 2 else "2" if r == 2 else "2-5" if r < 5 else "5+"


def _banded(m: dict) -> dict:
    out = {k: count_band(m[k]) for k in ("rows", "distinct", "nulls", "duplicates", "orphans", "matched") if k in m}
    for part, name in (("duplicates", "duplicate_ratio"), ("orphans", "orphan_ratio"), ("matched", "match_ratio")):
        if part in m:
            out[name] = ratio_band(m[part], m["rows"])
    if "sum_ratio" in m:
        out["sum_ratio"] = sum_ratio_band(m["sum_ratio"])
    return out


def to_shared(record: dict, *, contributor: str, share_id: str, consent: str) -> dict:
    """The tenant's record in the form that may be shared. The same inputs always give the same bytes. Raises
    ValueError when the input is not a valid tenant record or the result is not a valid shared record."""
    bad = problems(record)
    if bad or record.get("scope") != "tenant":
        raise ValueError("not a valid tenant case record: " + "; ".join(bad or ["scope is not 'tenant'"]))
    out = copy.deepcopy({k: v for k, v in record.items() if k not in ("case_id", "local_ref", "created")})
    out["scope"] = "shared"
    out["before"], out["after"] = _banded(record["before"]), _banded(record["after"])
    out["decision"] = {k: v for k, v in record["decision"].items() if k != "date"}
    if not record.get("names_opt_in"):
        out.pop("names", None)
        out.pop("names_opt_in", None)
    out.update(contributor=contributor, share_id=share_id, consent=consent)
    out["case_id"] = case_id(out)
    bad = problems(out)
    if bad:
        raise ValueError("the shared record is not valid: " + "; ".join(bad))
    return out


def signature(shared: dict) -> dict:
    """What makes two shared cases the same pattern: kind, pack, fix, outcome and the column shapes. No names, no
    numbers, no organisation."""
    return {"kind": shared["kind"], "pack": shared.get("pack"), "fix": shared["fix"]["id"], "outcome": shared["outcome"],
            "columns": sorted([c["role"], c["type"], c.get("length"), c.get("char_class"), bool(c.get("leading_zeros")),
                               bool(c.get("padded"))] for c in shared["columns"])}


def _n_band(n: int) -> str:
    return f"{max(b for b in N_BANDS if b <= n)}+"


def aggregate(shared_records: list[dict], k: int = K_DEFAULT) -> dict:
    """Patterns seen at `k` or more organisations. A pattern below k is counted in `held_back` and nothing else about
    it is returned. Numbers are bands; one organisation adds at most CAP_PER_CONTRIBUTOR cases to a count."""
    if k < min(N_BANDS):
        raise ValueError(f"k must be at least {min(N_BANDS)}")
    groups: dict[str, dict] = {}
    for r in shared_records:
        bad = problems(r)
        if bad or r.get("scope") != "shared":
            raise ValueError("not a valid shared case record: " + "; ".join(bad or ["scope is not 'shared'"]))
        sig = signature(r)
        g = groups.setdefault(json.dumps(sig, sort_keys=True), {"signature": sig, "by": {}})
        g["by"].setdefault(r["contributor"], set()).add(r["share_id"])
    patterns, held = [], 0
    for key in sorted(groups):
        g = groups[key]
        organisations = len(g["by"])
        if organisations < k:
            held += 1
            continue
        cases = sum(min(len(ids), CAP_PER_CONTRIBUTOR) for ids in g["by"].values())
        patterns.append({"signature": g["signature"], "organisations": _n_band(organisations), "cases": _n_band(cases),
                         "source_line": f"learned from {_n_band(cases)} customer cases at {_n_band(organisations)} organisations"})
    return {"k": k, "patterns": patterns, "held_back": held}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Check case records, or write the shareable form of one.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate")
    v.add_argument("files", nargs="+")
    s = sub.add_parser("share")
    s.add_argument("file")
    s.add_argument("--contributor", required=True)
    s.add_argument("--share-id", required=True)
    s.add_argument("--consent", required=True)
    a = ap.parse_args(argv)
    try:
        if a.cmd == "validate":
            failed = 0
            for f in a.files:
                bad = problems(json.loads(Path(f).read_text(encoding="utf-8")))
                failed += bool(bad)
                print(f"{f}: " + ("valid" if not bad else "; ".join(bad)))
            return 1 if failed else 0
        record = json.loads(Path(a.file).read_text(encoding="utf-8"))
        try:
            out = to_shared(record, contributor=a.contributor, share_id=a.share_id, consent=a.consent)
        except ValueError as e:
            print(f"case_record: {e}", file=sys.stderr)
            return 1
        print(json.dumps(out, indent=1, sort_keys=True))
        return 0
    except (OSError, json.JSONDecodeError) as e:
        print(f"case_record: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
