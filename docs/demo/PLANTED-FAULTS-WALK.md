> 2026-11-21, round BL21 (sprint item BL21, backlog C-37, C-38). Code: the `demo` command in
> `fabric_backend/krusgraph_cli.py`. Test: `tests/test_bl21_demo_faults.py`. Synthetic data only.

# The planted-faults walk: 15 minutes, one command

For a reseller, a partner or a sceptical data engineer who wants to see Krusgraph find real problems, not only say
"holds" on clean demo data. One command builds a small synthetic shop with five faults put in on purpose, runs
Krusgraph's checks on it and prints, for each fault, what was planted, what Krusgraph said, and the SQL that counted it.
Nobody from Krusgraph needs to be in the room, and nothing is connected to Fabric.

The sample and its faults are described in [`docs/PLANTED-FAULTS.md`](../PLANTED-FAULTS.md); the receipts in
[`docs/RECEIPTS.md`](../RECEIPTS.md).

## Before you start (2 minutes)

```bash
git clone https://github.com/Krusmaster/fabric-backend && cd fabric-backend
pip install .              # no extra packages: the sample is built in memory with SQLite
krusgraph check            # read-only, offline; lists "demo faults" under demos
```

## Run it (1 minute)

```bash
krusgraph demo faults --human            # the walk, for a person
krusgraph demo faults --json > faults.json   # the same answer for an agent or a CI job (the default when piped)
```

The first lines say how many planted faults were found. Then one block per fault:

- **planted**: what was put in the rows on purpose (from `shop_faults.FAULTS`).
- **Krusgraph**: what the checks said, word for word. This text is the tool's own answer (`shop_faults.check`, which
  runs `validate_plan`'s counting checks), not a sentence written for the demo. If the engine's wording changes, the
  walk changes with it.
- **receipt**: the sentence and the exact SQL that counted the number (`receipt.build`, the SQLite form of the
  statement). Copy it and run it yourself.

A fault the checks do not find today is printed as **NOT FOUND YET**, with no receipt. The output is not tuned to make
the demo look better.

## Walk through the five faults (10 minutes)

| Fault | What to point at |
| --- | --- |
| F1 `customers` | The key is not unique: one customer is on two rows. Run the receipt SQL: `n` is one more than `distinct_keys`. |
| F2 `order_items` | Three lines point at orders that do not exist. The receipt's `orphans` is the count. |
| F3 `orders` | The order total sits on the order header; summing it over the lines counts each order two or three times. The receipt counts lines per order (`avg_lines`, `max_lines`). |
| F4 `newsletter_signups` | The link is right by name and matches nothing: an older system's numbers. Every row is an orphan. Krusgraph also says the target key is not unique, which is F1's echo. |
| F5 `orders` | Amounts in SEK and EUR in one column, with a `currency` column beside it. On `main` on 21 November 2026 the counting checks do not read currency, so the walk prints "not found yet" (`docs/PLANTED-FAULTS.md` says why and where it belongs). |

Then show the closing lines: one more item is flagged (`products.list_price` summed over order lines), and it is
labelled as something the clean shop shows too, not a planted fault; and nothing else is flagged.

## Check it yourself (2 minutes)

Each receipt is a plain `SELECT`. To re-run one on the same rows:

```bash
python -c "
import json, sqlite3, subprocess
from fabric_backend import shop_faults as s
con = sqlite3.connect(':memory:'); con.row_factory = sqlite3.Row
con.execute(f'ATTACH DATABASE \":memory:\" AS [{s.SCHEMA}]')
for t, (cols, rows) in s.tables().items():
    con.execute(f'CREATE TABLE [{s.SCHEMA}].[{t}] ({\", \".join(c for c, _ in cols)})')
    con.executemany(f'INSERT INTO [{s.SCHEMA}].[{t}] VALUES ({\",\".join(\"?\" * len(cols))})', rows)
r = json.loads(subprocess.run(['krusgraph', 'demo', 'faults', '--json'], capture_output=True, text=True).stdout)['result']
for f in r['faults']:
    for x in f['receipt']:
        print(f['id'], x['counts'], dict(con.execute(x['sql']).fetchone()))
"
```

The two dicts on each line hold the same numbers. `tests/test_bl21_demo_faults.py` asserts exactly that for every
receipt, and that the found faults are the same as in `shop_faults.FAULTS` and `docs/PLANTED-FAULTS.md`, with no other
finding.

## What this demo is not

- Not a customer's data: every row is invented, built in memory on each run, the same rows every time.
- Not connected to anything: no Fabric, no network, nothing written. `--apply` is refused (exit 5).
- Not a claim about speed, coverage or any certification. It shows four kinds of check on eight small tables.
