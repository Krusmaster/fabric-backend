> 2026-11-21, round BL10 (sprint item BL10, backlog C-16).

# Currency, unit and sign in the suggested measures

A sum of `NETWR` over order lines in EUR and SEK is not an amount, and a sum of `KWMENG` over pieces and kilograms is
not a quantity. SAP rows carry the currency (`WAERS`, `WAERK`, `HWAER`, `RWCUR`, `RHCUR`) and the unit (`MEINS`,
`VRKME`, `BSTME`) next to the number. Other sources do the same with `currency`, `CurrencyIsoCode`, `valuta`, `unit`,
`uom` or `enhet`. The semantic model draft (`semantic_model_draft`, `create_semantic_model`) now keeps every suggested
sum within one currency or one unit. Nothing is created by these rules, and they are deterministic: column names, and
counts when rows are available. No model call is involved.

## The rules

The code is in `fabric_backend/amounts.py` (the names) and `fabric_backend/level_measures.py` (`respect_units`).

1. **Which column holds the currency or the unit.** A text column named like a currency or a unit in the same table.
   If there is none, the draft looks in the header of the same document: a relationship from the line to a table
   whose key is part of the line's key (`VBRP` to `VBRK`, `EKPO` to `EKKO`, `RSEG` to `RBKP`). Some SAP amounts have
   a fixed currency column: `WSL` uses `RWCUR`, `HSL` uses `RHCUR`, `KSL` uses `RKCUR`, `WRBTR` uses `WAERS` and
   `DMBTR` uses `HWAER`. A quantity (`MENGE`, `KWMENG`, `LFIMG`, `FKIMG`, `quantity`, `antal`) takes the unit; any
   other summed number takes the currency. An order amount computed as quantity × price takes the currency of the
   price's table. A rate or a share (`AverageRate`, `discount_pct`) is not treated as an amount.
2. **Counted with one value.** When the rows were counted (`amounts.unit_counts`, passed as
   `validation["unit_counts"]`) and every currency or unit column of the measure has one value, the plain `SUM` stays.
   Its description says that one value was counted.
3. **Several values, or not counted.** The measure is written per currency or per unit:

       IF(HASONEVALUE('sap_vbap'[WAERK]), SUM('sap_vbap'[NETWR]))

   It shows a value where the rows in the filter share one currency, and stays blank where they do not. Put the
   currency on the visual to see one total per currency. The description gives the reason ("amounts in several
   currencies") and whether the values were counted. For a currency on the document header, a filter on the lines
   alone does not narrow the header's currency (the relationship filters from header to line), so the measure stays
   blank until the currency is chosen. That is on purpose: blank is better than a mixed total.
4. **No sum at all.** A price per unit (`NETPR`, `KBETR`, `STPRS`, `unit_price`, `list_price`) is never summed. An
   amount whose currency column is in no table of the model (`EKBE.DMBTR`, in the company code's currency, which
   `EKBE` does not carry) gets no suggested sum. Neither does an amount whose header with the currency is left out of
   the model. `respect_units` returns these with the reason in `not_summed`.
5. **Sign.** When the table has a debit/credit indicator (`SHKZG`, `DRCRK`, `debit_credit`), the description of each
   amount measure says so. The sum adds the values as they are stored. Where the source stores them without a sign,
   a credit adds up like a debit. The expression is not changed, because the sign convention differs between tables.

## What changed in the drafts

- The SAP demo (`sap_demo.py`, full): every suggested `SUM` and `SUMX` over an amount or a quantity is either counted
  in one currency or unit, or guarded with `HASONEVALUE`. `EKBE.DMBTR` is no longer summed. This is asserted in
  `tests/test_bl10_currency.py`.
- The shop (`seed.py`) has no currency or unit column. Its measures are unchanged.
- The benchmark fixtures: the sums of prices per unit (`UnitPrice`, `ListPrice`, `RecommendedRetailPrice`,
  `LastCostPrice`, `P_RETAILPRICE`) are gone. The Salesforce demo's amounts are guarded by `CurrencyIsoCode`. The
  goldens in `tests/golden/` were updated for exactly these changes.

## What is not done

- `validate_plan` and `create_semantic_model` do not yet pass `unit_counts`. Without counts, every amount next to a
  currency column is guarded, even when the rows hold one currency. Wiring the count in belongs to the owners of
  `evidence.py` and `server.py`.
- The measures that are not suggested (rule 4) are not yet listed in the draft's README, which `semantic_model.py`
  writes.
- The DAX (`IF`, `HASONEVALUE`, `&&`) has not been evaluated in Power BI here. The TMDL is read back and every
  reference resolved, as in `tests/test_n133_level_measures.py`.
- Currency conversion is out of scope: the draft never converts, it only keeps currencies apart.
