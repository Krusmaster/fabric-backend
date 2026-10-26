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
name through the inference's synonym table (kund -> customer). What the rules flag is masked by default where values
would reach an answer (sample_rows) or an example, and left out of generated views and drafted queries; the tools
take `show_personal_data=true` to show them, and the user's own Fabric permissions apply either way. Nothing here
reads a value: a column of e-mail addresses called `contact` is not found, and a column called `name` in a products
table is not flagged. The answer always says which rule flagged what.
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
          ("geburtsdatum",), ("geburtstag",), ("born",), ("born", "on"), ("birth", "day")}

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


def classify(table: str, column: str) -> dict | None:
    """{"rule", "what", "why"} when the column is probably personal data, else None."""
    words = tuple(_words(column))
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
    if hit(_ADDRESS) or words[0] in _ADDRESS_PREFIX:
        return found("P5", f"the column name {column!r} names an address")
    if hit(_CITY) and (holds_addresses(table) or holds_people(table)):
        return found("P5", f"{column!r} in {table!r}, a table of addresses or people, is part of an address")
    return None


def personal_columns(schema, tables: list[str] | None = None) -> dict[tuple[str, str], dict]:
    """{(table, column): finding} for every column a rule flags (all tables, or the named ones)."""
    wanted = {t.lower() for t in tables} if tables else None
    out = {}
    for t in schema:
        if wanted is not None and t.name.lower() not in wanted:
            continue
        for c in t.column_names:
            f = classify(t.name, c)
            if f:
                out[(t.name, c)] = f
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
