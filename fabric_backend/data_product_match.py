"""Catalog data products suggested for any table, and what each product can answer (round DP2, 21 November 2026).

DP1 wrote the catalog of classic data products (data_products/catalog.yaml) and mapped the four knowledge packs' tables
to it (mapping.yaml). This module covers the tables no pack knows: a customer's own tables, another ERP, a CRM export.
It is deterministic: fixed word lists and rules decide, never an AI or a language model, so the same schema (and the
same counts) give the same answer, byte for byte.

    suggest(plan, validation=None, execute=None)  -> {"rule_version", "tables": [...], "products": {...},
                                                      "processes": [...], "line", "details", "counted"}
    brief(answer)                                 -> the same answer without the per-rule detail, for a tool answer
    requirement_product(understood)               -> the catalog product a requirement's measure needs (requirements_draft)

How a table gets a product, in this order:

1. Packs first. A table a knowledge pack recognises (plan.pack) takes its product and role from mapping.yaml.
2. Names. A table name is split into words (camel case, underscores, and German and Swedish compounds such as
   Auftragspositionen = auftrag + s + positionen) and each word is read through a word list in English, German and
   Swedish (customer/kunde/kund, order/auftrag/order, invoice/rechnung/faktura ...). A table whose last word is a list
   word (type, method, category, status, group ...) is a reference list (PaymentMethods), not the product.
3. Keys. A column read as "<concept> number" (KundenNr, OrderID, Fakturanummer) is a business-key candidate; a line
   number (PosNr, LineNo, Radnr) after a document number makes a header and line key.
4. Relationships. The links the engine inferred (plan.relationships), and a line table whose document number is the
   key of a header table of the same product (the pair is a candidate link).
5. Rows. validate_plan's counts (`validation`) or, with `execute`, the same counting statements (evidence.key_sql,
   evidence.relationship_sql; at most MAX_QUERIES): the candidate business key unique, and the line's link to its
   header without orphans.

Every suggestion carries its confidence and the evidence behind it (which rule, which counts):

- high:   names (or a pack) and keys agree, and the rows confirm it (key unique; a line's link to its header holds);
- medium: names (or a pack) and keys agree; the rows were not counted (or a count could not run);
- low:    one signal only (a table name), or the rows contradict the names. Shown as a hint, never counted as present.

A table with no signal gets no suggestion. Nothing here writes anywhere; the only reads are the counting statements
above, which return counts and never a row value.
"""
from __future__ import annotations

import re
from functools import lru_cache

from .infer import _TRANSLIT, Plan

RULE_VERSION = "DP2-1 (21 November 2026)"
MAX_QUERIES = 20
CONFIDENCE = ("high", "medium", "low")

# ------------------------------------------------------------------ the word lists ----------------------------------
# A word (lower case, after transliteration: ä -> a, ö -> o, ü -> u, ß -> ss) -> the concept it names. English, German
# and Swedish, singular and plural. Written for this round from general business vocabulary; extend it here.
_WORDS: dict[str, tuple[str, ...]] = {
    "customer": ("customer", "customers", "cust", "kunde", "kunden", "kund", "kunder", "client", "clients", "debitor",
                 "debitoren", "debtor", "debtors"),
    "supplier": ("supplier", "suppliers", "supp", "vendor", "vendors", "vend", "lieferant", "lieferanten", "leverantor",
                 "leverantorer", "kreditor", "kreditoren", "creditor", "creditors"),
    "product": ("product", "products", "prod", "produkt", "produkte", "produkter", "artikel", "artiklar", "article",
                "articles", "material", "materials", "materialien", "sku", "skus", "vara", "varor"),
    "item": ("item", "items"),
    "employee": ("employee", "employees", "emp", "mitarbeiter", "anstalld", "anstallda", "medarbetare", "personal",
                 "staff", "salesperson", "salespeople", "saljare", "verkaufer"),
    "organisation": ("company", "companies", "firma", "firmen", "bolag", "foretag", "organisation", "organisations",
                     "organization", "organizations", "org", "plant", "plants", "werk", "werke", "buchungskreis",
                     "division", "divisions", "businessunit"),
    "order": ("order", "orders", "ord", "ordrar", "auftrag", "auftrage", "auftraege", "bestellung", "bestellungen",
              "salesorder", "salesorders", "kundorder"),
    "purchase": ("purchase", "purchases", "purchasing", "einkauf", "inkop", "beschaffung"),
    "invoice": ("invoice", "invoices", "inv", "rechnung", "rechnungen", "faktura", "fakturor", "billing", "bill", "bills"),
    "delivery": ("delivery", "deliveries", "shipment", "shipments", "lieferung", "lieferungen", "lieferschein",
                 "lieferscheine", "leverans", "leveranser", "foljesedel", "foljesedlar", "dispatch", "dispatches",
                 "versand"),
    "goodsreceipt": ("wareneingang", "wareneingange", "wareneingaenge", "inleverans", "inleveranser", "goodsreceipt",
                     "goodsreceipts", "grn"),
    "goods": ("goods",),
    "receipt": ("receipt", "receipts"),
    "payment": ("payment", "payments", "zahlung", "zahlungen", "betalning", "betalningar", "inbetalning",
                "inbetalningar", "utbetalning", "utbetalningar", "remittance", "remittances"),
    "journal": ("journal", "journals", "buchung", "buchungen", "verifikation", "verifikationer", "voucher", "vouchers",
                "hauptbuch", "huvudbok", "bokforing", "glentry", "glentries"),
    "gl": ("gl", "sachkonto", "sachkonten", "kontoplan", "glaccount", "glaccounts"),
    "ledger": ("ledger", "ledgers"),
    "openitem": ("openitem", "openitems", "offeneposten", "reskontra", "kundreskontra", "leverantorsreskontra",
                 "receivable", "receivables", "payable", "payables", "forderung", "forderungen"),
    "transaction": ("transaction", "transactions", "trans", "txn", "transaktion", "transaktionen", "transaktioner"),
    "movement": ("movement", "movements", "bewegung", "bewegungen", "lagerbewegung", "lagerbewegungen"),
    "stock": ("stock", "stocks", "bestand", "bestande", "inventory", "inventories", "lager"),
    "budget": ("budget", "budgets", "forecast", "forecasts", "prognose", "prognosen", "prognos", "prognoser"),
    "quote": ("quote", "quotes", "quotation", "quotations", "angebot", "angebote", "offert", "offerter", "offerte"),
    "opportunity": ("opportunity", "opportunities", "verkaufschance", "verkaufschancen", "affarsmojlighet",
                    "affarsmojligheter"),
    "case": ("case", "cases", "incident", "incidents", "ticket", "tickets", "arende", "arenden", "reklamation",
             "reklamationen", "reklamationer"),
    "campaign": ("campaign", "campaigns", "kampagne", "kampagnen", "kampanj", "kampanjer"),
    "activity": ("activity", "activities", "aktivitat", "aktivitaet", "aktivitaten", "aktivitet", "aktiviteter", "task",
                 "tasks", "appointment", "appointments", "termin", "meeting", "meetings"),
    "subscription": ("subscription", "subscriptions", "abonnement", "abonnements", "abonnemang", "prenumeration",
                     "prenumerationer"),
    "lead": ("lead", "leads"),
    "contact": ("contact", "contacts", "kontakt", "kontakte", "kontakter", "ansprechpartner"),
    "account": ("account", "accounts", "acct", "konto", "konten", "konton"),
    "costcentre": ("costcenter", "costcenters", "costcentre", "costcentres", "kostenstelle", "kostenstellen",
                   "kostnadsstalle", "kostnadsstallen", "profitcenter", "profitcenters", "kst"),
    "currency": ("currency", "currencies", "curr", "waehrung", "wahrung", "waehrungen", "wahrungen", "valuta", "valutor"),
    "rate": ("rate", "rates", "kurs", "kurse", "kurser", "wechselkurs", "wechselkurse", "valutakurs", "valutakurser",
             "exchangerate", "exchangerates"),
    "calendar": ("calendar", "kalender", "dimdate"),
    "date": ("date", "dates", "datum", "dat", "day", "tag", "dag"),
    "price": ("price", "prices", "preis", "preise", "pris", "priser", "pricelist", "pricelists", "preisliste",
              "preislisten", "prislista", "prislistor", "pricebook", "pricebooks"),
    "list": ("list", "lists", "liste", "listen", "lista", "listor"),
    # roles and column kinds
    "line": ("line", "lines", "position", "positionen", "positions", "pos", "posten", "zeile", "zeilen", "rad", "rader",
             "detail", "details", "row", "rows"),
    "header": ("header", "headers", "head", "kopf", "kopfe", "kopfdaten", "huvud", "hdr"),
    "number": ("id", "nr", "no", "number", "nummer", "num", "nbr", "key", "code"),
    "amount": ("amount", "amounts", "betrag", "betrage", "belopp", "value", "wert", "varde", "total", "summe", "summa",
               "sum", "net", "netto", "brutto", "gross", "revenue", "umsatz", "cost", "kosten", "kostnad"),
    "quantity": ("quantity", "qty", "menge", "antal", "kvantitet", "anzahl"),
    # the last word of a reference list: PaymentMethods, OrderTypes, Kundengruppen
    "lookup": ("type", "types", "typ", "typen", "typer", "method", "methods", "category", "categories", "kategorie",
               "kategorien", "kategori", "kategorier", "status", "statuses", "group", "groups", "gruppe", "gruppen",
               "grupp", "grupper", "kind", "kinds", "art", "arten", "reason", "reasons", "term", "terms", "bedingung",
               "bedingungen", "villkor", "setting", "settings", "mode", "modes", "class", "classes"),
}
LEXICON: dict[str, str] = {w: c for c, ws in _WORDS.items() for w in ws}
_MIN_PIECE = 3

# A concept (or a pair of concepts in one table name) -> the catalog product. Read in this order; the first that
# applies wins, so "supplier invoice" is a supplier invoice before it is an invoice.
_DOCUMENT_RULES: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    # (product, all of these concepts, or any of these with the first)
    ("open_item", ("openitem",), ()),
    ("open_item", ("customer", "transaction"), ()),
    ("open_item", ("supplier", "transaction"), ()),
    ("open_item", ("customer", "ledger"), ()),
    ("open_item", ("supplier", "ledger"), ()),
    ("goods_receipt", ("goodsreceipt",), ()),
    ("goods_receipt", ("goods", "receipt"), ()),
    ("supplier_invoice", ("supplier", "invoice"), ()),
    ("supplier_invoice", ("purchase", "invoice"), ()),
    ("purchase_order", ("purchase",), ()),
    ("purchase_order", ("supplier", "order"), ()),
    ("inventory_movement", ("movement",), ()),
    ("inventory_movement", ("stock", "transaction"), ()),
    ("inventory_movement", ("item", "transaction"), ()),
    ("inventory_movement", ("product", "transaction"), ()),
    ("gl_journal_entry", ("journal",), ()),
    ("gl_journal_entry", ("gl", "transaction"), ()),
    ("gl_journal_entry", ("ledger",), ()),
    ("delivery", ("delivery",), ()),
    ("invoice", ("invoice",), ()),
    ("payment", ("payment",), ()),
    ("quote", ("quote",), ()),
    ("sales_order", ("order",), ()),
    ("opportunity", ("opportunity",), ()),
    ("case", ("case",), ()),
    ("campaign", ("campaign",), ()),
    ("activity", ("activity",), ()),
    ("subscription", ("subscription",), ()),
    ("lead", ("lead",), ()),
    ("budget", ("budget",), ()),
    ("price", ("price",), ()),
    ("currency", ("currency",), ()),
    ("currency", ("rate",), ()),
    ("cost_centre", ("costcentre",), ()),
    ("chart_of_accounts", ("gl",), ()),
    ("chart_of_accounts", ("account",), ()),
    ("contact", ("contact",), ()),
    ("employee", ("employee",), ()),
    ("organisation", ("organisation",), ()),
    ("supplier", ("supplier",), ()),
    ("customer", ("customer",), ()),
    ("product", ("product",), ()),
    ("product", ("item",), ()),
    ("inventory_movement", ("stock",), ()),
    ("date", ("calendar",), ()),
)
# The concept whose "<concept> number" column is a product's business key (KundenNr for customer, AuftragsNr for a
# sales order); a line role adds a line number. For a product whose key is named after another concept too (an invoice
# number in a payment), only the first is the table's own key.
KEY_CONCEPT = {
    "customer": ("customer",), "supplier": ("supplier",), "product": ("product", "item"), "employee": ("employee",),
    "organisation": ("organisation",), "chart_of_accounts": ("account", "gl"), "cost_centre": ("costcentre",),
    "currency": ("currency",), "date": ("date",), "sales_order": ("order",), "delivery": ("delivery",),
    "invoice": ("invoice",), "open_item": ("openitem", "transaction", "ledger", "journal"), "payment": ("payment",),
    "gl_journal_entry": ("journal", "transaction", "ledger"), "budget": ("budget",),
    "purchase_order": ("order", "purchase"), "goods_receipt": ("goodsreceipt", "receipt"),
    "supplier_invoice": ("invoice",), "inventory_movement": ("movement", "transaction"), "price": ("price",),
    "crm_account": ("account",), "contact": ("contact",), "lead": ("lead",), "opportunity": ("opportunity",),
    "quote": ("quote",), "case": ("case",), "campaign": ("campaign",), "activity": ("activity",),
    "subscription": ("subscription",),
}
DOCUMENTS = {"sales_order", "delivery", "invoice", "purchase_order", "goods_receipt", "supplier_invoice", "quote",
             "opportunity", "subscription", "payment", "gl_journal_entry", "open_item", "inventory_movement", "case",
             "campaign", "activity", "budget"}

# The processes the coverage answer speaks of: a process is a chain of catalog products. Written for this round.
PROCESSES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("order_to_cash", "Order to cash", ("customer", "product", "sales_order", "delivery", "invoice", "open_item", "payment")),
    ("procure_to_pay", "Procure to pay", ("supplier", "product", "purchase_order", "goods_receipt", "supplier_invoice",
                                          "open_item", "payment")),
    ("record_to_report", "Record to report", ("organisation", "chart_of_accounts", "gl_journal_entry", "cost_centre",
                                              "currency", "budget")),
    ("lead_to_cash", "Lead to cash", ("crm_account", "contact", "lead", "opportunity", "quote", "sales_order", "invoice")),
    ("service", "Customer service", ("crm_account", "contact", "case", "activity", "product")),
    ("subscription", "Subscription", ("customer", "subscription", "invoice", "payment")),
    ("inventory", "Inventory", ("product", "organisation", "inventory_movement", "goods_receipt", "delivery")),
)


# ------------------------------------------------------------------ words ------------------------------------------

def _split(name: str) -> list[str]:
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(name))
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", s)
    s = s.lower().translate(_TRANSLIT)
    s = re.sub(r"(?<=[a-z])(?=[0-9])|(?<=[0-9])(?=[a-z])", " ", s)
    return [w for w in re.split(r"[^a-z0-9]+", s) if w and not w.isdigit()]


@lru_cache(maxsize=4096)
def _segment(word: str) -> tuple[str, ...] | None:
    """A word as known pieces: auftragspositionen -> (auftrag, positionen), kundenauftrag -> (kunden, auftrag),
    leverantorsfakturor -> (leverantor, fakturor). A joining s between pieces is dropped (German and Swedish). None when
    the word is not made of known pieces."""
    if word in LEXICON:
        return (word,)
    if not word:
        return ()
    if word.endswith("s") and word[:-1] in LEXICON:                   # auftrags (in AuftragsNr): the joining s
        return (word[:-1],)
    for i in range(len(word) - _MIN_PIECE, _MIN_PIECE - 1, -1):          # the longest known first piece
        left, right = word[:i], word[i:]
        heads = [left] + ([left[:-1]] if left.endswith("s") and len(left) > _MIN_PIECE else [])
        for h in heads:
            if h in LEXICON:
                rest = _segment(right)
                if rest is not None:
                    return (h,) + rest
    return None


def words(name: str) -> list[str]:
    """The known words of a name, in order: `Auftragspositionen` -> [auftrag, positionen]; unknown words are kept as
    they are, so `tmp_load` -> [tmp, load]."""
    out: list[str] = []
    for w in _split(name):
        out += list(_segment(w) or (w,))
    return out


def concepts(name: str) -> list[str]:
    """The concepts a name's words carry, in order: `Kundenauftrag` -> [customer, order]; `PosNr` -> [line, number]."""
    return [LEXICON[w] for w in words(name) if w in LEXICON]


# ------------------------------------------------------------------ one table ----------------------------------------

def _table_product(cs: list[str]) -> str | None:
    """The product a table name points at, by _DOCUMENT_RULES (None for a reference list or no known word)."""
    if not cs or cs[-1] == "lookup":
        return None
    have = set(cs)
    for product, need, _ in _DOCUMENT_RULES:
        if set(need) <= have:
            return product
    return None


def _role_from_name(cs: list[str], product: str) -> str | None:
    have = set(cs)
    if "line" in have:
        return "line"
    if cs[-1] == "item" and product in DOCUMENTS:               # OrderItems: the item of a document is its line
        return "line"
    if "header" in have:
        return "header"
    return None


def _column_kinds(col: str) -> list[str]:
    return concepts(col)


def _number_columns(t) -> dict[str, list[str]]:
    """{concept: [columns]} for the columns read as "<concept> number" (KundenNr, OrderID, Fakturanummer, PosNr)."""
    out: dict[str, list[str]] = {}
    for c in t.column_names:
        cs = _column_kinds(c)
        if len(cs) < 2 or cs[-1] != "number":
            continue
        out.setdefault(cs[-2], []).append(c)
    return out


def _bare_line_columns(t) -> list[str]:
    """Columns that are a line number on their own (Pos, Position, Line, Rad, Zeile) or as line + number."""
    out = []
    for c in t.column_names:
        cs = _column_kinds(c)
        if cs in (["line"], ["line", "number"]) and all(w in LEXICON for w in words(c)):
            out.append(c)
    return out


def _has_kind(t, kind: str) -> list[str]:
    return [c for c in t.column_names if kind in _column_kinds(c)]


# ------------------------------------------------------------------ the answer -------------------------------------

def _catalog():
    from . import data_product_catalog as dpc
    return dpc.products()


def _pack_entries(plan: Plan) -> dict[str, list[dict]]:
    """{table: [mapping entries]} for the tables a knowledge pack recognised in the plan (mapping.yaml)."""
    pk = plan.pack or {}
    name = pk.get("pack")
    if not name:
        return {}
    from . import data_product_catalog as dpc
    try:
        mapped = dpc.tables(name)
    except KeyError:
        return {}
    return {t: mapped[n] for t, n in (pk.get("tables") or {}).items() if n in mapped}


class _Rows:
    """The row checks: validate_plan's counts first, then (with `execute`) the same statements, at most MAX_QUERIES."""

    def __init__(self, plan: Plan, validation: dict | None, execute):
        self.plan, self.execute = plan, execute
        self.queries = 0
        self.keys = {}
        self.rels = {}
        for k in (validation or {}).get("keys") or []:
            self.keys[(k.get("table"), tuple(c.lower() for c in k.get("columns") or []))] = k
        for r in (validation or {}).get("relationships") or []:
            self.rels[(r.get("source"), tuple(c.lower() for c in r.get("source_cols") or []), r.get("target"),
                       tuple(c.lower() for c in r.get("target_cols") or []))] = r
        self.counted = bool(validation) or execute is not None

    def _may_count(self) -> bool:
        """A statement may run: an execute, fewer than MAX_QUERIES so far, and the call's time budget not spent."""
        if self.execute is None or self.queries >= MAX_QUERIES:
            return False
        from . import budget
        return not budget.expired()

    def key(self, table: str, cols: list[str]) -> dict | None:
        """{rows, nulls, distinct, verdict, how} or None when not counted."""
        k = self.keys.get((table, tuple(c.lower() for c in cols)))
        if k is not None:
            return {"rows": k.get("rows"), "nulls": k.get("nulls"), "distinct": k.get("distinct"),
                    "verdict": k.get("verdict"), "how": "validate_plan"}
        if not self._may_count():
            return None
        from . import evidence
        self.queries += 1
        try:
            row = list(self.execute(evidence.key_sql(self.plan.schema.schema, table, cols, evidence.dialect_of(self.execute))))[0]
        except Exception as e:                                          # noqa: BLE001 - not counted, said so
            return {"verdict": "not counted: " + evidence.failed_reason(e), "how": "this call"}
        n, nulls, distinct = (int(row.get(x) or 0) for x in ("n", "nulls", "distinct_keys"))
        out = {"rows": n, "nulls": nulls, "distinct": distinct, "verdict": evidence.key_verdict(n, nulls, distinct),
               "how": "this call"}
        self.keys[(table, tuple(c.lower() for c in cols))] = {"table": table, "columns": cols, **out}
        return out

    def link(self, source: str, scols: list[str], target: str, tcols: list[str]) -> dict | None:
        r = self.rels.get((source, tuple(c.lower() for c in scols), target, tuple(c.lower() for c in tcols)))
        if r is not None:
            return {"rows_with_value": r.get("rows_with_value"), "orphans": r.get("orphans"), "verdict": r.get("verdict"),
                    "how": "validate_plan"}
        if not self._may_count():
            return None
        from . import evidence
        self.queries += 1
        try:
            row = list(self.execute(evidence.relationship_sql(self.plan.schema.schema, source, scols, target, tcols,
                                                              evidence.dialect_of(self.execute))))[0]
        except Exception as e:                                          # noqa: BLE001
            return {"verdict": "not counted: " + evidence.failed_reason(e), "how": "this call"}
        w, o = int(row.get("with_value") or 0), int(row.get("orphans") or 0)
        return {"rows_with_value": w, "orphans": o, "verdict": evidence.relationship_verdict(w, o), "how": "this call"}


def _key_ok(k: dict | None) -> bool | None:
    if not k or str(k.get("verdict", "")).startswith(("not counted", "empty")):
        return None
    return str(k.get("verdict", "")).startswith("unique")


def _link_ok(r: dict | None) -> bool | None:
    if not r or str(r.get("verdict", "")).startswith(("not counted", "no rows")):
        return None
    return str(r.get("verdict", "")).startswith("holds")


def _candidates(plan: Plan) -> dict[str, dict]:
    """Per table no pack knows: the product its name points at, the role, the key candidate and the name evidence."""
    out = {}
    for t in plan.schema:
        cs = concepts(t.name)
        product = _table_product(cs)
        nums = _number_columns(t)
        if product is None and cs and cs[-1] == "lookup":
            continue
        if product is None:
            continue
        role = _role_from_name(cs, product)
        own = next((nums[c][0] for c in KEY_CONCEPT.get(product, ()) if c in nums), None)
        if own is None and product in ("product",) and "item" in nums:
            own = nums["item"][0]
        line_cols = nums.get("line", []) + [c for c in _bare_line_columns(t) if c not in nums.get("line", [])]
        if own is None and nums.get("number"):
            own = nums["number"][0]
        bare = [c for c in t.column_names if _column_kinds(c) == ["number"]]
        out[t.name] = {"table": t.name, "product": product, "role": role, "concepts": cs, "own_key": own,
                       "line_cols": line_cols, "bare_id": bare[0] if bare else None,
                       "amounts": _has_kind(t, "amount"), "dates": _has_kind(t, "date")}
    return out


def _plan_key(plan: Plan, table: str) -> list[str]:
    k = plan.keys.get(table)
    return list(k[0]) if k else []


def suggest(plan: Plan, validation: dict | None = None, execute=None) -> dict:
    """Per table, the catalog product, its role, the confidence and the evidence; per product what is present; per
    process the coverage answer. `validation` is validate_plan's full answer (evidence.validate); `execute` lets the
    candidate keys and links the plan does not hold be counted with the same statements (at most MAX_QUERIES)."""
    prods = _catalog()
    rows = _Rows(plan, validation, execute)
    packed = _pack_entries(plan)
    pack_name = (plan.pack or {}).get("pack")
    tables: list[dict] = []

    # 1. the pack's tables, from mapping.yaml
    for name in sorted(packed):
        key = _plan_key(plan, name)
        k = rows.key(name, key) if key else None
        ok = _key_ok(k)
        for e in packed[name]:
            ev = [{"rule": "DP2-P1", "what": f"the {pack_name} pack recognises it as {plan.pack['tables'][name]}; "
                                             f"mapping.yaml maps that to {e['product']} ({e['role']}), "
                                             f"confidence {e['confidence']}"}]
            conf = e["confidence"]
            if key:
                ev.append({"rule": "DP2-K1", "what": f"key {'+'.join(key)} from the plan"})
            if ok is True:
                ev.append({"rule": "DP2-C1", "what": f"key counted: {k['verdict']}", "counts": _counts(k)})
            elif ok is False:
                ev.append({"rule": "DP2-C1", "what": f"key counted: {k['verdict']}", "counts": _counts(k)})
            conf = _level(conf in ("high", "medium"), ok, None, conf == "high")
            tables.append({"table": name, "product": e["product"], "role": e["role"], "confidence": conf,
                           "checked": ok is True, "source": "pack", "evidence": ev})

    # 2. every other table, by names, keys, links and rows
    cands = {n: c for n, c in _candidates(plan).items() if n not in packed}
    rels_by_source: dict[str, list] = {}
    pointed: dict[str, int] = {}
    for r in plan.relationships:
        rels_by_source.setdefault(r.source, []).append(r)
        pointed[r.target] = pointed.get(r.target, 0) + 1
    # header and line pairs: a table of the same product whose own key is this table's document number
    by_product: dict[str, list[str]] = {}
    for n, c in sorted(cands.items()):
        by_product.setdefault(c["product"], []).append(n)
    for n, c in sorted(cands.items()):
        score, ev = 3, [{"rule": "DP2-N1", "what": f"the table name reads as {' + '.join(words(n))}: "
                                                   f"{prods[c['product']]['title'].lower()}"}]
        role = c["role"]
        key: list[str] = []
        header = None
        link = None
        plan_key = _plan_key(plan, n)
        allowed = prods[c["product"]]["roles"]["required"] + prods[c["product"]]["roles"]["optional"]
        document = c["product"] in DOCUMENTS
        master_of = None
        if document:
            # the header this line belongs to: a plan relationship to a table of the same product, or the same column
            for r in rels_by_source.get(n, []):
                if r.target in cands and cands[r.target]["product"] == c["product"] and r.target != n \
                        and cands[r.target]["role"] != "line" and c["role"] != "header":
                    header, link = r.target, (list(r.source_cols), list(r.target_cols), f"plan relationship ({r.rule})")
                    break
            if header is None and c["own_key"]:
                for other in by_product.get(c["product"], []):
                    o = cands[other]
                    if other == n:
                        continue
                    okey = o["own_key"] or o["bare_id"]
                    if okey and okey.lower() == c["own_key"].lower() and (c["line_cols"] or role == "line") \
                            and o["role"] != "line" and not o["line_cols"]:
                        header, link = other, ([c["own_key"]], [okey], "same document number column")
                        break
        elif len(set(c["concepts"])) > 1 or len(words(n)) > 1:
            # a second table of a master product (CustomerDemographics, EmployeeTerritories) that points at the master
            for r in rels_by_source.get(n, []):
                t = cands.get(r.target)
                if t and t["product"] == c["product"] and r.target != n and len(words(r.target)) < len(words(n)):
                    master_of = r.target
                    role = "extension" if "extension" in allowed else "bridge" if "bridge" in allowed else "unknown"
                    link = (list(r.source_cols), list(r.target_cols), f"plan relationship ({r.rule})")
                    break
        if header is not None or (role == "line"):
            role = "line"
            if c["own_key"] and c["line_cols"]:
                key = [c["own_key"], c["line_cols"][0]]
            elif plan_key and len(plan_key) > 1:
                key = plan_key
            elif c["own_key"] and header is None:
                key = [c["own_key"]]
        elif master_of is not None:
            key = plan_key
        else:
            if role is None:
                req = prods[c["product"]]["roles"]["required"]
                role = "header" if document and "header" in req else (req[0] if req else "master")
            if c["own_key"]:
                key = [c["own_key"]]
            elif plan_key:
                key = plan_key
            elif c["bare_id"]:
                key = [c["bare_id"]]
        if role not in allowed:
            role = (prods[c["product"]]["roles"]["required"] or ["master"])[0]
            score -= 2
            ev.append({"rule": "DP2-N2", "what": f"a second {c['product'].replace('_', ' ')} table whose role the catalog "
                                                 "does not name"})
        if master_of is not None and role != "master":
            score += 1
            ev.append({"rule": "DP2-M2", "what": f"points at {master_of} through {'+'.join(link[0])} ({link[2]}): "
                                                 f"rows that add to it ({role})"})
        named_key = bool(key) and c["own_key"] is not None and (
            key == [c["own_key"]] or (len(key) == 2 and key[0] == c["own_key"] and key[1] in c["line_cols"]))
        if key:
            if named_key:
                score += 2
                generic = [g for g in prods[c["product"]]["business_key"] if g != "tenant_id"]
                if role != "line" or len(key) == 1:
                    generic = [g for g in generic if g != "line_number"]
                ev.append({"rule": "DP2-K1", "what": f"{'+'.join(key)} reads as the business key "
                                                     f"({', '.join(generic[-len(key):])})"})
            else:
                score += 1
                ev.append({"rule": "DP2-K2", "what": f"key {'+'.join(key)} ({'the plan' if key == plan_key else 'an id column'}), "
                                                     "not named after the product"})
        if header is not None:
            score += 2
            ev.append({"rule": "DP2-L1", "what": f"its lines point at {header} through {'+'.join(link[0])} ({link[2]})"})
        lines_here = [m for m, o in cands.items() if m != n and o["product"] == c["product"]
                      and (o["role"] == "line" or o["line_cols"]) and c["own_key"]
                      and (o["own_key"] or "").lower() == c["own_key"].lower()]
        if role in ("header",) and lines_here:
            score += 2
            ev.append({"rule": "DP2-L2", "what": f"{', '.join(sorted(lines_here))} {'holds' if len(lines_here) == 1 else 'hold'} "
                                                 f"its lines by {c['own_key']}"})
        if c["product"] in DOCUMENTS and c["amounts"]:
            score += 1
            ev.append({"rule": "DP2-A1", "what": f"amount column(s): {', '.join(c['amounts'][:3])}"})
        if role == "master" and pointed.get(n):
            score += 1
            ev.append({"rule": "DP2-M1", "what": f"{pointed[n]} relationship(s) of the plan point at it"})
        # rows
        k = rows.key(n, key) if key else None
        kok = _key_ok(k)
        if k:
            ev.append({"rule": "DP2-C1", "what": f"key {'+'.join(key)} counted: {k['verdict']}", "counts": _counts(k)})
        lok = None
        if header is not None:
            lr = rows.link(n, link[0], header, link[1])
            lok = _link_ok(lr)
            if lr:
                ev.append({"rule": "DP2-C2", "what": f"{n}.{'+'.join(link[0])} -> {header} counted: {lr['verdict']}",
                           "counts": _counts(lr)})
        conf = _level(score >= 5, kok, lok if header is not None else None, True)
        tables.append({"table": n, "product": c["product"], "role": role, "confidence": conf,
                       "checked": conf == "high", "source": "names", "score": score,
                       **({"key": key} if key else {}), **({"header": header} if header else {}), "evidence": ev})

    tables.sort(key=lambda x: (x["table"].lower(), x["product"], x["role"]))
    products = _products(tables, prods, plan)
    procs = _processes(products, prods)
    shown = [x for x in tables if x["confidence"] in ("high", "medium")]
    out = {"rule_version": RULE_VERSION, "tables": tables, "products": products, "processes": procs,
           "counted": {"with_rows": rows.counted, "queries": rows.queries,
                       **({"limit": MAX_QUERIES} if rows.queries >= MAX_QUERIES else {})},
           "unmatched": sorted(t.name for t in plan.schema if t.name not in {x["table"] for x in tables})}
    out["line"] = _line(procs, products, shown, rows.counted)
    out["details"] = _details(procs, products, tables)
    out["how"] = ("By rules, no AI: table and column names read through a word list in English, German and Swedish, "
                  "the plan's keys and links, and the row counts. high = names and keys agree and the rows confirm it; "
                  "medium = names and keys agree, the rows not counted; low = one signal only or the rows disagree, a "
                  "hint and never counted as present.")
    return out


def _counts(x: dict) -> dict:
    return {k: x[k] for k in ("rows", "nulls", "distinct", "rows_with_value", "orphans") if x.get(k) is not None}


def _level(agree: bool, key_ok: bool | None, link_ok: bool | None, strong: bool) -> str:
    """high only when the names agree and the rows confirm (key unique; the link to the header holds when there is
    one); a count that contradicts makes it low; otherwise medium (agreeing names, not counted) or low."""
    if key_ok is False or link_ok is False:
        return "low"
    if not agree:
        return "low"
    if key_ok is True and link_ok in (True, None) and strong:
        return "high"
    return "medium"


def _products(tables: list[dict], prods: dict, plan: Plan) -> dict[str, dict]:
    out = {}
    for pid, p in prods.items():
        mine = [x for x in tables if x["product"] == pid]
        good = [x for x in mine if x["confidence"] in ("high", "medium")]
        roles: dict[str, list[str]] = {}
        for x in good:
            roles.setdefault(x["role"], []).append(x["table"])
        req = p["roles"]["required"]
        if not req:
            state = "generated"
        elif not good:
            state = "missing"
        elif all(r in roles for r in req):
            state = "present"
        else:
            state = "partial"
        checked = bool(good) and all(x["confidence"] == "high" for x in good if x["role"] in req)
        row = {"title": p["title"], "state": state, "checked": checked and state == "present",
               "tables": {r: sorted(v) for r, v in sorted(roles.items())},
               "missing_roles": [r for r in req if r not in roles] if state in ("partial",) else []}
        hints = sorted({x["table"] for x in mine if x["confidence"] == "low"})
        if hints:
            row["hints"] = hints
        out[pid] = row
    return out


def _processes(products: dict, prods: dict) -> list[dict]:
    out = []
    for pid, title, chain in PROCESSES:
        present = [p for p in chain if products[p]["state"] == "present"]
        partial = [p for p in chain if products[p]["state"] == "partial"]
        missing = [p for p in chain if products[p]["state"] == "missing"]
        if not present:
            continue
        can = [q for p in present for q in prods[p]["questions"]]
        cannot = [{"product": p, "title": prods[p]["title"], "question": q,
                   "why": (f"{prods[p]['title'].lower()} is missing" if p in missing else
                           f"{prods[p]['title'].lower()} has no {', '.join(products[p]['missing_roles'])} table")}
                  for p in missing + partial for q in prods[p]["questions"]]
        out.append({"process": pid, "title": title, "products": len(chain), "present": present, "partial": partial,
                    "missing": missing, "checked": [p for p in present if products[p]["checked"]],
                    "line": _process_line(title, chain, present, partial, missing, products, prods),
                    "can_answer": can, "cannot_answer": cannot})
    out.sort(key=lambda x: (-len(x["present"]), [p[0] for p in PROCESSES].index(x["process"])))
    return out


def _short(prods: dict, p: str) -> str:
    return prods[p]["title"].split(" (")[0].lower()


def _process_line(title, chain, present, partial, missing, products, prods) -> str:
    s = f"{title}: {len(present)} of {len(chain)} {'product' if len(chain) == 1 else 'products'} present"
    if not missing and not partial:
        return s + "."
    parts = []
    if partial:
        parts.append(_join([f"{_short(prods, p)} without its {', '.join(products[p]['missing_roles'])} table" for p in partial]))
    if missing:
        parts.append(_join([_short(prods, p) for p in missing]) + " missing")
    first = prods[(partial + missing)[0]]["questions"][0]
    return s + "; " + ", and ".join(parts) + f", so a question like “{first}” cannot be answered."


def _join(xs: list[str]) -> str:
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]


def _line(procs: list[dict], products: dict, shown: list[dict], counted: bool) -> str:
    """The one line for the plan, the check and the start card's check step."""
    if not shown:
        return "Data products: no table reads as a catalog data product by the names, keys and links."
    if not procs:
        n = len({x["product"] for x in shown})
        return f"Data products: {n} found, no process covered yet."
    return "Data products: " + procs[0]["line"]


def _details(procs: list[dict], products: dict, tables: list[dict]) -> list[str]:
    """The lines under Details: each process, then each table that got a product with its confidence and evidence."""
    out = [p["line"] for p in procs]
    for x in tables:
        why = "; ".join(e["what"] for e in x["evidence"])
        out.append(f"{x['table']}: {x['product'].replace('_', ' ')} ({x['role']}), {x['confidence']}. {why}.")
    return out


def brief(answer: dict, max_tables: int = 40) -> dict:
    """The answer for a tool's JSON: the line, the processes with what they can and cannot answer, the products present
    or partial, and per table its product, role, confidence and evidence (at most max_tables, the rest counted)."""
    tables = answer["tables"]
    out = {"rule_version": answer["rule_version"], "line": answer["line"],
           "processes": [{k: p[k] for k in ("title", "line", "present", "partial", "missing", "checked")}
                         | {"can_answer": p["can_answer"][:6], "cannot_answer": [f"{c['question']} ({c['why']})"
                                                                                 for c in p["cannot_answer"][:6]]}
                         for p in answer["processes"]],
           "products": {pid: {k: v for k, v in p.items() if k != "title"} for pid, p in answer["products"].items()
                        if p["state"] in ("present", "partial") or p.get("hints")},
           "tables": [{"table": x["table"], "product": x["product"], "role": x["role"], "confidence": x["confidence"],
                       "evidence": [e["what"] for e in x["evidence"]]} for x in tables[:max_tables]],
           "how": answer["how"]}
    if len(tables) > max_tables:
        out["tables_not_shown"] = len(tables) - max_tables
    return out


# ------------------------------------------------------------------ for requirements_draft --------------------------
# A requirement's measure (requirements_draft.MEASURES) -> the catalog product it needs.
MEASURE_PRODUCT = {"open_items": "open_item", "late_delivery": "delivery", "margin": "invoice", "order_count": "sales_order",
                   "order_value": "sales_order", "revenue": "invoice", "quantity": "invoice"}


def requirement_product(understood: dict) -> str | None:
    m = understood.get("measure")
    if m in MEASURE_PRODUCT:
        return MEASURE_PRODUCT[m]
    if understood.get("sales_word"):
        return "invoice"
    return None
