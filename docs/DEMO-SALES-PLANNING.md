# The first customer demonstration: two companies, one sales view (preview)

Status: a preview for review, **not published**. The calculations are unit-tested and the page is browser-tested
locally at 375, 768 and 1440 pixels; nobody outside the project has tried it yet. The data is synthetic.

The brief of 26 October 2026 asks for one complete customer journey: Erik (an invented planner for two companies) asks
*"Show sales across our two companies and help me plan the next eight weeks"* and leaves with a combined weekly sales
view, a tested eight-week forecast and a note for his planning meeting, inside Krusgraph, without building an app.

## Run it

The page is served only when `KRUSGRAPH_PREVIEW=1` is set, so deploying `main` does not publish it. It is `noindex`,
disallowed in `robots.txt`, out of the sitemap and not linked from any page.

```
KRUSGRAPH_PREVIEW=1 PRODUCT_NAME=Krusgraph MCP_PUBLIC_URL=https://krusgraph.com/mcp \
  ENTRA_CLIENT_ID=00000000-0000-0000-0000-000000000000 ENTRA_CLIENT_SECRET=x \
  python -m fabric_backend.server --host 127.0.0.1 --port 8811
```

Then open <http://127.0.0.1:8811/example/sales-planning>. The result as JSON is at
`/example/sales-planning/result.json?d=B-7003:A-103&company=all&weeks=26`.

## The journey on the page

| Brief | On the page | What happens |
| --- | --- | --- |
| A. I describe what I need | *What do you want to understand or plan?* | The suggested question goes ahead. Any other question gets a plain answer: this example answers one question; with your own data the first conversation starts from yours (today a pilot). Nothing typed leaves the page. |
| B. I see what the answer covers | 1. What the answer will cover | Companies, product group, the definition of sold volume per company, unit, history per company, latest week, what is not included. Erik confirms the definition, or says he counts differently and is told this example supports one definition. |
| C. A difference I must review | 2. One product needs your decision | Company B's CMTR SET 2PC has no GTIN; its supplier article number matches Company A's Commuter Light Set. Erik confirms, links it to another light, says it is not a light, or leaves it open. Open means it is shown on its own and kept out of the combined numbers. |
| D. One sales view | 3. Sales across both companies | Filters (companies, period), totals, the comparison with the same weeks a year earlier when every company has data for them, the weekly chart, a table view, the checks. |
| E. I can judge the forecast | 4. The next eight weeks | The 80% range first, then what it forecasts, the method used, how it was tested, each method's error in the same tests. |
| F. Something for the meeting | 5. For the planning meeting | A note made only from the numbers above; save (this browser), copy link, download as Markdown. A saved link reopens the same definition, decision and filters. |

## What existed, and what was built

Existing and reused: the site's shell, components and status words; the demo labelling; the idea of keeping a person's
decision apart from what the data says (`review_plan`); the browser checks.

Built for this journey (nothing like it existed): `sales_example.py` (the synthetic data), `planning.py` (the engine
part: definition, product links, weekly view, checks, forecast, the meeting note), `sales_demo.py` and
`page_templates/sales_planning.html` with `static/sales.js` (the page), the route in `server.py`, and
`tests/test_planning.py`.

## How the numbers are made

- **Data.** Two companies keep their data the way two different systems would: Company A has order lines with status
  `delivered` and a delivery date; Company B has sales lines with state `SHIPPED`, a shipping date and other column
  names. Company B files lights under *Accessories*. Its history starts 78 weeks back (Company A's 104), and CMTR SET 2PC
  has sold for 20 weeks. Cancelled lines exist in both. Company B's register keeps two rows for a renamed product.
  Codes use the GS1 in-house range (prefix 2), so they cannot be a real product's.
- **Definition** (`sold-volume/1`). The units on counted lines by the ISO week (Monday to Sunday) of the delivery or
  shipping date. Other lines are left out and counted on the page.
- **Product group.** Company A's register defines *Bike lights*. A Company B product belongs to the group when its GTIN
  equals a group product's. A matching supplier article number alone is a suggestion for the person to decide.
- **One weekly view.** Units per company and week. A company has *no data* for weeks before its history starts, not
  zero. Each line joins its product's current register row once. The page shows what a join on every register row
  would have added.
- **Forecast.** Three methods: repeat last year; the average of the last eight weeks; last year's pattern scaled by how
  the last eight weeks compare with the same eight weeks a year earlier.
  - **How they are tested.** Each method forecasts eight weeks from up to 26 past points where its history was long
    enough (a year and eight weeks), and is compared with what was then sold.
  - **Which one is used.** The one with the smallest weighted error, also when that is the simplest. The page then says
    so.
  - **The 80% range.** It comes from the same tests: the 10th to 90th percentile of actual/forecast. When the method
    has come out low or high in most tests, the page says so; the range then sits beside the method's own figure.
  - **When there is no forecast.** Under 75 weeks of history there is no forecast, only the reason.
- **The meeting note** repeats the numbers, names the largest change against a year earlier with "The data does not
  say why", lists what is not in the numbers, and ends with "Sold volume, not demand". It never gives a cause or
  purchasing advice.

## How it is verified

`tests/test_planning.py`:

- Every weekly number, for every decision, company filter and period (48 combinations), equals a second calculation in
  SQL over the same raw lines and registers, written from the definition rather than from the engine. Changing the
  engine to count cancelled lines, or to join every register row, fails these tests (tried).
- The open product stays out until decided, then counts once. Linking it elsewhere moves its units between products,
  not the total. The renamed product's double count equals what a naive join adds.
- The forecast is checked on series with a known answer: a pure season is repeated exactly; growth on a season favours
  the scaled method; 74 weeks give no forecast, 75 do. On the example data, the method used is always the one with the
  smallest test error.
- The note contains the period total and the forecast range. It contains no advice or cause words.
- The same choices give the same result; different choices give different result ids.
- Choices the example does not offer are refused: `bad_input`, and a broken link starts over.
- Without the flag the routes do not exist. With it, the page is `noindex`, outside the sitemap, disallowed for
  crawlers and linked from no page.

`tests/browser_check.js` (in CI) runs the journey at 375 pixels:

- another question;
- the definition;
- the decision, whose tile totals must equal the JSON;
- the filters;
- the arrow keys in the chart;
- no element wider than the screen outside a table's own scroll;
- save, then reopen with the same numbers and the decision still selected.

## Limits to keep in view

- The data is generated with a clear season and steady growth, so the simple seasonal methods do well. Real sales are
  noisier, and the tests will show larger errors.
- With Company B's 78 weeks, the combined forecast rests on 11 tests. The 80% range is a rough guide, and the page says
  so.
- Sold volume is not demand. Weeks where a product could not be sold do not show what customers wanted.
- At 104 weeks on a phone the columns are thin. The table view carries the values.
- Saved results live in the visitor's browser (`localStorage`). There is no account and no server storage.

## Before publishing

1. Let three to five people who work with sales, analysis or planning try it without an introduction (the brief,
   section 7). Ask:
   - which question it helps them answer;
   - what they would confirm before using the result;
   - what the forecast says and does not say;
   - which task it would help with;
   - what would stop them from using it on their own data.
   Note where they need help.
2. A short video of the flow as it actually runs.
3. A page on krusgraph.com built from what the tests showed. The brief's headline to try is *"Two companies. One sales
   view. A clearer basis for planning."* with *"Explore the example."*
4. Gustav decides to publish: set `KRUSGRAPH_PREVIEW=1`, or turn the route on for everyone, link it, and add it to the
   sitemap.
5. The path to one's own data is a pilot with personal help today. The page says so and offers no self-service button.
