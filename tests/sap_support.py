"""A synthetic SAP schema for the pack tests: tables and columns only, written from the pack itself plus a few
ordinary non-key columns per table. No rows, no values from any real installation."""
from __future__ import annotations

from fabric_backend import sap_pack
from fabric_backend.schema import Schema

# a few non-key columns per table, so the name rules have something to read (dates, types, organisation fields)
EXTRA = {
    "KNA1": ["NAME1", "LAND1", "ORT01", "KTOKD"], "KNVV": ["KDGRP", "WAERS"], "MARA": ["MTART", "MATKL", "MEINS"],
    "MAKT": ["MAKTX"], "TVKO": ["WAERS", "BUKRS"], "VBAK": ["KNUMV", "AUART", "VBTYP", "KUNNR", "VKORG", "VTWEG", "SPART", "AUDAT"],
    "VBAP": ["MATNR", "PSTYV", "ABGRU"], "VBEP": ["EDATU", "ETTYP"], "VBPA": ["PARVW", "KUNNR", "ADRNR"],
    "LIKP": ["LFART", "KUNNR", "KUNAG", "VKORG", "WADAT_IST"], "LIPS": ["MATNR", "VGBEL", "VGPOS"],
    "VBRK": ["FKART", "KNUMV", "FKDAT", "KUNAG", "KUNRG", "VKORG", "BUKRS", "BELNR", "GJAHR", "FKSTO"],
    "VBRP": ["MATNR", "AUBEL", "AUPOS", "VGBEL", "VGPOS"], "VBFA": ["VBTYP_V", "RFMNG", "ERDAT"],
    "LFA1": ["NAME1", "LAND1", "KTOKK"], "LFB1": ["AKONT", "ZTERM"], "LFM1": ["ZTERM"], "T024E": ["BUKRS"],
    "T001W": ["NAME1"], "EBAN": ["MATNR", "WERKS", "BSART"], "EKKO": ["KNUMV", "BSTYP", "BSART", "LIFNR", "BUKRS", "EKORG", "BEDAT"],
    "EKPO": ["MATNR", "WERKS", "LOEKZ"], "EKET": ["EINDT"], "EKBE": ["SHKZG", "BUDAT"],
    "RBKP": ["LIFNR", "BUKRS", "BLDAT"], "RSEG": ["EBELN", "EBELP", "MATNR"],
    "BKPF": ["BLART", "BUDAT"], "BSEG": ["SHKZG", "HKONT", "KUNNR", "LIFNR"],
    "ACDOCA": ["RACCT", "BUDAT", "KUNNR", "LIFNR", "KOKRS", "RCNTR", "PRCTR"], "T001": ["KTOPL", "WAERS"],
    "BUT000": ["PARTNER_GUID", "TYPE", "BU_GROUP"], "BUT100": ["VALID_FROM"], "BUT020": ["ADDRESS_GUID"],
    "BUT050": ["RELTYP", "DATE_FROM"], "CVI_CUST_LINK": ["CUSTOMER"], "CVI_VEND_LINK": ["VENDOR"],
    "KONV": ["KSCHL", "KBETR", "KINAK", "KSTAT"], "PRCD_ELEMENTS": ["KSCHL", "KBETR", "KINAK", "KSTAT"],
    "KONH": ["KSCHL", "DATAB", "DATBI"], "KONP": ["KSCHL", "KBETR", "KPEIN"],
    "SKA1": ["KTOKS"], "SKB1": ["WAERS"], "BSID": ["SHKZG", "BUDAT"], "BSAD": ["SHKZG", "AUGDT"], "BSIK": ["SHKZG"],
    "BSAK": ["SHKZG"], "CSKS": ["DATAB", "BUKRS"], "CEPC": ["DATAB"],
}
DECIMALS = {"KWERT", "KBETR", "RMWWR", "WMWST1", "MENGE", "NETWR", "MWSBK", "KWMENG", "WMENG", "LFIMG", "FKIMG", "WRBTR", "DMBTR", "WSL", "HSL", "RFMNG"}


def columns(name: str) -> list[str]:
    t = sap_pack.table_info(name)
    out: list[str] = []
    for group in (t["key"], EXTRA.get(name, []), t.get("number_columns", []), [a["column"] for a in t.get("amounts", [])],
                  [q["column"] for q in t.get("quantities", [])], t.get("currency_columns", []), t.get("unit_columns", []),
                  t.get("delta", [])):
        out += [c for c in group if c not in out]
    return out


def schema(tables: list[str] | None = None, style: str = "upper", variant: str = "ecc", drop_client: bool = False) -> Schema:
    """style: upper (VBAK), lower (vbak), prefix (sap_vbak with lower-case columns)."""
    pack = sap_pack.load()
    names = tables or [n for n, t in pack["tables"].items() if not t.get("variants") or variant in t["variants"]]
    rows = []
    for name in names:
        tname = {"upper": name, "lower": name.lower(), "prefix": "sap_" + name.lower()}[style]
        i = 0
        for c in columns(name):
            if drop_client and c in sap_pack.CLIENT_COLUMNS:
                continue
            i += 1
            col = c if style == "upper" else c.lower()
            rows.append(("sap", tname, col, "decimal(15,2)" if c in DECIMALS else "nvarchar(10)", i))
    return Schema.from_information_schema(rows, schema="sap")


def truth(variant: str = "ecc") -> tuple[dict, set]:
    """The pack's own keys and applied relationships for the variant: what a perfect plan of schema() contains."""
    pack = sap_pack.load()
    names = {n for n, t in pack["tables"].items() if not t.get("variants") or variant in t["variants"]}
    keys = {n: tuple(c.lower() for c in pack["tables"][n]["key"]) for n in names}
    rels = {(r["source"], tuple(c.lower() for c in r["source_cols"]), r["target"]) for r in pack["relationships"]
            if r["source"] in names and r["target"] in names and r.get("apply") is not False
            and (not r.get("variants") or variant in r["variants"])}
    return keys, rels


def listed(variant: str = "ecc") -> set:
    """(source, columns, target) of the pack's relationships that are listed but not applied: conditional, many-to-many, or on a
    unique column that is not the key. A name rule that finds one of them is partly right, not simply wrong."""
    pack = sap_pack.load()
    names = {n for n, t in pack["tables"].items() if not t.get("variants") or variant in t["variants"]}
    rels = [r for r in pack["relationships"] if r.get("apply") is False
            and r["source"] in names and r["target"] in names and (not r.get("variants") or variant in r["variants"])]
    out = {(r["source"], tuple(c.lower() for c in r["source_cols"]), r["target"]) for r in rels}
    # a one-to-one link holds both ways: VBUK -> VBAK also reads VBAK -> VBUK (the status row of the same document)
    return out | {(r["target"], tuple(c.lower() for c in r["target_cols"]), r["source"]) for r in rels if r["cardinality"] == "one-to-one"}
