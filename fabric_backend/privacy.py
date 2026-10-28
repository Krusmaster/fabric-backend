"""Columns that are probably personal data, by name: one rule per pattern, never a guess from the values.

    P1  a person's name: first_name, last_name, full_name, surname, given_name, middle_name, förnamn, efternamn,
        vorname, nachname; a bare `name` / `namn` / `fullname` only in a table that holds people (customers,
        employees, persons, users, contacts, members, patients, students, kunder, anställda, kunden, mitarbeiter, ...)
    P2  an e-mail address: email, e_mail, mail, epost, e_post, emailaddress
    P3  a telephone number: phone, telephone, tel, mobile, mobil, cell, telefon, telefonnummer, mobilnummer, fax
    P4  a national identity number: ssn, social_security_number, personnummer, personnr, pnr, samordningsnummer,
        national_id, nin, steuer_id, sozialversicherungsnummer, passport_number
    P5  an address: street, street_address, address, address_line*, adress, gatuadress, strasse, postal_code, zip,
        zipcode, postcode, postnummer, plz; and `city` / `ort` / `stad` / `town` / `stadt` in a table that holds
        addresses or people
    P6  a birth date: birth_date, date_of_birth, dob, birthday, födelsedatum, födelsedag, geburtsdatum

A column is judged by its words (snake_case and CamelCase split, å ä ö transliterated), the table by the words of its
name through the inference's synonym table (kund -> customer). Where the catalog tags columns (Unity Catalog column
tags, read by the Databricks adapter), a tag that names one of the kinds above flags the column under that rule, and a
tag that only says "personal data" (pii, personal_data, gdpr, personuppgift) flags it as `tag`; a name rule that
already flags the column wins. What the rules flag is masked by default where values
would reach an answer (sample_rows) or an example, and left out of generated views and drafted queries; the tools
take `show_personal_data=true` to show them, and the user's own Fabric permissions apply either way. Nothing here
reads a value: a column of e-mail addresses called `contact` is not found, and a column called `name` in a products
table is not flagged. The answer always says which rule flagged what. For tables a knowledge pack recognises, the
pack names the personal columns too (SAP's ADR6.SMTP_ADDR is an e-mail address, KNA1.TELF1 a telephone number), under
the same rules; the reason then names the pack.
"""
from __future__ import annotations

from .infer import SYNONYMS, _singulars, _words

MASK = "***"
PARAMETER = "show_personal_data"

RULES = {
    "P1": "a person's name",
    "P2": "an e-mail address",
    "P3": "a telephone number",
    "P4": "a national identity number",
    "P5": "an address",
    "P6": "a birth date",
}

_NAME_PARTS = {("first", "name"), ("last", "name"), ("full", "name"), ("given", "name"), ("middle", "name"), ("family", "name"),
               ("sur", "name"), ("fornamn",), ("efternamn",), ("tilltalsnamn",), ("vorname",), ("nachname",), ("familienname",),
               ("surname",), ("firstname",), ("lastname",), ("fullname",), ("givenname",), ("middlename",), ("familyname",)}
_BARE_NAME = {("name",), ("namn",), ("fullname",), ("full", "name"), ("display", "name"), ("displayname",)}
_EMAIL = {("email",), ("e", "mail"), ("mail",), ("epost",), ("e", "post"), ("emailaddress",), ("email", "address"), ("mail", "address"),
          ("mailadress",), ("e", "mail", "address"), ("epostadress",)}
_PHONE = {("phone",), ("telephone",), ("tel",), ("mobile",), ("mobil",), ("cell",), ("cellphone",), ("telefon",), ("telefonnummer",),
          ("mobilnummer",), ("fax",), ("phone", "number"), ("phonenumber",), ("mobile", "number"), ("mobile", "phone"), ("telefonnr",),
          ("handynummer",), ("telefonnummer",)}
_NATIONAL = {("ssn",), ("social", "security", "number"), ("social", "security", "no"), ("personnummer",), ("personnr",), ("pnr",),
             ("samordningsnummer",), ("national", "id"), ("national", "identity", "number"), ("nin",), ("steuer", "id"), ("steuerid",),
             ("sozialversicherungsnummer",), ("passport", "number"), ("passport", "no"), ("passportnumber",), ("person", "nummer")}
_ADDRESS = {("street",), ("street", "address"), ("address",), ("adress",), ("gatuadress",), ("strasse",), ("postal", "code"), ("zip",),
            ("zipcode",), ("zip", "code"), ("postcode",), ("post", "code"), ("postnummer",), ("plz",), ("postleitzahl",), ("home", "address"),
            ("street", "name"), ("house", "number"), ("hausnummer",), ("c", "o"), ("care", "of")}
_ADDRESS_PREFIX = ("address", "adress", "addr")
_CITY = {("city",), ("ort",), ("stad",), ("town",), ("stadt",), ("postort",)}
_BIRTH = {("birth", "date"), ("date", "of", "birth"), ("dob",), ("birthday",), ("birthdate",), ("fodelsedatum",), ("fodelsedag",),
          ("geburtsdatum",), ("geburtstag",), ("born",), ("born", "on"), ("birth", "day"), ("birth", "dt"), ("birthdt",)}
# A trailing word that numbers or qualifies the value rather than naming it: phone_no, tel_nr, ssn_number, email1, address_2.
_QUALIFIERS = {"no", "nr", "num", "number", "nummer"}
# Who a `<word>_name` column names, in any table: customer_name in orders, contact_name in sales, CustomerName.
_NAMED_PEOPLE = {"customer", "client", "person", "user", "employee", "staff", "member", "contact", "patient", "student", "guest",
                 "passenger", "driver", "applicant", "candidate", "tenant", "buyer", "seller", "worker", "teacher", "pupil", "resident",
                 "citizen", "consumer", "visitor", "volunteer", "donor", "owner", "author", "elev", "anstalld", "medarbetare", "kunde",
                 "mitarbeiter"}

# Tables that hold people, by the English singular of their content words (after the synonym table).
_PEOPLE = {"customer", "client", "person", "people", "user", "employee", "staff", "member", "contact", "patient", "student", "guest",
           "passenger", "driver", "applicant", "candidate", "owner", "tenant", "subscriber", "buyer", "seller", "worker", "teacher",
           "pupil", "resident", "citizen", "account", "accountholder", "consumer", "visitor", "volunteer", "donor", "author",
           "elev", "anstalld", "medarbetare", "patient", "kunde", "mitarbeiter", "personal"}
_ADDRESS_TABLES = {"address", "adress", "adresse", "location", "shippingaddress", "billingaddress"}

_STRIP = {"id"}          # an id of a person is a reference, not personal data in itself: customer_id is never flagged


def _table_words(table: str) -> set[str]:
    out = set()
    for w in _words(table):
        for s in _singulars(w) | {w}:
            out.add(s)
            if s in SYNONYMS:
                out.add(SYNONYMS[s])
    joined = "".join(_words(table))
    out |= {s for s in _singulars(joined)} | {SYNONYMS.get(joined, joined)}
    return out


def holds_people(table: str) -> bool:
    return bool(_table_words(table) & _PEOPLE)


def holds_addresses(table: str) -> bool:
    return bool(_table_words(table) & _ADDRESS_TABLES)


def _own_name(table: str, words: tuple[str, ...]) -> bool:
    """`customer_name` in customers, `CustomerName` in dim_customer, `kundnamn` in kunder: the table's own word + name."""
    if len(words) >= 2 and words[-1] in ("name", "namn"):
        head = "".join(words[:-1])
    elif len(words) == 1 and words[0].endswith(("name", "namn")) and len(words[0]) > 4:
        head = words[0][:-4]
    else:
        return False
    forms = {head, SYNONYMS.get(head, head)} | _singulars(head)
    return bool(forms & _table_words(table))


def _strip_qualifiers(words: tuple[str, ...]) -> tuple[str, ...]:
    """phone_no -> phone, email1 -> email, address_2 -> address, ssn_number -> ssn; a name of one word stays."""
    words = list(words)
    while len(words) > 1 and (words[-1] in _QUALIFIERS or words[-1].isdigit()):
        words.pop()
    if words and len(words[-1]) > 1 and words[-1][-1].isdigit():
        words[-1] = words[-1].rstrip("0123456789") or words[-1]
    return tuple(words)


def _names_a_person(words: tuple[str, ...]) -> bool:
    if len(words) >= 2 and words[-1] in ("name", "namn"):
        head = "".join(words[:-1])
    elif len(words) == 1 and words[0].endswith(("name", "namn")) and len(words[0]) > 4:
        head = words[0][:-4]
    else:
        return False
    return bool(({head, SYNONYMS.get(head, head)} | _singulars(head)) & _NAMED_PEOPLE)


def classify(table: str, column: str) -> dict | None:
    """{"rule", "what", "why"} when the column is probably personal data, else None."""
    words = _strip_qualifiers(tuple(_words(column)))
    if not words:
        return None
    # the column's own name, and the same without a leading table-like word (customer_email, kund_telefon, ship_to_city)
    forms = {words}
    for i in range(1, len(words)):
        forms.add(words[i:])
    joined = {("".join(f),) for f in forms}

    def hit(patterns: set[tuple[str, ...]]) -> bool:
        return bool((forms | joined) & patterns)

    def found(rule: str, why: str) -> dict:
        return {"rule": rule, "what": RULES[rule], "why": why}
    if hit(_NATIONAL):
        return found("P4", f"the column name {column!r} names a national identity number")
    if words[-1] in _STRIP:                  # customer_id, email_id: a reference to a row, not the personal value itself
        return None
    if hit(_EMAIL):
        return found("P2", f"the column name {column!r} names an e-mail address")
    if hit(_PHONE):
        return found("P3", f"the column name {column!r} names a telephone number")
    if hit(_BIRTH):
        return found("P6", f"the column name {column!r} names a birth date")
    if hit(_NAME_PARTS):
        return found("P1", f"the column name {column!r} names part of a person's name")
    if (words in _BARE_NAME or _own_name(table, words)) and holds_people(table):
        return found("P1", f"{column!r} in {table!r}, a table that holds people, is a person's name")
    if _names_a_person(words):
        return found("P1", f"the column name {column!r} names a person (a customer, user, employee or contact) by name")
    if hit(_ADDRESS) or words[0] in _ADDRESS_PREFIX:
        return found("P5", f"the column name {column!r} names an address")
    if hit(_CITY) and (holds_addresses(table) or holds_people(table)):
        return found("P5", f"{column!r} in {table!r}, a table of addresses or people, is part of an address")
    return None


_TAG_PREFIXES = ("class", "pii", "gdpr", "personal", "data", "classification")
_GENERIC_TAGS = {("pii",), ("personal", "data"), ("personaldata",), ("personal",), ("gdpr",), ("personuppgift",), ("personuppgifter",),
                 ("personal", "information"), ("personally", "identifiable", "information"), ("pii", "true")}
_IP = {("ip", "address"), ("ipaddress",), ("ip",)}


def classify_tags(tags: dict[str, str] | None) -> dict | None:
    """A finding from a column's catalog tags ({tag: value}), or None: the first tag that names one of the kinds P1-P6
    (`class.email_address`, `pii: phone`), else a tag that only says personal data (`pii`, `gdpr`)."""
    if not tags:
        return None
    generic = None
    for name, value in sorted(tags.items()):
        label = f"{name}={value}" if value else name
        for text in (name, value or ""):
            words = tuple(_words(text))
            while words and words[0] in _TAG_PREFIXES and len(words) > 1:
                words = words[1:]
            if not words or words in _IP or words in {("true",), ("yes",), ("1",)}:
                continue
            forms = {words[i:] for i in range(len(words))} | {("".join(words),)}
            for patterns, rule in ((_NATIONAL, "P4"), (_EMAIL, "P2"), (_PHONE, "P3"), (_BIRTH, "P6"),
                                   (_NAME_PARTS | _BARE_NAME | {("person", "name"), ("personname",)}, "P1"),
                                   (_ADDRESS | _CITY | {("location",), ("street", "address"), ("postal", "address")}, "P5")):
                if forms & patterns:
                    return {"rule": rule, "what": RULES[rule], "why": f"the catalog tags the column {label!r}", "tag": label}
        if generic is None and ({tuple(_words(name))} | {tuple(_words(f"{name} {value}"))}) & _GENERIC_TAGS:
            generic = {"rule": "tag", "what": "personal data, by a catalog tag", "why": f"the catalog tags the column {label!r}", "tag": label}
    return generic


def personal_columns(schema, tables: list[str] | None = None) -> dict[tuple[str, str], dict]:
    """{(table, column): finding} for every column a rule flags (all tables, or the named ones): by name, else by the
    column's catalog tags (Unity Catalog)."""
    wanted = {t.lower() for t in tables} if tables else None
    out = {}
    for t in schema:
        if wanted is not None and t.name.lower() not in wanted:
            continue
        tags = {k.lower(): v for k, v in (getattr(t, "tags", None) or {}).items()}
        for c in t.column_names:
            f = classify(t.name, c) or classify_tags(tags.get(c.lower()))
            if f:
                out[(t.name, c)] = f
    for key, f in _pack_columns(schema, wanted).items():                # SAP's names say nothing to the rules above
        out.setdefault(key, f)
    return out


def _pack_columns(schema, wanted: set[str] | None) -> dict[tuple[str, str], dict]:
    """The columns a knowledge pack names as personal data (ADR6.SMTP_ADDR, KNA1.TELF1), for the tables it recognises;
    empty for a schema without such tables. A name rule that flags the column already wins."""
    from . import sap_pack
    m = sap_pack.match(schema)
    if m is None:
        return {}
    out = {}
    for table, name in m.tables.items():
        if wanted is not None and table.lower() not in wanted:
            continue
        have = {c.upper(): c for c in schema[table].column_names}
        for p in sap_pack.table_info(name, m.pack).get("personal", []):
            col = have.get(p["column"])
            if col:
                out[(table, col)] = {"rule": p["rule"], "what": RULES[p["rule"]],
                                     "why": f"the {m.pack} pack names {name}.{p['column']} {RULES[p['rule']]}"}
    return out


def findings(flagged: dict[tuple[str, str], dict]) -> list[dict]:
    return [{"table": t, "column": c, **f} for (t, c), f in sorted(flagged.items())]


def mask_value(value):
    """NULL stays NULL (how often a column is empty is not personal data); anything else becomes MASK."""
    return None if value is None else MASK


def mask_rows(table: str, rows: list[dict], flagged: dict[tuple[str, str], dict]) -> tuple[list[dict], list[str]]:
    """Rows with every flagged column of `table` masked, and the names of the masked columns (the row keys as given)."""
    cols = {c.lower() for (t, c) in flagged if t.lower() == table.lower()}
    masked = [k for k in (rows[0].keys() if rows else []) if str(k).lower() in cols]
    return [{k: (mask_value(v) if str(k).lower() in cols else v) for k, v in r.items()} for r in rows], masked


def notice(flagged_here: list[dict], shown: bool) -> str:
    if not flagged_here:
        return ""
    cols = ", ".join(f"{f['table']}.{f['column']} ({f['rule']})" for f in flagged_here)
    if shown:
        return (f"{PARAMETER}=true: these columns look like personal data by name and are shown as they are: {cols}. Handle the "
                "answer as personal data.")
    return (f"Masked because the column name looks like personal data (rule per column, judged by name only, values not read): "
            f"{cols}. To see the values, ask again with {PARAMETER}=true; your own Fabric permissions still decide what you can read.")


def label_of(item: dict | None) -> dict | None:
    """The Microsoft Purview sensitivity label on a Fabric item, as the Items API returns it (`sensitivityLabel.id`,
    read-only; fabric-rest-api-specs a96c37a common/definitions.json Item.sensitivityLabel). Only the label's id is
    returned there; its name needs Microsoft Graph and a scope the app does not ask for (docs/SCOPES.md)."""
    label = (item or {}).get("sensitivityLabel") or (item or {}).get("sensitivity_label")
    if isinstance(label, dict) and label.get("id"):
        return {"id": label["id"], "source": "the item's sensitivityLabel in the Fabric Items API",
                "note": "Fabric returns the label's id only; its name is shown in the Fabric portal. A label applies to the whole item, "
                        "so the column rules above still decide what is masked."}
    return None
