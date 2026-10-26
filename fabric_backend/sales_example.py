"""The synthetic data behind the first customer demonstration: two companies, one product group, weekly sales
(the brief of 26 October 2026, "Two companies. One sales view. A clearer basis for planning.").

Everything here is invented and labelled so on the page: "Company A" and "Company B" are no real companies, the
products and codes are made up (the GTINs use the 20-29 prefix GS1 keeps for in-house numbering, so they cannot be
anyone's product), and the numbers come from a seeded random generator. The two companies keep their data the way two
different systems would: other column names, other status words, other categories. The engine reads both through the
column maps below; nothing is aggregated in advance, so the page's numbers come from the raw lines every time.

What the data holds on purpose, so the demonstration has something real to find:
- Company B files the lights under a broader category (Accessories); which of its products belong to the group comes from
  matching them to Company A's register. Two match by identical GTIN.
- One Company B product (CMTR SET 2PC) has no GTIN but the same supplier article number as Company A's Commuter Light
  Set. That is a suggestion, not proof: the person decides.
- Company B's register keeps two rows for B-7002 (it was renamed); joining sales to every register row counts its sales
  twice.
- Cancelled lines exist in both; the definition leaves them out.
- Company B's history starts later (78 weeks) than Company A's (104 weeks); CMTR SET 2PC has sold for 20 weeks.
"""
from __future__ import annotations

import math
import random
from datetime import date, timedelta
from functools import lru_cache

LATEST_WEEK = date(2026, 10, 19)            # Monday of the latest complete week (ISO week 43, 19-25 October 2026)
A_WEEKS, B_WEEKS, NEW_WEEKS = 104, 78, 20
SEED = 20261026

GROUP = "Bike lights"                       # the product group, as Company A's register names it
REFERENCE = "A"                             # the company whose register defines the group

COMPANIES = {
    "A": {"name": "Company A", "source": "order lines from an order system",
          "register_columns": {"product": "product_id", "name": "name", "category": "category", "gtin": "gtin",
                               "supplier_article": "supplier_article", "unit": "unit"},
          "line_columns": {"product": "product_id", "quantity": "quantity", "status": "status", "date": "delivered_on"},
          "counted": "delivered", "date_meaning": "delivery date"},
    "B": {"name": "Company B", "source": "sales lines from another business system",
          "register_columns": {"product": "artnr", "name": "description", "category": "group", "gtin": "ean",
                               "supplier_article": "supplier_no", "unit": "unit", "valid_to": "valid_to"},
          "line_columns": {"product": "artnr", "quantity": "qty", "status": "state", "date": "ship_date"},
          "counted": "SHIPPED", "date_meaning": "shipping date"},
}

REGISTER_A = [
    {"product_id": "A-101", "name": "Trail Light Front 400", "category": "Bike lights", "gtin": "2000000000015",
     "supplier_article": "SUP-2210", "unit": "pcs"},
    {"product_id": "A-102", "name": "Trail Light Rear", "category": "Bike lights", "gtin": "2000000000022",
     "supplier_article": "SUP-2211", "unit": "pcs"},
    {"product_id": "A-103", "name": "Commuter Light Set", "category": "Bike lights", "gtin": "2000000000039",
     "supplier_article": "SUP-4471", "unit": "pcs"},
    {"product_id": "A-201", "name": "Trail Helmet M", "category": "Helmets", "gtin": "2000000000046",
     "supplier_article": "SUP-3105", "unit": "pcs"},
]
REGISTER_B = [
    {"artnr": "B-7001", "description": "TRL FRNT LT 400LM", "group": "Accessories", "ean": "2000000000015",
     "supplier_no": "SUP-2210", "unit": "pcs", "valid_to": ""},
    {"artnr": "B-7002", "description": "TRL REAR LT V1", "group": "Accessories", "ean": "2000000000022",
     "supplier_no": "SUP-2211", "unit": "pcs", "valid_to": "2025-12-31"},
    {"artnr": "B-7002", "description": "TRL REAR LT", "group": "Accessories", "ean": "2000000000022",
     "supplier_no": "SUP-2211", "unit": "pcs", "valid_to": ""},
    {"artnr": "B-7003", "description": "CMTR SET 2PC", "group": "Accessories", "ean": "",
     "supplier_no": "SUP-4471", "unit": "pcs", "valid_to": ""},
    {"artnr": "B-7101", "description": "BELL CLASSIC", "group": "Accessories", "ean": "2000000000053",
     "supplier_no": "SUP-5120", "unit": "pcs", "valid_to": ""},
    {"artnr": "B-7102", "description": "LOCK U 18MM", "group": "Accessories", "ean": "2000000000060",
     "supplier_no": "SUP-5188", "unit": "pcs", "valid_to": ""},
]

# (product, mean units per week at the start, growth per year, season: "dark" peaks in December, "summer" in June)
_PRODUCTS = {
    "A": [("A-101", 55, 0.08, "dark"), ("A-102", 40, 0.10, "dark"), ("A-103", 22, 0.06, "dark"), ("A-201", 30, 0.03, "summer")],
    "B": [("B-7001", 28, 0.15, "dark"), ("B-7002", 24, 0.12, "dark"), ("B-7003", 14, 0.0, "dark"),
          ("B-7101", 9, 0.02, "summer"), ("B-7102", 11, 0.02, "flat")],
}


def _season(kind: str, day: date) -> float:
    doy = day.timetuple().tm_yday
    if kind == "dark":
        return 1 + 0.5 * math.cos(2 * math.pi * (doy - 350) / 365.25)
    if kind == "summer":
        return 1 + 0.45 * math.cos(2 * math.pi * (doy - 170) / 365.25)
    return 1.0


def _first_week(company: str, product: str) -> date:
    if product == "B-7003":
        return LATEST_WEEK - timedelta(weeks=NEW_WEEKS - 1)
    return LATEST_WEEK - timedelta(weeks=(A_WEEKS if company == "A" else B_WEEKS) - 1)


@lru_cache(maxsize=1)
def lines() -> dict[str, list[dict]]:
    """Every sales line of both companies, in each company's own column names. Deterministic."""
    rnd = random.Random(SEED)
    out: dict[str, list[dict]] = {"A": [], "B": []}
    for company, products in _PRODUCTS.items():
        cols = COMPANIES[company]["line_columns"]
        counted, cancelled = COMPANIES[company]["counted"], ("cancelled" if company == "A" else "CANCELLED")
        order = 100000 if company == "A" else 500000
        for product, base, growth, season in products:
            start = _first_week(company, product)
            week, n = start, 0
            while week <= LATEST_WEEK:
                years = (week - start).days / 365.25
                ramp = min(1.0, (n + 1) / 6) if product == "B-7003" else 1.0          # a new product takes a few weeks
                mean = base * _season(season, week + timedelta(days=3)) * (1 + growth) ** years * ramp
                units = max(0, round(rnd.gauss(mean, math.sqrt(max(mean, 1)))))
                while units > 0:
                    q = min(units, rnd.choice((1, 1, 1, 1, 2, 2, 3)))
                    units -= q
                    order += 1
                    out[company].append({"order": order, cols["product"]: product, cols["quantity"]: q,
                                         cols["status"]: counted, cols["date"]: (week + timedelta(days=rnd.randrange(7))).isoformat()})
                    if rnd.random() < 0.04:                                            # a cancelled line next to it
                        order += 1
                        out[company].append({"order": order, cols["product"]: product, cols["quantity"]: rnd.choice((1, 2)),
                                             cols["status"]: cancelled,
                                             cols["date"]: (week + timedelta(days=rnd.randrange(7))).isoformat()})
                week += timedelta(weeks=1)
                n += 1
    return out


def registers() -> dict[str, list[dict]]:
    return {"A": REGISTER_A, "B": REGISTER_B}
