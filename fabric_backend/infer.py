"""Keys and relationships for tables that have none declared.

A lakehouse SQL endpoint has no primary keys and no foreign keys. A warehouse may have them
(NOT ENFORCED) — if so, they win. Otherwise we go by names, in this order, and every result says
which rule produced it so you can overrule it.

Names are compared without case, separators or a table-wide column prefix (TPC-H style `N_NATIONKEY` in
NATION is read as `nationkey`), after transliteration of å ä ö ü ß, and a table named `<X>Header` also answers to
`<X>`; a leading kind word (`dim_`, `fact_`, `tbl_`, `stg_`, `vw_`, `ref_`, `lkp_`) is not part of a table's name. When a
literal name finds nothing, the same comparison is made through the synonym table SYNONYMS (abbreviations, Swedish and
German business words); every such match is reported under plan.synonyms and on the relationship's `note`.

Keys (per table):
  K0  declared primary key
  K1  `keys` override from the caller
  K2  a column named `id`, `no`, `nr`, `<table>_id`, `<table>id`, `<singular>_id`, `<singular>id`, `<table>_key`, `<table>_code`, `<table>_nr`, `<table>_no`, `<table>_sk`, `<table>_bk`, or an abbreviation of the table name
      (four letters or more) with one of those suffixes: `cust_key` in customer. An abbreviation that is another
      table's name (`ps_partkey` in PARTSUPP names PART) is a reference, not a key. When nothing matches literally, the
      same through the synonym table (`KundNr` in `kunder`, `cust_id` in `dim_customer`), reported under `synonyms`.
  K3  nothing — the table gets no key; it can be queried but not by pk, and nothing can point at it
  K4  junction: no column names a key and the table starts with two or more reference columns; together they are the key
      (film_actor: actor_id + film_id). Not applied to history tables (a column named start_*, valid_from,
      effective_* or *_from), whose key also needs the date.
  K5  line: no column names a key; the reference to the header table plus a line-number column
      (line_no, position, seq…). The header is the table the line table is named after (order_items → orders),
      else the first reference column.

Relationships (per column of a table A that is not A's own key):
  R0  declared foreign key
  R1  column named `<B>_id` / `<B>id` / `<singular B>_id` / `<singular B>id` (also _key, _code, _nr, _no, _sk, _bk) where B has a single key
  R2  column has exactly the same name as B's single key column, and that name is not just `id`
      (`customer_id` in orders -> customers.customer_id; `id` never matches)
  R3  all of B's composite key columns appear in A (header/items: order_id+line in order_items
      vs order_id in orders is R1; sales_org+plant in both is R3)
  R4  weaker name match when R1 and R2 find nothing: the R1/R2 shapes through the synonym table (`Kunde_ID` → `Kunden`,
      `cust_id` → `customers`, noted on the relationship), a role before B's name (`manager_staff_id` → staff,
      `ShipToAddressID` → Address), or an abbreviation of B of four letters or more (`o_custkey` → customer); never
      across suffixes (`wwi_order_id` does not point at a table keyed by `order_key`). When two tables answer to the
      same name, the one whose key carries the column's suffix wins; otherwise the column is ambiguous.
  R5  checked against the rows: a code column `<stem>_code` / `<stem>_no` / `<stem>_key` where a table with the same stem
      (singular/plural, snake/camel; a trailing Salesforce `__c` aside, words before the stem allowed:
      `ERP_Customer_No__c`) is keyed by `code`/`no`/`key` or `<stem>_code`/`_no`/`_key`, or has no key and a column
      `code`/`no`/`key` that is unique and never NULL in the rows (that column then becomes its key, rule R5); or a role
      name (`ship_to_id`, `created_by`, `approved_by`) whose role word says what the table holds (an address, a
      person). Runs only when plan() is given `execute`, for columns R0–R4 left unlinked. Planned only when the rows
      support it: same type family, every non-NULL value of the column is in the table's key, at least two distinct
      values, and exactly one table qualifies. Otherwise it goes to plan.proposed with the reason, never applied.
      Same-named columns (`code`, `name`) in two unrelated tables are never compared with each other.
A column that could point at two tables is reported as ambiguous and not applied.

SAP pack (before K2–K5 and R1–R4): when two or more tables are tables a knowledge pack describes (sap_pack.py,
fabric_backend/packs/sap/), with or without a prefix (`VBAK`, `vbak`, `sap_vbak`), their keys and the relationships
between them come from the pack, with the rule "SAP pack" and the public source on the relationship's note. Name
rules add nothing between two such tables (`LIPS.VBELN` is a delivery, not an order). Declared keys (K0), the
caller's keys (K1) and confirmed relationships still win. A schema without such tables gets exactly the plan it got
before. The pack is a suggestion with a source; validate_plan checks it against the rows.
A pack join that is not an equality on the target's key goes to plan.extended (ExtendedRelationship), never to
plan.relationships: kind "unique" (a unique column set of the target that is not its key, CVI_CUST_LINK.PARTNER_GUID ->
BUT000) and kind "valid_on" (the key without its valid-to column, plus a date inside the target row's period,
ACDOCA.RCNTR on BUDAT -> CSKS DATAB..DATBI); and any join that holds only where a column has given values (where:
VBFA.VBELN -> LIKP for rows whose VBTYP_N is a delivery). Everything built from plan.relationships stays a key join.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .schema import Schema, Table


@dataclass
class Relationship:
    source: str                      # the table holding the reference (the "many" side)
    source_cols: list[str]
    target: str                      # the table being pointed at (the "one" side)
    target_cols: list[str]
    rule: str                        # R0..R5, "SAP pack", or "confirmed"
    field_name: str = ""             # GraphQL field on the source, e.g. "customer"
    reverse_name: str = ""           # GraphQL field on the target, e.g. "orders"
    note: str = ""                   # how the name was read when it was not literal: "through the synonym table: kund -> customer"

    @property
    def key(self) -> tuple:
        return (self.source, tuple(c.lower() for c in self.source_cols), self.target)


@dataclass
class ExtendedRelationship(Relationship):
    """A relationship that is not an equality join on the target's key, so it lives in plan.extended and not in
    plan.relationships (which the API, the semantic model, the views and the notebooks read as key joins):
      kind "unique":   equality on a unique column set of the target that is not its key (KONV.KNUMV -> VBAK.KNUMV,
                       CVI_CUST_LINK.PARTNER_GUID -> BUT000.PARTNER_GUID);
      kind "valid_on": equality on the target's key without its validity column, plus a date of the source row that
                       falls in the target row's validity period (ACDOCA.RCNTR on BUDAT -> CSKS.KOSTL, DATAB..DATBI).
    valid_on = {"source_date": ..., "target_from": ..., "target_to": ...} for kind "valid_on".
    valid_on may say {"on": "today", ...} instead of a source_date: the target row valid on the date of the call
    (KNA1.ADRNR -> ADRC, DATE_FROM..DATE_TO).
    where: filters that say for which rows the join holds, on either side, as [{"side": "source"|"target", "column": ...,
    "in": [values]}], or {"blank": true} for SAP's blank (NULL, '' or ' ': ADRC.NATION, the standard version): VBFA.VBELN -> LIKP where VBFA.VBTYP_N is a delivery, EKBE -> RBKP where EKBE.VGABE is '2'. Any kind
    can carry them, a key join too; a filtered relationship always lives in plan.extended."""
    kind: str = "unique"
    valid_on: dict | None = None
    cardinality: str = "many-to-one"
    where: list = field(default_factory=list)

    def filter_sql(self, side: str, alias: str, quote=lambda c: f"[{c}]") -> list[str]:
        """The where entries of one side as SQL conditions: s.[VBTYP_N] IN ('J', 'T')."""
        out = []
        for w in self.where:
            if w["side"] != side:
                continue
            col = f"{alias}.{quote(w['column'])}"
            if w.get("blank"):                                          # NULL, '' or ' ': however the tool wrote SAP's blank
                out.append(f"COALESCE(LTRIM(RTRIM({col})), '') = ''")
            else:
                values = ", ".join("'" + str(v).replace("'", "''") + "'" for v in w["in"])
                out.append(f"{col} IN ({values})")
        return out

    def period_sql(self, source_alias: str = "s", target_alias: str = "t", quote=lambda c: f"[{c}]", today: str | None = None) -> str:
        """For kind valid_on: the date inside the target row's period. The date is the source row's (source_date), or
        with on="today" the date of the call as text in SAP's YYYYMMDD form, the form SAP stores dates in."""
        v = self.valid_on or {}
        if v.get("on") == "today":
            from datetime import date
            when = "'" + (today or date.today().strftime("%Y%m%d")) + "'"
        else:
            when = f"{source_alias}.{quote(v['source_date'])}"
        return f"{when} BETWEEN {target_alias}.{quote(v['target_from'])} AND {target_alias}.{quote(v['target_to'])}"

    def join_sql(self, source_alias: str = "s", target_alias: str = "t", quote=lambda c: f"[{c}]") -> str:
        """The ON clause of the join, in the target's terms."""
        on = [f"{source_alias}.{quote(a)} = {target_alias}.{quote(b)}" for a, b in zip(self.source_cols, self.target_cols)]
        if self.kind == "valid_on" and self.valid_on:
            on.append(self.period_sql(source_alias, target_alias, quote))
        on += self.filter_sql("source", source_alias, quote) + self.filter_sql("target", target_alias, quote)
        return " AND ".join(on)


@dataclass
class Plan:
    schema: Schema
    keys: dict[str, tuple[list[str], str]] = field(default_factory=dict)  # table -> (cols, rule)
    relationships: list[Relationship] = field(default_factory=list)
    ambiguous: list[dict] = field(default_factory=list)
    keyless: list[str] = field(default_factory=list)
    synonyms: list[dict] = field(default_factory=list)    # keys and relationships that rest on the synonym table (SYNONYMS)
    pack: dict | None = None                               # what a knowledge pack recognised (sap_pack.py); None when none did
    extended: list = field(default_factory=list)          # ExtendedRelationship: joins on a unique non-key column or valid on a date
    proposed: list[dict] = field(default_factory=list)    # R5 candidates the rows did not support, each with its reason; never applied

    def summary(self) -> str:
        lines = [f"{len(self.schema)} tables, {len(self.keys)} with keys, {len(self.relationships)} relationships"]
        if self.keyless:
            lines.append("no key (query only; can reference others, cannot be referenced): " + ", ".join(self.keyless))
        if self.ambiguous:
            lines.append(f"{len(self.ambiguous)} ambiguous columns not applied — see plan.ambiguous")
        if self.synonyms:
            lines.append(f"{len(self.synonyms)} name(s) read through the synonym table (translations, abbreviations) — see plan.synonyms")
        if self.proposed:
            lines.append(f"{len(self.proposed)} code or role column(s) the rows did not support (R5), not applied — see plan.proposed")
        if self.pack:
            lines.append(f"{len(self.pack['tables'])} table(s) recognised by the {self.pack['pack']} pack: keys and relationships from its "
                         f"public sources (rule \"{self.pack['rule']}\"), to be checked with validate_plan — see plan.pack")
        return "\n".join(lines)

    def mermaid(self) -> str:
        out = ["erDiagram"]
        for t in self.schema:
            out.append(f"  {_m(t.name)} {{")
            for c in t.column_names:
                mark = " PK" if c in self.keys.get(t.name, ([], ""))[0] else ""
                out.append(f"    {_m(c)} {_m(_type_word(t, c))}{mark}")
            out.append("  }")
        for r in self.relationships:
            out.append(f'  {_m(r.target)} ||--o{{ {_m(r.source)} : "{"+".join(r.source_cols)} {r.rule}"')
        return "\n".join(out)


# The rules, in the words of the docstring above. The site's demo and the MCP tools quote these, so the
# wording users read is the wording the engine documents. Kept in sync by a test.
RULES = {
    "K0": "declared primary key",
    "K1": "`keys` override from the caller",
    "K2": "a column named `id`, `no`, `nr`, `<table>_id`, `<table>id`, `<singular>_id`, `<singular>id`, `<table>_key`, `<table>_code`, "
          "`<table>_nr`, `<table>_no`, `<table>_sk`, `<table>_bk`, or an abbreviation of the table name (four letters or more) with one of those "
          "suffixes (`<table>snr` too: the Swedish genitive, `Leverantorsnr` in `Leverantor`); a leading `dim_`/`fact_`/`tbl_` is not part of the table's name; when nothing matches literally, the same through the "
          "synonym table (`KundNr` in `kunder`, `cust_id` in `dim_customer`), reported under `synonyms`",
    "K3": "nothing — the table gets no key; it can be queried but not by pk, and nothing can point at it",
    "K4": "junction: no column names a key and the table starts with two or more reference columns; together they are the key "
          "(not applied to history tables with a start_*/valid_from/effective_* column)",
    "K5": "line: no column names a key; the reference to the header table plus a line-number column (line_no, position, seq…)",
    "R0": "declared foreign key",
    "R1": "column named `<B>_id` / `<B>id` / `<singular B>_id` / `<singular B>id` (also _key, _code, _nr, _no, _sk, _bk) where B has a single key",
    "R2": "column has exactly the same name as B's single key column, and that name is not just `id`",
    "R3": "all of B's composite key columns appear in A",
    "R4": "weaker name match when R1 and R2 find nothing: the R1/R2 shapes through the synonym table (`Kunde_ID` → `Kunden`, `cust_id` → "
          "`customers`, noted on the relationship), a role before B's name (`manager_staff_id` → staff), or an abbreviation of B of four "
          "letters or more (`o_custkey` → customer); never across suffixes (`wwi_order_id` does not point at a table keyed by `order_key`)",
    "R5": "checked against the rows: a code column `<stem>_code` / `<stem>_no` / `<stem>_key` where a table with the same stem "
          "(singular/plural, snake/camel) has the key `code`/`no`/`key`, or a role name (`ship_to_id`, `created_by`, `approved_by`) "
          "whose role word says what the table holds; planned only when every value is in that table's key, the type family is "
          "the same, there are two or more distinct values and one table qualifies, otherwise proposed with the reason",
    "confirmed": "given by the caller in `confirmed=[...]`, applied as-is, before inference",
}

_SPLIT = re.compile(r"[^a-z0-9]+")
_SUFFIXES = ("id", "key", "code", "nr", "no", "sk", "bk")
_SUFFIX_RE = re.compile(r"^(.*?)(id|key|code|nr|no|sk|bk)$")
_HEADER = ("header", "hdr")
_TRANSLIT = str.maketrans({"å": "a", "ä": "a", "ö": "o", "ü": "u", "ß": "ss", "é": "e", "è": "e", "ø": "o", "æ": "ae"})
_IRREGULAR = {"people": "person", "children": "child", "men": "man", "women": "woman", "indices": "index", "matrices": "matrix",
              "criteria": "criterion", "mice": "mouse", "geese": "goose", "staff": "staff", "data": "data"}
TABLE_PREFIXES = ("tbl", "t", "dim", "fact", "stg", "vw", "v", "ref", "lkp")      # a leading word that says what kind of table, not what it holds

# The synonym table: a word as it appears in a name -> the English singular the rest of the names use. Abbreviations
# first, then Swedish and German business words in singular and plural (after transliteration, so `leverantörer` is
# `leverantorer`). Used by K2, R1, R2 and R4 when the raw name finds nothing; every such match is reported in
# plan.synonyms and on the relationship's `note`, so a user can see that the link rests on this table.
SYNONYMS = {
    # abbreviations
    "cust": "customer", "prod": "product", "ord": "order", "emp": "employee", "inv": "invoice", "acct": "account", "acc": "account",
    "addr": "address", "cat": "category", "dept": "department", "dep": "department", "supp": "supplier", "vend": "vendor",
    "whs": "warehouse", "mgr": "manager", "org": "organization", "terr": "territory", "trans": "transaction", "txn": "transaction",
    "ctry": "country", "cntry": "country", "curr": "currency", "loc": "location", "proj": "project", "pos": "position",
    # Swedish
    "kund": "customer", "kunder": "customer", "artikel": "product", "artiklar": "product", "produkt": "product", "produkter": "product",
    "ordrar": "order", "faktura": "invoice", "fakturor": "invoice", "leverantor": "supplier", "leverantorer": "supplier",
    "anstalld": "employee", "anstallda": "employee", "medarbetare": "employee", "lager": "warehouse", "avdelning": "department",
    "avdelningar": "department", "adress": "address", "adresser": "address", "land": "country", "lander": "country", "konto": "account",
    "konton": "account", "betalning": "payment", "betalningar": "payment", "projekt": "project", "kategori": "category",
    "kategorier": "category", "butik": "store", "butiker": "store", "region": "region", "regioner": "region", "valuta": "currency",
    "valutor": "currency", "avtal": "contract", "person": "person", "personer": "person", "foretag": "company", "bolag": "company",
    # German
    "kunde": "customer", "kunden": "customer", "bestellung": "order", "bestellungen": "order", "auftrag": "order", "auftraege": "order",
    "auftrage": "order", "rechnung": "invoice", "rechnungen": "invoice", "lieferant": "supplier", "lieferanten": "supplier",
    "mitarbeiter": "employee", "abteilung": "department", "abteilungen": "department", "adresse": "address", "adressen": "address",
    "laender": "country", "konten": "account", "zahlung": "payment", "zahlungen": "payment", "produkte": "product", "kategorien": "category",
    "filiale": "store", "filialen": "store", "waehrung": "currency", "wahrung": "currency", "waehrungen": "currency", "vertrag": "contract",
    "vertraege": "contract", "vertrage": "contract", "firma": "company", "firmen": "company", "personen": "person", "standort": "location",
    "standorte": "location",
}
_PREFIX = re.compile(r"^([a-z]{1,4})_(?=.)")
_LINE_LIKE = {"line", "lineno", "linenumber", "linenr", "linenum", "position", "pos", "seq", "sequence", "seqno",
              "itemno", "rowno", "rownumber", "rad", "radnr", "radnummer", "zeile", "zeilennr", "zeilennummer", "posnr", "positionsnr"}
PACK_RULE = "SAP pack"
# Not in RULES: the rule tables a plan renders (data dictionary, docs) list it only when a pack was used, so answers on
# schemas without SAP tables stay as they were.
PACK_RULES = {PACK_RULE: "keys and relationships of tables a knowledge pack describes (fabric_backend/packs/sap/: VBAK, VBAP, LIKP, "
                         "VBRK…), recognised with or without a prefix; each relationship names its public source; name rules add "
                         "nothing between two such tables"}
_CLIENT = ("MANDT", "RCLNT")
_HISTORY = re.compile(r"^(start|validfrom|effective)|from$")
_MIN_ABBREVIATION = 4


def _norm(s: str) -> str:
    return _SPLIT.sub("", s.lower().translate(_TRANSLIT))


def _words(name: str) -> list[str]:
    """`ShipToAddressID` -> [ship, to, address, id]; `manager_staff_id` -> [manager, staff, id]; `Leverantörer` -> [leverantorer]."""
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name)
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", s)
    return [w for w in _SPLIT.split(s.lower().translate(_TRANSLIT)) if w]


def _canon(words: list[str]) -> str:
    """The words with each one replaced by its synonym-table entry, joined: [kund, nr] -> customernr; [cust] -> customer."""
    return "".join(SYNONYMS.get(w, w) for w in words)


def _content_words(table: str) -> list[str]:
    """The words of a table name without a leading kind prefix: dim_customer -> [customer], tbl_orders -> [orders]."""
    w = _words(table)
    return w[1:] if len(w) > 1 and w[0] in TABLE_PREFIXES else w


def _singulars(name: str) -> set[str]:
    n = name.lower()
    out = {n}
    for plural, singular in _IRREGULAR.items():
        if n.endswith(plural) and (len(n) == len(plural) or not n[-len(plural) - 1].isalpha()) or n == plural:
            out.add(n[: -len(plural)] + singular)
    if n.endswith("ies"):
        out.add(n[:-3] + "y")
    if n.endswith("sses") or n.endswith("xes") or n.endswith("ches") or n.endswith("shes"):
        out.add(n[:-2])
    if n.endswith("s") and not n.endswith("ss"):
        out.add(n[:-1])
    return out


def _bases(table: str) -> set[str]:
    """The normalised names a key or reference may use for `table`: its singular forms, the same without a
    trailing `header` (SalesOrderHeader is keyed by SalesOrderID and referenced as SalesOrderID), and the same
    without a leading kind prefix (dim_customer answers to customer)."""
    out = {_norm(x) for x in _singulars(table)}
    n = table.lower()
    for h in _HEADER:
        for sep in ("_", ""):
            if n.endswith(sep + h) and len(n) > len(h) + len(sep):
                out |= {_norm(x) for x in _singulars(n[: -len(h) - len(sep)])}
    content = _content_words(table)
    if content != _words(table):
        out |= {_norm(x) for x in _singulars("".join(content))}
    return {b for b in out if b}


def _canon_bases(table: str) -> set[str]:
    """The bases a key or reference may use for `table` through the synonym table: kunder -> customer, Kunden ->
    customer, dim_kund -> customer. Only the forms the raw bases do not already contain."""
    words = _content_words(table)
    canon = _canon(words)
    raw = _bases(table)
    out = {_norm(x) for x in _singulars(canon)} if canon != "".join(words) else set()
    for h in _HEADER:                                               # orderheader -> order, through the synonym too
        if len(words) > 1 and words[-1] == h:
            c = _canon(words[:-1])
            if c != "".join(words[:-1]):
                out |= {_norm(x) for x in _singulars(c)}
    return {b for b in out if b and b not in raw}


def _key_candidates(table: str, synonyms: bool = False) -> set[str]:
    c = {"id", "no", "nr"} if not synonyms else set()      # a bare No / Nr is the key of its table, as in many ERP exports
    for b in (_canon_bases(table) if synonyms else _bases(table)):
        c.update(b + suf for suf in _SUFFIXES)
        c.update(b + "s" + suf for suf in ("nr", "nummer"))   # the Swedish genitive: Leverantorsnr in Leverantor
    return c


def _ref_candidates(target: str, synonyms: bool = False) -> set[str]:
    c = set()
    for b in (_canon_bases(target) if synonyms else _bases(target)):
        c.update(b + suf for suf in _SUFFIXES)
        c.update(b + "s" + suf for suf in ("nr", "nummer"))
    return c


def _canon_column(col: str) -> str:
    """The column name with its words passed through the synonym table: KundNr -> customernr, Kunde_ID -> customerid,
    cust_key -> customerkey. Equal to the plain normalised name when no word is in the table."""
    return _canon(_words(col))


def _table_prefix(t: Table) -> str:
    """`n_` when every column of NATION is N_…: a prefix shared by all columns is not part of the name."""
    if len(t.columns) < 2:
        return ""
    found = set()
    for c in t.column_names:
        m = _PREFIX.match(c.lower())
        if not m:
            return ""
        found.add(m.group(1))
    return found.pop() if len(found) == 1 else ""


def _strip_prefix(col: str, prefix: str) -> str:
    return col[len(prefix) + 1:] if prefix and col.lower().startswith(prefix + "_") else col


def _bare(t: Table, prefix: str) -> dict[str, str]:
    """column name -> normalised name without the table-wide prefix."""
    return {c: _norm(_strip_prefix(c, prefix)) for c in t.column_names}


def _stem(col: str) -> tuple[list[str], str]:
    """Words before the reference suffix, and the suffix: `ShipToAddressID` -> ([ship, to, address], "id"),
    `custkey` -> ([cust], "key"); ([], "") when the column carries no such suffix."""
    words = _words(col)
    if not words:
        return [], ""
    if words[-1] in _SUFFIXES:
        return words[:-1], words[-1]
    m = _SUFFIX_RE.match(words[-1])
    if m and m.group(1):
        return words[:-1] + [m.group(1)], m.group(2)
    return [], ""


def _first_word(table: str) -> str:
    w = _words(table)
    return w[0] if w else ""


def _abbreviates(stem: str, table: str) -> bool:
    """`cust` abbreviates `customer` (the first word of the table's name): a proper prefix of at least four letters,
    or an entry of the synonym table that names the table's first word (`ord` -> order, `emp` -> employee)."""
    first = _first_word(table)
    if len(stem) >= _MIN_ABBREVIATION and len(stem) < len(first) and first.startswith(stem):
        return True
    canon = SYNONYMS.get(stem)
    return bool(canon) and canon != stem and canon in _singulars(first) | {_canon([first])}


def _role_targets(stem: list[str], tables: dict[str, set[str]]) -> list[str]:
    """`[ship, to, address]` ends with the base `address` on a word boundary, with a role before it -> [Address].
    The longest base wins; two different tables with the same longest base are both returned (ambiguous)."""
    best, hits = 0, []
    for table, bases in tables.items():
        for k in range(1, len(stem)):
            tail = "".join(stem[k:])
            if tail in bases:
                if len(tail) > best:
                    best, hits = len(tail), [table]
                elif len(tail) == best and table not in hits:
                    hits.append(table)
                break
    return hits


def infer_keys(schema: Schema, keys: dict[str, list[str]] | None = None, notes: list[dict] | None = None,
               pack_keys: dict[str, list[str]] | None = None) -> dict[str, tuple[list[str], str]]:
    keys = {k.lower(): v for k, v in (keys or {}).items()}
    out: dict[str, tuple[list[str], str]] = {}
    for t in schema:
        if t.name.lower() in keys:
            out[t.name] = ([t.col(c) for c in keys[t.name.lower()]], "K1")
        elif t.keys:
            out[t.name] = (list(t.keys), "K0")
        elif pack_keys and t.name in pack_keys:
            out[t.name] = (list(pack_keys[t.name]), PACK_RULE)
        else:
            prefix = _table_prefix(t)
            bare = _bare(t, prefix)
            cands = _key_candidates(t.name)
            hits = [c for c in t.column_names if bare[c] in cands]
            # prefer the most specific name: <table>_id over id
            hits.sort(key=lambda c: (bare[c] == "id", len(c)))
            via = ""
            if not hits:                                                   # the synonym table: KundNr in kunder, cust_id in dim_customer
                syn = _key_candidates(t.name, synonyms=True) | cands
                hits = [c for c in t.column_names if _canon_column(_strip_prefix(c, prefix)) in syn and bare[c] != "id"]
                hits.sort(key=len)
                via = "synonym"
            if not hits:                                                   # abbreviation: cust_key in customer
                others = set().union(*(_bases(o.name) | _canon_bases(o.name) for o in schema if o.name != t.name)) if len(schema) > 1 else set()
                for c in t.column_names:
                    stem, suf = _stem(_strip_prefix(c, prefix))
                    # ps_partkey in PARTSUPP names PART, another table: a reference, not an abbreviated key
                    if suf and len(stem) == 1 and _abbreviates(stem[0], t.name) and stem[0] not in others:
                        hits.append(c)
                hits.sort(key=len)
                via = "abbreviation"
            if hits:
                out[t.name] = ([hits[0]], "K2")
                if via == "synonym" and notes is not None:
                    notes.append({"table": t.name, "column": hits[0], "rule": "K2", "via": _synonym_words(t.name, hits[0])})
    return out


def _synonym_words(*names: str) -> str:
    """Which entries of the synonym table a match rested on: `kunder -> customer, kund -> customer`."""
    used = []
    for name in names:
        for w in _content_words(name):
            if w in SYNONYMS and SYNONYMS[w] != w and f"{w} -> {SYNONYMS[w]}" not in used:
                used.append(f"{w} -> {SYNONYMS[w]}")
    return ", ".join(used)


def infer_relationships(schema: Schema, keys: dict[str, tuple[list[str], str]],
                        confirmed: list[dict] | None = None, notes: list[dict] | None = None,
                        pack: list[dict] | None = None, pack_tables: set[str] | None = None) -> tuple[list[Relationship], list[dict]]:
    """confirmed: [{"source": "orders", "source_cols": ["customer_id"], "target": "customers",
    "target_cols": ["customer_id"]}] — applied as-is, before inference, and never contradicted."""
    rels: list[Relationship] = []
    ambiguous: list[dict] = []
    seen: set[tuple] = set()

    def add(r: Relationship) -> None:
        if r.key in seen:
            return
        seen.add(r.key)
        rels.append(r)

    names = {t.name.lower(): t for t in schema}
    pinned: set[tuple[str, str]] = set()                                  # (table, column) a confirmed entry already links
    for c in confirmed or []:
        src, tgt = names.get(str(c["source"]).lower()), names.get(str(c["target"]).lower())
        scols = [src.col(str(x)) if src else x for x in c["source_cols"]]  # the schema's own spelling, as check_input accepts any case
        tcols = [tgt.col(str(x)) if tgt else x for x in (c.get("target_cols") or c["source_cols"])]
        add(Relationship(src.name if src else c["source"], scols, tgt.name if tgt else c["target"], tcols,
                         "confirmed", field_name=c.get("field_name") or "", reverse_name=c.get("reverse_name") or ""))
        if src and len(scols) == 1:
            pinned.add((src.name, scols[0]))
    pack_tables = pack_tables or set()
    for r in pack or []:                                                  # SAP pack: after confirmed, before the name rules
        rel = Relationship(r["source"], list(r["source_cols"]), r["target"], list(r["target_cols"]), PACK_RULE, note=r.get("note", ""))
        if (r["source"], tuple(c.lower() for c in r["source_cols"])) in {(x.source, tuple(c.lower() for c in x.source_cols)) for x in rels if x.rule == "confirmed"}:
            continue
        add(rel)
        pinned.update((r["source"], c) for c in r["source_cols"] if c.upper() not in _CLIENT)

    prefixes = {t.name: _table_prefix(t) for t in schema}
    bares = {t.name: _bare(t, prefixes[t.name]) for t in schema}
    single_key: dict[str, str] = {t: k[0] for t, (k, _) in keys.items() if len(k) == 1}
    by_ref_name: dict[str, list[str]] = {}
    by_key_name: dict[str, list[str]] = {}                                # R2 index: normalised key column -> tables
    by_syn_ref: dict[str, list[str]] = {}                                 # the same two indexes through the synonym table
    by_syn_key: dict[str, list[str]] = {}
    bases_of: dict[str, set[str]] = {}
    key_suffix: dict[str, str] = {}
    for t, k in single_key.items():
        for cand in _ref_candidates(t):
            by_ref_name.setdefault(cand, []).append(t)
        for cand in _ref_candidates(t, synonyms=True):
            by_syn_ref.setdefault(cand, []).append(t)
        by_key_name.setdefault(bares.get(t, {}).get(k, _norm(k)), []).append(t)
        by_syn_key.setdefault(_canon_column(_strip_prefix(k, prefixes.get(t, ""))), []).append(t)
        bases_of[t] = _bases(t) | _canon_bases(t)
        key_suffix[t] = _stem(_strip_prefix(k, prefixes.get(t, "")))[1]

    for t in schema:
        own_key = set(x.lower() for x in keys.get(t.name, ([], ""))[0])
        bare = bares[t.name]
        for cols, target, tcols in t.foreign_keys:                     # R0
            if target in schema and not (len(cols) == 1 and (t.name, cols[0]) in pinned):
                add(Relationship(t.name, cols, target, tcols, "R0"))
        in_pack = t.name in pack_tables
        for c in t.column_names:
            if (c.lower() in own_key and len(own_key) == 1) or (t.name, c) in pinned:  # confirmed: never inferred again or ambiguous
                continue
            n = bare[c]
            via = ""
            targets = [b for b in by_ref_name.get(n, []) if b != t.name]  # R1
            rule = "R1"
            if not targets and n != "id":                                 # R2
                targets = [b for b in by_key_name.get(n, []) if b != t.name]
                rule = "R2"
            if not targets and n != "id":                                 # R4 (a): the R1 and R2 shapes through the synonym table
                cn = _canon_column(_strip_prefix(c, prefixes[t.name]))
                targets = [b for b in by_syn_ref.get(cn, []) + by_ref_name.get(cn, []) if b != t.name]
                if not targets:
                    targets = [b for b in by_syn_key.get(cn, []) if b != t.name]
                rule = "R4"
                if targets:
                    via = "synonym"
                    stem, suf = _stem(_strip_prefix(c, prefixes[t.name]))
                    if suf and len(stem) == 1:                           # prod_id with both products and producers: still ambiguous
                        targets += [b for b in single_key if b != t.name and b not in targets and _abbreviates(stem[0], b)]
            if not targets:                                               # R4: role before the name, or abbreviation
                stem, suf = _stem(_strip_prefix(c, prefixes[t.name]))
                if suf:
                    cstem = [SYNONYMS.get(w, w) for w in stem]
                    targets = [b for b in _role_targets(stem, bases_of) if b != t.name] or [b for b in _role_targets(cstem, bases_of) if b != t.name]
                    if not targets and len(stem) == 1:
                        targets = [b for b in single_key if b != t.name and _abbreviates(stem[0], b)]
                    # the weakest rule does not cross suffixes: `WWI Order ID` is not a reference to a table keyed by `Order Key`
                    targets = [b for b in targets if not key_suffix.get(b) or key_suffix[b] == suf or {key_suffix[b], suf} <= {"id", "key", "sk"} and key_suffix[b] == suf]
                    rule = "R4"
                    if targets and cstem != stem:
                        via = "synonym"
            if in_pack:                                                   # between two pack tables the pack has said it all
                targets = [b for b in targets if b not in pack_tables]
            if len(targets) > 1:                                         # two tables answer to the name: the one whose key carries
                suf = _stem(_strip_prefix(c, prefixes[t.name]))[1]       # the column's suffix wins (customer_sk -> dim_customer, not customers)
                narrowed = [b for b in targets if key_suffix.get(b) == suf]
                if len(narrowed) == 1:
                    targets = narrowed
            if len(targets) > 1:
                ambiguous.append({"table": t.name, "column": c, "candidates": targets, "rule": rule})
                continue
            if targets:
                b = targets[0]
                r = Relationship(t.name, [c], b, [single_key[b]], rule)
                if via == "synonym":
                    r.note = "through the synonym table: " + (_synonym_words(c, b) or "a translated or abbreviated name")
                    if notes is not None:
                        notes.append({"table": t.name, "column": c, "target": b, "rule": rule, "via": _synonym_words(c, b)})
                add(r)
        for b, (bk, _) in keys.items():                                  # R3
            if b == t.name or len(bk) < 2 or (in_pack and b in pack_tables):
                continue
            bbare = bares[b]
            wanted = [bbare.get(k, _norm(k)) for k in bk]
            mine = {v: k for k, v in bare.items()}
            if all(w in mine for w in wanted) and set(x.lower() for x in bk) != own_key:
                add(Relationship(t.name, [mine[w] for w in wanted], b, list(bk), "R3"))

    _name_fields(rels, prefixes)
    return rels, ambiguous


_CODE_WORDS = ("code", "no", "key")                     # R5: the suffixes of a code column and the bare keys it points at
_ROLE_END = ("id", "by", "key", "no", "code", "nr")     # R5: the last word of a role name (ship_to_id, created_by)
R5_MIN_DISTINCT = 2


def _family(data_type: str) -> str:
    t = (data_type or "").lower()
    return "number" if any(w in t for w in ("int", "decimal", "double", "float", "numeric", "real", "number", "money")) else \
           "date" if "date" in t or "time" in t else "text"


def _r5_candidates(schema: Schema, keys: dict[str, tuple[list[str], str]], linked: set[tuple[str, str]],
                   pack_tables: set[str]) -> list[dict]:
    """Columns R0–R4 left unlinked that R5 could link, each with every table that answers to its name:
    {"source", "column", "kind": "code"|"role", "targets": [(table, key column, needs_key)]}."""
    from .graphs import ROLE_WORDS                                    # lazily: graphs imports this module
    single = {t: k[0] for t, (k, _) in keys.items() if len(k) == 1}
    out = []
    for t in schema:
        prefix = _table_prefix(t)
        own = {c.lower() for c in keys.get(t.name, ([], ""))[0]}
        for c in t.column_names:
            if c.lower() in own or (t.name, c.lower()) in linked:
                continue
            words = _words(_strip_prefix(c, prefix))
            if len(words) > 2 and words[-1] == "c" and c.lower().endswith("__c"):
                words = words[:-1]                                    # Salesforce's custom-field suffix
            found: list[tuple[str, str, bool]] = []
            kind = ""
            if len(words) >= 2 and words[-1] in _CODE_WORDS:          # <stem>_code / _no / _key
                suf, stem = words[-1], words[:-1]
                for b in schema:
                    if b.name == t.name or (t.name in pack_tables and b.name in pack_tables):
                        continue
                    bases = _bases(b.name)
                    if not any("".join(stem[k:]) in bases for k in range(len(stem))):
                        continue
                    bprefix = _table_prefix(b)
                    keyed = {_norm(x) + suf for x in bases} | {suf}
                    if b.name in single:
                        if _norm(_strip_prefix(single[b.name], bprefix)) in keyed:
                            found.append((b.name, single[b.name], False))
                    elif b.name not in keys:
                        bare = [x for x in b.column_names if _norm(_strip_prefix(x, bprefix)) == suf]
                        if len(bare) == 1:
                            found.append((b.name, bare[0], True))
                kind = "code"
            if not found and len(words) >= 2 and words[-1] in _ROLE_END:  # role name: ship_to_id, created_by
                for roles, nouns, _why in ROLE_WORDS:
                    if not set(words[:-1]) & roles:
                        continue
                    for b, k in single.items():
                        if b == t.name or (t.name in pack_tables and b in pack_tables):
                            continue
                        bwords = set(_content_words(b)) | {w for x in _singulars(b) for w in _words(x)}
                        if bwords & nouns:
                            found.append((b, k, False))
                    kind = "role"
                    break
            if found:
                out.append({"source": t.name, "column": c, "kind": kind, "targets": found})
    return out


def _r5_check(schema: Schema, execute, source: str, column: str, target: str, key: str, needs_key: bool) -> tuple[bool, str]:
    """Count in the rows whether source.column can point at target.key: (supported, what was counted)."""
    from . import evidence
    from .dialects import of as dialect_of
    s, b = schema[source], schema[target]
    types = {x.name: x.data_type for x in s.columns}, {x.name: x.data_type for x in b.columns}
    fa, fb = _family(types[0][column]), _family(types[1][key])
    if fa != fb:
        return False, f"{source}.{column} is {fa}, {target}.{key} is {fb}"
    dialect = dialect_of(execute)
    try:
        if needs_key:
            row = (list(execute(evidence.key_sql(schema.schema, target, [key], dialect))) or [{}])[0]
            n, nulls, d = (evidence._int(row.get(x)) for x in ("n", "nulls", "distinct_keys"))
            if not n or nulls or d != n:
                return False, f"{target}.{key} is not unique and non-NULL in the rows ({n} rows, {d} distinct, {nulls} NULL), so it is no key"
        row = (list(execute(evidence.inclusion_sql(schema.schema, source, column, target, key, dialect))) or [{}])[0]
    except Exception as e:                                         # noqa: BLE001 - a candidate the rows could not answer stays a proposal
        return False, f"could not count: {type(e).__name__}: {e}"
    with_value, matched, distinct = (evidence._int(row.get(x)) for x in ("with_value", "matched", "distinct_values"))
    if not with_value:
        return False, f"{source}.{column} has no values to compare"
    if matched != with_value:
        return False, f"{with_value - matched} of {with_value} value(s) of {source}.{column} are not in {target}.{key}"
    if distinct < R5_MIN_DISTINCT:
        return False, f"{source}.{column} has {distinct} distinct value: too few to tell"
    return True, f"{with_value} of {with_value} value(s) ({distinct} distinct) of {source}.{column} are in {target}.{key}, same type family ({fa})"


def infer_from_rows(schema: Schema, keys: dict[str, tuple[list[str], str]], rels: list[Relationship], ambiguous: list[dict],
                    execute, pack_tables: set[str] | None = None) -> tuple[list[Relationship], dict[str, tuple[list[str], str]], list[dict]]:
    """R5: the code and role columns R0–R4 left unlinked, checked against the rows. Returns the relationships the rows
    support, the keys R5 gave keyless targets, and the proposals with their reasons (plan.proposed)."""
    linked = {(r.source, c.lower()) for r in rels for c in r.source_cols} | {(a["table"], a["column"].lower()) for a in ambiguous}
    new_rels: list[Relationship] = []
    new_keys: dict[str, tuple[list[str], str]] = {}
    proposed: list[dict] = []
    for cand in _r5_candidates(schema, keys, linked, pack_tables or set()):
        src, col = cand["source"], cand["column"]
        results = [(b, k, nk) + _r5_check(schema, execute, src, col, b, k, nk) for b, k, nk in cand["targets"]]
        ok = [r for r in results if r[3]]
        if len(ok) == 1:
            b, k, nk, _, why = ok[0]
            if nk:
                new_keys[b] = ([k], "R5")
            new_rels.append(Relationship(src, [col], b, [k], "R5", note=f"R5 ({cand['kind']} column), counted in the rows: {why}"))
            continue
        for b, k, nk, supported, why in results:
            reason = why if not supported else f"the rows fit {len(ok)} tables ({', '.join(r[0] for r in ok)}); which one is for a person to say"
            proposed.append({"source": src, "source_cols": [col], "target": b, "target_cols": [k], "rule": "R5", "kind": cand["kind"],
                             "reason": reason, "confirmed": {"source": src, "source_cols": [col], "target": b, "target_cols": [k]}})
    return new_rels, new_keys, proposed


def _line_like(col: str) -> bool:
    """`line_no`, `LineNumber`, `position`, `order_line`, `item_seq`: the last word (or two) names a line number."""
    w = _words(col)
    return bool(w) and (w[-1] in _LINE_LIKE or "".join(w[-2:]) in _LINE_LIKE)


def composite_keys(schema: Schema, keys: dict[str, tuple[list[str], str]],
                   rels: list[Relationship]) -> dict[str, tuple[list[str], str]]:
    """K5 and K4 for the tables still without a key, from the single-column references already inferred or confirmed."""
    out: dict[str, tuple[list[str], str]] = {}
    for t in schema:
        if t.name in keys:
            continue
        prefix = _table_prefix(t)
        bare = _bare(t, prefix)
        refs = [r for r in rels if r.source == t.name and len(r.source_cols) == 1]
        if not refs:
            continue
        ref_cols = [r.source_cols[0] for r in refs]
        lines = [c for c in t.column_names if c not in ref_cols and _line_like(_strip_prefix(c, prefix))]
        if lines:                                                                                          # K5
            stem = _first_word(t.name).rstrip("s")
            header = [r for r in refs if _first_word(r.target).rstrip("s").startswith(stem)
                      or stem.startswith(_first_word(r.target).rstrip("s"))]
            ref = min(header or refs, key=lambda r: t.column_names.index(r.source_cols[0]))
            out[t.name] = ([ref.source_cols[0], lines[0]], "K5")
            continue
        if any(_HISTORY.search(bare[c]) for c in t.column_names):
            continue
        leading = []
        for c in t.column_names:                                                                           # K4
            if c in ref_cols:
                leading.append(c)
            else:
                break
        if len(leading) >= 2:
            out[t.name] = (leading, "K4")
    return out


_REF_SUFFIX = re.compile(r"(_?(id|key|code|nr|no))$", re.I)


def _role(r: Relationship, prefix: str = "") -> str:
    """The name a single-column reference gives its target: `ship_to_id` -> `ship_to`, `manager_id` -> `manager`,
    `origin_airport_id` -> `origin_airport`. Empty when the column is just the target's own name (`customer_id` ->
    customers, `o_custkey` -> customer), or composite."""
    if len(r.source_cols) != 1:
        return ""
    col = _strip_prefix(r.source_cols[0], prefix)
    stem = _REF_SUFFIX.sub("", col).strip("_")
    if not stem or _norm(stem) in _bases(r.target) | {_norm(r.target)} or _abbreviates(_norm(stem), r.target):
        return ""
    return stem


def _name_fields(rels: list[Relationship], prefixes: dict[str, str] | None = None) -> None:
    """GraphQL field names: `customer` on orders, `orders` on customers. A column that names a role rather than the
    target (`ship_to_id` -> addresses) gives the field that role's name. Names given in `confirmed` are kept.
    Any remaining clash on the same table is disambiguated by column."""
    from collections import Counter
    prefixes = prefixes or {}
    for r in rels:
        role = _role(r, prefixes.get(r.source, ""))
        if not r.field_name:
            r.field_name = _gql(role or sorted(_singulars(r.target), key=len)[0])
        if not r.reverse_name:
            r.reverse_name = _gql(f"{r.source}_as_{role}" if role else r.source)
    for attr, owner in (("field_name", "source"), ("reverse_name", "target")):
        counts = Counter((getattr(r, owner), getattr(r, attr)) for r in rels)
        for r in rels:
            if counts[(getattr(r, owner), getattr(r, attr))] > 1 and r.rule != "confirmed":
                setattr(r, attr, _gql(f"{getattr(r, attr)}_by_{'_'.join(r.source_cols)}"))


RESERVED_FIELDS = {"items", "edges", "nodes", "pageinfo", "endcursor", "hasnextpage"}


def _gql(s: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_]", "_", s).lower()
    s = s if not s[:1].isdigit() else "_" + s
    # "items" as a relationship field collides with the GraphQL connection's own `items` list (500 in Fabric)
    return s + "_lines" if s in RESERVED_FIELDS else s


class PlanInputError(ValueError):
    """`keys=` or `confirmed=` names a table or column that is not in the schema (or an entry is malformed)."""


def check_input(schema: Schema, keys: dict[str, list[str]] | None, confirmed: list[dict] | None) -> None:
    """Every table and column the caller names must exist, so a typo is reported here and never reaches Fabric
    as a definition that refers to a column that is not there."""
    tables = {t.name.lower(): t for t in schema}
    problems: list[str] = []
    for name, cols in (keys or {}).items():
        t = tables.get(str(name).lower())
        if t is None:
            problems.append(f"keys: table {name!r} is not in the schema")
        elif not cols:
            problems.append(f"keys: table {name!r} has an empty column list")
        else:
            problems += [f"keys: column {c!r} is not in table {name!r}" for c in cols if not t.has(str(c))]
    for i, c in enumerate(confirmed or []):
        if not isinstance(c, dict) or not c.get("source") or not c.get("target") or not c.get("source_cols"):
            problems.append(f"confirmed[{i}]: each entry needs source, source_cols and target")
            continue
        for side, cols in (("source", c["source_cols"]), ("target", c.get("target_cols") or c["source_cols"])):
            t = tables.get(str(c[side]).lower())
            if t is None:
                problems.append(f"confirmed[{i}]: {side} table {c[side]!r} is not in the schema")
            else:
                problems += [f"confirmed[{i}]: column {col!r} is not in table {c[side]!r}" for col in cols if not t.has(str(col))]
    if problems:
        raise PlanInputError("; ".join(problems))


def check_tables(schema: Schema, tables: list[str] | None) -> None:
    """A `tables=` filter must name tables that exist; a filter that matches nothing would build an empty API."""
    if tables is None:
        return
    known = {t.name.lower() for t in schema}
    missing = [str(t) for t in tables if str(t).lower() not in known]
    if missing:
        raise PlanInputError("tables: not in the schema: " + ", ".join(repr(m) for m in missing))
    if not tables:
        raise PlanInputError("tables: the list is empty; omit it to take every table")


def _pack(schema: Schema, keys: dict[str, list[str]] | None) -> tuple[dict | None, dict[str, list[str]], list[dict], set[str]]:
    """What the knowledge packs recognise in the schema: (summary for plan.pack, keys, relationships, tables)."""
    from . import sap_pack
    m = sap_pack.match(schema)
    if m is None:
        return None, {}, [], set()
    p = sap_pack.load(m.pack)
    rels = []
    for r in m.relationships:
        why = "; ".join(x for x in (r.get("condition", ""), "source: " + "; ".join(p["sources"][i]["title"].split(":")[0] for i in r["sources"])) if x)
        rels.append({**r, "note": f"{m.pack} pack ({r['module']}): {why}"})
    summary = {"pack": m.pack, "rule": PACK_RULE, "tables": dict(m.tables), "status": "documented, not verified against data",
               "not_applied": m.not_applied, "missing_tables": m.missing_tables, "missing_columns": m.missing_columns,
               "client_dropped": m.client_dropped, "variant_hint": m.variant_hint,
               "amounts": sap_pack.amounts(m),
               "sources": sorted({i for r in m.relationships for i in r["sources"]} | {i for n in m.tables.values() for i in p["tables"][n]["sources"]}),
               "traps": [{"id": t["id"], "title": t["title"]} for t in p["traps"]]}
    return summary, m.keys, rels, set(m.tables)


def plan(schema: Schema, keys: dict[str, list[str]] | None = None, confirmed: list[dict] | None = None, packs: bool = True,
         execute=None) -> Plan:
    """packs=False plans by the name rules alone, as before the knowledge packs (for comparison). With `execute` (a
    read-only query callable over the same tables) R5 also counts code and role columns in the rows; without it the
    plan is exactly the plan by names."""
    check_input(schema, keys, confirmed)
    summary, pack_keys, pack_rels, pack_tables = _pack(schema, keys) if packs else (None, {}, [], set())
    plain = lambda r: r.get("kind", "key") == "key" and not r.get("where")
    special = [r for r in pack_rels if not plain(r)]                  # not plain key joins: plan.extended, never plan.relationships
    pack_rels = [r for r in pack_rels if plain(r)]
    notes: list[dict] = []
    k = infer_keys(schema, keys, notes, pack_keys)
    # a pack relationship whose target has another key now (K0/K1 given by the caller) is left to the name rules
    pack_rels = [r for r in pack_rels if [c.lower() for c in k.get(r["target"], ([], ""))[0]] == [c.lower() for c in r["target_cols"]]
                 or k.get(r["target"], ([], ""))[1] == PACK_RULE]
    rel_notes: list[dict] = []
    rels, amb = infer_relationships(schema, k, confirmed, rel_notes, pack_rels, pack_tables)
    extra = composite_keys(schema, k, rels)
    if extra:                                   # K4/K5 keys can be R3 targets: run the relationships once more
        k.update(extra)
        rel_notes = []
        rels, amb = infer_relationships(schema, k, confirmed, rel_notes, pack_rels, pack_tables)
    proposed: list[dict] = []
    if execute is not None:                     # R5: code and role columns, only where the rows support them
        r5, r5_keys, proposed = infer_from_rows(schema, k, rels, amb, execute, pack_tables)
        if r5:
            k.update(r5_keys)
            rels += r5
            _name_fields(rels, {t.name: _table_prefix(t) for t in schema})
    # an extended relationship stands while the target's key is still the pack's: a caller's own key says otherwise
    extended = [ExtendedRelationship(r["source"], list(r["source_cols"]), r["target"], list(r["target_cols"]), PACK_RULE,
                                     note=r.get("note", ""), kind=r.get("kind", "key"), valid_on=r.get("valid_on"),
                                     cardinality=r.get("cardinality", "many-to-one"), where=list(r.get("where") or []))
                for r in special if k.get(r["target"], ([], ""))[1] == PACK_RULE]
    return Plan(schema, k, rels, amb, keyless=[t.name for t in schema if t.name not in k], synonyms=notes + rel_notes, pack=summary,
                extended=extended, proposed=proposed)


def _m(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", s)


def _type_word(t: Table, c: str) -> str:
    for col in t.columns:
        if col.name == c:
            return re.sub(r"[^a-z0-9]", "", col.data_type.split("(")[0]) or "string"
    return "string"
