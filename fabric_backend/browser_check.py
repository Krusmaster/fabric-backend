"""What /check runs in the visitor's browser (Pyodide): the same engine as the 20-minute demo, on files that never leave it.

The page hands the files it was given (name and bytes) or a pasted columns list to `analyze`, which writes the files to
Pyodide's in-memory file system and reads them with the local adapter's own `folder_source` (CSV and .xlsx, the same
code as `fabric-backend demo`), or `pasted_source` for a columns list, or `sample_source` for the synthetic shop. The
plan, the health check and the five states of step 1 come from `demo_app.Session`, unchanged; this module only picks
the parts the page shows and names the rule behind each one. Nothing here does any I/O beyond that temporary folder.

The server serves this package as a zip (`engine_zip`) built from its own files, so the browser runs the exact engine
the hosted service and the CLI run: there is no second implementation to drift.
"""
from __future__ import annotations

import io
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

KINDS = ("sample", "files", "columns")
_RULE = re.compile(r"\brule ([KR]\d|SAP pack|confirmed)\b")
_SHOWN = {"problem", "warning", "question", "info"}            # suggestions are listed apart: they are not something wrong


def _source(kind: str, files: list | None, text: str):
    from .platforms.local import folder_source, pasted_source, sample_source
    if kind == "sample":
        return sample_source(), None
    if kind == "columns":
        return pasted_source(text or ""), None
    folder = Path(tempfile.mkdtemp(prefix="check-"))                # in the browser: Pyodide's memory, nothing on a disk
    for name, data in files or []:
        safe = Path(str(name).replace("\\", "/")).name.strip() or "file"
        (folder / safe).write_bytes(bytes(data))
    try:
        src = folder_source(folder)
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    n = len(files or [])
    src.label = f"{n} file{'s' if n != 1 else ''} read in this browser"
    return src, folder


def analyze(kind: str = "sample", files: list | None = None, text: str = "") -> dict:
    """The page's whole result: the five-state verdict, the map (tables with key and rule, relationships with rule), what
    is wrong or unclear (health findings with the engine's rule and check names), the suggestions, and the source's notes.
    `files` is [(name, bytes)]; a failed read comes back as a verdict too, never as a traceback."""
    from .demo_app import Session, verdict
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}")
    try:
        src, folder = _source(kind, files, text)
    except Exception as e:                                         # noqa: BLE001 - the page shows the verdict instead
        return {"verdict": verdict(None, None, error=f"{type(e).__name__}: {e}"), "source": None, "tables": [],
                "relationships": [], "findings": [], "suggestions": [], "summary": ""}
    try:
        st = Session(src).state()
    finally:
        if folder is not None:
            shutil.rmtree(folder, ignore_errors=True)
        if src.close:
            src.close()
    p = st["plan"]
    findings, suggestions = [], []
    for f in st["health"]["findings"]:
        rules = sorted(set(_RULE.findall(f.get("saw", "") + " " + f.get("title", ""))))
        item = {"severity": f["severity"], "check": f["kind"], "rules": rules, "table": f["table"], "title": f["title"],
                "saw": f["saw"], "means": f["means"], "next": f.get("next_text", ""), "sql": f.get("next", {}).get("sql", "")}
        (findings if f["severity"] in _SHOWN else suggestions).append(item)
    return {"verdict": st["verdict"],
            "source": {"kind": src.kind, "label": src.label, "has_data": src.has_data, "notes": st["source"]["notes"]},
            "summary": p["summary"], "rules": p["rules"],
            "tables": [{"name": t["name"], "key": t["key"], "key_rule": t["key_rule"],
                        "columns": [c["name"] for c in t["columns"]]} for t in p["tables"]],
            "relationships": [{k: r[k] for k in ("source", "source_cols", "target", "target_cols", "rule")} for r in p["relationships"]],
            "ambiguous": p["ambiguous"], "health": st["health"]["summary"], "findings": findings, "suggestions": suggestions}


# ------------------------------------------------------------------ the engine as one download ---------------------
# Everything under fabric_backend/ that is Python or a knowledge pack, and nothing else (no templates, no static files,
# no fonts). Built once from the files this server runs.

_ZIP: bytes | None = None


def engine_zip() -> bytes:
    global _ZIP
    if _ZIP is None:
        root = Path(__file__).resolve().parent
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            for p in sorted(root.rglob("*")):
                rel = p.relative_to(root)
                if "__pycache__" in rel.parts or rel.parts[0] in ("static", "page_templates") or not p.is_file():
                    continue
                if p.suffix == ".py" or (rel.parts[0] == "packs" and p.suffix == ".json"):
                    z.writestr(zipfile.ZipInfo(f"fabric_backend/{rel.as_posix()}", (2026, 1, 1, 0, 0, 0)), p.read_bytes(),
                               zipfile.ZIP_DEFLATED)
        _ZIP = buf.getvalue()
    return _ZIP
