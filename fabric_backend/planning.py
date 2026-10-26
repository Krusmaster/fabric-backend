"""From sales lines in two systems to one weekly sales view and a tested forecast (the first customer demonstration,
26 October 2026: "Show sales across our two companies and help me plan the next eight weeks").

Pure: it reads a dataset (each company's register and lines in its own column names, see sales_example.py) and returns
plain data. What it does, in the order a person meets it:

1. The definition. Sold volume is the units on a company's counted lines (Company A: delivered, Company B: shipped) by
   the ISO week of that date; other lines (cancelled) are left out and counted, so the scope can say how many.
2. The product group. The reference company's register defines it. Another company's product belongs to it when its
   GTIN equals a group product's (evidence enough); a matching supplier article number alone is a suggestion the person
   confirms, changes or leaves open. An open product is shown on its own, never folded into the combined numbers.
3. One weekly view. Units per company and week; a company with no data yet for a week has no value, not zero. Sales
   join each register once (its current row): joining every register row would count a renamed product twice, and the
   check says by how much.
4. The forecast. Three simple methods, each tested on the history it would have had: repeat last year, the average of the
   last eight weeks, and last year's pattern at this year's level. The one with the smallest error over those tests is
   used, also when that is the simplest. The range comes from the same tests. Too little history means no forecast and a
   plain reason; the history stays.

What it is not: demand (sold volume misses what could not be sold), a cause for a change, or advice on what to buy.
"""
from __future__ import annotations

import hashlib
import json
import statistics
from datetime import date, timedelta

DEFINITION_ID = "sold-volume/1"
HORIZON = 8                 # weeks ahead
SEASON = 52                 # weeks in a year, for "the same week a year earlier"
LEVEL = 8                   # weeks the level is measured over
NEED = SEASON + LEVEL       # history a method needs before its first forecast
MIN_TESTS, MAX_TESTS = 8, 26
PERIODS = (13, 26, 52, 104)

METHODS = (  # id, name, how it forecasts; the order breaks ties toward the simpler method
    ("last_year", "Repeat last year", "each week as the same week a year earlier"),
    ("recent_average", "Average of the last 8 weeks", "every week at the average of the last eight weeks"),
    ("seasonal_level", "Last year's pattern at this year's level",
     "the same weeks a year earlier, scaled by how the last eight weeks compare with the same eight weeks a year earlier"),
)


class PlanningInputError(ValueError):
    """A choice the example does not offer (a company, a period or a product decision)."""


def week_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


def week_label(monday: date) -> str:
    y, w, _ = monday.isocalendar()
    return f"week {w}, {y}"


def _weeks(first: date, last: date) -> list[date]:
    return [first + timedelta(weeks=i) for i in range((last - first).days // 7 + 1)]


# ------------------------------------------------------------------ 1. the definition, read per company -------------

def _lines(dataset: dict, company: str) -> tuple[list[tuple[str, date, int]], dict]:
    spec = dataset["companies"][company]
    c = spec["line_columns"]
    kept, left = [], {"lines": 0, "units": 0}
    for row in dataset["lines"][company]:
        if row[c["status"]] == spec["counted"]:
            kept.append((row[c["product"]], week_of(date.fromisoformat(row[c["date"]])), int(row[c["quantity"]])))
        else:
            left["lines"] += 1
            left["units"] += int(row[c["quantity"]])
    return kept, left


def _register(dataset: dict, company: str) -> tuple[dict[str, dict], dict[str, int]]:
    """Each product's current row (no end date), in common field names, and how many rows each product has."""
    c = dataset["companies"][company]["register_columns"]
    current, rows = {}, {}
    for r in dataset["registers"][company]:
        p = r[c["product"]]
        rows[p] = rows.get(p, 0) + 1
        if not r.get(c.get("valid_to", ""), ""):
            current[p] = {k: r.get(v, "") for k, v in c.items()}
    return current, rows


# ------------------------------------------------------------------ 2. the product group and the links --------------

def links(dataset: dict, decisions: dict[str, str] | None = None) -> list[dict]:
    """Every product of every company, with whether and why it belongs to the group. `decisions` answers suggested
    links: {product: "<reference product>" | "none" | "open"}."""
    ref = dataset["reference"]
    ref_reg, _ = _register(dataset, ref)
    group = {p: r for p, r in ref_reg.items() if r["category"] == dataset["group"]}
    by_gtin = {r["gtin"]: p for p, r in ref_reg.items() if r["gtin"]}
    by_supplier = {r["supplier_article"]: p for p, r in group.items() if r["supplier_article"]}
    decisions = dict(decisions or {})
    out = []
    for p, r in sorted(ref_reg.items()):
        out.append({"company": ref, "product": p, "name": r["name"], "target": p if p in group else None,
                    "status": "in group" if p in group else "outside",
                    "basis": f"{dataset['companies'][ref]['name']}'s register files it under {r['category']}"})
    for company in dataset["companies"]:
        if company == ref:
            continue
        reg, _ = _register(dataset, company)
        for p, r in sorted(reg.items()):
            item = {"company": company, "product": p, "name": r["name"], "gtin": r["gtin"] or None,
                    "supplier_article": r["supplier_article"] or None}
            hit = by_gtin.get(r["gtin"]) if r["gtin"] else None
            if hit:
                inside = hit in group
                item.update(target=hit if inside else None, status="linked" if inside else "outside",
                            basis=f"same GTIN as {ref_reg[hit]['name']} ({r['gtin']})")
            elif r["supplier_article"] in by_supplier:
                cand = by_supplier[r["supplier_article"]]
                choice = decisions.pop(p, "open")
                item.update(suggested=cand, evidence=[
                    f"same supplier article number as {group[cand]['name']} ({r['supplier_article']})",
                    f"no GTIN in {dataset['companies'][company]['name']}'s register",
                    f"the names differ: {r['name']!r} and {group[cand]['name']!r}"])
                if choice == "open":
                    item.update(target=None, status="open", basis="suggested; not decided")
                elif choice == "none":
                    item.update(target=None, status="outside", basis="you said it is not one of the group's products")
                elif choice in group:
                    item.update(target=choice, status="linked",
                                basis=("you confirmed the suggestion" if choice == cand
                                       else f"you linked it to {group[choice]['name']} instead of the suggestion"))
                else:
                    raise PlanningInputError(f"{p} can be linked to one of {', '.join(sorted(group))}, 'none' or 'open'; not {choice!r}")
            else:
                item.update(target=None, status="outside",
                            basis=f"no matching GTIN or supplier article number in {dataset['companies'][ref]['name']}'s {dataset['group']}")
            out.append(item)
    if decisions:
        raise PlanningInputError(f"there is no suggested link to decide for {', '.join(sorted(decisions))}")
    return out


# ------------------------------------------------------------------ 3. one weekly view ------------------------------

def weekly(dataset: dict, link_list: list[dict]) -> dict:
    """Units per company, week and group product (by the reference product it is linked to); the open products on
    their own; each company's first week; the lines the definition left out; what a join on every register row adds."""
    targets = {(l["company"], l["product"]): l["target"] for l in link_list}
    opened = {(l["company"], l["product"]) for l in link_list if l["status"] == "open"}
    out = {"by_company": {}, "by_product": {}, "open": {}, "first_week": {}, "left_out": {}, "join_every_row_adds": {}}
    for company in dataset["companies"]:
        kept, left = _lines(dataset, company)
        _, rows = _register(dataset, company)
        out["left_out"][company] = left
        out["first_week"][company] = min(w for _, w, _ in kept)
        series, extra = {}, 0
        for product, week, q in kept:
            t = targets.get((company, product))
            if t:
                series[week] = series.get(week, 0) + q
                key = (company, t)
                out["by_product"].setdefault(key, {})
                out["by_product"][key][week] = out["by_product"][key].get(week, 0) + q
                extra += q * (rows.get(product, 1) - 1)
            elif (company, product) in opened:
                out["open"].setdefault((company, product), {})
                out["open"][(company, product)][week] = out["open"][(company, product)].get(week, 0) + q
        out["by_company"][company] = series
        out["join_every_row_adds"][company] = extra
    return out


# ------------------------------------------------------------------ 4. the forecast ---------------------------------

def _predict(method: str, history: list[float], horizon: int = HORIZON) -> list[float]:
    n = len(history)
    if method == "last_year":
        return [history[n - SEASON + i] for i in range(horizon)]
    if method == "recent_average":
        return [sum(history[-LEVEL:]) / LEVEL] * horizon
    if method == "seasonal_level":
        before = sum(history[n - SEASON - LEVEL:n - SEASON])
        ratio = sum(history[-LEVEL:]) / before if before else 1.0
        return [history[n - SEASON + i] * ratio for i in range(horizon)]
    raise ValueError(method)


def _range(ratios: list[float]) -> tuple[float, float]:
    """The 10th and 90th percentile of actual/forecast over the tests (an 80% range)."""
    if len(ratios) < 2:
        return 1.0, 1.0
    q = statistics.quantiles(ratios, n=10, method="inclusive")
    return q[0], q[8]


def forecast(series: list[float], last_week: date, horizon: int = HORIZON) -> dict:
    """Test each method on every point of the history where it could have been used (up to the last MAX_TESTS), use
    the one with the smallest weighted absolute percentage error, and give its range from the same tests."""
    n = len(series)
    origins = list(range(NEED, n - horizon + 1))[-MAX_TESTS:]
    if len(origins) < MIN_TESTS:
        need = NEED + horizon + MIN_TESTS - 1
        return {"available": False, "weeks_of_history": n, "weeks_needed": need,
                "reason": (f"{n} weeks of history. A tested forecast here needs at least {need}: a year and eight weeks "
                           f"to make each forecast, and {MIN_TESTS} forecasts whose following {horizon} weeks are known "
                           f"to test them against.")}
    scores = []
    for mid, name, how in METHODS:
        err = tot = 0.0
        per_h = [[] for _ in range(horizon)]
        totals = []
        for o in origins:
            pred, actual = _predict(mid, series[:o], horizon), series[o:o + horizon]
            err += sum(abs(a - f) for a, f in zip(actual, pred))
            tot += sum(actual)
            for h, (a, f) in enumerate(zip(actual, pred)):
                if f > 0:
                    per_h[h].append(a / f)
            if sum(pred) > 0:
                totals.append(sum(actual) / sum(pred))
        scores.append({"id": mid, "name": name, "how": how, "error_pct": round(100 * err / tot, 1) if tot else None,
                       "_per_h": per_h, "_totals": totals})
    best = min((s for s in scores if s["error_pct"] is not None), key=lambda s: s["error_pct"])
    pred = _predict(best["id"], series, horizon)
    weeks = [last_week + timedelta(weeks=i + 1) for i in range(horizon)]
    points = []
    for h, (w, f) in enumerate(zip(weeks, pred)):
        lo, hi = _range(best["_per_h"][h])
        points.append({"week": w.isoformat(), "label": week_label(w), "forecast": round(f), "low": round(f * lo), "high": round(f * hi)})
    lo, hi = _range(best["_totals"])
    above = sum(1 for r in best["_totals"] if r > 1)
    lean = ("low" if above >= 0.75 * len(best["_totals"]) else "high" if above <= 0.25 * len(best["_totals"]) else "")
    simplest = min((s for s in scores if s["id"] != "seasonal_level"), key=lambda s: s["error_pct"])
    return {"available": True, "method": best["id"], "method_name": best["name"], "how": best["how"],
            "tests": len(origins), "tested_from": (last_week - timedelta(weeks=n - 1 - origins[0])).isoformat(),
            "tested_to": (last_week - timedelta(weeks=n - 1 - origins[-1])).isoformat(),
            "weeks_of_history": n, "points": points, "total": round(sum(pred)), "total_low": round(sum(pred) * lo),
            "total_high": round(sum(pred) * hi), "actual_above": above, "leans": lean,
            "methods": [{"id": s["id"], "name": s["name"], "how": s["how"], "error_pct": s["error_pct"], "used": s is best}
                        for s in scores],
            "elaborate_lost": best["id"] != "seasonal_level",
            "baseline": {"name": simplest["name"], "error_pct": simplest["error_pct"]}}


# ------------------------------------------------------------------ the result the page shows -----------------------

def _pct(a: float, b: float) -> float | None:
    return round(100 * (a - b) / b, 1) if b else None


def _num(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def result(dataset: dict, decisions: dict[str, str] | None = None, company: str = "all", weeks: int = 26) -> dict:
    companies = list(dataset["companies"])
    if company != "all" and company not in companies:
        raise PlanningInputError(f"company must be all or one of {', '.join(companies)}")
    if weeks not in PERIODS:
        raise PlanningInputError(f"weeks must be one of {', '.join(map(str, PERIODS))}")
    chosen = companies if company == "all" else [company]
    names = {c: dataset["companies"][c]["name"] for c in companies}
    link_list = links(dataset, decisions)
    w = weekly(dataset, link_list)
    last = dataset["latest_week"]
    common_first = max(w["first_week"][c] for c in chosen)

    # the period shown, and the same weeks a year earlier where every chosen company has data for them
    shown = _weeks(last - timedelta(weeks=weeks - 1), last)
    def units(c: str, ws: list[date]) -> int:
        return sum(w["by_company"][c].get(x, 0) for x in ws)
    rows = [{"week": x.isoformat(), "label": week_label(x),
             **{c: (w["by_company"][c].get(x, 0) if x >= w["first_week"][c] else None) for c in chosen},
             "total": sum(w["by_company"][c].get(x, 0) for c in chosen if x >= w["first_week"][c]),
             "complete": all(x >= w["first_week"][c] for c in chosen)} for x in shown]
    prior = [x - timedelta(weeks=SEASON) for x in shown]
    comparable = all(prior[0] >= w["first_week"][c] for c in chosen)
    period = {"weeks": weeks, "from": shown[0].isoformat(), "to": last.isoformat(), "from_label": week_label(shown[0]),
              "to_label": week_label(last), "by_company": {c: units(c, [x for x in shown if x >= w["first_week"][c]]) for c in chosen},
              "complete": all(shown[0] >= w["first_week"][c] for c in chosen)}
    period["total"] = sum(period["by_company"].values())
    if comparable:
        before = sum(units(c, prior) for c in chosen)
        period["year_earlier"] = {"total": before, "change": period["total"] - before, "change_pct": _pct(period["total"], before)}
    else:
        late = [names[c] for c in chosen if prior[0] < w["first_week"][c]]
        period["year_earlier"] = {"total": None, "why_not": f"{' and '.join(late)}'s data starts {week_label(max(w['first_week'][c] for c in chosen))}, "
                                                            f"so the same weeks a year earlier are not all there"}

    # each group product, per company, in the period (and against a year earlier where comparable)
    ref_reg, _ = _register(dataset, dataset["reference"])
    products = []
    for (c, t), series in sorted(w["by_product"].items()):
        if c not in chosen:
            continue
        now = sum(series.get(x, 0) for x in shown)
        ok = prior[0] >= w["first_week"][c] and min(series) <= prior[0]
        was = sum(series.get(x, 0) for x in prior) if ok else None
        products.append({"company": c, "company_name": names[c], "product": t, "name": ref_reg[t]["name"], "units": now,
                         "year_earlier": was, "change": (now - was) if was is not None else None})

    # the forecast: on the weeks where every chosen company has data
    hist_weeks = _weeks(common_first, last)
    series = [sum(w["by_company"][c].get(x, 0) for c in chosen) for x in hist_weeks]
    fc = forecast(series, last)
    fc["built_on"] = f"{len(hist_weeks)} weeks ({week_label(common_first)} to {week_label(last)})"

    opened = []
    for (c, p), s in sorted(w["open"].items()):
        if c not in chosen:
            continue
        item = next(l for l in link_list if l["company"] == c and l["product"] == p)
        weeks_sold = _weeks(min(s), last)
        sf = forecast([s.get(x, 0) for x in weeks_sold], last)
        opened.append({"company": c, "company_name": names[c], "product": p, "name": item["name"],
                       "units_in_period": sum(s.get(x, 0) for x in shown), "units_all": sum(s.values()),
                       "first_week": week_label(min(s)), "weeks_sold": len(weeks_sold),
                       "forecast": None if not sf["available"] else sf["total"], "no_forecast_because": sf.get("reason")})

    checks = [{"name": "Combined equals the companies added up",
               "result": "holds in every week shown" if all(r["total"] == sum(r[c] or 0 for c in chosen) for r in rows) else "does not hold",
               "ok": all(r["total"] == sum(r[c] or 0 for c in chosen) for r in rows)}]
    for c in chosen:
        _, regrows = _register(dataset, c)
        doubled = [p for p, k in regrows.items() if k > 1]
        if doubled:
            checks.append({"name": f"Each of {names[c]}'s lines counted once", "ok": True,
                           "result": (f"its register has {sum(regrows[p] for p in doubled)} rows for {', '.join(doubled)} (renamed); "
                                      f"the current row is used. Joining on every row would add "
                                      f"{_num(w['join_every_row_adds'][c])} units over the whole history")})
        lo = w["left_out"][c]
        checks.append({"name": f"{names[c]}: lines left out by the definition", "ok": True,
                       "result": f"{_num(lo['lines'])} cancelled lines ({_num(lo['units'])} units)"})

    # what the answer covers, in words, before any number
    ref = dataset["reference"]
    group_names = [ref_reg[t]["name"] for t in sorted(ref_reg) if ref_reg[t]["category"] == dataset["group"]]
    unit_of = {}
    for c in companies:
        reg, _ = _register(dataset, c)
        for l in link_list:
            if l["company"] == c and l["target"]:
                unit_of.setdefault(reg[l["product"]]["unit"], []).append(f"{c}:{l['product']}")
    spec = dataset["companies"]
    scope = {"group": dataset["group"], "reference": names[ref], "reference_code": ref, "group_products": group_names,
             "membership": (f"{dataset['group']} as {names[ref]}'s register files them ({len(group_names)} products). A product of "
                            f"another company counts when it is linked to one of them."),
             "unit": (f"units ({next(iter(unit_of))}), the unit both registers use for these products" if len(unit_of) == 1
                      else "the registers use different units for these products; they are not added up"),
             "definition": [f"{names[c]}: units on {spec[c]['source']} with status {spec[c]['counted']}, by the ISO week of the "
                            f"{spec[c]['date_meaning']}; other lines left out" for c in chosen],
             "not_included": ["margin, prices and currencies", "purchasing or staffing advice",
                              "demand: sold volume misses what could not be sold"]}

    state = {"decisions": dict(sorted((decisions or {}).items())), "company": company, "weeks": weeks}
    rid = "r-" + hashlib.sha256(json.dumps({"d": DEFINITION_ID, "data": dataset.get("version", ""), **state},
                                           sort_keys=True).encode()).hexdigest()[:10]
    out = {"result_id": rid, "definition_id": DEFINITION_ID, "state": state, "scope": scope, "companies": {c: names[c] for c in chosen},
           "latest": {"week": last.isoformat(), "label": week_label(last)},
           "history": {c: {"first_week": w["first_week"][c].isoformat(), "first_label": week_label(w["first_week"][c]),
                           "weeks": len(_weeks(w["first_week"][c], last))} for c in chosen},
           "links": link_list,
           "period": period, "rows": rows, "products": products, "open": opened, "forecast": fc, "checks": checks}
    out["summary"] = summary(out)
    return out


def summary(r: dict) -> list[str]:
    """The note for the planning meeting: only what the numbers above say. No cause, no purchasing advice."""
    p, names = r["period"], r["companies"]
    who = " and ".join(names.values())
    lines = [f"Sold volume of the group, {p['from_label']} to {p['to_label']} ({who}): {_num(p['total'])} units"
             + (" (" + ", ".join(f"{names[c]} {_num(v)}" for c, v in p["by_company"].items()) + ")" if len(names) > 1 else "") + "."]
    ye = p["year_earlier"]
    if ye.get("total") is not None:
        sign = "+" if ye["change"] >= 0 else "−"
        lines.append(f"Against the same weeks a year earlier: {sign}{_num(abs(ye['change']))} units"
                     + (f" ({sign}{abs(ye['change_pct'])}%)." if ye["change_pct"] is not None else "."))
    else:
        lines.append(f"No comparison with a year earlier: {ye['why_not']}.")
    moved = [x for x in r["products"] if x["change"] is not None]
    if moved:
        top = max(moved, key=lambda x: abs(x["change"]))
        sign = "+" if top["change"] >= 0 else "−"
        lines.append(f"Largest change against a year earlier: {top['name']} at {top['company_name']}, {sign}{_num(abs(top['change']))} "
                     f"units. The data does not say why.")
    f = r["forecast"]
    if f["available"]:
        used = next(m for m in f["methods"] if m["used"])
        lines.append(f"Next eight weeks ({f['points'][0]['label']} to {f['points'][-1]['label']}): "
                     f"{_num(f['total_low'])}–{_num(f['total_high'])} units (80% range from {f['tests']} past tests). "
                     f"Method: {f['method_name']}, {_num(f['total'])} units, error {used['error_pct']}% in those tests.")
        if f["leans"]:
            lines.append(f"In those tests the actual sales came out {'above' if f['leans'] == 'low' else 'below'} this method's figure "
                         f"{f['actual_above'] if f['leans'] == 'low' else f['tests'] - f['actual_above']} times out of {f['tests']}; "
                         f"the range allows for that.")
        if f["elaborate_lost"]:
            lines.append("The more elaborate method did not beat a simpler one in those tests, so the simpler one is used.")
    else:
        lines.append(f"No forecast: {f['reason']} The history above still holds.")
    for o in r["open"]:
        lines.append(f"Not in these numbers: {o['name']} ({o['company_name']}, {_num(o['units_in_period'])} units in the period); "
                     f"its link to the group is not decided.")
    lines.append("Sold volume, not demand: weeks where a product could not be sold do not show what customers wanted.")
    return lines
