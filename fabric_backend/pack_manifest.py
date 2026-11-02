"""One manifest per knowledge pack: `fabric_backend/packs/<pack>/manifest.yaml` (round n77).

A pack's modules (`packs/<pack>/<module>.json`, read by sap_pack.py) are what the engine runs on. The manifest is the
same knowledge in one file of one shape for every pack, for a person to review: what the pack claims, where each claim
comes from, which check on the rows can confirm it, which synthetic fixture exercises it, and whether a person has
reviewed it. Its sections `sources`, `entities`, `candidate_relationships` and `traps` are derived from the module files
(derive); the rest is kept by hand: id, version, title, source_systems, scope, sharing, fixtures, review_status,
reviewed_by, reviewed_at, and `check` per trap. The test (tests/test_pack_manifest.py) runs problems() on every
manifest: every rule in the module files has a row in the manifest and the other way round, so the two cannot drift.

    load(pack)            -> the manifest as a dict (needs PyYAML, which the test extra installs)
    header(pack)          -> {id, version, review_status} read without PyYAML, for a tool's answer
    derive(pack)          -> the derived sections, from the module files
    problems(manifest)    -> what differs between the manifest and the module files, and what is malformed
    render(manifest)      -> the manifest as text in the layout the files use (one line per row)
    python -m fabric_backend.pack_manifest <pack> --write   regenerates the derived sections of a manifest in place,
                                                            keeping the hand-kept fields

The format is described in docs/PACKS.md and checked by packs/manifest.schema.json. Nothing here connects to anything.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from . import sap_pack

PACKS = sap_pack.PACKS
SCHEMA = PACKS / "manifest.schema.json"
FILE = "manifest.yaml"
HEADER = ("id", "version", "title", "source_systems", "scope", "sharing", "rule", "variants", "modules")
DERIVED = ("sources", "entities", "candidate_relationships", "traps")
TAIL = ("fixtures", "review_status", "reviewed_by", "reviewed_at")
HAND_KEPT = ("id", "version", "title", "source_systems", "scope", "sharing") + TAIL     # plus `check` per trap
VALIDATIONS = ("referential_integrity", "cardinality", "amount_level")
CHECKS = ("referential_integrity", "amount_level", "privacy", "manual")
SHARING = ("public-synthetic",)
REVIEW = ("proposed", "reviewed")
_MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december")
_DATE = re.compile(r"\b(\d{1,2}) (" + "|".join(m.capitalize() for m in _MONTHS) + r") (\d{4})\b")


def path(pack: str) -> Path:
    return PACKS / pack / FILE


def available() -> list[str]:
    """The packs that have a manifest."""
    return sorted(p.name for p in PACKS.iterdir() if p.is_dir() and (p / FILE).is_file())


def load(pack: str) -> dict:
    import yaml
    return yaml.safe_load(path(pack).read_text(encoding="utf-8"))


def header(pack: str) -> dict:
    """id, version and review_status of a pack's manifest, read from its first lines without a YAML library: what
    sap_pack_draft adds to its answer. {} when the pack has no manifest."""
    p = path(pack)
    if not p.is_file():
        return {}
    out = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^(id|version|review_status): (.+?)\s*$", line)
        if m:
            out[m.group(1)] = json.loads(m.group(2)) if m.group(2).startswith('"') else m.group(2)
        if len(out) == 3:
            break
    return out


# ------------------------------------------------------------------ derived from the module files ------------------

def _ref(table: str, cols: list[str]) -> str:
    return f"{table}.{'+'.join(cols)}"


def parse_ref(ref: str) -> tuple[str, list[str]]:
    """'VBAP.MANDT+VBELN' -> ('VBAP', ['MANDT', 'VBELN'])."""
    table, _, cols = ref.partition(".")
    return table, cols.split("+")


def _accessed(source: dict) -> str | None:
    """The date a fetched source was read, when its note says one (ISO form); None otherwise."""
    m = _DATE.search(source.get("note", "")) if source.get("fetched") else None
    if not m:
        return None
    return f"{m.group(3)}-{_MONTHS.index(m.group(2).lower()) + 1:02d}-{int(m.group(1)):02d}"


def _validation(r: dict, target: dict) -> list[str]:
    """Which checks of validate_plan can confirm a relationship on the rows: orphans (every relationship), rows that
    match more than one target row (every relationship that is not many-to-many), and the header amounts a join
    repeats (a many-to-one relationship to a table whose amounts the pack names; amounts.header_amounts)."""
    out = ["referential_integrity"]
    if r["cardinality"] != "many-to-many":
        out.append("cardinality")
    if r["cardinality"] == "many-to-one" and target.get("amounts"):
        out.append("amount_level")
    return out


def derive(pack: str) -> dict:
    """The sections of the manifest that come from the module files, in the manifest's shape. `check` per trap is
    hand-kept, so the traps come out without it."""
    p = sap_pack.load(pack)
    sources = [{"id": sid, "title": s["title"], "url": s["url"], "publisher": s["publisher"], "accessed": _accessed(s),
                "verified": bool(s["fetched"]), **({"note": s["note"]} if s.get("note") else {})}
               for sid, s in sorted(p["sources"].items())]
    entities = []
    for t in sorted(p["tables"].values(), key=lambda t: (t["module"], t["name"])):
        e = {"name": t["name"], "module": t["module"], "level": t["level"], "title": t["en"], "key": list(t["key"])}
        if t.get("unique_keys"):
            e["unique_keys"] = [list(u) for u in t["unique_keys"]]
        if t.get("amounts"):
            e["amounts"] = [{"column": a["column"], "level": a["level"], "currency": a["currency"]} for a in t["amounts"]]
        if t.get("variants"):
            e["variants"] = list(t["variants"])
        if t.get("area"):
            e["area"] = t["area"]
        if t.get("note"):
            e["note"] = t["note"]
        e["sources"] = list(t["sources"])
        entities.append(e)
    rels = []
    for r in p["relationships"]:
        row = {"from": _ref(r["source"], r["source_cols"]), "to": _ref(r["target"], r["target_cols"]), "cardinality": r["cardinality"],
               "kind": r.get("kind", "key"), "module": r["module"], "rule": p["rule"], "applied": r.get("apply", True) is not False}
        for k in ("role", "condition", "variants", "where", "valid_on", "verified"):
            if r.get(k):
                row[k] = r[k]
        row["validation"] = _validation(r, p["tables"][r["target"]])
        row["sources"] = list(r["sources"])
        rels.append(row)
    traps = [{"name": t["id"], "title": t["title"], "description": t["text"], "module": t["module"], "sources": list(t["sources"])}
             for t in p["traps"]]
    return {"rule": p["rule"], "variants": dict(p["variants"]),
            "modules": [{"module": m["module"], "title": m["title"], "status": m["status"], "file": m["file"]} for m in p["modules"]],
            "sources": sources, "entities": entities, "candidate_relationships": rels, "traps": traps}


def identity(section: str, row: dict) -> str:
    return {"sources": row.get("id"), "entities": row.get("name"), "traps": row.get("name"),
            "candidate_relationships": f"{row.get('from')} -> {row.get('to')}"}[section]


# ------------------------------------------------------------------ the check -----------------------------------------

def problems(manifest: dict, pack: str | None = None) -> list[str]:
    """What is inconsistent between a manifest and the module files of its pack, and what the JSON schema does not say:
    a derived row missing on either side or differing, a bad id or version, review fields that do not match the
    review status, a trap check or a validation outside the known ones. Empty when the manifest is in step."""
    out = []
    pack = pack or manifest.get("id")
    if not isinstance(pack, str) or not (PACKS / pack).is_dir():
        return [f"id {pack!r} is not a pack directory under {PACKS.name}/"]
    if manifest.get("id") != pack:
        out.append(f"id {manifest.get('id')!r} is not the pack's directory name {pack!r}")
    if not re.fullmatch(r"\d+\.\d+\.\d+", str(manifest.get("version", ""))):
        out.append(f"version {manifest.get('version')!r} is not major.minor.patch")
    if manifest.get("sharing") not in SHARING:
        out.append(f"sharing {manifest.get('sharing')!r} is not one of {', '.join(SHARING)}")
    status = manifest.get("review_status")
    if status not in REVIEW:
        out.append(f"review_status {status!r} is not one of {', '.join(REVIEW)}")
    by, at = manifest.get("reviewed_by") or "", manifest.get("reviewed_at") or ""
    if status == "proposed" and (by or at):
        out.append("review_status proposed, but reviewed_by or reviewed_at is filled in")
    if status == "reviewed" and not (by and re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(at))):
        out.append("review_status reviewed needs reviewed_by and reviewed_at (YYYY-MM-DD)")
    for k in ("title", "source_systems", "scope", "fixtures"):
        if not manifest.get(k):
            out.append(f"{k} is missing or empty")
    want = derive(pack)
    for k in ("rule", "variants", "modules"):
        if manifest.get(k) != want[k]:
            out.append(f"{k} differs from the module files: {json.dumps(manifest.get(k), ensure_ascii=False)[:120]}")
    for section in DERIVED:
        have = {identity(section, r): r for r in manifest.get(section) or []}
        mine = {identity(section, r): r for r in want[section]}
        if len(have) != len(manifest.get(section) or []):
            out.append(f"{section}: a row is repeated")
        for key in mine.keys() - have.keys():
            out.append(f"{section}: in the module files but not in the manifest: {key}")
        for key in have.keys() - mine.keys():
            out.append(f"{section}: in the manifest but not in the module files: {key}")
        for key in mine.keys() & have.keys():
            theirs = dict(have[key])
            check = theirs.pop("check", None)
            if section == "traps" and check not in CHECKS:
                out.append(f"traps: {key}: check {check!r} is not one of {', '.join(CHECKS)}")
            if theirs != mine[key]:
                fields = sorted(k for k in set(theirs) | set(mine[key]) if theirs.get(k) != mine[key].get(k))
                out.append(f"{section}: {key} differs in {', '.join(fields)}")
    return out


# ------------------------------------------------------------------ writing -------------------------------------------

_PLAIN = re.compile(r"^[A-Za-z_][A-Za-z0-9_\-]*$")
_RESERVED = {"true", "false", "null", "yes", "no", "on", "off", "y", "n", "~"}


def _scalar(v) -> str:
    if isinstance(v, str) and _PLAIN.match(v) and v.lower() not in _RESERVED:
        return v
    return json.dumps(v, ensure_ascii=False)


def render(manifest: dict) -> str:
    """The manifest as text: the header as plain YAML, every row of a derived section on one line (a JSON object is a
    YAML flow mapping), the tail as plain YAML. Key order is the format's, not the dict's."""
    lines = [f"# Knowledge pack manifest ({manifest.get('id')}). Format: docs/PACKS.md; schema: packs/manifest.schema.json.",
             "# sources, entities, candidate_relationships and traps are derived from the module files in this directory;",
             "# regenerate them with: python -m fabric_backend.pack_manifest " + str(manifest.get("id")) + " --write",
             "# Hand-kept: id, version, title, source_systems, scope, sharing, fixtures, review_status, reviewed_by, reviewed_at, and check per trap."]
    for k in HEADER:
        v = manifest.get(k)
        if k == "source_systems" or k == "scope":
            lines.append(f"{k}: {json.dumps(v, ensure_ascii=False)}")
        elif k == "variants":
            lines.append("variants:")
            lines += [f"  {_scalar(name)}: {json.dumps(text, ensure_ascii=False)}" for name, text in (v or {}).items()]
        elif k == "modules":
            lines.append("modules:")
            lines += [f"  - {json.dumps(m, ensure_ascii=False)}" for m in v or []]
        else:
            lines.append(f"{k}: {_scalar(v)}")
    for section in DERIVED:
        lines.append(f"{section}:")
        lines += [f"  - {json.dumps(row, ensure_ascii=False)}" for row in manifest.get(section) or []]
    lines.append("fixtures:")
    lines += [f"  {k}: {_scalar(v)}" for k, v in (manifest.get("fixtures") or {}).items()]
    for k in TAIL[1:]:
        lines.append(f"{k}: {_scalar(manifest.get(k) or '')}")
    return "\n".join(lines) + "\n"


def regenerate(pack: str, current: dict | None = None) -> dict:
    """A manifest for the pack with the derived sections rebuilt from the module files and the hand-kept fields taken
    from `current` (the manifest as it is, or a header for a new pack). A trap's check is kept where the trap still
    exists and is `manual` for a new one."""
    cur = current or {}
    want = derive(pack)
    checks = {t["name"]: t.get("check", "manual") for t in cur.get("traps") or []}
    out = {k: cur.get(k) for k in ("id", "version", "title", "source_systems", "scope", "sharing")}
    out["id"] = pack
    out.setdefault("version", "0.1.0")
    out.update(want)
    out["traps"] = [{**t, "check": checks.get(t["name"], "manual")} for t in want["traps"]]
    out["fixtures"] = cur.get("fixtures") or {}
    out["review_status"] = cur.get("review_status") or "proposed"
    out["reviewed_by"] = cur.get("reviewed_by") or ""
    out["reviewed_at"] = cur.get("reviewed_at") or ""
    return out


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] not in sap_pack.available():
        print(f"usage: python -m fabric_backend.pack_manifest <pack> [--write]   packs: {', '.join(sap_pack.available())}")
        return 2
    pack, write = argv[0], "--write" in argv
    current = load(pack) if path(pack).is_file() else None
    text = render(regenerate(pack, current))
    if write:
        path(pack).write_text(text, encoding="utf-8")
        print(f"wrote {path(pack)}")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
