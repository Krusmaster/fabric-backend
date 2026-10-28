"""A synthetic SAP schema for the pack tests: tables and columns only, written from the pack itself plus a few
ordinary non-key columns per table. No rows, no values from any real installation."""
from __future__ import annotations

from fabric_backend import sap_pack
from fabric_backend.schema import Schema

# a few non-key columns per table, so the name rules have something to read (dates, types, organisation fields)
EXTRA = {
    "KNA1": ["NAME1", "LAND1", "ORT01", "KTOKD"], "KNVV": ["KDGRP", "WAERS"], "MARA": ["MTART", "MATKL", "MEINS"],
    "MAKT": ["MAKTX"], "TVKO": ["WAERS", "BUKRS"], "VBAK": ["AUART", "VBTYP", "KUNNR", "VKORG", "VTWEG", "SPART", "AUDAT"],
    "VBAP": ["MATNR", "PSTYV", "ABGRU"], "VBEP": ["EDATU", "ETTYP"], "VBPA": ["PARVW", "KUNNR", "ADRNR"],
    "LIKP": ["LFART", "KUNNR", "KUNAG", "VKORG", "WADAT_IST"], "LIPS": ["MATNR", "VGBEL", "VGPOS"],
    "VBRK": ["FKART", "FKDAT", "KUNAG", "KUNRG", "VKORG", "BUKRS", "BELNR", "GJAHR", "FKSTO"],
    "VBRP": ["MATNR", "AUBEL", "AUPOS", "VGBEL", "VGPOS"], "VBFA": ["VBTYP_V", "RFMNG", "ERDAT"],
    "BKPF": ["BLART", "BUDAT"], "BSEG": ["SHKZG", "HKONT"], "ACDOCA": ["RACCT", "BUDAT"],
}
DECIMALS = {"NETWR", "MWSBK", "KWMENG", "WMENG", "LFIMG", "FKIMG", "WRBTR", "DMBTR", "WSL", "HSL", "RFMNG"}


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
