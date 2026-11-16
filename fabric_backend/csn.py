"""SAP Core Schema Notation (CSN): keys, links and amounts that come with the data, as candidates (round CDS2).

Why. SAP publishes the fields and associations of its CDS views in pages a session may not read (api.sap.com disallows
/cdsviews/ in robots.txt; help.sap.com disallows all agents), so the SAP pack ([SAP-CDS.md]) could only propose them.
The customer's own SAP tooling can export the same metadata next to the data: SAP Datasphere exports the CSN of a view
or an entity ("Export to CSN/JSON File"), a CAP project compiles its model to CSN (`cds compile --to csn`). That file is
the customer's, read where it lies; nothing here fetches anything.

What it reads, per entity or view (`definitions` whose `kind` is `entity` or `view`):

- elements with their CDS type (`cds.String`, `cds.Decimal(15,2)`, ...), the `key` flag and the label;
- associations and compositions: the target, the declared cardinality, and the ON condition as column pairs; a managed
  association (CAP: `keys`, or the old `foreignKeys`) as the generated columns `<association>_<key>`;
- semantic hints: `@Semantics.amount.currencyCode` and `@Measures.ISOCurrency` (an amount and its currency column),
  `@Semantics.quantity.unitOfMeasure` and `@Measures.Unit` (a quantity and its unit), `@Semantics.currencyCode`,
  `@Semantics.unitOfMeasure`, `@Semantics.text`, `@ObjectModel.text.element` / `.association` (the text of an ID),
  `@ObjectModel.foreignKey.association` (the association a field is the foreign key of), `@Analytics.dataCategory`
  (#FACT, #DIMENSION, #CUBE, #TEXT, ...), `@ObjectModel.dataCategory` and `@ObjectModel.modelingPattern`.

What it does with them. The metadata is a declaration, not evidence: SAP may declare `[0..1]` where the rows hold
duplicates, a landing may drop rows, a replication may lag. So

- a CSN key becomes the table's key with the rule "CSN metadata" (RULE), and validate_plan counts it like any other;
- an association whose ON condition equals the target's whole key becomes a link source -> target with that rule; one
  whose ON condition equals the *source's* whole key (a header's `_Item`, a product's `_Text`) is read the other way
  round, target -> source, whatever cardinality is declared, and says so; any other ON condition (a part of the key,
  a literal, a function) is not applied and is listed with why;
- an amount (`@Semantics.amount...`) gets its level from the links: on an entity others point at many-to-one it is a
  header amount, which a join with those rows repeats; amounts.py adds these to the doubled-total check.

Every key and link carries `provenance` "declared by metadata (CSN)" with the file and the element or association it
came from. What is not understood is never guessed: `Model.ignored` lists it (definitions of other kinds, annotations
not read, ON conditions not reducible to column pairs), and the plan report lists what did not match the lakehouse.

Names. CSN names are the modeller's (`SalesDocument`, `my.bookshop.Books`, `I_SalesDocumentItem`); what lands in
OneLake through a mirror or a Copy job may differ in case, underscores, a namespace or a layer prefix (`sap_`,
`bronze_`), and carries the change columns `__operation_type`, `__sequence_number`, `__timestamp` ([SAP-CDS.md]).
Tables match an entity by name without case, underscores and namespace, with a leading layer word or the caller's
`prefix` dropped, and by the name without its VDM prefix (`I_`, `C_`, `A_`, `R_`, `P_`, `X_`); columns match without
case and underscores. A table is taken only when every key element is among its columns, and two entities that
answer to one table name are reported, not resolved.

    read(path | dict | list)       -> Model: entities, files, versions, ignored
    match(schema, model, prefix)   -> NameMatch: table per entity, column map, unmatched with why
    plan(schema, model, ...)       -> (plan, report): infer.plan with CSN keys and links first; plan.csn = report
    summary(model)                 -> a JSON-able digest (the `csn` CLI prints it)

Tested on a public CSN file from SAP-samples/datasphere-content (Apache-2.0) and on synthetic CSN written for the
tests (tests/fixtures/csn/); not run on a CSN exported from a customer's tenant. docs/SAP-CSN.md.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

RULE = "CSN metadata"
PROVENANCE = "declared by metadata (CSN)"
CDC_COLUMNS = ("__operation_type", "__sequence_number", "__timestamp")      # added by a Datasphere replication flow
KINDS = ("entity", "view")
ASSOCIATIONS = ("cds.Association", "cds.Composition", "Association", "Composition")
VDM_PREFIXES = ("I", "C", "A", "R", "P", "X", "E", "D", "F")               # I_SalesDocument, C_..., A_...; Z/Y custom keep theirs
_LEADING = ("sap", "raw", "stg", "src", "bronze", "silver", "landing", "mirror", "mirrored", "ext", "extract", "cds", "s4",
            "s4hana", "dsp", "datasphere", "bdc", "csn")
_NUMERIC_CDS = {"cds.Decimal", "cds.Double", "cds.Integer", "cds.Integer64", "cds.Int16", "cds.Int32", "cds.Int64",
                "cds.UInt8", "cds.DecimalFloat", "cds.hana.SMALLDECIMAL", "cds.hana.REAL", "cds.hana.TINYINT",
                "cds.hana.SMALLINT", "Decimal", "Double", "Integer", "Integer64"}
_SQL_NUMERIC = ("int", "bigint", "smallint", "tinyint", "decimal", "numeric", "float", "real", "double", "money", "number", "long")

# annotations this module reads; every other annotation name is counted in Model.ignored (never an error)
READ_ANNOTATIONS = {
    "@Semantics.amount.currencyCode", "@Semantics.currencyCode", "@Semantics.quantity.unitOfMeasure",
    "@Semantics.unitOfMeasure", "@Semantics.text", "@Measures.ISOCurrency", "@Measures.Unit", "@Measures.Currency",
    "@ObjectModel.text.element", "@ObjectModel.text.association", "@ObjectModel.foreignKey.association",
    "@Analytics.dataCategory", "@ObjectModel.dataCategory", "@ObjectModel.modelingPattern", "@EndUserText.label",
    "@Common.Label", "@title", "@Aggregation.default", "@DefaultAggregation",
}
_LABELS = ("@EndUserText.label", "@Common.Label", "@title")


# --------------------------------------------------------------------------------------------------------------------
# reading


@dataclass
class Association:
    name: str
    target: str
    composition: bool = False
    cardinality: dict | None = None           # as declared: {"src": .., "min": .., "max": ..}; None: not declared
    pairs: list[tuple[str, str]] = field(default_factory=list)    # (source element, target element), equalities only
    managed: bool = False
    understood: bool = True
    why: str = ""                              # when not understood: what was not

    @property
    def to_many(self) -> bool | None:
        """Declared max '*' or > 1: True; declared max 1: False; nothing declared: None (CDS then reads it as to-one)."""
        if not self.cardinality or "max" not in self.cardinality:
            return None
        m = self.cardinality["max"]
        return m == "*" or (isinstance(m, int) and m > 1)

    def declared(self) -> str:
        if not self.cardinality:
            return "no cardinality declared (CDS reads it as to-one, [0..1])"
        c = self.cardinality
        return f"[{c.get('min', 0)}..{c.get('max', 1)}]" + (f" from [{c['src']}]" if "src" in c else "")


@dataclass
class Entity:
    name: str
    kind: str
    file: str
    label: str = ""
    elements: dict[str, dict] = field(default_factory=dict)      # name -> {type, key, length, precision, scale, label}
    keys: list[str] = field(default_factory=list)
    associations: list[Association] = field(default_factory=list)
    amounts: list[dict] = field(default_factory=list)            # {column, currency, from}
    quantities: list[dict] = field(default_factory=list)         # {column, unit, from}
    currency_codes: list[str] = field(default_factory=list)
    units: list[str] = field(default_factory=list)
    texts: list[dict] = field(default_factory=list)              # {column, text_element | text_association}
    text_fields: list[str] = field(default_factory=list)
    foreign_keys: dict[str, str] = field(default_factory=dict)   # element -> association it is the foreign key of
    data_category: str | None = None                             # FACT, DIMENSION, CUBE, TEXT, ... as declared
    measures: list[str] = field(default_factory=list)            # elements with a default aggregation (SUM, ...)


@dataclass
class Model:
    entities: dict[str, Entity] = field(default_factory=dict)
    files: list[str] = field(default_factory=list)
    versions: list[dict] = field(default_factory=list)           # per file: $version, version.csn, meta.creator/flavor
    ignored: list[dict] = field(default_factory=list)            # {file, what, why}

    def entity(self, name: str) -> Entity | None:
        return self.entities.get(name)


def _value(v):
    """An annotation value: {'=': 'X'} (an element reference), {'#': 'FACT'} (an enum), ['X'] / [{'=': 'X'}], or plain."""
    if isinstance(v, dict):
        if "=" in v:
            return v["="]
        if "#" in v:
            return v["#"]
        return None
    if isinstance(v, list):
        out = [_value(x) for x in v]
        return [x for x in out if x is not None]
    return v


def _annotations(d: dict) -> dict:
    """Flatten nested annotations ({'@Semantics': {'amount': {'currencyCode': ...}}}) to dotted names."""
    out: dict = {}

    def walk(prefix: str, v):
        if isinstance(v, dict) and not ({"=", "#"} & set(v)) and v:
            for k, x in v.items():
                walk(f"{prefix}.{k}", x)
        else:
            out[prefix] = v
    for k, v in d.items():
        if k.startswith("@"):
            walk(k, v)
    return out


def _type(el: dict) -> str:
    t = el.get("type")
    if isinstance(t, dict):                   # {ref: [...]}: a type by reference
        t = "/".join(str(x) for x in t.get("ref", [])) or "unknown"
    t = str(t or ("structured" if "elements" in el else "unknown"))
    if el.get("precision") is not None:
        t += f"({el['precision']},{el.get('scale', 0)})"
    elif el.get("length") is not None:
        t += f"({el['length']})"
    return t


def _flatten(elements: dict, prefix: str = "") -> dict[str, dict]:
    """Structured elements flatten to name_sub, as CAP does for the database."""
    out: dict[str, dict] = {}
    for n, el in (elements or {}).items():
        if not isinstance(el, dict):
            continue
        if isinstance(el.get("elements"), dict) and el.get("type") not in ASSOCIATIONS:
            for sn, sel in _flatten(el["elements"], f"{prefix}{n}_").items():
                out[sn] = {**sel, "key": bool(el.get("key") or sel.get("key"))}
        else:
            out[f"{prefix}{n}"] = el
    return out


def _ref(tok) -> list[str] | None:
    if isinstance(tok, dict) and isinstance(tok.get("ref"), list):
        out = []
        for x in tok["ref"]:
            if isinstance(x, dict) and "id" in x:      # a path step with a filter: {"id": "_Item", "where": [...]}
                return None
            out.append(str(x))
        return out
    return None


def _on_pairs(assoc_name: str, on: list, elements: dict, model_defs: dict, target: str) -> tuple[list[tuple[str, str]], str]:
    """The ON condition as (source element, target element) pairs, or ([], why) when it is anything but equalities of
    one source element and one target element joined by AND (a literal, a function, OR, a filtered path)."""
    toks = [t for t in on if t not in ("(", ")")]
    if any(isinstance(t, dict) and "xpr" in t for t in toks):
        flat = []
        for t in toks:
            flat += [x for x in t["xpr"] if x not in ("(", ")")] if isinstance(t, dict) and "xpr" in t else [t]
        toks = flat
    pairs: list[tuple[str, str]] = []
    i = 0
    while i < len(toks):
        if i + 2 >= len(toks) or toks[i + 1] != "=":
            return [], f"ON condition is not a list of equalities joined by AND (at {json.dumps(toks[i:i + 3])[:120]})"
        a, b = _ref(toks[i]), _ref(toks[i + 2])
        if a is None or b is None:
            lit = next((t for t in (toks[i], toks[i + 2]) if isinstance(t, dict) and "val" in t), None)
            return [], ("ON condition compares with a literal (" + json.dumps(lit)[:60] + "): a filtered association, not a key join"
                        if lit else "ON condition holds an expression other than a column reference")
        side = {}
        for r in (a, b):
            if r[0] in ("$projection", "$self") and len(r) == 2:
                side.setdefault("s", r[1])
            elif r[0] == assoc_name and len(r) == 2:
                side.setdefault("t", r[1])
            elif r == ["$self"]:
                side.setdefault("self", True)
            elif r[0] == assoc_name and len(r) == 3:          # backlink through a managed association: _Item.parent_ID?
                side.setdefault("t", f"{r[1]}_{r[2]}")
            elif len(r) == 1:
                side.setdefault("s", r[0])
            else:
                return [], f"ON condition refers to {'.'.join(r)}, which is neither this entity's element nor {assoc_name}'s"
        if "self" in side and "t" in side:                    # CAP backlink: _Item.parent = $self
            back = model_defs.get(target, {}).get("elements", {}).get(side["t"])
            if not isinstance(back, dict) or back.get("type") not in ASSOCIATIONS:
                return [], f"ON condition {assoc_name}.{side['t']} = $self, and {side['t']} is not an association of {target}"
            keys = _managed_keys(back, model_defs)
            if not keys:
                return [], f"ON condition {assoc_name}.{side['t']} = $self: the backlink's keys could not be read"
            pairs += [(k, f"{side['t']}_{alias}") for k, alias in keys]
        elif "s" in side and "t" in side:
            pairs.append((side["s"], side["t"]))
        else:
            return [], "ON condition compares two columns of the same side"
        i += 3
        if i < len(toks):
            if str(toks[i]).lower() != "and":
                return [], f"ON condition joins comparisons with {toks[i]!r}, not AND"
            i += 1
    return pairs, ""


def _managed_keys(el: dict, model_defs: dict) -> list[tuple[str, str]]:
    """A managed association's foreign keys: [(target element, generated suffix)]. `keys` (CSN 1.0+), `foreignKeys`
    (CSN 0.1), or none given: the target's key elements."""
    if isinstance(el.get("keys"), list):
        out = []
        for k in el["keys"]:
            r = _ref(k)
            if r:
                out.append((".".join(r), str(k.get("as") or "_".join(r))))
        return out
    if isinstance(el.get("foreignKeys"), dict):
        return [(".".join(_ref(v) or [n]) if isinstance(v, dict) else n, n) for n, v in el["foreignKeys"].items()]
    target = model_defs.get(_target(el), {})
    return [(n, n) for n, e in _flatten(target.get("elements", {})).items() if isinstance(e, dict) and e.get("key")
            and e.get("type") not in ASSOCIATIONS]


def _target(el: dict) -> str:
    t = el.get("target")
    return str(t) if t is not None else ""


def _read_definitions(csn: dict, file: str, model: Model) -> None:
    ver = {"file": file, "$version": csn.get("$version"), "csn": (csn.get("version") or {}).get("csn") if isinstance(csn.get("version"), dict) else csn.get("version"),
           "creator": (csn.get("meta") or {}).get("creator"), "flavor": (csn.get("meta") or {}).get("flavor") or (csn.get("meta") or {}).get("kind"),
           **({"interop": csn["csnInteropEffective"]} if "csnInteropEffective" in csn else {})}
    model.versions.append(ver)
    defs = csn.get("definitions")
    if not isinstance(defs, dict):
        model.ignored.append({"file": file, "what": "the file", "why": "no 'definitions' object: not CSN, or a CSN form this reader does not know"})
        return
    for k in csn:
        if k not in ("definitions", "$version", "version", "meta", "namespace", "requires", "$location", "$sources", "$schema",
                     "csnInteropEffective"):
            model.ignored.append({"file": file, "what": k, "why": "top-level property not read (only 'definitions' carries entities)"})
    unknown_annotations: dict[str, int] = {}
    for name, d in defs.items():
        if not isinstance(d, dict):
            continue
        kind = d.get("kind")
        if kind not in KINDS:
            model.ignored.append({"file": file, "what": name, "why": f"kind {kind!r}: only entities and views carry rows"})
            continue
        if not isinstance(d.get("elements"), dict) or not d["elements"]:
            model.ignored.append({"file": file, "what": name, "why": "no elements (a view in parsed CSN without its inferred "
                                                                  "elements: export the compiled/inferred CSN)"})
            continue
        if name in model.entities:
            model.ignored.append({"file": file, "what": name, "why": f"defined again; the first definition ({model.entities[name].file}) is kept"})
            continue
        ann = _annotations(d)
        e = Entity(name, "view" if kind == "view" or "query" in d or "projection" in d else "entity", file)
        e.label = next((str(_value(ann[a])) for a in _LABELS if a in ann and _value(ann[a])), "")
        cat = _value(ann.get("@Analytics.dataCategory")) or _value(ann.get("@ObjectModel.dataCategory")) or _value(ann.get("@ObjectModel.modelingPattern"))
        e.data_category = str(cat).lstrip("#").upper() if cat else None
        for a in ann:
            if a not in READ_ANNOTATIONS:
                unknown_annotations[a] = unknown_annotations.get(a, 0) + 1
        flat = _flatten(d["elements"])
        for en, el in flat.items():
            if el.get("type") in ASSOCIATIONS or (isinstance(el.get("target"), str) and ("on" in el or "keys" in el or "foreignKeys" in el)):
                comp = "Composition" in str(el.get("type"))
                card = el.get("cardinality") if isinstance(el.get("cardinality"), dict) else None
                if card is None and comp and el.get("cardinality") is None and el.get("$many"):
                    card = {"max": "*"}
                a = Association(en, _target(el), comp, card)
                if isinstance(el.get("on"), list):
                    a.pairs, a.why = _on_pairs(en, el["on"], flat, defs, a.target)
                else:
                    a.managed = True
                    keys = _managed_keys(el, defs)
                    a.pairs = [(f"{en}_{alias}", tk) for tk, alias in keys]
                    a.why = "" if keys else "managed association whose keys could not be read"
                    if el.get("key"):
                        e.keys += [s for s, _ in a.pairs]
                a.understood = bool(a.pairs) and not a.why
                e.associations.append(a)
                continue
            ea = _annotations(el)
            for x in ea:
                if x not in READ_ANNOTATIONS:
                    unknown_annotations[x] = unknown_annotations.get(x, 0) + 1
            e.elements[en] = {"type": _type(el), "key": bool(el.get("key")),
                              "label": next((str(_value(ea[a])) for a in _LABELS if a in ea and _value(ea[a])), "")}
            if el.get("key"):
                e.keys.append(en)
            cur = _value(ea.get("@Semantics.amount.currencyCode")) or _value(ea.get("@Measures.ISOCurrency")) or _value(ea.get("@Measures.Currency"))
            if cur:
                e.amounts.append({"column": en, "currency": str(cur), "from": "@Semantics.amount.currencyCode"
                                  if "@Semantics.amount.currencyCode" in ea else "@Measures.ISOCurrency"})
            unit = _value(ea.get("@Semantics.quantity.unitOfMeasure")) or _value(ea.get("@Measures.Unit"))
            if unit:
                e.quantities.append({"column": en, "unit": str(unit), "from": "@Semantics.quantity.unitOfMeasure"
                                     if "@Semantics.quantity.unitOfMeasure" in ea else "@Measures.Unit"})
            if _value(ea.get("@Semantics.currencyCode")) is True:
                e.currency_codes.append(en)
            if _value(ea.get("@Semantics.unitOfMeasure")) is True:
                e.units.append(en)
            if _value(ea.get("@Semantics.text")) is True:
                e.text_fields.append(en)
            te = _value(ea.get("@ObjectModel.text.element"))
            if te:
                e.texts.append({"column": en, "text_element": te[0] if isinstance(te, list) else str(te)})
            ta = _value(ea.get("@ObjectModel.text.association"))
            if ta:
                e.texts.append({"column": en, "text_association": str(ta)})
            fk = _value(ea.get("@ObjectModel.foreignKey.association"))
            if fk:
                e.foreign_keys[en] = str(fk)
            agg = _value(ea.get("@Aggregation.default")) or _value(ea.get("@DefaultAggregation"))
            if agg and str(agg).upper() not in ("NONE", "NOP", "FORMULA"):
                e.measures.append(en)
        for a in e.associations:
            if not a.understood:
                model.ignored.append({"file": file, "what": f"{name}.{a.name}", "why": a.why or "association not understood"})
        model.entities[name] = e
    for a, n in sorted(unknown_annotations.items()):
        model.ignored.append({"file": file, "what": a, "why": f"annotation not read ({n} use(s))"})


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        raise ValueError(f"{path.name}: not JSON ({e.msg} at line {e.lineno})") from None


def read(source, name: str | None = None) -> Model:
    """A CSN file (`.json` or `.csn`), a folder of them (read in name order, not recursively), a parsed CSN object, or a
    list of any of these. Entities defined in two files keep the first definition and the second is listed as ignored."""
    model = Model()
    items = source if isinstance(source, list) else [source]
    for item in items:
        if isinstance(item, dict):
            label = name or "(given as JSON)"
            model.files.append(label)
            _read_definitions(item, label, model)
            continue
        p = Path(item)
        if p.is_dir():
            files = sorted(f for f in p.iterdir() if f.is_file() and f.suffix.lower() in (".json", ".csn"))
            if not files:
                raise ValueError(f"{p}: no .json or .csn file in the folder")
        elif p.is_file():
            files = [p]
        else:
            raise ValueError(f"{p}: no such file or folder")
        for f in files:
            model.files.append(f.name)
            _read_definitions(_load_json(f), f.name, model)
    return model


# --------------------------------------------------------------------------------------------------------------------
# names


def norm(name: str) -> str:
    """A name without case, underscores, dots, slashes and spaces: SalesDocument, SALES_DOCUMENT, sales_document -> SALESDOCUMENT."""
    return re.sub(r"[^A-Za-z0-9]", "", str(name)).upper()


def entity_names(name: str) -> list[tuple[str, str]]:
    """The normalised names an entity answers to, strongest first, each with how: the full name, the persistence name
    (dots to underscores: my.bookshop.Books -> my_bookshop_Books, the same after norm), the last segment of a dotted or
    `::` name, and the name without a VDM prefix (I_SalesDocument -> SalesDocument)."""
    out = [(norm(name), "name")]
    last = re.split(r"\.|::", name)[-1]
    if last != name:
        out.append((norm(last), "name without namespace"))
    m = re.match(r"^([A-Za-z])_(.+)$", last)
    if m and m.group(1).upper() in VDM_PREFIXES:
        out.append((norm(m.group(2)), f"name without the VDM prefix {m.group(1)}_"))
    m = re.match(r"^(YY1_|[ZY][A-Za-z]?_)(.+)$", last)              # a customer's own view: ZI_ServiceOrder, YY1_Order
    if m:
        out.append((norm(m.group(2)), f"name without the customer prefix {m.group(1)}"))
    seen, uniq = set(), []
    for n, how in out:
        if n and n not in seen:
            seen.add(n)
            uniq.append((n, how))
    return uniq


def table_names(table: str, prefix: str | None = None) -> list[str]:
    """The normalised names a lakehouse table could carry an entity's name under: as it is, without the caller's
    prefix, and without leading layer words (bronze_, sap_, dsp_)."""
    base = table.split(".")[-1]
    out = [norm(base)]
    if prefix and base.lower().startswith(prefix.lower()) and len(base) > len(prefix):
        out.append(norm(base[len(prefix):]))
    words = [w for w in re.split(r"[^A-Za-z0-9]+", base) if w]
    while len(words) > 1 and words[0].lower() in _LEADING:
        words = words[1:]
        out.append(norm("".join(words)))
    return list(dict.fromkeys(out))


@dataclass
class NameMatch:
    tables: dict[str, str] = field(default_factory=dict)          # entity -> schema table
    how: dict[str, str] = field(default_factory=dict)             # entity -> which name matched
    columns: dict[str, dict[str, str]] = field(default_factory=dict)   # entity -> element -> table column (schema spelling)
    unmatched: list[dict] = field(default_factory=list)           # entities with no table, or whose key columns are missing
    ambiguous: list[dict] = field(default_factory=list)           # a table two entities answer to equally well
    cdc_columns: dict[str, list[str]] = field(default_factory=dict)  # table -> change columns found
    extra_columns: dict[str, list[str]] = field(default_factory=dict)  # table -> columns the CSN does not name
    type_differences: list[dict] = field(default_factory=list)


def _columns(table) -> dict[str, str]:
    out: dict[str, str] = {}
    for c in table.columns:
        out.setdefault(norm(c.name), c.name)
    return out


def _numeric_sql(t: str) -> bool:
    b = (t or "").lower().split("(")[0].strip()
    return b in _SQL_NUMERIC or b.startswith(("decimal", "numeric"))


def match(schema, model: Model, prefix: str | None = None) -> NameMatch:
    """Which table of the schema each entity is. A table is taken only when every key element is one of its columns."""
    nm = NameMatch()
    index: dict[str, list[str]] = {}
    for t in schema:
        for i, n in enumerate(table_names(t.name, prefix)):
            index.setdefault(n, []).append(t.name)
    claims: dict[str, list[tuple[int, str, str]]] = {}            # table -> [(strength, entity, how)]
    for en, e in model.entities.items():
        found = None
        for strength, (n, how) in enumerate(entity_names(en)):
            hits = index.get(n, [])
            if len(hits) > 1:
                nm.ambiguous.append({"entity": en, "tables": sorted(hits), "why": f"{len(hits)} tables answer to {en} by {how}; give the name"})
                found = "ambiguous"
                break
            if hits:
                found = (strength, hits[0], how)
                break
        if found is None:
            nm.unmatched.append({"entity": en, "why": "no table of the schema carries its name (in any case, with or without "
                                                      "underscores, namespace, VDM or layer prefix)"})
        elif found != "ambiguous":
            claims.setdefault(found[1], []).append((found[0], en, found[2]))
    for table, cl in claims.items():
        cl.sort()
        if len(cl) > 1 and cl[0][0] == cl[1][0]:
            nm.ambiguous.append({"table": table, "entities": [c[1] for c in cl], "why": "two entities answer to this table equally well"})
            continue
        for _, en, how in cl[1:]:
            nm.unmatched.append({"entity": en, "why": f"{table} is taken by {cl[0][1]}, which matches it by a stronger name"})
        _, en, how = cl[0]
        e, t = model.entities[en], schema[table]
        cols = _columns(t)
        missing = [k for k in e.keys if norm(k) not in cols]
        if missing:
            nm.unmatched.append({"entity": en, "table": table, "why": f"{table} lacks key element(s) {', '.join(missing)}"})
            continue
        nm.tables[en], nm.how[en] = table, how
        nm.columns[en] = {el: cols[norm(el)] for el in list(e.elements) + [s for a in e.associations for s, _ in a.pairs]
                          if norm(el) in cols}
        cdc = [c.name for c in t.columns if c.name.lower() in CDC_COLUMNS]
        if cdc:
            nm.cdc_columns[table] = cdc
        known = {norm(x) for x in nm.columns[en]} | {norm(c) for c in CDC_COLUMNS}
        extra = [c.name for c in t.columns if norm(c.name) not in known]
        if extra:
            nm.extra_columns[table] = extra
        for el, col in nm.columns[en].items():
            ty = e.elements.get(el, {}).get("type", "")
            sql = next((c.data_type for c in t.columns if c.name == col), "")
            if ty.split("(")[0] in _NUMERIC_CDS and sql and not _numeric_sql(sql) and sql.lower() not in ("unknown",):
                nm.type_differences.append({"table": table, "column": col, "csn": ty, "table_type": sql,
                                            "why": "numeric in the CSN, not numeric in the lakehouse: sums need a cast"})
    return nm


# --------------------------------------------------------------------------------------------------------------------
# links, amounts and the plan


def links(model: Model, nm: NameMatch) -> tuple[list[dict], list[dict]]:
    """(applied, not_applied): every association between two matched entities as a Krusgraph link, many-to-one from
    the side that holds the reference, in the schema's spelling, with provenance; or why it is not one."""
    applied: dict[tuple, dict] = {}
    not_applied: list[dict] = []
    for en, e in model.entities.items():
        for a in e.associations:
            where = f"{e.file}: {en}.{a.name} -> {a.target}"
            if not a.understood:
                not_applied.append({"association": f"{en}.{a.name}", "target": a.target, "file": e.file, "why": a.why})
                continue
            t = model.entities.get(a.target)
            if t is None:
                not_applied.append({"association": f"{en}.{a.name}", "target": a.target, "file": e.file,
                                    "why": f"target {a.target} is not defined in the CSN files read"})
                continue
            if en not in nm.tables or a.target not in nm.tables:
                miss = [x for x in (en, a.target) if x not in nm.tables]
                not_applied.append({"association": f"{en}.{a.name}", "target": a.target, "file": e.file,
                                    "why": f"no table for {', '.join(miss)} in the schema"})
                continue
            s_cols = [s for s, _ in a.pairs]
            t_cols = [x for _, x in a.pairs]
            tk, sk = {norm(k) for k in t.keys}, {norm(k) for k in e.keys}
            if tk and {norm(c) for c in t_cols} == tk:
                src, scols, tgt, tcols, reverse = en, s_cols, a.target, t_cols, False
            elif sk and {norm(c) for c in s_cols} == sk and len(s_cols) == len(t_cols):
                src, scols, tgt, tcols, reverse = a.target, t_cols, en, s_cols, True
            else:
                not_applied.append({"association": f"{en}.{a.name}", "target": a.target, "file": e.file, "declared": a.declared(),
                                    "on": [f"{en}.{s} = {a.target}.{x}" for s, x in a.pairs],
                                    "why": f"the ON condition is not {a.target}'s whole key ({', '.join(t.keys) or 'none declared'}) "
                                           f"nor {en}'s ({', '.join(e.keys) or 'none declared'}): not a key join (a time-dependent or "
                                           "text association, or a part of a key); confirm it yourself if it is one"})
                continue
            sc, tc = nm.columns.get(src, {}), nm.columns.get(tgt, {})
            lack = [c for c in scols if c not in sc] + [c for c in tcols if c not in tc]
            if lack:
                not_applied.append({"association": f"{en}.{a.name}", "target": a.target, "file": e.file,
                                    "why": f"column(s) {', '.join(lack)} not in the lakehouse tables"})
                continue
            order = sorted(range(len(tcols)), key=lambda i: [norm(k) for k in model.entities[tgt].keys].index(norm(tcols[i])))
            scols, tcols = [scols[i] for i in order], [tcols[i] for i in order]
            note = f"{a.name} {a.declared()}" + (f"; read as {model.entities[src].name} -> {tgt}: the ON condition is "
                                                 f"{en}'s whole key" if reverse else "")
            if reverse and a.to_many is False:
                note += "; the CSN declares to-one, the keys say one-to-many: validate_plan's count decides"
            if not reverse and a.to_many:
                note += "; the CSN declares to-many, the ON condition is the target's whole key: read as many-to-one, validate_plan's count decides"
            fk_ann = [c for c in scols if model.entities[src].foreign_keys.get(c)]
            rel = {"source": nm.tables[src], "source_cols": [sc[c] for c in scols], "target": nm.tables[tgt],
                   "target_cols": [tc[c] for c in tcols], "rule": RULE, "provenance": PROVENANCE,
                   "declared_in": [{"file": e.file, "association": f"{en}.{a.name}", "cardinality": a.declared(),
                                    "composition": a.composition, "managed": a.managed, "read_as": "reverse" if reverse else "as declared"}],
                   "note": note, "foreign_key_annotation": fk_ann}
            k = (rel["source"], tuple(c.lower() for c in rel["source_cols"]), rel["target"])
            if k in applied:
                applied[k]["declared_in"] += rel["declared_in"]
                applied[k]["foreign_key_annotation"] = sorted(set(applied[k]["foreign_key_annotation"]) | set(fk_ann))
            else:
                applied[k] = rel
    return list(applied.values()), not_applied


def amount_levels(model: Model, nm: NameMatch, applied: list[dict]) -> list[dict]:
    """Every amount and quantity the CSN marks, in the schema's spelling, with its level: 'header' when another matched
    table points at this one many-to-one (a join with those rows repeats the value), else 'item'."""
    by_table = {nm.tables[en]: en for en in nm.tables}
    one_to_one = set()
    for r in applied:                            # a link whose source columns are the source's whole key is one-to-one
        src_keys = {norm(k) for k in model.entities[by_table[r["source"]]].keys}
        if {norm(c) for c in r["source_cols"]} == src_keys:
            one_to_one.add((r["source"], r["target"]))
    lines: dict[str, list[str]] = {}
    for r in applied:
        if r["source"] != r["target"] and (r["source"], r["target"]) not in one_to_one:
            lines.setdefault(r["target"], []).append(r["source"])
    out = []
    for en, table in nm.tables.items():
        e, cols = model.entities[en], nm.columns.get(en, {})
        for kind, items, other in (("amount", e.amounts, "currency"), ("quantity", e.quantities, "unit")):
            for x in items:
                if x["column"] not in cols:
                    continue
                level = "header" if table in lines else "item"
                out.append({"table": table, "column": cols[x["column"]], "kind": kind, "level": level,
                            other: cols.get(x[other], x[other]), "from": x["from"], "provenance": PROVENANCE,
                            "repeated_by": sorted(set(lines.get(table, []))),
                            "why": (f"{', '.join(sorted(set(lines[table])))} point(s) at {table} many-to-one: a join with them repeats "
                                    f"{cols[x['column']]} on every row" if level == "header" else
                                    "no matched table points at this one many-to-one: summed on its own rows")})
    return out


def plan(schema, model: Model, prefix: str | None = None, **kwargs):
    """infer.plan with the CSN's keys and links first: (plan, report). CSN keys go in as keys (rule RULE), CSN links as
    confirmed links (rule RULE); keys and confirmed links the caller passes still win. plan.csn is the report: what
    matched, what was not applied and why, the amounts with their level. Nothing is counted here: validate_plan counts
    the CSN's keys and links against the rows like any other."""
    from .infer import plan as _plan
    nm = match(schema, model, prefix)
    applied, not_applied = links(model, nm)
    given_keys = {str(k).lower() for k in (kwargs.get("keys") or {})}
    mine = {nm.tables[en]: [nm.columns[en][k] for k in model.entities[en].keys]
            for en in nm.tables if model.entities[en].keys and nm.tables[en].lower() not in given_keys}
    keep = []
    for r in applied:                          # a link stands while its target's key is the CSN's
        if r["target"] in mine and [c.lower() for c in mine[r["target"]]] == [c.lower() for c in r["target_cols"]]:
            keep.append(r)
        else:
            not_applied.append({"association": "; ".join(d["association"] for d in r["declared_in"]), "target": r["target"],
                                "why": f"{r['target']}'s key is not the CSN's here (a key given by the caller wins)"})
    applied = keep
    confirmed = [{"source": r["source"], "source_cols": r["source_cols"], "target": r["target"], "target_cols": r["target_cols"]}
                 for r in applied]
    p = _plan(schema, keys={**mine, **(kwargs.pop("keys", None) or {})}, confirmed=confirmed + list(kwargs.pop("confirmed", None) or []),
              **kwargs)
    for t, cols in mine.items():
        if t in p.keys and p.keys[t][1] == "K1" and [c.lower() for c in p.keys[t][0]] == [c.lower() for c in cols]:
            p.keys[t] = (p.keys[t][0], RULE)
    ours = {(r["source"], tuple(c.lower() for c in r["source_cols"]), r["target"]): r for r in applied}
    for rel in p.relationships:
        r = ours.get(rel.key)
        if r is not None and rel.rule == "confirmed":
            rel.rule = RULE
            rel.note = f"{PROVENANCE}: " + "; ".join(f"{d['file']} {d['association']} {d['cardinality']}" for d in r["declared_in"]) \
                       + (f" ({r['note'].split('; ', 1)[1]})" if "; " in r["note"] else "")
    report = {
        "rule": RULE, "provenance": PROVENANCE, "status": "declared by metadata, not verified against the rows: validate_plan counts it",
        "files": list(model.files), "versions": model.versions,
        "entities": len(model.entities), "matched": {en: {"table": t, "by": nm.how[en]} for en, t in nm.tables.items()},
        "keys": {t: cols for t, cols in mine.items()},
        "links": applied, "not_applied": not_applied,
        "amounts": amount_levels(model, nm, applied),
        "texts": [{"table": nm.tables[en], **x} for en in nm.tables for x in model.entities[en].texts],
        "data_categories": {nm.tables[en]: model.entities[en].data_category for en in nm.tables if model.entities[en].data_category},
        "unmatched": nm.unmatched, "ambiguous": nm.ambiguous,
        "cdc_columns": nm.cdc_columns, "extra_columns": nm.extra_columns, "type_differences": nm.type_differences,
        "ignored": model.ignored,
    }
    p.csn = report
    return p, report


def declared_amounts(plan) -> list[dict]:
    """The amounts a knowledge pack and a CSN file name on a plan's tables ({table, column, ...}): what amounts.py treats
    as amounts whatever their names say."""
    out = list((getattr(plan, "pack", None) or {}).get("amounts") or [])
    out += [a for a in (getattr(plan, "csn", None) or {}).get("amounts") or [] if a.get("kind", "amount") == "amount"]
    return out


def summary(model: Model) -> dict:
    """A digest of what was read, per entity: keys, element types, associations, semantic hints; and what was ignored."""
    ents = {}
    for en, e in model.entities.items():
        ents[en] = {
            "kind": e.kind, "file": e.file, **({"label": e.label} if e.label else {}),
            **({"data_category": e.data_category} if e.data_category else {}),
            "keys": e.keys,
            "elements": {n: el["type"] for n, el in e.elements.items()},
            "associations": [{"name": a.name, "target": a.target, "cardinality": a.declared(),
                              **({"composition": True} if a.composition else {}), **({"managed": True} if a.managed else {}),
                              "on": [f"{s} = {a.target}.{t}" for s, t in a.pairs] if a.understood else None,
                              **({"why": a.why} if not a.understood else {})} for a in e.associations],
            **({"amounts": e.amounts} if e.amounts else {}), **({"quantities": e.quantities} if e.quantities else {}),
            **({"currency_codes": e.currency_codes} if e.currency_codes else {}), **({"units": e.units} if e.units else {}),
            **({"texts": e.texts} if e.texts else {}), **({"text_fields": e.text_fields} if e.text_fields else {}),
            **({"foreign_keys": e.foreign_keys} if e.foreign_keys else {}), **({"measures": e.measures} if e.measures else {}),
        }
    return {"files": model.files, "versions": model.versions, "entities": ents, "ignored": model.ignored,
            "provenance": PROVENANCE, "note": "metadata only: keys and links are candidates until validate_plan counts them in the rows"}
