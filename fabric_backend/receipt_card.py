"""The query behind each number on the chat's check card (round BL41, 23 November 2026; backlog C-36, BL1 follow-up).

A buyer's architect wants to see the statement behind every number where the number is shown, and to run it again.
receipt.build (BL1) already writes one row per number of validate_plan's answer with the read-only statement that
counted it. This module hands those statements to the check card (mcp_apps_next.check_rows):

    for_card(plan, validation, dialect="tsql") -> {"sql": {check id: statement}, "beside": str}

- `sql`: per check id of the card (key:<table>, rel:<source>.<cols>><target>, amount:<header>><line>), the statement
  as Fabric's SQL endpoint runs it. A check that was not counted has no statement and no entry.
- `beside`: the one sentence (at most 25 words) the card shows beside the queries.

Not here: the receipt notebook (BL19). The card may not save a file or read the clipboard (tests/test_n119_mcp_apps.py
bans `navigator.` and `url(`), and receipt_notebook builds only on the samples today; loosening the card's rules is
Gustav's decision. Statements only: no row value. Deterministic for a given `generated_at`."""
from __future__ import annotations

BESIDE = ("Each number's own read-only query, as Fabric's SQL endpoint runs it. Select one to copy it. "
          "Nothing here shows a row.")


def _card_id(item: str) -> str:
    """receipt.build's item id as the check card writes it (amount:<header><<line> -> amount:<header>><line>)."""
    if item.startswith("amount:") and "<" in item:
        head, line = item[len("amount:"):].split("<", 1)
        return f"amount:{head}>{line}"
    return item


def for_card(plan, validation: dict, dialect: str = "tsql", generated_at=None) -> dict:
    from . import receipt
    sql = {}
    for r in receipt.build(plan, validation, generated_at=generated_at, dialect=dialect):
        if r.get("sql"):
            sql.setdefault(_card_id(r["item"]), r["sql"])
    return {"sql": sql, "beside": BESIDE}
