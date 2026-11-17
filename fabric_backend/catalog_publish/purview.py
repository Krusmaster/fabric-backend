"""CA1: the product card in Microsoft Purview Unified Catalog's terms, for a Purview steward to create. Nothing here is
sent: the APIs are public preview, documented with a service principal (not the signed-in user Krusgraph acts as), and
Purview's data governance is being retired (apis.PURVIEW_RETIRING, on Learn 17 November 2026). A customer who uses it
until then gets the requests ready.

Rule types are Purview's own names in its rule list (unified-catalog-data-quality-rules, updated 12 Nov 2026). The
API's `type` string is documented only for "Duplicate rows" (`Duplicate`); for the others it is left None and the rule
is created by its name in the portal (Unverified)."""
from __future__ import annotations

from . import apis

API = "2026-03-20-preview"
DQ_API = "2026-01-12-preview"
ENDPOINT = "{purview-endpoint}"     # e.g. https://api.purview-service.microsoft.com, the customer's


def dq_rules(card: dict) -> list[dict]:
    """Krusgraph's rules as Purview Data Quality rules. A rule Purview cannot express as documented is kept with why."""
    mine = {t.lower() for t in card["tables"]}
    out = []
    for r in card["quality_rules"]:
        base = {"from": r["id"], "asset": r["table"], "status": r["status"], "description": r["says"]}
        if r["kind"] == "unique_key":
            if len(r["columns"]) == 1:
                out.append({**base, "rule_type": "Unique values", "api_type": None, "columns": r["columns"],
                            "dimension": "Uniqueness"})
            else:
                out.append({**base, "rule_type": "Duplicate rows", "api_type": "Duplicate", "columns": r["columns"],
                            "dimension": "Uniqueness", "note": "one Duplicate rows rule per asset"})
            for c in r["columns"]:
                out.append({**base, "from": r["id"] + "_" + c.lower() + "_not_empty", "rule_type": "Empty/blank fields",
                            "api_type": None, "columns": [c], "dimension": "Completeness",
                            "description": f"{r['table']}.{c} (part of the key) is never empty"})
        elif r["kind"] == "no_orphans":
            same = r["target"].lower() in mine
            out.append({**base, "rule_type": "Table lookup", "api_type": None, "columns": r["columns"],
                        "reference": {"asset": r["target"], "columns": r["target_columns"]}, "dimension": "Consistency",
                        **({} if same else {"note": "the reference table must be in the same governance domain"})})
        else:
            out.append({**base, "rule_type": None, "api_type": None, "dimension": "Accuracy",
                        "note": ("not expressible as documented: Purview's Custom (SQL) rules are row predicates, and a "
                                 "count across two tables is not one (Unverified). Krusgraph's own check keeps it "
                                 "(the T-SQL in the card).")})
    return out


def requests(card: dict) -> list[dict]:
    """The Unified Catalog requests for one card, in order, with the role each needs. Ids are placeholders."""
    gd = "{governance-domain-id}"
    product = {"name": card["name"], "description": card["description"], "domain": gd}
    out = [
        {"step": f"Governance domain for {card['domain']['proposed']}", "by": "purview_domain_creator",
         "method": "POST", "url": f"{ENDPOINT}/datagovernance/catalog/businessdomains?api-version={API}",
         "body": {"name": card["domain"]["proposed"], "description": f"Proposed by Krusgraph: {card['domain']['why']}"},
         "note": "only if no governance domain fits; one may already exist"},
        {"step": f"Data product {card['name']}", "by": "purview_steward", "method": "POST",
         "url": f"{ENDPOINT}/datagovernance/catalog/dataProducts?api-version={API}", "body": product,
         "add_by_hand": {"owner": card["owner"], "documentation": card["contract"]["file"]},
         "note": "the endorsed flag is left out: endorsement is a person's decision"},
    ]
    for t in card["glossary"]:
        out.append({"step": f"Glossary term {t['term']}", "by": "purview_steward", "method": "POST",
                    "url": f"{ENDPOINT}/datagovernance/catalog/terms?api-version={API}",
                    "body": {"name": t["term"], "description": t["definition"], "domain": gd}})
    for r in dq_rules(card):
        if not r["rule_type"]:
            continue
        out.append({"step": f"Data quality rule {r['rule_type']} on {r['asset']}", "by": "purview_dq_steward",
                    "method": "PUT", "url": (f"{ENDPOINT}/datagovernance/quality/business-domains/{gd}/data-products/"
                                             f"{{data-product-id}}/data-assets/{{id of {r['asset']}}}/rules/{r['from']}"
                                             f"?api-version={DQ_API}"),
                    "rule": r, "note": "the asset's metadata must exist in Purview first"})
    return out


def handover(cards: list[dict]) -> dict:
    return {"retiring": apis.PURVIEW_RETIRING, "source": apis.SOURCES["purview_unified_catalog"][0],
            "auth": "the APIs are documented with a service principal and scope https://purview.azure.net/.default",
            "products": [{"name": c["name"], "requests": requests(c), "rules": dq_rules(c)} for c in cards]}
