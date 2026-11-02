"""What /check runs in the visitor's browser (Pyodide): the same engine as the 20-minute demo, on files that never leave it.

The page hands the files it was given (name and bytes), a pasted columns list, or the name of one of four synthetic
examples to `analyze` (the shop, SAP, Salesforce + ERP, and since n78 Younium + Salesforce subscription billing). Files
are written to Pyodide's in-memory file system and read with the local adapter's own `folder_source` (CSV and .xlsx,
the same code as `fabric-backend demo`); a columns list goes through `pasted_source`. Then the engine's steps run one after the other, and each one is reported to `emit` as it finishes, with what it found
and how long it took: the plan (keys K0–K5, relationships R0–R4), validate_plan's counts, suggest_relationships, and
the findings and five states of step 1 from `demo_app.Session`, unchanged. The page draws those events as they come;
nothing on it is a made-up progress line.

The server serves this package as a zip (`engine_zip`) built from its own files, so the browser runs the exact engine
the hosted service and the CLI run: there is no second implementation to drift.

n73: one example row runs through everything the page says about a total that doubles. For each amount finding the
engine reads one header row from the rows (the one with the most lines; `_amount_examples`): its key, its amount, how
many line rows point at it and what a join counts it as. The finding's text names it, Onto's answer, the Power BI
preview and the domain's data contract (a custom property) repeat it, and none of them computes a number of its own.
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

KINDS = ("sample", "sap", "crm", "billing", "files", "columns")
_RULE = re.compile(r"\brule ([KR]\d|confirmed|[A-Z][A-Za-z0-9 +]*? pack)\b")     # a pack by its own name (n79)
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
    if kind == "billing":                                         # n78: the engine reads the Younium + Salesforce pack
        from . import younium_demo
        return _sqlite_source("folder", "Synthetic Younium + Salesforce tables (fabric_backend.younium_demo)", "billing", younium_demo.rows_for_check(),
                              "Synthetic Younium- and Salesforce-shaped rows from fabric_backend.younium_demo: invented accounts and invoices, no tenant or org."), None
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


def _finding(f: dict, validation: dict | None = None, has_data: bool = True) -> dict:
    return {"severity": f["severity"], "check": f["kind"], "rules": sorted(set(_RULE.findall(f.get("saw", "") + " " + f.get("title", "")))),
            "table": f["table"], "title": f["title"], "saw": f["saw"], "means": f["means"], "next": f.get("next_text", ""),
            "sql": f.get("next", {}).get("sql", ""), "link": _link(f), "amount": f.get("amount"),
            "checked": _checked(f, validation, has_data)}


def _n(n, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def _checked(f: dict, validation: dict | None, has_data: bool) -> str:
    """n75: how much of the rows the finding's check read, in the finding's own words, from the counts the engine
    returned (validate_plan's per key and per relationship, suggest_relationships' per candidate, the keyless count).
    Every count is over the whole table at the moment of the run; nothing here is assumed or hard-coded."""
    if not has_data:
        return "Not counted: a list of columns has no rows, so this rests on the names alone."
    v = validation or {}
    rows_of = {k["table"]: k["rows"] for k in v.get("keys", [])}
    kind, table = f["kind"], f["table"]

    def whole(source: str, with_value) -> str:
        n = rows_of.get(source)
        if n is not None:
            return f"Checked on all {_n(n, 'row')} of {source}: {with_value} with a value."
        return f"Checked on every row of {source} with a value: {with_value}."
    if kind == "key":
        k = next((k for k in v.get("keys", []) if k["table"] == table), None)
        return f"Checked on all {_n(k['rows'], 'row')} of {table}." if k else "Not counted."
    if kind == "relationship":
        link = _link(f) or {}
        r = next((r for r in v.get("relationships", []) if r["source"] == link.get("source") and r["target"] == link.get("target")
                  and list(r["columns"]) == list(link.get("source_cols", []))), None)
        return whole(r["source"], r["rows_with_value"]) if r else "Not counted."
    if kind == "amount_level":
        a = f.get("amount") or {}
        rp = a.get("rows_per_header")
        if not isinstance(rp, dict):
            return "Not counted: the two sums could not be run on these rows."
        if not a.get("on_map"):
            return (f"Counted on all rows of the example's two tables: {_n(rp['headers'], a['header'] + ' row')} with "
                    f"{_n(rp['max_lines'], a['line'] + ' row')}.")
        return (f"Counted on all rows of {a['header']} and {a['line']}: {_n(rp['headers'], a['header'] + ' row')} with {a['line']} rows, "
                f"at most {rp['max_lines']} each.")
    if kind == "suggestion":
        c = f.get("counted")
        if not c:
            return "Counted with the plan's relationships above once accepted."
        link = _link(f) or {}
        return whole(link.get("source", table), c["rows_with_value"])
    if kind == "ambiguous":
        return "Not counted: the name fits more than one table, and the engine does not count between targets; your decision is applied first."
    if kind == "composite_key":
        return "Not counted yet: accept it and the check counts whether it is unique."
    if kind in ("key_candidate", "keyless"):
        c = f.get("counted") or {}
        if c.get("rows") is not None:
            return f"Checked on all {_n(c['rows'], 'row')} of {table}: the first {_n(c['columns'], 'column')}."
        return "Not counted."
    return "Not counted."


def _coverage(p, validation: dict | None, has_data: bool) -> dict:
    """n75: how much of the plan the run counted in the rows, for the line under the state: every key and relationship
    (validate_plan's default is enough for most schemas) or how many of them, from the result itself."""
    keys, rels = len(p.keys), len(p.relationships) + len(getattr(p, "extended", []))
    if not has_data:
        return {"counted": False, "complete": False, "keys": 0, "keys_total": keys, "relationships": 0, "relationships_total": rels,
                "text": "Nothing counted: a list of columns has no rows, so the plan is by names alone."}
    if validation is None:
        return {"counted": False, "complete": False, "keys": 0, "keys_total": keys, "relationships": 0, "relationships_total": rels,
                "text": "Nothing counted: the check could not run on these rows (How the engine got here says why)."}
    ck, cr = len(validation.get("keys", [])), len(validation.get("relationships", []))
    complete = ck == keys and cr == rels
    text = (f"Counted in the rows: all {_n(ck, 'key')} and all {_n(cr, 'relationship')} of the plan, each over the whole table."
            if complete else f"Counted in the rows: {ck} of {_n(keys, 'key')} and {cr} of {_n(rels, 'relationship')}; the rest were not counted in this run.")
    return {"counted": True, "complete": complete, "keys": ck, "keys_total": keys, "relationships": cr, "relationships_total": rels, "text": text}


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
        tables = [{"name": x.name, "key": p.keys.get(x.name, ([], ""))[0], "key_rule": p.label(p.keys.get(x.name, ([], "K3"))[1] or "K3"),
                   "columns": x.column_names} for x in p.schema]
        rels = [{"source": r.source, "source_cols": r.source_cols, "target": r.target, "target_cols": r.target_cols, "rule": p.label(r.rule)}
                for r in p.relationships]                                  # the page shows the rule: a pack by its own name (n79)
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
        examples = _amount_examples(p, src, validation)           # n73: one header row per total that doubles
        notes: dict[str, list[dict]] = {}
        for (header, line, column), ex in examples.items():
            lv = next((f for f in ((validation or {}).get("amount_levels") or {}).get("findings", [])
                       if (f["header"], f["line"], f["amount_columns"][0]) == (header, line, column)), None)
            synthetic = lv is None and src.kind == "sample"
            wrong = right = None
            if lv is not None:
                from . import amounts
                ba = amounts.before_after(p.schema.schema, lv, src.execute)
                wrong, right = (ba or {}).get("summed_over_lines"), (ba or {}).get("summed_per_header")
            elif synthetic:
                wrong, right = ex["repeated"], ex["amount"]      # one order: the join's sum is its amount once per line
            line_columns = lv["line_columns"] if lv is not None else ["order_id"]
            note = _amount_note(header, line, line_columns, column, ex, wrong, right, synthetic)
            for table in {header, line}:
                notes.setdefault(table, []).append(note)
        try:                                                       # n63: domains.draft, the same call domain_draft makes
            dom = _domains(p, src, validation, notes)
            step("domains", "domain_draft: proposed domains", t, f"{len(dom['domains'])} domain(s), {len(dom['interfaces'])} interface(s) between them"
                 + (f", {len(dom['unassigned'])} table(s) unassigned" if dom["unassigned"] else ""), domains=dom)
        except Exception as e:                                     # noqa: BLE001 - the rest of the result still shows
            dom = None
            step("domains", "domain_draft: proposed domains", t, f"could not run: {type(e).__name__}: {e}")
        t = time.perf_counter()
        session = Session(src)
        found = session.findings(p, validation, suggestions)
        findings = [_finding(f, validation, src.has_data) for f in found if f["severity"] in _SHOWN]
        sugg = [_finding(f, validation, src.has_data) for f in found if f["severity"] not in _SHOWN]
        for f in findings:                                         # n73: the finding names the example row it is about
            a = f.get("amount")
            ex = examples.get((a["header"], a["line"], a["column"])) if a else None
            if ex:
                a["example"] = ex
                f["saw"] += (f" For example {ex['key']} {ex['id']}: {_amount_words(ex['amount'])} on its {a['header']} row; "
                             f"{_rows(ex['lines'], a['line'])} point at it, so the join counts it {_times(ex['lines'])}: {_amount_words(ex['repeated'])}.")
        out = {"verdict": verdict(src, p, validation),
               "source": {"kind": src.kind, "label": src.label, "has_data": src.has_data, "notes": src.notes},
               "summary": p.summary() if hasattr(p, "summary") else "", "tables": tables, "relationships": rels, "ambiguous": p.ambiguous,
               "health": validation["summary"] if validation else "No rows to check: a columns list gives the plan only.",
               "findings": findings, "suggestions": sugg, "domains": dom, "coverage": _coverage(p, validation, src.has_data),
               "evidence_report": _evidence_report(p, src, validation, kind), "ontology_rdfxml": _ontology_rdfxml(p, src, kind)}
        step("findings", "Findings and the five states", t, f"{len(findings)} wrong or unclear, {len(sugg)} to decide on; {out['verdict']['headline']['title']}",
             result=out)
        return out
    finally:
        if folder is not None:
            shutil.rmtree(folder, ignore_errors=True)
        if src.close:
            src.close()


NAMES = {"sample": "shop", "sap": "sap_sales", "crm": "crm_erp", "billing": "subscription_billing"}   # the downloads' file names


def _evidence_report(p, src, validation: dict | None, kind: str) -> dict:
    """n79: the evidence report of this run as a Markdown file for the page to save (evidence_report.py): the plan and
    validate_plan's counts only, so none of the example rows the findings quote is in it."""
    from . import evidence_report, tool_status as ts
    base = NAMES.get(kind) or re.sub(r"\W+", "_", getattr(src.schema, "schema", "") or "data")
    rep = evidence_report.report(p, validation, source=src.label)
    return {"name": f"{base}_evidence_report.md", "markdown": evidence_report.markdown(rep), "status": ts.EVIDENCE_REPORT,
            "summary": rep["summary"]}


def _ontology_rdfxml(p, src, kind: str) -> dict | None:
    """n80: the plan as RDF/XML for Microsoft's Ontology Playground (ontology.ontology_rdfxml), a file for the page to
    save: entity types, their columns and the relationships with the rule in each description, no rows. None when there
    is nothing to write or the file would pass the Playground's 8 MiB."""
    from . import ontology, tool_status as ts
    base = NAMES.get(kind) or re.sub(r"\W+", "_", getattr(src.schema, "schema", "") or "data")
    try:
        xml = ontology.ontology_rdfxml(p, base, getattr(src.schema, "schema", "") or "dbo")
    except ValueError:
        return None
    return {"name": f"{base}_ontology.rdf", "xml": xml, "status": ts.ONTOLOGY_RDFXML,
            "entity_types": xml.count("<owl:Class "), "relationship_types": xml.count("<owl:ObjectProperty ")}


def _amount_examples(p, src, validation: dict | None) -> dict[tuple, dict]:
    """n73: for each header amount a join would repeat, one header row read from the rows, keyed by (header, line,
    column): {"key", "id", "amount", "lines", "repeated"}, the row with the most line rows (ties: the smallest key). On
    the synthetic shop the example of seed.AMOUNT_DEMO (the finding demo_app adds) is read the same way, from its own
    in-memory tables, under the key ("orders", "order_lines", "order_amount")."""
    from . import amounts
    out: dict[tuple, dict] = {}
    if not src.has_data:
        return out
    levels = (validation or {}).get("amount_levels") or amounts.check(p)
    for f in levels["findings"][:5]:
        ex = _one_header_row(p.schema.schema, f, src.execute)
        if ex:
            out[(f["header"], f["line"], f["amount_columns"][0])] = ex
    if src.kind == "sample":                                       # the same tables amounts.demo() runs, typed as its DDL says
        from .dialects import sqlite_sql
        from .infer import plan
        from .schema import Column, Schema, Table
        from .seed import AMOUNT_DEMO
        con = sqlite3.connect(":memory:")
        con.execute("ATTACH DATABASE ':memory:' AS demo")
        schema = Schema(schema="demo")
        for name, (ddl, data) in AMOUNT_DEMO.items():
            con.execute(f"CREATE TABLE demo.[{name}] ({ddl})")
            con.executemany(f"INSERT INTO demo.[{name}] VALUES ({','.join('?' * len(data[0]))})", data)
            schema.tables[name] = Table(name, [Column(c.split()[0], c.split()[1].lower()) for c in ddl.split(", ")], schema="demo")

        def execute(sql: str):
            cur = con.execute(sqlite_sql(sql))
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
        try:
            for f in amounts.check(plan(schema))["findings"][:1]:
                ex = _one_header_row("demo", f, execute)
                if ex:
                    out[(f["header"], f["line"], f["amount_columns"][0])] = ex
        finally:
            con.close()
    return out


def _one_header_row(schema: str, f: dict, execute) -> dict | None:
    """The header row a join repeats most: key, amount, the number of line rows and the amount summed over them."""
    from .dialects import of
    d = of(execute)
    col = f["amount_columns"][0]
    on = " AND ".join(f"l.{d.quote(a)} = h.{d.quote(b)}" for a, b in zip(f["line_columns"], f["header_columns"]))
    keys = ", ".join(f"h.{d.quote(k)}" for k in f["header_columns"])
    sql = d.select(f"{keys}, h.{d.quote(col)} AS amount_value, {d.count}(*) AS line_rows, SUM(h.{d.quote(col)}) AS repeated_value",
                   f" FROM {d.table(schema, f['line'])} AS l JOIN {d.table(schema, f['header'])} AS h ON {on} "
                   f"GROUP BY {keys}, h.{d.quote(col)} ORDER BY {d.count}(*) DESC, {keys}", 1)
    try:
        rows = list(execute(sql))
    except Exception:                                              # noqa: BLE001 - the finding stands without an example
        return None
    if not rows or rows[0].get("amount_value") is None:
        return None
    r = rows[0]
    num = lambda v: int(float(v)) if float(v).is_integer() else round(float(v), 2)
    return {"key": "+".join(f["header_columns"]), "id": " + ".join(str(r[k]) for k in f["header_columns"]),
            "amount": num(r["amount_value"]), "lines": int(r["line_rows"]), "repeated": num(r["repeated_value"])}


def _amount_words(v) -> str:
    """1000.0 as 1 000, the way demo_app tells the example; 5.9 keeps its decimals (5.90)."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    return (f"{f:,.0f}" if f.is_integer() else f"{f:,.2f}").replace(",", " ")


def _times(n: int) -> str:
    return "once" if n == 1 else "twice" if n == 2 else f"{n} times"


def _rows(n: int, table: str) -> str:
    return f"{n} {table} row" + ("" if n == 1 else "s")


def _amount_note(header: str, line: str, line_columns: list, column: str, ex: dict, wrong, right, synthetic: bool) -> dict:
    """The contract's custom property for a total that doubles: what to sum where, and the example row counted in the rows."""
    return {"property": f"amountLevel.{header}.{column}",
            "value": f"sum {header}.{column} once per {header} row, never over {line} rows",
            "description": (f"{header}.{column} is an amount on {header}, and {line} rows point at it ({line}.{'+'.join(line_columns)} → {header}); "
                            f"a join counts it once per line. Counted in the rows: {ex['key']} {ex['id']} is {_amount_words(ex['amount'])} on its "
                            f"{header} row and {_rows(ex['lines'], line)} point at it, so the join counts it {_times(ex['lines'])} "
                            f"({_amount_words(ex['repeated'])}); over all rows {_amount_words(wrong)} against {_amount_words(right)} (amount_level)."
                            + (" A synthetic example beside these tables (fabric_backend.seed.AMOUNT_DEMO): its orders and order_lines are not the shop's."
                               if synthetic else ""))}


def _domains(p, src, validation: dict | None, notes: dict[str, list[dict]] | None = None) -> dict:
    """domains.draft on the plan, with each domain's contract (ODCS YAML) and the checks validate_plan made on its
    tables and on the relationships they hold."""
    from . import domains, tool_status as ts
    schema = getattr(src.schema, "schema", None) or "dbo"
    # n73: the amount notes go to every domain that holds the header or the line table (by name)
    def extra(d):                                          # once per note, even when both its tables are in the domain
        seen, out = set(), []
        for t in d["tables"]:
            for n in (notes or {}).get(t, []):
                if n["property"] not in seen:
                    seen.add(n["property"])
                    out.append(n)
        return out
    out = domains.draft(p, schema, src.label, validation, extra=extra)
    out["status"] = ts.label("domain_draft")             # the status word the page puts on the contract download
    for i in out["interfaces"]:                          # the panel prints the interface's rule: the pack by its own name (n79)
        i["rule"] = p.label(i["rule"])
    for d in out["domains"]:
        mine = set(d["tables"])
        d["keys"] = {t: list(p.keys.get(t, ([], ""))[0]) for t in d["tables"]}
        d["relationships"] = [{"source": r.source, "source_cols": r.source_cols, "target": r.target, "target_cols": r.target_cols,
                               "rule": p.label(r.rule)} for r in p.relationships if r.source in mine and r.target in mine]
        d["checks"] = ([{"what": f"key of {k['table']}", "verdict": k["verdict"]} for k in (validation or {}).get("keys", []) if k.get("table") in mine]
                       + [{"what": f"{r['source']}.{'+'.join(r['columns'])} → {r['target']}", "verdict": r["verdict"]}
                          for r in (validation or {}).get("relationships", []) if r.get("source") in mine])
    return out


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
