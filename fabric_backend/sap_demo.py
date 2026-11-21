"""Synthetic SAP-shaped tables with rows, for running the SAP pack's checks end to end (round n32).

Every value is made up: customers "Demo Customer 10", e-mail addresses at example.invalid, materials numbered from 1.
Nothing comes from an SAP system or an installation. The tables follow the pack's keys and relationships, so a run on
them shows that the tools work on SAP-shaped data in Fabric, never that the pack is right about SAP: the rows are
written from the pack. A `verified` entry from such a run would prove nothing and must not be written (sap-verify
refuses a `where` that names this demo).

The traps are planted, and EXPECTED says what each check should find:
- two clients: client 200 has an order numbered like one in client 100, and the same customer number;
- order 0000000001 has three items, so its VBAK.NETWR summed over its VBAP rows counts three times; the other orders have
  one item each, so over all orders the join gives 1 950 against 750 summed once per order (2.6 times, not three);
- an item of an order that does not exist (VBAP 0000000009): an orphan the check must report;
- a payer that differs from the sold-to party, a ship-to on the delivery, a document address in VBPA;
- the document flow from the order to its delivery (J) and its invoice (M);
- an address with an international version (NATION I) and one with an expired period: one row each is valid today;
- two e-mail addresses for one address, a contact person: personal data the pack names.

The SAP full demo (round SAPD1, 21 Nov 2026): tables(full=True) adds 28 tables of the pack's procure-to-pay, finance,
accounting document, business partner and pricing modules (FULL_TABLES), so the engine proposes five data products
instead of two (EXPECTED_FULL). The 17 tables and their rows above stay as they are; everything that takes no `full`
argument still sees only them. Planted in the full set (EXPECTED_FULL names what the checks find):
- client 200 has purchase order 4500000001 too, but its supplier has no company code, purchasing organization or
  plant data in client 200: with MANDT in the join it points at nothing (four reviews), without it it borrows 100's;
- an item of a purchase order that does not exist (EKPO 4500000009): an orphan;
- a deleted purchase order item (EKPO.LOEKZ L) that is still in the table;
- the order history (EKBE) has a goods receipt and an invoice receipt per item: EKPO.NETWR over EKBE counts twice;
- the supplier invoice's gross amount on its header (RBKP.RMWWR) and two items on invoice 5105600001;
- the invoice number 5105600001 in 2025 and in 2026 (GJAHR in the key), and as a G/L document's BELNR in BKPF;
- ACDOCA: client column RCLNT, signed amounts, every line in two ledgers (0L and 2L), a cost center with two validity
  periods, an account number in two charts of accounts (SKA1);
- business partner numbers that differ from the customer numbers (linked through CVI_CUST_LINK's GUID);
- conditions with a statistical line (KSTAT) and a tax rate (KBETR in percent), and a price record replaced by a
  newer one (KONH validity).

    tables(full=False)      -> {name: (columns, types, rows)}
    write_csv(folder, full=False) -> one CSV per table, the types in _types.json, and load_sap_demo.py, a PySpark notebook
                               that loads them into a lakehouse as Delta tables (sap_vbak, ...): run it in Fabric yourself
    sqlite(full=False)      -> (Schema, execute) over the same rows in SQLite, as the tests and a local run use
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

PREFIX = "sap_"
DEMO_WHERE = "synthetic SAP demo"          # what a run on these tables is; sap-verify refuses to record it
_D = "decimal(15,2)"
FOREVER, START = "99991231", "00010101"


def _t(cols: list[str], rows: list[tuple], decimals: tuple[str, ...] = ()) -> tuple[list[str], list[str], list[tuple]]:
    return cols, [_D if c in decimals else "string" for c in cols], rows


def tables(full: bool = False) -> dict[str, tuple[list[str], list[str], list[tuple]]]:
    """The 17 order-to-cash tables; with full=True also the 28 tables of the SAP full demo (FULL_TABLES, round SAPD1)."""
    out = _small()
    if full:
        out.update(_full())
    return out


def _small() -> dict[str, tuple[list[str], list[str], list[tuple]]]:
    m1, m2, m3 = "000000000000000001", "000000000000000002", "000000000000000003"
    return {
        "T001": _t(["MANDT", "BUKRS", "KTOPL", "WAERS", "ADRNR"], [("100", "1000", "DEMO", "EUR", "0000000101"),
                                                                ("200", "1000", "DEMO", "EUR", "")]),
        "TVKO": _t(["MANDT", "VKORG", "BUKRS", "WAERS"], [("100", "1000", "1000", "EUR"), ("200", "1000", "1000", "EUR")]),
        "KNA1": _t(["MANDT", "KUNNR", "NAME1", "STRAS", "PSTLZ", "ORT01", "LAND1", "TELF1", "ADRNR"], [
            ("100", "0000000010", "Demo Customer 10", "Demo Street 1", "11111", "Demo City", "DE", "+00 000 0010", "0000000201"),
            ("100", "0000000011", "Demo Customer 11", "Demo Street 2", "11112", "Demo City", "DE", "+00 000 0011", "0000000202"),
            ("100", "0000000012", "Demo Customer 12", "Demo Street 3", "11113", "Demo City", "DE", "+00 000 0012", "0000000203"),
            ("200", "0000000010", "Other Client Customer 10", "Other Street 1", "22221", "Other City", "DE", "", "")]),
        "MARA": _t(["MANDT", "MATNR", "MTART", "MEINS"], [("100", m1, "FERT", "ST"), ("100", m2, "FERT", "ST"), ("100", m3, "HAWA", "ST"),
                                                         ("200", m1, "FERT", "ST")]),
        "MAKT": _t(["MANDT", "MATNR", "SPRAS", "MAKTX"], [("100", m, l, f"Demo material {m[-1]} ({l})") for m in (m1, m2, m3) for l in ("E", "D")]),
        "VBAK": _t(["MANDT", "VBELN", "AUART", "VBTYP", "KUNNR", "VKORG", "NETWR", "WAERK", "ERDAT", "AEDAT", "KNUMV"], [
            ("100", "0000000001", "TA", "C", "0000000010", "1000", 600.00, "EUR", "20261001", "20261002", "0000000501"),
            ("100", "0000000002", "TA", "C", "0000000011", "1000", 100.00, "EUR", "20261003", "20261003", "0000000502"),
            ("200", "0000000001", "TA", "C", "0000000010", "1000", 50.00, "EUR", "20261001", "20261001", "0000000501")], ("NETWR",)),
        "VBAP": _t(["MANDT", "VBELN", "POSNR", "MATNR", "NETWR", "WAERK", "KWMENG", "VRKME", "ERDAT"], [
            ("100", "0000000001", "000010", m1, 300.00, "EUR", 3, "ST", "20261001"),
            ("100", "0000000001", "000020", m2, 200.00, "EUR", 2, "ST", "20261001"),
            ("100", "0000000001", "000030", m3, 100.00, "EUR", 1, "ST", "20261001"),
            ("100", "0000000002", "000010", m1, 100.00, "EUR", 1, "ST", "20261003"),
            ("100", "0000000009", "000010", m2, 40.00, "EUR", 1, "ST", "20261004"),       # planted: no such order
            ("200", "0000000001", "000010", m1, 50.00, "EUR", 1, "ST", "20261001")], ("NETWR", "KWMENG")),
        "VBEP": _t(["MANDT", "VBELN", "POSNR", "ETENR", "EDATU", "WMENG", "VRKME"], [
            ("100", "0000000001", "000010", "0001", "20261010", 2, "ST"), ("100", "0000000001", "000010", "0002", "20261020", 1, "ST"),
            ("100", "0000000001", "000020", "0001", "20261010", 2, "ST"), ("100", "0000000001", "000030", "0001", "20261010", 1, "ST"),
            ("100", "0000000002", "000010", "0001", "20261012", 1, "ST")], ("WMENG",)),
        "LIKP": _t(["MANDT", "VBELN", "LFART", "KUNNR", "KUNAG", "VKORG", "ERDAT"], [
            ("100", "0080000001", "LF", "0000000011", "0000000010", "1000", "20261010")]),
        "LIPS": _t(["MANDT", "VBELN", "POSNR", "MATNR", "VGBEL", "VGPOS", "LFIMG", "VRKME"], [
            ("100", "0080000001", "000010", m1, "0000000001", "000010", 2, "ST"),
            ("100", "0080000001", "000020", m2, "0000000001", "000020", 2, "ST")], ("LFIMG",)),
        "VBRK": _t(["MANDT", "VBELN", "FKART", "KUNAG", "KUNRG", "VKORG", "BUKRS", "NETWR", "MWSBK", "WAERK", "FKDAT", "KNUMV"], [
            ("100", "0090000001", "F2", "0000000010", "0000000012", "1000", "1000", 400.00, 80.00, "EUR", "20261011", "0000000601")], ("NETWR", "MWSBK")),
        "VBRP": _t(["MANDT", "VBELN", "POSNR", "MATNR", "AUBEL", "AUPOS", "VGBEL", "VGPOS", "NETWR", "FKIMG", "VRKME"], [
            ("100", "0090000001", "000010", m1, "0000000001", "000010", "0080000001", "000010", 200.00, 2, "ST"),
            ("100", "0090000001", "000020", m2, "0000000001", "000020", "0080000001", "000020", 200.00, 2, "ST")], ("NETWR", "FKIMG")),
        "VBFA": _t(["MANDT", "VBELV", "POSNV", "VBELN", "POSNN", "VBTYP_N", "VBTYP_V", "RFMNG"], [
            ("100", "0000000001", "000010", "0080000001", "000010", "J", "C", 2), ("100", "0000000001", "000020", "0080000001", "000020", "J", "C", 2),
            ("100", "0000000001", "000010", "0090000001", "000010", "M", "C", 2), ("100", "0000000001", "000020", "0090000001", "000020", "M", "C", 2)],
            ("RFMNG",)),
        "VBPA": _t(["MANDT", "VBELN", "POSNR", "PARVW", "KUNNR", "PARNR", "ADRNR"], [
            ("100", "0000000001", "000000", "AG", "0000000010", "", ""),
            ("100", "0000000001", "000000", "WE", "0000000011", "", "0000000901"),           # a ship-to address typed into the order
            ("100", "0000000001", "000000", "RG", "0000000012", "", ""),
            ("100", "0000000001", "000000", "AP", "", "0000000701", ""),                     # a contact person
            ("100", "0080000001", "000000", "WE", "0000000011", "", "")]),                   # a partner row of the delivery
        "KNVK": _t(["MANDT", "PARNR", "KUNNR", "LIFNR", "NAMEV", "NAME1", "TELF1", "PAFKT"], [
            ("100", "0000000701", "0000000010", "", "Demo", "Contact", "+00 000 0701", "01")]),
        "ADRC": _t(["CLIENT", "ADDRNUMBER", "DATE_FROM", "NATION", "DATE_TO", "NAME1", "STREET", "POST_CODE1", "CITY1", "COUNTRY"], [
            ("100", "0000000101", START, "", FOREVER, "Demo Company Code", "Demo Street 100", "11100", "Demo City", "DE"),
            ("100", "0000000201", START, "", FOREVER, "Demo Customer 10", "Demo Street 1", "11111", "Demo City", "DE"),
            ("100", "0000000201", START, "I", FOREVER, "DEMO CUSTOMER 10", "DEMO STREET 1", "11111", "DEMO CITY", "DE"),   # international version
            ("100", "0000000202", START, "", "20251231", "Demo Customer 11", "Old Street 2", "11112", "Demo City", "DE"),   # expired
            ("100", "0000000202", "20260101", "", FOREVER, "Demo Customer 11", "Demo Street 2", "11112", "Demo City", "DE"),
            ("100", "0000000203", START, "", FOREVER, "Demo Customer 12", "Demo Street 3", "11113", "Demo City", "DE"),
            ("100", "0000000901", START, "", FOREVER, "Demo Ship-to", "Dock 9", "11119", "Demo Harbour", "DE")]),
        "ADR6": _t(["CLIENT", "ADDRNUMBER", "PERSNUMBER", "DATE_FROM", "CONSNUMBER", "SMTP_ADDR", "FLGDEFAULT"], [
            ("100", "0000000201", "", START, "001", "orders@customer10.example.invalid", "X"),
            ("100", "0000000201", "", START, "002", "invoices@customer10.example.invalid", "")]),
    }


# ---------------------------------------------------------------- the SAP full demo (round SAPD1, 21 Nov 2026)
# 28 more tables of the pack's procure-to-pay, finance, accounting document, business partner and pricing modules,
# on the same client, company code, customers and materials as the 17 above. Every table and column name is one the
# pack (fabric_backend/packs/sap/*.json) names; every value is made up: "Demo Supplier 1", numbers counted from 1.
# Where the pack has an ECC and an S/4HANA table for one thing, the S/4HANA one (ACDOCA, not BSEG and the open-item
# tables; PRCD_ELEMENTS, not KONV), so no table sits next to its twin of the other variant.
FULL_TABLES = ("LFA1", "LFB1", "LFM1", "T024E", "T001W", "EBAN", "EKKO", "EKPO", "EKET", "EKBE", "RBKP", "RSEG",
               "T004", "SKA1", "SKB1", "KNB1", "TKA01", "CSKS", "CEPC", "BKPF", "ACDOCA",
               "BUT000", "BUT020", "CVI_CUST_LINK", "T685", "KONH", "KONP", "PRCD_ELEMENTS")


def _full() -> dict[str, tuple[list[str], list[str], list[tuple]]]:
    m1, m2, m3 = "000000000000000001", "000000000000000002", "000000000000000003"
    s1, s2 = "0000300001", "0000300002"
    po0, po1, po2 = "4500000000", "4500000001", "4500000002"
    iv1, iv2 = "5105600001", "5105600002"                        # supplier invoice numbers (RBKP.BELNR)
    a_rec, a_pay, a_rev, a_out, a_in, a_grir, a_use, a_dp, a_bank = (
        "0000140000", "0000160000", "0000800000", "0000175000", "0000154000", "0000191100", "0000400000",
        "0000170000", "0000113100")
    accounts = (a_rec, a_pay, a_rev, a_out, a_in, a_grir, a_use, a_dp, a_bank)
    cc, pc = "0000001000", "0000001000"                         # a cost center and a profit center

    def guid(n: str) -> str:                                    # a made-up partner GUID, 32 hex characters
        return ("DE30" + n).rjust(32, "0")
    return {
        # ------------------------------------------------ procure to pay
        "LFA1": _t(["MANDT", "LIFNR", "NAME1", "STRAS", "PSTLZ", "ORT01", "TELF1", "ERDAT"], [
            ("100", s1, "Demo Supplier 1", "Supply Street 1", "33331", "Demo Town", "+00 000 3001", "20250105"),
            ("100", s2, "Demo Supplier 2", "Supply Street 2", "33332", "Demo Town", "+00 000 3002", "20250106"),
            ("200", s1, "Other Client Supplier 1", "Other Street 9", "22229", "Other City", "", "20250105")]),
        "LFB1": _t(["MANDT", "LIFNR", "BUKRS", "ERDAT"], [("100", s1, "1000", "20250105"), ("100", s2, "1000", "20250106")]),
        "LFM1": _t(["MANDT", "LIFNR", "EKORG", "WAERS", "ERDAT"], [("100", s1, "1000", "EUR", "20250105"),
                                                                 ("100", s2, "1000", "EUR", "20250106")]),
        "T024E": _t(["MANDT", "EKORG", "BUKRS"], [("100", "1000", "1000")]),
        "T001W": _t(["MANDT", "WERKS"], [("100", "1000")]),
        "EBAN": _t(["MANDT", "BANFN", "BNFPO", "MATNR", "WERKS", "MENGE", "MEINS", "BADAT", "ERDAT"], [
            ("100", "0010000001", "00010", m1, "1000", 10, "ST", "20261001", "20261001"),
            ("100", "0010000001", "00020", "", "1000", 1, "ST", "20261001", "20261001")], ("MENGE",)),   # a service: no material
        "EKKO": _t(["MANDT", "EBELN", "BSART", "LIFNR", "BUKRS", "EKORG", "WAERS", "KNUMV", "AEDAT"], [
            ("100", po0, "NB", s2, "1000", "1000", "EUR", "0000000700", "20251110"),
            ("100", po1, "NB", s1, "1000", "1000", "EUR", "0000000701", "20261005"),
            ("100", po2, "NB", s2, "1000", "1000", "EUR", "0000000702", "20261012"),
            # the same number in client 200, whose supplier has no company code, purchasing organization or plant data
            # there: joined with MANDT it points at nothing, joined without it, it borrows client 100's
            ("200", po1, "NB", s1, "1000", "1000", "EUR", "0000000701", "20261005")]),
        "EKPO": _t(["MANDT", "EBELN", "EBELP", "MATNR", "WERKS", "MENGE", "MEINS", "NETWR", "BANFN", "BNFPO", "LOEKZ", "AEDAT"], [
            ("100", po0, "00010", m3, "1000", 1, "ST", 100.00, "", "", "", "20251110"),
            ("100", po1, "00010", m1, "1000", 10, "ST", 500.00, "0010000001", "00010", "", "20261005"),
            ("100", po1, "00020", m2, "1000", 5, "ST", 250.00, "", "", "", "20261005"),
            ("100", po1, "00030", m3, "1000", 2, "ST", 80.00, "", "", "L", "20261006"),     # planted: deleted, still here
            ("100", po2, "00010", "", "1000", 1, "ST", 300.00, "0010000001", "00020", "", "20261012"),   # a service item
            ("100", "4500000009", "00010", m2, "1000", 1, "ST", 25.00, "", "", "", "20261013"),       # planted: no such order
            ("200", po1, "00010", m1, "1000", 1, "ST", 40.00, "", "", "", "20261005")], ("MENGE", "NETWR")),
        "EKET": _t(["MANDT", "EBELN", "EBELP", "ETENR", "MENGE"], [
            ("100", po1, "00010", "0001", 6), ("100", po1, "00010", "0002", 4), ("100", po1, "00020", "0001", 5),
            ("100", po2, "00010", "0001", 1)], ("MENGE",)),
        # the history of an order item: a goods receipt (VGABE 1, a material document number) and an invoice receipt
        # (VGABE 2, the supplier invoice's number) per item, so a sum of EKPO.NETWR over EKBE counts each item twice
        "EKBE": _t(["MANDT", "EBELN", "EBELP", "ZEKKN", "VGABE", "GJAHR", "BELNR", "BUZEI", "MENGE", "WRBTR", "DMBTR", "WAERS", "SHKZG", "CPUDT"], [
            ("100", po1, "00010", "00", "1", "2026", "5000000001", "0001", 10, 500.00, 500.00, "EUR", "S", "20261008"),
            ("100", po1, "00010", "00", "2", "2026", iv1, "0001", 10, 500.00, 500.00, "EUR", "S", "20261015"),
            ("100", po1, "00020", "00", "1", "2026", "5000000001", "0002", 5, 250.00, 250.00, "EUR", "S", "20261008"),
            ("100", po1, "00020", "00", "2", "2026", iv1, "0002", 5, 250.00, 250.00, "EUR", "S", "20261015"),
            ("100", po2, "00010", "00", "2", "2026", iv2, "0001", 1, 300.00, 300.00, "EUR", "S", "20261020")],
            ("MENGE", "WRBTR", "DMBTR")),
        # the gross amount of the whole invoice on the header (RMWWR), and the same number 5105600001 in 2025 and 2026
        "RBKP": _t(["MANDT", "BELNR", "GJAHR", "BUKRS", "LIFNR", "WAERS", "RMWWR", "WMWST1", "CPUDT"], [
            ("100", iv1, "2025", "1000", s2, "EUR", 119.00, 19.00, "20251120"),
            ("100", iv1, "2026", "1000", s1, "EUR", 892.50, 142.50, "20261015"),
            ("100", iv2, "2026", "1000", s2, "EUR", 357.00, 57.00, "20261020")], ("RMWWR", "WMWST1")),
        "RSEG": _t(["MANDT", "BELNR", "GJAHR", "BUZEI", "EBELN", "EBELP", "MATNR", "MENGE", "BSTME", "WRBTR"], [
            ("100", iv1, "2025", "000001", po0, "00010", m3, 1, "ST", 100.00),
            ("100", iv1, "2026", "000001", po1, "00010", m1, 10, "ST", 500.00),
            ("100", iv1, "2026", "000002", po1, "00020", m2, 5, "ST", 250.00),
            ("100", iv2, "2026", "000001", po2, "00010", "", 1, "ST", 300.00)], ("MENGE", "WRBTR")),
        # ------------------------------------------------ finance (S/4HANA: BKPF and the universal journal ACDOCA)
        "T004": _t(["MANDT", "KTOPL"], [("100", "DEMO"), ("100", "DEM2"), ("200", "DEMO")]),
        # the account number 0000800000 in two charts of accounts: SAKNR alone is not a key
        "SKA1": _t(["MANDT", "KTOPL", "SAKNR", "ERDAT"], [("100", "DEMO", a, "20250101") for a in accounts]
                   + [("100", "DEM2", a_rev, "20250101")]),
        "SKB1": _t(["MANDT", "BUKRS", "SAKNR", "ERDAT"], [("100", "1000", a, "20250101") for a in accounts]),
        "KNB1": _t(["MANDT", "KUNNR", "BUKRS", "AKONT", "ERDAT"], [
            ("100", "0000000010", "1000", a_rec, "20250101"), ("100", "0000000011", "1000", a_rec, "20250101"),
            ("100", "0000000012", "1000", a_rec, "20250101")]),
        "TKA01": _t(["MANDT", "KOKRS"], [("100", "1000")]),
        # one cost center with two validity periods (DATBI is in the key): a join on KOSTL alone doubles a line
        "CSKS": _t(["MANDT", "KOKRS", "KOSTL", "DATBI", "DATAB", "BUKRS", "ERSDA"], [
            ("100", "1000", cc, "20251231", "20250101", "1000", "20250101"),
            ("100", "1000", cc, FOREVER, "20260101", "1000", "20251201")]),
        "CEPC": _t(["MANDT", "PRCTR", "DATBI", "KOKRS", "DATAB", "ERSDA"], [("100", pc, FOREVER, "1000", "20250101", "20250101")]),
        # 5105600001 is also a G/L document's number in 2026: the accounting document of supplier invoice 5105600001
        # is 5100000001 (AWKEY = invoice number and year), so a join of RBKP and BKPF on BELNR pairs unrelated documents
        "BKPF": _t(["MANDT", "BUKRS", "BELNR", "GJAHR", "WAERS", "AWTYP", "AWKEY", "CPUDT", "AEDAT"], [
            ("100", "1000", "0090000001", "2026", "EUR", "VBRK", "0090000001", "20261011", "20261011"),
            ("100", "1000", "5100000001", "2026", "EUR", "RMRP", iv1 + "2026", "20261015", "20261015"),
            ("100", "1000", iv1, "2026", "EUR", "BKPF", "", "20261016", "20261016"),
            ("100", "1000", "1400000001", "2026", "EUR", "BKPF", "", "20261017", "20261017")]),
        # signed amounts (credit negative); the client column is RCLNT and the company code RBUKRS; and every line twice,
        # once in the leading ledger 0L and once in the parallel ledger 2L, so a sum over both ledgers doubles
        "ACDOCA": _t(["RCLNT", "RLDNR", "RBUKRS", "GJAHR", "BELNR", "DOCLN", "RACCT", "KUNNR", "LIFNR", "KOKRS", "RCNTR", "PRCTR",
                      "BUDAT", "WSL", "RWCUR", "HSL", "RHCUR"], [
            ("100", ld, "1000", "2026", bel, n, acct, kunnr, lifnr, "1000" if (kostl or prctr) else "", kostl, prctr, budat, amt, "EUR", amt, "EUR")
            for ld in ("0L", "2L")
            for bel, n, acct, kunnr, lifnr, kostl, prctr, budat, amt in (
                ("0090000001", "000001", a_rec, "0000000012", "", "", "", "20261011", 480.00),
                ("0090000001", "000002", a_rev, "", "", "", pc, "20261011", -400.00),
                ("0090000001", "000003", a_out, "", "", "", "", "20261011", -80.00),
                ("5100000001", "000001", a_pay, "", s1, "", "", "20261015", -892.50),
                ("5100000001", "000002", a_grir, "", "", "", "", "20261015", 750.00),
                ("5100000001", "000003", a_in, "", "", "", "", "20261015", 142.50),
                (iv1, "000001", a_use, "", "", cc, pc, "20261016", 50.00),
                (iv1, "000002", a_rev, "", "", "", pc, "20261016", -50.00),
                ("1400000001", "000001", a_dp, "0000000010", "", "", "", "20261017", -100.00),
                ("1400000001", "000002", a_bank, "", "", "", "", "20261017", 100.00))], ("WSL", "HSL")),
        # ------------------------------------------------ the business partner behind the customers (S/4HANA)
        # partner numbers differ from customer numbers (0001000010 is customer 0000000010): join through CVI_CUST_LINK's GUID
        "BUT000": _t(["CLIENT", "PARTNER", "TYPE", "PARTNER_GUID", "CRDAT"], [
            ("100", "00010000" + n, "2", guid(n), "20250101") for n in ("10", "11", "12")]),
        "BUT020": _t(["CLIENT", "PARTNER", "ADDRNUMBER"], [
            ("100", "0001000010", "0000000201"), ("100", "0001000011", "0000000202"), ("100", "0001000012", "0000000203")]),
        "CVI_CUST_LINK": _t(["CLIENT", "PARTNER_GUID", "CUSTOMER"], [("100", guid(n), "00000000" + n) for n in ("10", "11", "12")]),
        # ------------------------------------------------ pricing (S/4HANA: PRCD_ELEMENTS)
        "T685": _t(["MANDT", "KVEWE", "KAPPL", "KSCHL"], [("100", "A", "V", "PR00"), ("100", "A", "V", "MWST"),
                                                        ("100", "A", "V", "VPRS"), ("100", "A", "M", "PB00")]),
        # a price record valid in 2025 and its successor valid from 2026: a document keeps the record it used (KNUMH)
        "KONH": _t(["MANDT", "KNUMH", "DATAB", "DATBI", "ERDAT"], [
            ("100", "0000001001", "20250101", "20251231", "20241201"), ("100", "0000001002", "20260101", FOREVER, "20251201"),
            ("100", "0000002001", "20250101", FOREVER, "20241201"), ("100", "0000002002", "20250101", FOREVER, "20241201")]),
        "KONP": _t(["MANDT", "KNUMH", "KOPOS", "KBETR", "KONWA", "KPEIN", "KMEIN", "KRECH"], [
            ("100", "0000001001", "01", 90.00, "EUR", 1, "ST", "C"), ("100", "0000001002", "01", 100.00, "EUR", 1, "ST", "C"),
            ("100", "0000002001", "01", 50.00, "EUR", 1, "ST", "C"), ("100", "0000002002", "01", 50.00, "EUR", 1, "ST", "C")],
            ("KBETR", "KPEIN")),
        # conditions of sales order 0000000001 (KNUMV 0000000501), its invoice (0000000601) and two purchase orders
        # (0000000701, 0000000702; KAPPL M). The statistical cost line (VPRS, KSTAT X) and the tax (MWST, KBETR a rate
        # in percent) are not part of the net value: summing every KWERT of the order gives 837, not its 600.
        "PRCD_ELEMENTS": _t(["MANDT", "KNUMV", "KPOSN", "STUNR", "ZAEHK", "KAPPL", "KSCHL", "KNUMH", "KBETR", "KWERT", "WAERS", "KSTAT", "KINAK"], [
            ("100", "0000000501", "000010", "010", "01", "V", "PR00", "0000001002", 100.00, 300.00, "EUR", "", ""),
            ("100", "0000000501", "000010", "800", "01", "V", "VPRS", "", 60.00, 180.00, "EUR", "X", ""),
            ("100", "0000000501", "000010", "900", "01", "V", "MWST", "", 19.00, 57.00, "EUR", "", ""),
            ("100", "0000000501", "000020", "010", "01", "V", "PR00", "0000001002", 100.00, 200.00, "EUR", "", ""),
            ("100", "0000000501", "000030", "010", "01", "V", "PR00", "0000001002", 100.00, 100.00, "EUR", "", ""),
            ("100", "0000000601", "000010", "010", "01", "V", "PR00", "0000001002", 100.00, 200.00, "EUR", "", ""),
            ("100", "0000000601", "000010", "900", "01", "V", "MWST", "", 20.00, 40.00, "EUR", "", ""),
            ("100", "0000000601", "000020", "010", "01", "V", "PR00", "0000001002", 100.00, 200.00, "EUR", "", ""),
            ("100", "0000000601", "000020", "900", "01", "V", "MWST", "", 20.00, 40.00, "EUR", "", ""),
            ("100", "0000000701", "000010", "010", "01", "M", "PB00", "0000002001", 50.00, 500.00, "EUR", "", ""),
            ("100", "0000000701", "000020", "010", "01", "M", "PB00", "0000002002", 50.00, 250.00, "EUR", "", ""),
            ("100", "0000000702", "000010", "010", "01", "M", "PB00", "", 300.00, 300.00, "EUR", "", "")],
            ("KBETR", "KWERT")),
    }


# What the checks should find on these rows. The tests run validate_plan, amount_levels, the privacy rules and
# sap-verify on them in SQLite and compare with this; docs/LIVE-TEST-SAP.md asks for the same on Fabric.
EXPECTED = {
    "tables": 17,
    "review": {("VBAP", "VBAK"): "the planted item of order 0000000009"},
    "no_evidence": [("VBFA", "VBAK")],                    # no flow row whose subsequent document is a sales document
    "verified_at_least": [("VBAP", "MARA"), ("VBRP", "VBRK"), ("LIPS", "VBAP"), ("VBRK", "KNA1"), ("VBFA", "LIPS"), ("VBFA", "VBRP"),
                          ("KNA1", "ADRC"), ("VBPA", "ADRC")],
    "header_amount": ("VBAK", "VBAP", "NETWR"),
    "masked": [("ADR6", "SMTP_ADDR"), ("KNA1", "TELF1"), ("KNVK", "NAMEV")],
}

# What the checks find on the full set (tables(full=True)); tests/test_sapd1_sap_full_demo.py compares.
EXPECTED_FULL = {
    "tables": 45,
    "review": {("VBAP", "VBAK"): "the planted item of order 0000000009",
               ("EKPO", "EKKO"): "the planted item of purchase order 4500000009",
               ("EKKO", "T024E"): "client 200's purchase order", ("EKKO", "LFM1"): "client 200's purchase order",
               ("EKKO", "LFB1"): "client 200's purchase order", ("EKPO", "T001W"): "client 200's purchase order item"},
    "no_evidence": [("VBFA", "VBAK"), ("KNVK", "LFA1")],
    "verified_at_least": EXPECTED["verified_at_least"] + [
        ("EKKO", "LFA1"), ("EKPO", "MARA"), ("EKPO", "EBAN"), ("EKBE", "EKPO"), ("EKBE", "RBKP"), ("RSEG", "RBKP"),
        ("RSEG", "EKPO"), ("ACDOCA", "BKPF"), ("ACDOCA", "SKB1"), ("ACDOCA", "CSKS"), ("ACDOCA", "CEPC"), ("KNB1", "SKB1"),
        ("SKA1", "T004"), ("CVI_CUST_LINK", "KNA1"), ("CVI_CUST_LINK", "BUT000"), ("PRCD_ELEMENTS", "EKKO"),
        ("PRCD_ELEMENTS", "KONH"), ("PRCD_ELEMENTS", "T685"), ("KONP", "KONH")],
    "header_amounts": [("VBAK", "VBAP", "NETWR"), ("RBKP", "RSEG", "RMWWR")],
    "masked": EXPECTED["masked"] + [("LFA1", "NAME1"), ("LFA1", "TELF1")],
    "products": ("procure-to-pay", "order-to-cash", "finance", "customer master", "pricing"),
}


def write_csv(folder: str | Path, prefix: str = PREFIX, full: bool = False) -> list[Path]:
    """One CSV per table (header row; text as text, so leading zeros stay), _types.json with each column's type, and
    load_sap_demo.py, the PySpark cells that load them. Upload the folder to the lakehouse's Files/sap_demo and run
    the notebook there; nothing here connects to Fabric."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    written, types = [], {}
    for name, (cols, kinds, rows) in (tables(full=True) if full else tables()).items():
        path = folder / f"{name}.csv"
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(cols)
            w.writerows(rows)
        written.append(path)
        types[name] = dict(zip(cols, kinds))
    (folder / "_types.json").write_text(json.dumps(types, indent=2) + "\n", encoding="utf-8")
    (folder / "load_sap_demo.py").write_text(notebook(prefix), encoding="utf-8")
    return written + [folder / "_types.json", folder / "load_sap_demo.py"]


def notebook(prefix: str = PREFIX) -> str:
    """PySpark for a Fabric notebook attached to the lakehouse that holds the CSVs under Files/sap_demo."""
    return f'''# Synthetic SAP demo tables for Krusgraph (fabric_backend/sap_demo.py). Every value is made up.
# Attach this notebook to the lakehouse, upload the CSV files and _types.json to Files/sap_demo, then run.
# Tables are written as {prefix}<name> (sap_vbak, ...) in the default schema; existing tables of that name are replaced.
import json
from pyspark.sql import functions as F

base = "Files/sap_demo"
types = json.loads("".join(r.value for r in spark.read.text(f"{{base}}/_types.json").collect()))
for name, cols in types.items():
    df = spark.read.option("header", True).option("inferSchema", False).csv(f"{{base}}/{{name}}.csv")
    for c, t in cols.items():
        if t != "string":
            df = df.withColumn(c, F.col(c).cast(t))
    df.write.mode("overwrite").format("delta").saveAsTable("{prefix}" + name.lower())
    print(name, df.count(), "rows")
'''


def sqlite(prefix: str = PREFIX, schema: str = "sap", full: bool = False):
    """(Schema, execute) over the demo rows in an in-memory SQLite database, the way the tests and a local run use them."""
    import sqlite3

    from .dialects import sqlite_sql
    from .schema import Schema
    con = sqlite3.connect(":memory:")
    con.execute(f"ATTACH DATABASE ':memory:' AS {schema}")
    info = []
    for name, (cols, kinds, rows) in (tables(full=True) if full else tables()).items():
        t = prefix + name.lower()
        con.execute(f"CREATE TABLE {schema}.[{t}] ({', '.join(f'[{c}]' for c in cols)})")
        con.executemany(f"INSERT INTO {schema}.[{t}] VALUES ({','.join('?' * len(cols))})", rows)
        info += [(schema, t, c, "decimal" if k != "string" else "nvarchar", i) for i, (c, k) in enumerate(zip(cols, kinds), 1)]

    def execute(sql: str):
        cur = con.execute(sqlite_sql(sql))
        names = [d[0] for d in cur.description]
        return [dict(zip(names, r)) for r in cur.fetchall()]
    return Schema.from_information_schema(info, schema=schema), execute


def notebook_inline(prefix: str = PREFIX, full: bool = False) -> str:
    """One notebook cell that holds every row itself: paste it into a Fabric notebook attached to the lakehouse and
    run it. No files to upload. The rows are the same as tables() and write_csv()."""
    data = {name: {"columns": cols, "types": kinds, "rows": [list(r) for r in rows]} for name, (cols, kinds, rows) in (tables(full=True) if full else tables()).items()}
    return f'''# Synthetic SAP demo tables for Krusgraph (fabric_backend/sap_demo.py, round n33). Every value is made up.
# Paste this whole cell into a notebook attached to the lakehouse (demo_lh) and run it. It writes {prefix}<name> tables
# (sap_t001, sap_kna1, sap_vbak, ...) as Delta tables in the default schema, replacing tables of those names.
import json
from decimal import Decimal
from pyspark.sql.types import DecimalType, StringType, StructField, StructType

DATA = json.loads(r"""{json.dumps(data, ensure_ascii=False)}""")

for name, t in DATA.items():
    fields = [StructField(c, DecimalType(15, 2) if k != "string" else StringType(), True) for c, k in zip(t["columns"], t["types"])]
    rows = [tuple(Decimal(str(v)) if k != "string" else v for v, k in zip(r, t["types"])) for r in t["rows"]]
    df = spark.createDataFrame(rows, StructType(fields))
    df.write.mode("overwrite").format("delta").option("overwriteSchema", "true").saveAsTable("{prefix}" + name.lower())
    print(name, df.count(), "rows")
'''
