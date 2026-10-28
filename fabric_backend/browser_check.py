"""What /check runs in the visitor's browser (Pyodide): the same engine as the 20-minute demo, on files that never leave it.

The page hands the files it was given (name and bytes), a pasted columns list, or the name of one of three synthetic
examples to `analyze`. Files are written to Pyodide's in-memory file system and read with the local adapter's own
`folder_source` (CSV and .xlsx, the same code as `fabric-backend demo`); a columns list goes through `pasted_source`.
Then the engine's steps run one after the other, and each one is reported to `emit` as it finishes, with what it found
and how long it took: the plan (keys K0–K5, relationships R0–R4), validate_plan's counts, suggest_relationships, and
the findings and five states of step 1 from `demo_app.Session`, unchanged. The page draws those events as they come;
nothing on it is a made-up progress line.

The server serves this package as a zip (`engine_zip`) built from its own files, so the browser runs the exact engine
the hosted service and the CLI run: there is no second implementation to drift.
"""
from __future__ import annotations

import io
import re
import shutil
import sqlite3
import tempfile
import time
import zipfile
from pathlib import Path

KINDS = ("sample", "sap", "crm", "files", "columns")
_RULE = re.compile(r"\brule ([KR]\d|SAP pack|confirmed)\b")
_SHOWN = {"problem", "warning", "question", "info"}            # suggestions are listed apart: they are not something wrong


# ------------------------------------------------------------------ the Salesforce + ERP example --------------------
# Synthetic, like the shop: Salesforce-shaped objects (Account, Contact, Opportunity) beside an ERP's customers and
# sales orders. No name links the two systems: Account.ERP_Customer_No__c holds the ERP's customer_no, which only the
# rows show (suggest_relationships). Planted: a contact whose account does not exist, an order whose customer does not,
# an account not linked yet, and order_total on the order header that a join with its lines repeats.

def crm_tables() -> dict[str, tuple[list[str], list[tuple]]]:
    t: dict[str, tuple[list[str], list[tuple]]] = {}
    t["Account"] = (["Id", "Name", "Industry", "ERP_Customer_No__c"],
                    [(f"001A{i:02d}", f"Account {i:02d}", ["Software", "Retail", "Health", "Finance"][i % 4],
                      None if i == 8 else f"C{1000 + i}") for i in range(1, 9)])
    t["Contact"] = (["Id", "AccountId", "FirstName", "LastName", "Email"],
                    [(f"003C{i:02d}", "001A99" if i == 11 else f"001A{i % 8 + 1:02d}", f"First{i:02d}", f"Last{i:02d}",
                      f"contact{i:02d}@example.invalid") for i in range(1, 13)])
    t["Opportunity"] = (["Id", "AccountId", "Name", "StageName", "Amount", "CloseDate"],
                        [(f"006O{i:02d}", f"001A{i % 8 + 1:02d}", f"Opportunity {i:02d}", ["Prospecting", "Negotiation", "Closed Won"][i % 3],
                          1000 * i, f"2026-0{i % 9 + 1}-15") for i in range(1, 11)])
    t["customers"] = (["customer_no", "name", "country"], [(f"C{1000 + i}", f"Customer {i:02d}", "SE" if i % 2 else "NO") for i in range(1, 11)])
    orders = [(f"SO{5000 + i}", "C1999" if i == 12 else f"C{1000 + i % 10 + 1}", f"2026-0{i % 9 + 1}-01") for i in range(1, 13)]
    lines = [(o[0], n, f"Licence tier {n}", 100 * n) for o in orders for n in range(1, 3 + int(o[0][-1]) % 2)]
    t["sales_orders"] = (["sales_order_no", "customer_no", "order_date", "order_total"],
                         [o + (sum(x[3] for x in lines if x[0] == o[0]),) for o in orders])
    t["sales_order_lines"] = (["sales_order_no", "line_no", "description", "line_amount"], lines)
    return t


def _sqlite_source(kind: str, label: str, schema_name: str, tables: dict, note: str):
    """A Source over rows held here: one in-memory SQLite database, like folder_source builds from files."""
    from .platforms.local import Source, _sqlite_execute
    from .schema import Schema
    con = sqlite3.connect(":memory:", check_same_thread=False)
    con.execute(f"ATTACH DATABASE ':memory:' AS [{schema_name}]")
    rows = []
    for name, (cols, data) in tables.items():
        types = ["int" if all(isinstance(r[i], int) for r in data if r[i] is not None) else "string" for i in range(len(cols))]
        con.execute(f"CREATE TABLE [{schema_name}].[{name}] (" + ", ".join(f"[{c}] {ty.upper()}" for c, ty in zip(cols, types)) + ")")
        con.executemany(f"INSERT INTO [{schema_name}].[{name}] VALUES ({','.join('?' * len(cols))})", data)
        rows += [{"table_schema": schema_name, "table_name": name, "column_name": c, "data_type": ty, "ordinal_position": i + 1}
                 for i, (c, ty) in enumerate(zip(cols, types))]
    return Source(kind, label, Schema.from_information_schema(rows, schema=schema_name), _sqlite_execute(con), "sqlite", [note], con.close)


def _source(kind: str, files: list | None, text: str):
    from .platforms.local import folder_source, pasted_source, sample_source
    if kind == "sample":
        return sample_source(), None
    if kind == "sap":
        from . import sap_demo
        t = {name: (cols, rows) for name, (cols, _types, rows) in sap_demo.tables().items()}
        return _sqlite_source("folder", "Synthetic SAP sales tables (fabric_backend.sap_demo)", "sap", {sap_demo.PREFIX + n.lower(): v for n, v in t.items()},
                              "Synthetic SAP-shaped rows from fabric_backend.sap_demo: invented customers and materials, no SAP system."), None
    if kind == "crm":
        return _sqlite_source("folder", "Synthetic Salesforce + ERP tables", "crm", crm_tables(),
                              "Synthetic Salesforce-shaped objects and ERP tables: invented accounts, contacts and orders, no real company."), None
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


def _finding(f: dict) -> dict:
    return {"severity": f["severity"], "check": f["kind"], "rules": sorted(set(_RULE.findall(f.get("saw", "") + " " + f.get("title", "")))),
            "table": f["table"], "title": f["title"], "saw": f["saw"], "means": f["means"], "next": f.get("next_text", ""),
            "sql": f.get("next", {}).get("sql", ""), "link": _link(f)}


def _link(f: dict) -> dict | None:
    """The relationship a finding is about, so the map can mark it: an orphan, a suggestion, an ambiguous column."""
    c = f.get("next", {}).get("confirmed")
    if c:
        return {"source": c["source"], "target": c["target"], "source_cols": c["source_cols"]}
    m = re.match(r"rel:(.+?)\.(.+?)>(.+)$", f.get("id", ""))
    return {"source": m.group(1), "target": m.group(3), "source_cols": m.group(2).split("+")} if m else None


def analyze(kind: str = "sample", files: list | None = None, text: str = "", emit=None) -> dict:
    """The engine's steps on one source, each reported to `emit(event)` when it is done: {"step", "title", "detail",
    "ms", ...data}. Returns the whole result (the last event's content): the five-state verdict, the map, what is wrong
    or unclear with the engine's rule and check names, and the suggestions. `files` is [(name, bytes)]; a failed read
    comes back as a verdict too, never as a traceback."""
    from . import evidence, graphs
    from .demo_app import Session, verdict
    from .infer import plan
    send = emit or (lambda e: None)

    def step(name: str, title: str, t0: float, detail: str, **data) -> None:
        send({"step": name, "title": title, "detail": detail, "ms": round((time.perf_counter() - t0) * 1000), **data})

    if kind not in KINDS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}")
    t = time.perf_counter()
    try:
        src, folder = _source(kind, files, text)
    except Exception as e:                                         # noqa: BLE001 - the page shows the verdict instead
        out = {"verdict": verdict(None, None, error=f"{type(e).__name__}: {e}"), "source": None, "tables": [],
               "relationships": [], "findings": [], "suggestions": [], "summary": "", "health": ""}
        step("read", "Read the input", t, out["verdict"]["headline"]["title"] + " " + out["verdict"]["headline"]["text"], result=out)
        return out
    try:
        step("read", "Read the input", t, f"{src.label}: {len(src.schema)} tables" + ("" if src.has_data else ", names only"),
             notes=src.notes[:20])
        t = time.perf_counter()
        p = plan(src.schema)
        tables = [{"name": x.name, "key": p.keys.get(x.name, ([], ""))[0], "key_rule": p.keys.get(x.name, ([], "K3"))[1] or "K3",
                   "columns": x.column_names} for x in p.schema]
        rels = [{"source": r.source, "source_cols": r.source_cols, "target": r.target, "target_cols": r.target_cols, "rule": r.rule}
                for r in p.relationships]
        ms_plan = round((time.perf_counter() - t) * 1000)
        by_rule = lambda items, key: ", ".join(f"{k} {n}" for k, n in sorted(_count(items, key).items()))
        send({"step": "keys", "title": "Keys (rules K0–K5)", "ms": ms_plan, "tables": tables,
              "detail": f"{len(p.keys)} of {len(tables)} tables have a key ({by_rule([x for x in tables if x['key']], 'key_rule') or 'none'})"
                        + (f"; no key: {', '.join(p.keyless[:6])}" if p.keyless else "")})
        send({"step": "relationships", "title": "Relationships (rules R0–R4)", "ms": 0, "relationships": rels, "ambiguous": p.ambiguous,
              "detail": f"{len(rels)} relationships ({by_rule(rels, 'rule') or 'none'})" + (f"; {len(p.ambiguous)} ambiguous column(s), not linked" if p.ambiguous else "")
                        + " — keys and relationships come from one plan() call"})
        validation = suggestions = None
        if src.has_data:
            t = time.perf_counter()
            try:
                validation = evidence.validate(p, src.execute)
                bad = [{"source": r["source"], "target": r["target"], "source_cols": r["columns"], "orphans": r["orphans"]}
                       for r in validation["relationships"] if not r["verdict"].startswith("holds")]
                step("validate", "validate_plan: counted in the rows", t, validation["summary"]
                     + (f"; {len(validation['amount_levels']['findings'])} amount(s) repeated by a join" if validation.get("amount_levels", {}).get("findings") else ""),
                     orphans=bad)
            except Exception as e:                                 # noqa: BLE001 - the map still shows without counts
                step("validate", "validate_plan: counted in the rows", t, f"could not run: {type(e).__name__}: {e}")
            t = time.perf_counter()
            try:
                suggestions = graphs.suggest(p, src.execute, check=15)
            except Exception as e:                                 # noqa: BLE001
                step("suggest", "suggest_relationships: values checked", t, f"could not run: {type(e).__name__}: {e}")
        else:
            t = time.perf_counter()
            suggestions = graphs.suggest(p, None)
        if suggestions is not None:
            cands = [{"source": s["source"], "target": s["target"], "source_cols": s["source_cols"]} for s in suggestions.get("candidates", [])
                     if (s.get("evidence") or {}).get("inclusion") is not None and s["evidence"]["inclusion"] >= 0.9]
            step("suggest", "suggest_relationships: values checked" if src.has_data else "suggest_relationships: names only", t,
                 f"{len(suggestions.get('candidates', []))} candidate column(s) ranked" + (f", {len(cands)} with 90% or more of their values in the target's key" if src.has_data else ""),
                 suggested=cands)
        t = time.perf_counter()
        session = Session(src)
        found = session.findings(p, validation, suggestions)
        findings = [_finding(f) for f in found if f["severity"] in _SHOWN]
        sugg = [_finding(f) for f in found if f["severity"] not in _SHOWN]
        out = {"verdict": verdict(src, p, validation),
               "source": {"kind": src.kind, "label": src.label, "has_data": src.has_data, "notes": src.notes},
               "summary": p.summary() if hasattr(p, "summary") else "", "tables": tables, "relationships": rels, "ambiguous": p.ambiguous,
               "health": validation["summary"] if validation else "No rows to check: a columns list gives the plan only.",
               "findings": findings, "suggestions": sugg}
        step("findings", "Findings and the five states", t, f"{len(findings)} wrong or unclear, {len(sugg)} to decide on; {out['verdict']['headline']['title']}",
             result=out)
        return out
    finally:
        if folder is not None:
            shutil.rmtree(folder, ignore_errors=True)
        if src.close:
            src.close()


def _count(items: list[dict], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for x in items:
        out[x[key]] = out.get(x[key], 0) + 1
    return out


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
