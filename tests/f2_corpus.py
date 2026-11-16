"""The regression corpus (round F2, SCOPE-REVIEW section 6, mechanism 5).

Each corpus is a schema with rows in an in-memory SQLite database and a ground truth (the keys and links the source
declares, or the ones its generator was written to hold). `run(name)` plans it three ways and scores each against the
truth:

  names    plan(schema): names only, as tests/test_inference_quality.py does
  before   plan(schema, execute=…): names and R5 over the rows, as main planned before round F2 (commit 8066dd0)
  after    plan(schema, execute=…, profile=True): this round's row profile (fabric_backend/propose.py)

and it checks the `after` plan against the rows (evidence.validate). tests/test_f2_corpus.py asserts the scores, the
plan and the row results exactly against tests/corpus/<name>.json, and that docs/SCORES.md and docs/scores.json are
what `python tests/f2_corpus.py --write-docs` writes.

  python tests/f2_corpus.py                  print the score table
  python tests/f2_corpus.py --write-docs     write docs/SCORES.md and docs/scores.json from the expected files
  python tests/f2_corpus.py --write-expected write tests/corpus/<name>.json from what the engine does now

--write-expected is for a conscious change of a rule: read the diff of every file it changes before committing it. A
number is never changed to make a test pass.

The rows are synthetic everywhere. For AdventureWorks the tables, columns, keys and foreign keys are the ones
Microsoft's script declares (tests/fixtures/schemas/adventureworks.json); the rows are generated here from those
declared constraints, because the sample's own rows are not in this repository. The scores therefore say what the
rules do with rows that follow the declared constraints; they are not a measurement on the sample's own rows.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fabric_backend import evidence, propose, sap_sample                    # noqa: E402
from fabric_backend.infer import plan                                       # noqa: E402
from fabric_backend.platforms.local import _sqlite_execute, sample_source   # noqa: E402
from fabric_backend.schema import Schema                                    # noqa: E402

CORPUS = Path(__file__).parent / "corpus"
FIXTURES = Path(__file__).parent / "fixtures" / "schemas"
BEFORE_COMMIT = "8066dd0"
ORDER = ("adventureworks", "shop", "sap_sd", "sap_mm", "sap_renamed", "nordic_erp", "bc_like")
NOT_PRESENT = {"sap_cds": "n230's CDS-shaped sample (seed(spark, schema='sap_cds')) is not on main at the time of this round; "
                          "it is added here when it is"}


class Rng:
    """A small generator of its own, so the rows are the same on every Python version."""

    def __init__(self, seed: int):
        self.s = (seed * 2654435761 + 1) % 2**32

    def below(self, n: int) -> int:
        self.s = (self.s * 1664525 + 1013904223) % 2**32
        return (self.s >> 8) % n

    def pick(self, seq):
        return seq[self.below(len(seq))]


# ------------------------------------------------------------------ SQLite ------------------------------------------

def _affinity(sql_type: str) -> str:
    t = sql_type.lower()
    if propose.type_class(t) == "integer" or t == "bit":
        return "INTEGER"
    if any(w in t for w in ("decimal", "money", "float", "double", "numeric", "real")):
        return "REAL"
    return "TEXT"


def database(schema_name: str, tables: dict[str, list[tuple[str, str]]], rows: dict[str, list[tuple]]):
    """(Schema, execute, close): the tables in an in-memory SQLite database, read with the engine's T-SQL."""
    con = sqlite3.connect(":memory:", check_same_thread=False)
    con.execute(f"ATTACH DATABASE ':memory:' AS [{schema_name}]")
    info = []
    for name, cols in tables.items():
        con.execute(f"CREATE TABLE [{schema_name}].[{name}] ({', '.join(f'[{c}] {_affinity(t)}' for c, t in cols)})")
        if rows.get(name):
            con.executemany(f"INSERT INTO [{schema_name}].[{name}] VALUES ({','.join('?' * len(cols))})", rows[name])
        info += [(schema_name, name, c, t, i) for i, (c, t) in enumerate(cols, 1)]
    return Schema.from_information_schema(info, schema=schema_name), _sqlite_execute(con), con.close


# ------------------------------------------------------------------ AdventureWorks ----------------------------------

_AW_TYPES = {"name": "nvarchar", "sysname": "nvarchar", "accountnumber": "nvarchar", "ordernumber": "nvarchar", "phone": "nvarchar",
             "flag": "bit", "namestyle": "bit", "computed": "nvarchar"}
_AW_UNIQUE = ("name", "rowguid", "loginid", "nationalidnumber", "accountnumber")     # columns with a unique index in the script


def adventureworks(seed: int = 11):
    """The AdventureWorks tables with rows generated from the declared keys and foreign keys.

    Keys: a key column that no foreign key covers is an identity (1, 2, 3 …) or, for a date or a text, a value per
    row; a key column a foreign key covers takes the target's key values. A table whose whole key is a foreign key (a
    subtype: Employee in Person in BusinessEntity) takes a slice of its parent's keys from the start, and two subtypes
    of one parent take slices that do not overlap. Foreign key columns outside the key take a target key at random, 8 in
    100 are NULL. Other whole numbers are small (1 to 50), so they fit into any dense identity: the profile has to
    leave them alone. Columns the script gives a unique index (Name, rowguid, LoginID, …) are unique."""
    fx = json.loads((FIXTURES / "adventureworks.json").read_text(encoding="utf-8"))
    rnd = Rng(seed)
    tabs = {t["name"]: t for t in fx["tables"]}
    types = {t["name"]: [(c, _AW_TYPES.get(ty, ty)) for c, ty in t["columns"]] for t in fx["tables"]}
    subtype_parent = {}
    for t in fx["tables"]:
        for f in t["foreign_keys"]:
            if t["primary_key"] and sorted(f["columns"]) == sorted(t["primary_key"]) and f["ref_table"] != t["name"]:
                subtype_parent[t["name"]] = f
    children: dict[str, list[str]] = {}
    for c, f in subtype_parent.items():
        children.setdefault(f["ref_table"], []).append(c)
    keys: dict[str, list[tuple]] = {}

    def size(t: dict) -> int:
        if t["name"] in children:
            return 600
        return 60 if not t["foreign_keys"] else 300

    def key_rows(name: str) -> list[tuple]:
        if name in keys:
            return keys[name]
        t = tabs[name]
        pk = t["primary_key"]
        if not pk:
            keys[name] = []
            return []
        keys[name] = []                                             # a cycle sees no keys yet
        ty = dict(types[name])
        if name in subtype_parent:
            f = subtype_parent[name]
            parent = key_rows(f["ref_table"])
            sibs = children[f["ref_table"]]
            share = max(len(sibs), 2)
            i = sibs.index(name)
            part = parent[i * len(parent) // share:(i + 1) * len(parent) // share]
            order = [f["columns"].index(c) for c in pk]
            keys[name] = [tuple(r[j] for j in order) for r in part]
            return keys[name]
        fks = [f for f in t["foreign_keys"] if set(f["columns"]) <= set(pk) and f["ref_table"] != name]
        covered: dict[str, tuple[dict, int]] = {}
        for f in sorted(fks, key=lambda f: -len(f["columns"])):
            if not any(c in covered for c in f["columns"]):
                for j, c in enumerate(f["columns"]):
                    covered[c] = (f, j)
        n = size(t)
        free = [c for c in pk if c not in covered]
        if not free:
            dom = 1
            for f in {id(v[0]): v[0] for v in covered.values()}.values():
                dom *= max(1, len(key_rows(f["ref_table"])))
            n = min(n, max(2, dom * 6 // 10))
        out, seen, tries = [], set(), 0
        while len(out) < n and tries < n * 50:
            tries += 1
            drawn: dict[int, tuple] = {}
            row = []
            for c in pk:
                if c in covered:
                    f, j = covered[c]
                    if id(f) not in drawn:
                        target = key_rows(f["ref_table"])
                        if not target:
                            drawn[id(f)] = tuple(len(out) + 1 for _ in f["columns"])
                        else:
                            ref_pk = tabs[f["ref_table"]]["primary_key"]
                            pickd = rnd.pick(target)
                            drawn[id(f)] = tuple(pickd[ref_pk.index(rc)] if rc in ref_pk else pickd[0] for rc in f["ref_columns"])
                    row.append(drawn[id(f)][j])
                elif propose.type_class(ty[c]) == "integer":
                    row.append(len(out) + 1)
                elif "date" in ty[c] or "time" in ty[c]:
                    row.append(f"20{20 + rnd.below(6):02d}-{1 + rnd.below(12):02d}-{1 + rnd.below(28):02d}")
                else:
                    row.append(f"{name[:3].upper()}{len(out) + 1:05d}" if len(free) == 1 else f"{c[:2].upper()}{rnd.below(40):03d}")
            if tuple(row) not in seen:
                seen.add(tuple(row))
                out.append(tuple(row))
        keys[name] = out
        return out

    for name in tabs:
        key_rows(name)
    rows: dict[str, list[tuple]] = {}
    for name, t in tabs.items():
        pk = t["primary_key"]
        cols = types[name]
        n = len(keys[name]) if pk else 40
        fk_of: dict[str, tuple[dict, int]] = {}
        for f in t["foreign_keys"]:
            if not set(f["columns"]) <= set(pk):
                for j, c in enumerate(f["columns"]):
                    if c not in pk:
                        fk_of.setdefault(c, (f, j))
        data = []
        for i in range(n):
            drawn: dict[int, tuple | None] = {}
            row = []
            for c, ty in cols:
                if c in pk:
                    row.append(keys[name][i][pk.index(c)])
                elif c in fk_of:
                    f, j = fk_of[c]
                    if id(f) not in drawn:
                        target = keys[f["ref_table"]][:i] if f["ref_table"] == name else keys[f["ref_table"]]
                        if not target or rnd.below(100) < 8:
                            drawn[id(f)] = None
                        else:
                            ref_pk = tabs[f["ref_table"]]["primary_key"]
                            got = rnd.pick(target)
                            drawn[id(f)] = tuple(got[ref_pk.index(rc)] for rc in f["ref_columns"])
                    row.append(None if drawn[id(f)] is None else drawn[id(f)][j])
                elif ty == "uniqueidentifier":
                    row.append(f"{rnd.below(2**32):08x}-{i:04x}-4000-8000-{abs(hash_name(name)) % 10**12:012d}")
                elif c.lower() in _AW_UNIQUE:
                    row.append(f"{c} {i + 1:05d}")
                elif propose.type_class(ty) == "integer":
                    row.append(1 + rnd.below(50))
                elif ty == "bit":
                    row.append(rnd.below(2))
                elif propose.type_class(ty) == "string":
                    row.append(f"{c} {rnd.below(max(2, n // 3))}")
                elif "date" in ty or "time" in ty:
                    row.append(f"20{20 + rnd.below(6):02d}-{1 + rnd.below(12):02d}-{1 + rnd.below(28):02d}")
                elif _affinity(ty) == "REAL":
                    row.append(round(1 + rnd.below(900000) / 100, 2))
                else:
                    row.append(None)
            data.append(tuple(row))
        rows[name] = data
    truth = {"keys": {t["name"]: t["primary_key"] for t in fx["tables"] if t["primary_key"]},
             "links": [[t["name"], f["columns"], f["ref_table"]] for t in fx["tables"] for f in t["foreign_keys"]]}
    return types, rows, truth


def hash_name(name: str) -> int:
    h = 0
    for ch in name:
        h = (h * 131 + ord(ch)) % 10**12
    return h


# ------------------------------------------------------------------ a Nordic-ERP-like shape -------------------------

def nordic_erp(seed: int = 5):
    """Short Swedish table and column names of the kind a Nordic ERP's database has (kus, ar, oh, orp, fh; ftgnr, artnr,
    ordernr). Synthetic, written for this corpus; not a product's schema. Planted: the invoice table keeps the customer
    number without its leading zeros (an export that went through a spreadsheet), three order rows point at an order
    that does not exist, and the stock table's own number column has duplicates."""
    rnd = Rng(seed)
    tables = {
        "kus": [("ftgnr", "nvarchar"), ("ftgnamn", "nvarchar"), ("landskod", "nvarchar"), ("saljare", "nvarchar"), ("kreditgrans", "decimal")],
        "ar": [("artnr", "nvarchar"), ("artbeskr", "nvarchar"), ("varugrupp", "nvarchar"), ("vikt", "decimal")],
        "vg": [("varugrupp", "nvarchar"), ("vgbeskr", "nvarchar")],
        "salj": [("sign", "nvarchar"), ("namn", "nvarchar")],
        "oh": [("ordernr", "int"), ("ftgnr", "nvarchar"), ("orddatum", "date"), ("saljare", "nvarchar"), ("ordstat", "int")],
        "orp": [("ordernr", "int"), ("ordradnr", "int"), ("artnr", "nvarchar"), ("ordantal", "int"), ("vb_pris", "decimal")],
        "fh": [("faktnr", "int"), ("ordernr", "int"), ("kundnr", "nvarchar"), ("faktdatum", "date"), ("belopp", "decimal")],
        "lagsaldo": [("lagplats", "nvarchar"), ("artnr", "nvarchar"), ("saldo", "int")],
    }
    kus = [(f"{1000 + i:06d}", f"Kund {i + 1}", rnd.pick(["SE", "NO", "FI", "DK"]), None, float(10000 * (1 + rnd.below(9)))) for i in range(80)]
    signs = ["AB", "CD", "EF", "GH", "IJ", "KL"]
    kus = [(a, b, c, rnd.pick(signs), e) for a, b, c, _d, e in kus]
    vg = [(f"VG{i:02d}", f"Varugrupp {i}") for i in range(1, 9)]
    ar = [(f"A-{100 + i}", f"Artikel {i + 1}", rnd.pick(vg)[0], round(1 + rnd.below(500) / 10, 1)) for i in range(120)]
    salj = [(s, f"Säljare {s}") for s in signs]
    oh, orp, fh = [], [], []
    for i in range(200):
        nr = 50001 + i
        k = rnd.pick(kus)
        oh.append((nr, k[0], f"2026-{1 + rnd.below(10):02d}-{1 + rnd.below(28):02d}", rnd.pick(signs), rnd.below(4)))
        for line in range(1, 2 + rnd.below(4)):
            orp.append((nr, line, rnd.pick(ar)[0], 1 + rnd.below(20), round(10 + rnd.below(90000) / 100, 2)))
        if rnd.below(10) < 8:
            fh.append((900001 + len(fh), nr, k[0].lstrip("0"), f"2026-{1 + rnd.below(11):02d}-{1 + rnd.below(28):02d}", round(100 + rnd.below(9000000) / 100, 2)))
    for line in (1, 2, 3):
        orp.append((59999, line, ar[0][0], 1, 10.0))                 # planted: order 59999 does not exist
    lag = []
    for a in ar[:60]:
        for plats in ("H1", "H2")[:1 + rnd.below(2)]:
            lag.append((plats, a[0], rnd.below(400)))
    rows = {"kus": kus, "ar": ar, "vg": vg, "salj": salj, "oh": oh, "orp": orp, "fh": fh, "lagsaldo": lag}
    truth = {"keys": {"kus": ["ftgnr"], "ar": ["artnr"], "vg": ["varugrupp"], "salj": ["sign"], "oh": ["ordernr"],
                      "orp": ["ordernr", "ordradnr"], "fh": ["faktnr"], "lagsaldo": ["lagplats", "artnr"]},
             "links": [["kus", ["saljare"], "salj"], ["ar", ["varugrupp"], "vg"], ["oh", ["ftgnr"], "kus"], ["oh", ["saljare"], "salj"],
                       ["orp", ["ordernr"], "oh"], ["orp", ["artnr"], "ar"], ["fh", ["ordernr"], "oh"], ["fh", ["kundnr"], "kus"],
                       ["lagsaldo", ["artnr"], "ar"]],
             "planted": {"leading_zeros": "fh.kundnr holds kus.ftgnr without its leading zeros: the link holds only after stripping them",
                         "orphans": "orp: 3 rows of order 59999, which is not in oh"}}
    return tables, rows, truth


# ------------------------------------------------------------------ a Business-Central-like shape -------------------

BC = "Example AB$"
BC_APP = "$437dbf0e-84ff-417a-965d-ed2bb9650972"


def bc_like(seed: int = 9):
    """Tables named and laid out the way Business Central's SQL database names them: `<company>$<table>$<app id>`, keys
    called `No_`, `Document No_`, `Line No_`, `Entry No_`, references called `Sell-to Customer No_`. Synthetic, written
    for this corpus; not Microsoft's schema and not its data. Sales and purchase documents share the column names but
    not the number series (S-ORD…, P-ORD…), so only the rows say that a ledger entry's document is a sales document."""
    rnd = Rng(seed)
    n = lambda t: f"{BC}{t}{BC_APP}"
    tables = {
        n("Customer"): [("No_", "nvarchar"), ("Name", "nvarchar"), ("Country_Region Code", "nvarchar"), ("Salesperson Code", "nvarchar")],
        n("Vendor"): [("No_", "nvarchar"), ("Name", "nvarchar"), ("Country_Region Code", "nvarchar")],
        n("Item"): [("No_", "nvarchar"), ("Description", "nvarchar"), ("Base Unit of Measure", "nvarchar"), ("Unit Price", "decimal")],
        n("Salesperson_Purchaser"): [("Code", "nvarchar"), ("Name", "nvarchar")],
        n("Country_Region"): [("Code", "nvarchar"), ("Name", "nvarchar")],
        n("Sales Header"): [("Document Type", "int"), ("No_", "nvarchar"), ("Sell-to Customer No_", "nvarchar"), ("Bill-to Customer No_", "nvarchar"),
                            ("Order Date", "date"), ("Salesperson Code", "nvarchar")],
        n("Sales Line"): [("Document Type", "int"), ("Document No_", "nvarchar"), ("Line No_", "int"), ("No_", "nvarchar"), ("Quantity", "decimal"),
                          ("Unit Price", "decimal")],
        n("Purchase Header"): [("Document Type", "int"), ("No_", "nvarchar"), ("Buy-from Vendor No_", "nvarchar"), ("Order Date", "date")],
        n("Purchase Line"): [("Document Type", "int"), ("Document No_", "nvarchar"), ("Line No_", "int"), ("No_", "nvarchar"), ("Quantity", "decimal")],
        n("Cust_ Ledger Entry"): [("Entry No_", "int"), ("Customer No_", "nvarchar"), ("Posting Date", "date"), ("Document No_", "nvarchar"),
                                  ("Amount", "decimal")],
    }
    sp = [(c, f"Seller {c}") for c in ("AH", "BD", "JR", "LM", "PS")]
    cr = [(c, f"Country {c}") for c in ("SE", "NO", "DK", "FI", "DE")]
    cust = [(f"C{10000 + 10 * i}", f"Customer {i + 1}", rnd.pick(cr)[0], rnd.pick(sp)[0]) for i in range(90)]
    vend = [(f"V{20000 + 10 * i}", f"Vendor {i + 1}", rnd.pick(cr)[0]) for i in range(40)]
    item = [(f"{1000 + i}", f"Item {i + 1}", rnd.pick(["PCS", "BOX", "KG"]), round(5 + rnd.below(50000) / 100, 2)) for i in range(110)]
    sh, sl, ph, pl, cle = [], [], [], [], []
    for i in range(180):
        doc = f"S-ORD{101000 + i}"
        c = rnd.pick(cust)
        bill = c if rnd.below(10) < 8 else rnd.pick(cust)
        sh.append((1, doc, c[0], bill[0], f"2026-{1 + rnd.below(10):02d}-{1 + rnd.below(28):02d}", c[3]))
        for line in range(1, 2 + rnd.below(4)):
            it = rnd.pick(item)
            sl.append((1, doc, 10000 * line, it[0], float(1 + rnd.below(12)), it[3]))
        if rnd.below(10) < 7:
            cle.append((len(cle) + 1, bill[0], f"2026-{1 + rnd.below(11):02d}-{1 + rnd.below(28):02d}", doc, round(50 + rnd.below(900000) / 100, 2)))
    for i in range(70):
        doc = f"P-ORD{106000 + i}"
        v = rnd.pick(vend)
        ph.append((1, doc, v[0], f"2026-{1 + rnd.below(10):02d}-{1 + rnd.below(28):02d}"))
        for line in range(1, 2 + rnd.below(3)):
            pl.append((1, doc, 10000 * line, rnd.pick(item)[0], float(1 + rnd.below(40))))
    rows = {n("Customer"): cust, n("Vendor"): vend, n("Item"): item, n("Salesperson_Purchaser"): sp, n("Country_Region"): cr,
            n("Sales Header"): sh, n("Sales Line"): sl, n("Purchase Header"): ph, n("Purchase Line"): pl, n("Cust_ Ledger Entry"): cle}
    truth = {"keys": {n("Customer"): ["No_"], n("Vendor"): ["No_"], n("Item"): ["No_"], n("Salesperson_Purchaser"): ["Code"],
                      n("Country_Region"): ["Code"], n("Sales Header"): ["Document Type", "No_"],
                      n("Sales Line"): ["Document Type", "Document No_", "Line No_"], n("Purchase Header"): ["Document Type", "No_"],
                      n("Purchase Line"): ["Document Type", "Document No_", "Line No_"], n("Cust_ Ledger Entry"): ["Entry No_"]},
             "links": [[n("Customer"), ["Country_Region Code"], n("Country_Region")], [n("Customer"), ["Salesperson Code"], n("Salesperson_Purchaser")],
                       [n("Vendor"), ["Country_Region Code"], n("Country_Region")],
                       [n("Sales Header"), ["Sell-to Customer No_"], n("Customer")], [n("Sales Header"), ["Bill-to Customer No_"], n("Customer")],
                       [n("Sales Header"), ["Salesperson Code"], n("Salesperson_Purchaser")],
                       [n("Sales Line"), ["Document Type", "Document No_"], n("Sales Header")], [n("Sales Line"), ["No_"], n("Item")],
                       [n("Purchase Header"), ["Buy-from Vendor No_"], n("Vendor")],
                       [n("Purchase Line"), ["Document Type", "Document No_"], n("Purchase Header")], [n("Purchase Line"), ["No_"], n("Item")],
                       [n("Cust_ Ledger Entry"), ["Customer No_"], n("Customer")]]}
    return tables, rows, truth


# ------------------------------------------------------------------ the SAP-shaped samples --------------------------

_SAP_TRUTH = {
    "sap_sd": {"keys": {"ZSD_ORDER_EXT": ["MANDT", "VBELN"], "ZSD_KAM_ASSIGN": ["ZZ_KUNDE_NR"]},
               "links": [["ZSD_ORDER_EXT", ["MANDT", "VBELN"], "VBAK"], ["ZSD_KAM_ASSIGN", ["ZZ_KUNDE_NR"], "KNA1"]]},
    "sap_mm": {"keys": {"ZMM_PO_CONF": ["MANDT", "EBELN", "EBELP"]},
               "links": [["ZMM_PO_CONF", ["MANDT", "EBELN", "EBELP"], "EKPO"]]},
}
# sap_renamed: the sap_sd tables under names that say nothing to the pack; the columns are unchanged
RENAMED = {"T001": "company_codes", "KNA1": "customer_master", "MARA": "material_master", "MAKT": "material_texts",
           "VBAK": "sales_doc_header", "VBAP": "sales_doc_item", "LIKP": "delivery_header", "LIPS": "delivery_item",
           "VBRK": "billing_header", "VBRP": "billing_item", "ZSD_ORDER_EXT": "order_extension", "ZSD_KAM_ASSIGN": "kam_assignment"}


def sap(sample: str, rename: dict[str, str] | None = None):
    """The SAP-shaped sample of fabric_backend/sap_sample.py (synthetic, SAP-shaped, not SAP data). The truth is the SAP
    pack's documented keys and key links for the standard tables, and for the Z tables what the generator writes."""
    from fabric_backend import sap_pack
    rename = rename or {}
    r = lambda t: rename.get(t, t)
    tables = {r(t): [(c, ty.lower().split("(")[0]) for c, ty in sap_sample._cols(sample, t)] for t in sap_sample.SCHEMAS[sample]}
    rows = {r(t): [tuple(v.isoformat() if hasattr(v, "isoformat") else v for v in row) for row in data]
            for t, data in sap_sample.rows(sample).items()}
    m = sap_pack.match(sap_sample.schema(sample), "sap")
    keys = {r(t): list(k) for t, k in m.keys.items()}
    links = [[r(x["source"]), list(x["source_cols"]), r(x["target"])] for x in m.relationships
             if x.get("kind", "key") == "key" and not x.get("where")]
    keys.update({r(t): k for t, k in _SAP_TRUTH[sample]["keys"].items()})
    links += [[r(s), c, r(t)] for s, c, t in _SAP_TRUTH[sample]["links"]]
    return tables, rows, {"keys": keys, "links": links}


def shop():
    """The synthetic shop of fabric_backend/seed.py; the truth is what its generator writes (ship_to_id is an address)."""
    from fabric_backend import seed
    tables = {t: [(c.split()[0], c.split()[1].lower()) for c in ddl.split(", ")] for t, ddl in seed.SCHEMAS.items()}
    rows = {t: [tuple(v.isoformat() if hasattr(v, "isoformat") else v for v in r) for r in data] for t, data in seed.rows().items()}
    truth = {"keys": {"customers": ["customer_id"], "categories": ["id"], "products": ["product_id"], "addresses": ["address_id"],
                      "orders": ["order_id"], "order_items": ["order_id", "line_no"]},
             "links": [["products", ["category_id"], "categories"], ["addresses", ["customer_id"], "customers"],
                       ["orders", ["customer_id"], "customers"], ["orders", ["ship_to_id"], "addresses"],
                       ["order_items", ["order_id"], "orders"], ["order_items", ["product_id"], "products"],
                       ["audit_log", ["customer_id"], "customers"]]}
    return tables, rows, truth


SOURCES = {
    "adventureworks": ("AdventureWorks (OLTP)", "tables, keys and foreign keys as Microsoft's script declares them; rows generated "
                       "from those constraints (synthetic), not the sample's own rows", adventureworks),
    "shop": ("Shop sample", "fabric_backend/seed.py, synthetic", shop),
    "sap_sd": ("SAP-shaped sample, order to invoice", "fabric_backend/sap_sample.py, synthetic, SAP-shaped, not SAP data", lambda: sap("sap_sd")),
    "sap_mm": ("SAP-shaped sample, purchase to pay", "fabric_backend/sap_sample.py, synthetic, SAP-shaped, not SAP data", lambda: sap("sap_mm")),
    "sap_renamed": ("SAP-shaped sample, tables renamed", "the order-to-invoice sample with table names that say nothing to the pack "
                    "(sales_doc_header for VBAK); synthetic", lambda: sap("sap_sd", RENAMED)),
    "nordic_erp": ("Nordic-ERP-like shape", "short Swedish names (kus, oh, orp, ftgnr, artnr); synthetic, written for this corpus, "
                   "not a product's schema", nordic_erp),
    "bc_like": ("Business-Central-like shape", "`<company>$<table>$<app id>` table names, `No_` keys; synthetic, written for this "
                "corpus, not Microsoft's schema", bc_like),
}


# ------------------------------------------------------------------ scoring -----------------------------------------

def _k(cols) -> list[str]:
    return sorted(c.lower() for c in cols)


def score(p, truth: dict) -> dict:
    """Keys: per table with a true key, is the plan's key exactly that set of columns (right), another set (wrong) or
    none (missed)? `keys_extra` counts keys the plan gives a table that has none. Links: per true link (source, columns, target), is it in the plan (found)? `links_wrong` counts the
    plan's links that are not true links."""
    tk = {t: _k(c) for t, c in truth["keys"].items()}
    pk = {t: _k(c) for t, (c, _r) in p.keys.items()}
    right = sorted(t for t, k in tk.items() if pk.get(t) == k)
    wrong = sorted(t for t, k in tk.items() if t in pk and pk[t] != k)
    extra = sorted(t for t in pk if t not in tk)                    # a key on a table that has none
    tl = {(s, tuple(_k(c)), t) for s, c, t in truth["links"]}
    pl = {(r.source, tuple(_k(r.source_cols)), r.target) for r in p.relationships}
    f = lambda xs: sorted(f"{s}.{'+'.join(c)} -> {t}" for s, c, t in xs)
    return {"tables": len(p.schema), "keys_true": len(tk), "keys_right": len(right), "keys_wrong": len(wrong),
            "keys_missed": len(tk) - len(right) - len(wrong), "keys_extra": len(extra), "keys_extra_list": extra, "links_true": len(tl), "links_found": len(tl & pl),
            "links_wrong": len(pl - tl), "keys_wrong_list": wrong, "keys_missed_list": sorted(set(tk) - set(right) - set(wrong)),
            "links_missed_list": f(tl - pl), "links_wrong_list": f(pl - tl)}


NUMBERS = ("tables", "keys_true", "keys_right", "keys_wrong", "keys_missed", "keys_extra", "links_true", "links_found", "links_wrong")


def plan_of(p) -> dict:
    """The plan as the expected file keeps it: every key and link with its rule, and what was proposed."""
    out = {"keys": {t: {"columns": list(c), "rule": r} for t, (c, r) in sorted(p.keys.items())},
           "links": sorted(f"{r.source}.{'+'.join(r.source_cols)} -> {r.target}.{'+'.join(r.target_cols)} [{r.rule}]" for r in p.relationships),
           "ambiguous": sorted(f"{a['table']}.{a['column']}: {', '.join(a['candidates'])}" for a in p.ambiguous),
           "proposed": sorted(f"{x['source']}.{'+'.join(x['source_cols'])} -> {x['target']} [{x['rule']}]: {x['reason']}" for x in p.proposed)}
    if p.pack and p.pack.get("by_signature"):
        out["by_signature"] = {t: v["pack_table"] for t, v in sorted(p.pack["by_signature"].items())}
    if p.profile:
        for f in ("keys_from_rows", "key_candidates", "not_unique"):
            if p.profile.get(f):
                out[f] = p.profile[f]
    return out


def rows_of(p, execute) -> dict:
    """What the rows say about the plan (evidence.validate over every key and link): the verdicts, word for word."""
    v = evidence.validate(p, execute, max_items=1000)
    return {"summary": v["summary"],
            "keys": {k["table"]: k["verdict"] for k in v["keys"]},
            "links": {f"{r['source']}.{'+'.join(r['columns'])} -> {r['target']}": r["verdict"] + (f" | re-count: {r['recount']}" if r.get("recount") else "")
                      for r in v["relationships"]}}


def run(name: str) -> dict:
    title, where, make = SOURCES[name]
    tables, rows, truth = make()
    schema, execute, close = database(name, tables, rows)
    try:
        aliases = propose.signature_aliases
        propose.signature_aliases = lambda *a, **k: ({}, {})        # main before this round knew a pack table by its name only
        try:
            names = plan(schema)
            before = plan(schema, execute=execute)
        finally:
            propose.signature_aliases = aliases
        after = plan(schema, execute=execute, profile=True)
        return {"name": name, "title": title, "source": where, "rows": sum(len(r) for r in rows.values()),
                "names": score(names, truth), "before": score(before, truth), "after": score(after, truth),
                "plan": plan_of(after), "row_results": rows_of(after, execute),
                **({"planted": truth["planted"]} if truth.get("planted") else {})}
    finally:
        close()


def expected(name: str) -> dict:
    return json.loads((CORPUS / f"{name}.json").read_text(encoding="utf-8"))


# ------------------------------------------------------------------ the published page ------------------------------

def scores_json(results: dict[str, dict]) -> dict:
    return {
        "about": "Krusgraph's regression corpus: keys and links found on schemas whose true keys and links are known. Written by "
                 "tests/f2_corpus.py from tests/corpus/*.json; tests/test_f2_corpus.py fails when the engine's numbers differ.",
        "rows": "synthetic in every corpus; see each corpus's source",
        "columns": {"names": "names only, no rows read", "before": f"names and R5 over the rows, as main planned at commit {BEFORE_COMMIT}",
                    "after": "with the row profile of round F2 (keys counted, K6, R6, a pack table by its key columns)"},
        "how_scored": "a key is right when it is exactly the true set of columns, wrong when it is another set, missed when the table "
                      "gets none, extra when the table has no key and the plan gives it one; a link is found when source, columns and target are a true link; wrong links are the plan's links "
                      "that are not true links",
        "corpora": [{"name": n, "title": r["title"], "source": r["source"], "row_count": r["rows"],
                     **{w: {k: r[w][k] for k in NUMBERS} for w in ("names", "before", "after")}} for n, r in results.items()],
        "not_present": NOT_PRESENT,
    }


def scores_md(results: dict[str, dict]) -> str:
    out = ["# Scores", "",
           "How many keys and links Krusgraph's rules find on schemas whose true keys and links are known. The numbers are",
           "written by `python tests/f2_corpus.py --write-docs` from `tests/corpus/*.json`, and `tests/test_f2_corpus.py` fails",
           "when the engine gives other numbers, a different plan or different row results. `docs/scores.json` holds the same",
           "numbers for a program.", "",
           "- **Names**: names only, no rows read (what `tests/test_inference_quality.py` measures).",
           f"- **Before**: names and R5 over the rows, as `main` planned at commit `{BEFORE_COMMIT}`, before round F2.",
           "- **After**: with the row profile of round F2: keys counted in the same call, K6 (a key from the rows), R6 (a link",
           "  from the rows) and a pack table recognised by its key columns (`fabric_backend/propose.py`, `docs/INFERENCE.md`).", "",
           "A key is right when it is exactly the true set of columns, wrong when it is another set, missed when the table gets",
           "none, extra when the table has no key and the plan gives it one. A link is found when source, columns and target are a true link; a wrong link is a link of the plan that is",
           "not a true link.", "",
           "**The rows are synthetic in every corpus.** For AdventureWorks the tables, columns, keys and foreign keys are the ones",
           "Microsoft's script declares; the rows are generated from those declared constraints, because the sample's own rows",
           "are not in this repository. Its numbers say what the rules do with rows that follow the declared constraints. They",
           "are not a measurement on the sample's own rows, and no corpus here is a customer's data. Nothing on this page was run",
           "in Fabric: the corpus runs on SQLite with the SQL the engine writes.", "",
           "## Keys", "",
           "| Corpus | Tables | True keys | Names: right / wrong / missed / extra | Before: right / wrong / missed / extra | After: right / wrong / missed / extra |",
           "| --- | --- | --- | --- | --- | --- |"]
    k = lambda s: f"{s['keys_right']} / {s['keys_wrong']} / {s['keys_missed']} / {s['keys_extra']}"
    for n, r in results.items():
        out.append(f"| {r['title']} (`{n}`) | {r['after']['tables']} | {r['after']['keys_true']} | {k(r['names'])} | {k(r['before'])} | {k(r['after'])} |")
    out += ["", "## Links", "",
            "| Corpus | True links | Names: found / wrong | Before: found / wrong | After: found / wrong |",
            "| --- | --- | --- | --- | --- |"]
    lk = lambda s: f"{s['links_found']} / {s['links_wrong']}"
    for n, r in results.items():
        out.append(f"| {r['title']} (`{n}`) | {r['after']['links_true']} | {lk(r['names'])} | {lk(r['before'])} | {lk(r['after'])} |")
    out += ["", "## The corpora", ""]
    for n, r in results.items():
        a = r["after"]
        out += [f"### {r['title']} (`{n}`)", "", f"Source: {r['source']}. {r['rows']} rows in {a['tables']} tables.", ""]
        if r.get("planted"):
            out += ["Planted on purpose: " + "; ".join(r["planted"].values()) + ".", ""]
        for label, key in (("Keys still wrong", "keys_wrong_list"), ("Keys still missed", "keys_missed_list"), ("Keys on a table that has none", "keys_extra_list"),
                           ("Links still missed", "links_missed_list"), ("Links still wrong", "links_wrong_list")):
            if a[key]:
                out += [f"{label} after ({len(a[key])}): " + ", ".join(f"`{x}`" for x in a[key]) + ".", ""]
        if r["plan"].get("by_signature"):
            out += ["Recognised by key columns: " + ", ".join(f"`{t}` as {p}" for t, p in r["plan"]["by_signature"].items()) + ".", ""]
        if r["plan"]["proposed"]:
            out += [f"Proposed, not applied ({len(r['plan']['proposed'])}):", ""] + [f"- {x}" for x in r["plan"]["proposed"][:12]]
            if len(r["plan"]["proposed"]) > 12:
                out.append(f"- … and {len(r['plan']['proposed']) - 12} more in `tests/corpus/{n}.json`")
            out.append("")
        out += [f"Row results of the plan after: {r['row_results']['summary']}.", ""]
    out += ["## Not in the corpus", ""] + [f"- `{n}`: {why}." for n, why in NOT_PRESENT.items()] + [
        "- Real ERP data, a schema of several hundred tables, and a run on a Fabric SQL endpoint: none is here. The profile's",
        "  statements are T-SQL that SQLite also runs; the leading-zero strip uses `PATINDEX`, which the test database emulates.", ""]
    return "\n".join(out)


def main(argv: list[str]) -> int:
    if "--write-expected" in argv:
        CORPUS.mkdir(exist_ok=True)
        for n in ORDER:
            (CORPUS / f"{n}.json").write_text(json.dumps(run(n), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
            print("wrote", n)
        return 0
    if "--write-docs" in argv:
        res = {n: expected(n) for n in ORDER}
        (ROOT / "docs" / "SCORES.md").write_text(scores_md(res), encoding="utf-8")
        (ROOT / "docs" / "scores.json").write_text(json.dumps(scores_json(res), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print("wrote docs/SCORES.md and docs/scores.json")
        return 0
    for n in ORDER:
        r = run(n)
        print(f"\n## {n} ({r['rows']} rows)")
        for w in ("names", "before", "after"):
            s = r[w]
            print(f"  {w:7} keys {s['keys_right']}/{s['keys_true']} right, {s['keys_wrong']} wrong, {s['keys_missed']} missed, {s['keys_extra']} extra; "
                  f"links {s['links_found']}/{s['links_true']} found, {s['links_wrong']} wrong")
        a = r["after"]
        for key in ("keys_wrong_list", "keys_missed_list", "keys_extra_list", "links_missed_list", "links_wrong_list"):
            if a[key]:
                print("   ", key, a[key])
        if "-v" in argv:
            print(json.dumps(r["plan"], indent=1)[:6000])
            print(json.dumps(r["row_results"], indent=1)[:3000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
