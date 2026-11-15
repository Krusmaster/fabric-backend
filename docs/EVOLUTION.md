# Evolution: how Krusgraph gets better, by rules (design, E1)

Round E1, 15 November 2026. The founder, 12 November 2026: "we need to build in evolution, i.e. that Krusgraph has a
system for how it gets smarter", and "Krusgraph must also get smarter the more our customers use it with their real
data, and from the cases it finds."

**Status.** A design, and four small tools that exist and are tested (part 5). **Nothing in this document is switched
on**: no case record is written by the product yet, nothing is shared, nothing new is counted by the hosted service,
no routine was created, and no page of the site was changed. Each part says what exists and what does not.

**Two rules that everything below keeps.**

1. *Deterministic in the product.* Krusgraph for Fabric uses no AI model. "Smarter" means more rules, more pack facts,
   more decisions remembered and more cases recognised, each with the evidence it rests on. The same input gives the
   same answer. AI is used only in the development rounds that read the signals and write code, tests and documents,
   and what such a round writes passes the same gate as any other change.
2. *A customer's data stays the customer's.* Krusgraph learns from **cases**: schema-level patterns with their
   outcome. A case never holds a row value, and it leaves the customer's tenant only when a person there chose to
   share it, in a form built so that one organisation cannot be recognised (part 2).

**What was read, and what was not there.** `docs/SCOPE-REVIEW.md` (S1), `docs/DOMAINS-DESIGN.md` part 5 (W8),
`docs/LANDSCAPE.md`, `docs/PILOT.md`, `docs/DPA-DRAFT.md`, the privacy page (`fabric_backend/page_templates/PRIVACY.md`),
`fabric_backend/usage.py`, `fabric_backend/review.py`, `tests/test_inference_quality.py`, `CONTRIBUTING.md`. Three
documents this design was meant to build on are claimed in `CONTRIBUTING.md` and were not on `main` when it was
written: `docs/LEARNING-DESIGN.md` (L1), `docs/INTEGRATE-AND-HEAL-DESIGN.md` (W9), and `docs/SCORES.md` with a larger
regression corpus (F2, which claimed while this was being written: the corpus in `tests/corpus/`, `docs/scores.json`,
and the re-count of orphans under trim, case fold, leading-zero strip and cast). `docs/FINDINGS-13NOV.md` (F1) is on a
branch with its method and no findings yet. Where this design would lean on them it says so, and it should be read
against them when they land.

---

## 1. The loop

```
signals  ->  proposals  ->  gate  ->  ship  ->  measure  ->  record
   ^                                                            |
   +------------------------------------------------------------+
```

One turn of the loop is one change to the product. A change with no signal behind it is not evolution; a change that
did not pass the gate does not ship; a change that was not measured and recorded did not teach anything.

### Signals: where a reason to change comes from

| Signal (kind in the log) | What it is | Where it is read | Exists today |
|---|---|---|---|
| Per-tenant decisions (`tenant_decision`) | A person accepted or rejected a key or a link, with a reason | In the tenant's own review file (`review.py`) and rule book (`DOMAINS-DESIGN.md` part 5). It reaches the project only inside a shared case (part 2) | The review file: yes. The rule book: designed |
| Failed checks (`failed_check`) | A counted key that is not unique, a link with orphans | The answer of `validate_plan`; counts by rule id for the hosted service only with consent (part 3) | The checks: yes |
| Checks that were not counted (`not_counted_check`) | A query failed, the time ran out, the item was beyond the limit | The same answer (`not_counted`, `not_checked_beyond_max_items`) | Yes |
| The flag on a chat card (`card_flag`) | A person says "this is wrong" on a card, with one reason from a closed list | A case in the tenant; a count by card and reason with consent | Not built |
| First-user tests (`first_user_test`) | A round walks the MCP, the site and the editor as a new user, at phone width too, and ranks what it finds | `docs/FINDINGS-13NOV.md` and its successors | Started (F1) |
| The MCP scout (`mcp_scout`) | What other servers do that Krusgraph does not, with each licence as read | `docs/LANDSCAPE.md`; the verdicts are kept privately | Yes |
| Platform changes (`platform_release`) | A change on Microsoft Learn or in a Fabric release that moves what Krusgraph can read, create or must say | The pages each design cites, re-read monthly | By hand |
| Pack gaps (`pack_gap`) | A table or column a pack should know and does not; a pack fact the data contradicts | The plan's unlinked columns and pack matches (`docs/PACKS.md`) | In part |
| Regression scores (`regression_score`) | A score that is low, or lower than last week | `tools/evolution/scores.py`, `tests/test_inference_quality.py`; F2's `docs/scores.json` when it lands | Yes, on eleven schemas |
| The case library (`case_library`) | A pattern seen in real sources, with what fixed it | Part 2 | Schema and tools only |
| The founder (`founder`) | An instruction or a decision | The chat; quoted with its date | Yes |

### Proposals

A proposal is one line: the signal it answers (with a reference anyone on the project can open), what would change,
which score or measure should move, the evidence it will need, and its size. Proposals are kept in the private
backlog. Once a week the open proposals are ranked and the top five go to the founder (part 4). Nothing becomes work
by itself: the founder approves each idea before it is built (`docs/LANDSCAPE.md`, Process 6).

### The gate

A change ships only when all of these hold. None of them is a judgement call.

1. **No score goes down.** `python tools/evolution/score_diff.py <baseline> <current>` exits 0. Each score stands
   alone: a gain in one does not pay for a loss in another, and a score that disappears counts as a loss. A loss that
   is wanted (a wrong fixture removed) is made by changing the baseline in a commit of its own that says why and that
   the founder said yes.
2. **Every claim has evidence.** A sentence about what Krusgraph does rests on a test, a counted result on synthetic
   or openly licensed data, or a public source that was opened and is cited with its date. "Not checked" is never
   shown as passed (`SCOPE-REVIEW.md` section 6). This is `CONTRIBUTING.md`'s rule; the gate only repeats it.
3. **The founder's yes for other people's code.** Code is reused only under the licence gate in `docs/LANDSCAPE.md`
   (Process 3) and `CONTRIBUTING.md` ("Reusing external code"), per file, with the founder's yes.
4. **A rule that came from cases reproduces on a synthetic test** (part 2, "From a shared case to a rule").
5. **The whole suite is green** on the rebased branch, as for any change.

### Ship

An ordinary round: claim, build, test, release (`CONTRIBUTING.md`). Deployment stays the maintainer's.

### Measure

| Measure | Definition | State |
|---|---|---|
| Scores before and after | The two score files of the gate, kept with the log entry | Exists for the name-only inference on eleven schemas; the row-level corpus S1 asks for is claimed by F2 and not on `main` yet |
| Evidence coverage | Of all keys and links in the plans of the sample schemas, the share whose state is "counted" (holds or fails) or "declared", against "by name only" and "not checked" | Defined here; needs S1's evidence state on every answer |
| Steps to a first trusted model | On each sample: the number of tool calls and of decisions a person must make from the first plan until every key and link the model uses is counted and holds, or was accepted by a person. A count, so it is the same on every run | Defined here; not yet computed |

Wall-clock time on the samples may be noted beside the step count for the project's own use. It is not published and
is not a claim about speed.

### Record

Every turn ends as one entry in the **evolution log**: the signals, the proposal, what the gate said, the commits,
the measures, what comes next. The log is append-only; a correction is a new entry that names the old one.
`tools/evolution/log.py` writes it and checks the gate again, so the log cannot hold "shipped" beside a lower score, a
missing piece of evidence or reused code without the founder's yes. The log is kept in the private repository,
because an entry may point at a customer's signal; the public trace of the same change is `CHANGELOG.md`.

---

## 2. The case library

**What it is for.** The second sentence of the founder's: Krusgraph should get better from the real sources it meets,
and from what it finds there. What it must not do is take anything from those sources.

**How this sits with `DOMAINS-DESIGN.md` part 5.** That part keeps decisions and rules inside one organisation and
says that learning across customers "is not proposed", because it "would need each customer's opt-in and would send
their names out". This part proposes it under exactly those two conditions turned into rules: nothing is shared
without opt-in, and what is shared carries no names unless the tenant separately chose that. Part 5's rule book is
unchanged; cases are a second file beside it.

### A case

A case is a schema-level pattern with its outcome. Five examples, each a kind in the schema:

| In words | Kind | Fix | What the record keeps |
|---|---|---|---|
| A key by name failed uniqueness; it held after trimming | `key_not_unique` | `trim` | duplicates before and after, the column's type and length, that values were padded |
| Orphans fell to 0 after stripping leading zeros on a 10-character customer number | `orphans` | `strip_leading_zeros` | orphans before and after, two column shapes (10 characters, digits, one side with leading zeros) |
| A header amount was repeated on the lines, so the total doubled | `amount_repeated_on_lines` | `sum_at_header_level` | the ratio of the two totals before and after (2, then 1); never a total |
| Two systems' customer ids matched through a mapping table | `ids_matched_through_mapping` | `mapping_table` | three table roles (two masters, one mapping), matched and unmatched counts |
| A CDS view landed without the client column | `client_column_missing` | `composite_key` | the pack, the rule, that the key was not unique without the column |

**The record** (`tools/evolution/case-record.schema.json`, checked by `tools/evolution/case_record.py`):

| Field | Holds | Never holds |
|---|---|---|
| `kind`, `fix`, `outcome` | One value each from a closed list | Free text |
| `rule_ids`, `pack` | The engine's rule ids (K0 to K5, R0 to R5, O1, O2) and a published pack's id | |
| `tables`, `columns` | References (`t1`, `c1`), a role (header, line, master, mapping; key, reference, amount, client), a generic entity from a closed list, the type, the length, the character class, whether values have leading zeros or padding | A table or column name; a value |
| `before`, `after` | Counts (rows, distinct, nulls, duplicates, orphans, matched) and one ratio of two totals | A total, a minimum, a maximum, a sample, a value |
| `decision` | What a person decided (accepted, rejected, open) and their role | Who. The person stays in the tenant's review file |
| `names`, `names_opt_in` | Real table and column names, **only** when the tenant opted in; identifier characters only | Present by default |
| `engine`, `case_id` | The version, and a hash of the record | |

There is no field for a row value, a sample, a query, a reason typed by a person, a person, a workspace or a tenant
id, and unknown fields are refused. That is checked by tests, not by intention
(`tests/test_e1_evolution.py`). Column names are abstracted because a name can itself be sensitive
(`DOMAINS-DESIGN.md` part 5, "Sensitive names").

**When a case is written.** By rule, from a closed list of triggers; never by a model, never from reading rows
beyond the counting queries the checks already run:

1. A check failed, and a re-count under one fix from the closed list (trim, case fold, strip or pad leading zeros,
   cast) changed the result. This is S1's mechanism 4, "count before claiming, and let the data propose"; the re-count
   is claimed by F2 and was not on `main` when this was written.
2. A person accepted or rejected a key or link whose check had failed or was not counted.
3. A pack matched a table and one of the pack's facts did not hold on the data.
4. The sum over lines and the sum over headers of the same amount differ by a whole factor.
5. A person pressed the flag on a card.

### Where a case is stored

| | |
|---|---|
| By default | **In the customer's tenant, and nowhere else.** For Krusgraph for Fabric: a `cases.json` part beside `rules.json` in the organisation's rule book item (`DOMAINS-DESIGN.md` part 5; if an item definition is too small, a lakehouse file the item points at). For the chat: in the review file the person keeps. For Krusgraph Open Source: a file in the user's repository |
| On the hosted service | Nothing. The service keeps no customer content today and this design does not change that |
| What the tenant gets from its own cases, without sharing | The same pattern is recognised the next time in the same organisation: "this link had orphans in three products until leading zeros were stripped; the same shape is here". A proposal, counted before it is shown as holding |
| Shared | Only what a person in the tenant chose to share, in the shared form below, to one store kept by Kruse Consulting AB |

### Sharing: opt-in, and what the shared form is

Sharing is off. It is turned on per organisation by someone who may decide that (in the workload: a setting of the
rule book item, which Fabric lets its stewards change; in a pilot: the written consent, below). With it on, sharing
is still an act: a person sees the list of cases, sees **the exact bytes that would leave** for each, and sends the
ones they choose. Nothing is sent in the background.

The shared form is made from the tenant's record by a fixed function (`to_shared` in
`tools/evolution/case_record.py`); the same record always gives the same bytes:

- Counts become bands (`0`, `1-9`, `10-99`, `100-999`, `1e3-1e4`, and so on); ratios become bands (`0`, `0-1%`,
  `1-10%`, `10-50%`, `50-100%`, `100%`). 48 210 rows with 48 210 orphans becomes "1e4-1e5 rows, orphan ratio 100%".
- The date, and the reference into the tenant's own plan, are removed. The decision keeps the role and loses nothing
  else, because it never held the person.
- Names are removed unless `names_opt_in` is true. Opting in to names is a second, separate choice, and a case with
  names is used only for pack facts about systems whose names are public (an SAP table is the same everywhere).
- Three fields are added: a random `share_id` made in the tenant, a `contributor` (a keyed hash that stands for the
  organisation so that organisations can be counted; never the tenant id), and the id of the consent text.

The synthetic example: `tools/evolution/examples/case-leading-zeros.tenant.json` and, as it would leave,
`tools/evolution/examples/case-leading-zeros.shared.json`.

### Aggregation: so that one customer cannot be recognised

Shared records are read one by one only by the round that turns them into tests, and never appear in this
repository. What is said in public about them comes from `aggregate` in `tools/evolution/case_record.py`, with these
thresholds, in the manner of k-anonymity:

| Rule | Value | Why |
|---|---|---|
| A pattern is counted in public only when it was shared by **at least 5 organisations** (k = 5; the function refuses a lower k) | 5 | Below that, a reader who knows one customer can guess whose case it is |
| A pattern is the kind, the pack, the fix, the outcome and the column shapes. Not the numbers, not the names | | Few, coarse attributes keep the groups large |
| A published number is a band: 5+, 10+, 25+, 50+, 100+ | | An exact number that goes from 5 to 6 the week a known customer starts tells who the sixth was |
| One organisation adds at most 3 cases to a pattern's count | 3 | So "learned from 50 cases" is never 46 cases from one customer |
| A pattern below the threshold is counted as "held back", and nothing else about it is said | | |
| Public numbers are refreshed at most once a month | | The same reason as the bands |

This lowers the risk of recognition; it is not a proof of anonymity, and it is not presented as one. What remains:
with few customers nothing passes the threshold (which is the intent); a rare combination of shapes stays held back
for a long time; opt-in names are identifying for anything that is not a standard system, so they are used for
standard systems only; and a rule that appears soon after a pilot can be guessed at, which is why rules from cases
ship in the monthly pack round and not as they arrive.

### From a shared case to a rule or a pack fact

1. **A candidate**: a pattern over the threshold, or, in a pilot, a case the customer agreed in writing may be used
   this way (below).
2. **A synthetic reproduction.** A development round writes a new synthetic fixture from the *shape* alone (types,
   lengths, character classes, roles) with numbers of its own, and a test in which the pattern occurs. No number,
   name or value is copied from a case. If the pattern cannot be reproduced synthetically, it does not become a rule.
3. **The rule or pack fact** is written so that the test passes, deterministically, with its rule id.
4. **The gate** (part 1): no score down, evidence for each claim, the suite green. The founder's yes.
5. **The source line.** A rule that came through the threshold says so where rules are explained: "learned from 10+
   customer cases at 5+ organisations", beside the path of its synthetic test. A pack fact from cases is marked as
   observed in cases, which is weaker than a fact from the vendor's public documentation, and both kinds say which
   they are. A rule from a pilot case below the threshold carries no "learned from" line at all: its source is its
   synthetic test.
6. **The record**: one entry in the evolution log, signal `case_library`.

A shipped rule holds nothing of any customer's: it is code and a synthetic test. So when an organisation deletes what
it shared (below), its records are deleted and the public counts are recomputed at the next monthly refresh; a rule
whose count falls under the threshold loses its "learned from" line and keeps its synthetic test. The rule itself
stays. The consent text has to say this in plain words.

### How a tenant sees and deletes what it shared

- **The list.** The tenant keeps its own list of what it shared, in the same place as its cases: per share the
  `share_id`, the date, the consent text's id and the exact bytes that left. "What we have shared" in the editor
  shows it; in the chat and in Open Source it is the file. It does not depend on Kruse Consulting answering.
- **Delete.** One or all shares, by `share_id`. Until the hosted service has an address for it: a message to the
  contact address on the privacy page naming the ids, from someone who may speak for the organisation. Kruse
  Consulting deletes the records within 30 days and confirms. Turning sharing off stops new shares and deletes
  nothing by itself; the page says so beside the switch.
- **The store.** Shared records are kept in one store with real deletion, in the same Azure region as the service,
  readable only by the operator. **Never in a git repository**, public or private: history cannot be deleted from
  reliably. The store does not exist yet; creating it is the maintainer's act and a change to the privacy page
  first.

### The wording a contract and the DPA need (draft, not legal advice)

`docs/DPA-DRAFT.md` and the privacy page were not changed by this round. What they would need, for the lawyers:

1. **In the DPA, section 5 (instructions):** "The processor derives nothing from the controller's data for its own
   purposes. Case records are written to the controller's own tenant. The processor receives a case record only when
   a person authorised by the controller sends it under the Case Sharing Terms."
2. **Case Sharing Terms** (a separate, optional text, so that declining it changes nothing else): what a shared case
   holds and never holds (the table above); that Kruse Consulting AB may use shared cases to improve Krusgraph,
   including its open-source code, as general rules and synthetic tests; that it publishes only counts over at least
   5 organisations, in bands; that the organisation can see what it shared and have it deleted, within 30 days; that
   a rule already published is not withdrawn, because it holds none of the organisation's data; that the organisation
   is never named without a separate written agreement.
3. **On the privacy page**, under "What we process": one row for shared case records (what, why, where, kept until
   deleted on request or until the organisation's agreement ends plus a stated period), and one sentence in "In
   short": "Krusgraph learns from cases only when your organisation shares them."

Open for a lawyer: whether a shared case is personal data at all (it holds no person; the contributor hash stands for
an organisation), and so whether Kruse Consulting AB is a controller for the store or the store is outside the GDPR;
whether the role in `decision` should be dropped where an organisation has one steward; the retention period after an
agreement ends.

### Pilots as structured case collection

A pilot (`docs/PILOT.md`) is where the first cases come from, and with one customer no threshold can be met. So a
pilot does it by consent instead of by numbers:

1. **Before the pilot**: the customer signs the Case Sharing Terms in a pilot form, which adds that cases from the
   pilot may be turned into general rules and synthetic tests although fewer than 5 organisations have shared, and
   that the customer is not named.
2. **During**: every failed or uncounted check and every decision becomes a case in the customer's tenant, by the
   triggers above. Nothing leaves.
3. **At the end**: the customer's person and the consultant go through the cases together; the customer sees the
   shared form of each and sends the ones they agree to, as one file.
4. **After**: the pilot's write-up (`docs/PILOT.md`, deliverable 5) lists the cases by kind and outcome. The cases go
   through "From a shared case to a rule" in the next monthly pack round.

The consent form, the customer's name and the pilot's findings are kept privately and never in this repository.

---

## 3. Telemetry, with consent, minimal

**The open-source version sends nothing.** Krusgraph Open Source and a self-hosted server make no call to Kruse
Consulting AB; the usage line described below is written to the operator's own console and can be turned off
(`KRUSGRAPH_USAGE_LOG=0`). The tools in `tools/evolution/` open no connection either, and a test keeps it so.

**Today, on the hosted service** (`fabric_backend/usage.py`, the privacy page's "Usage statistics"): per tool call the
tool's name, the outcome, the duration, whether it was a dry run and, when configured, a salted hash of the tenant id.
No user, no names, no queries, no results. This stays as it is.

**Proposed, and off until an organisation says yes:** a second line per plan or check, `krusgraph.evolution`, holding
only counts by closed vocabulary:

| Field | Example | Why |
|---|---|---|
| `rules` | `{"K2": 14, "R1": 31, "R5": 2}` | Which rules carry real plans |
| `checks` | `{"passed": 40, "failed": 5, "not_counted": 2}` by rule id | Where the rules are wrong on real data |
| `fixes` | `{"strip_leading_zeros": 1}` offered, and accepted | Which fixes people take |
| `flag` | card kind and one reason from a closed list | What people say is wrong |
| `pack` | pack id and how many of its tables matched, in bands | Pack gaps |
| `tables` | a band (`10-99`) | Whether the large-schema path is used |
| `org` | the same salted hash as today | To count organisations; to honour "off" |

Never: a table or column name, a value, a count of rows, a query, a plan, a user. These are the same exclusions the
privacy page already makes.

| Question | Answer |
|---|---|
| Consent | Opt-in per organisation: an allow list of salted tenant hashes. An organisation is put on it by its administrator's written yes (in a pilot: the pilot form), later by a setting in the workload. Not on the list: the line is never written |
| Turning it off | The same person writes to the contact address, or flips the setting; the hash leaves the list and no further line is written. Lines already written age out with the retention |
| Retention | The usage log's own retention (the privacy page states the number of days); monthly totals without `org` are kept as numbers in the evolution log |
| Legal basis | Consent of the organisation for this line; the existing usage line stays on its present basis |
| What the privacy page needs | A paragraph under "Usage statistics" listing these fields, a row in "What we process", and the sentence that it is off unless the organisation turned it on. Not written by this round |

---

## 4. Recurring routines

Six routines keep the loop turning. They are proposals; none was created. The full briefs, with the model for each
and a note on cost, are kept privately because they name what is watched and what it costs. In outline:

| Routine | How often | Reads | Writes |
|---|---|---|---|
| Scout diff | Weekly | The MCP registry and GitHub search, the watched repositories' licences | `docs/LANDSCAPE.md` rows (facts only); verdicts privately |
| Regression and scores | Weekly | `tools/evolution/scores.py`, the whole suite | A raised baseline when scores rose; a finding when anything fell |
| First-user test at 375 px | Weekly | A local server, every page and the chat at phone width | Findings, ranked, with the round that should take each |
| Learn and Fabric watch | Monthly | The Microsoft Learn pages the designs cite, the Fabric release notes | What changed against what the documents say |
| Pack growth | Monthly | Pack gaps; shared cases over the threshold or under a pilot's consent | Synthetic tests, pack facts, rules, through the gate |
| Evolution review | Weekly | Everything the others wrote that week | The evolution log, and the top five proposals for the founder |

Each routine is an AI development round and is bound by `CONTRIBUTING.md`: it claims, it deploys nothing, it
publishes nothing, it sends no email.

---

## 5. What exists now

| File | What it does |
|---|---|
| `tools/evolution/score_diff.py` | Compares two score files; exits 1 when any score got worse, 2 when a file is not a score file. No switch lets a regression through |
| `tools/evolution/scores.py` | Writes today's scores as a score file: the 77 numbers `tests/test_inference_quality.py` already asserts (keys and foreign keys recovered from names alone on eleven schemas) |
| `tools/evolution/baseline/scores.json` | The baseline on `main` |
| `tools/evolution/log.py` | Appends a round's report to the evolution log and renders it; refuses what the gate forbids |
| `tools/evolution/case-record.schema.json` | The case record as JSON Schema (draft 2020-12), tenant and shared scope |
| `tools/evolution/case_record.py` | Checks a record, makes the shared form, aggregates with the threshold |
| `tools/evolution/examples/case-leading-zeros.tenant.json`, `.shared.json` | A synthetic case, as kept and as shared |
| `tests/test_e1_evolution.py` | The tests of all of the above |

**In CI.** The larger regression corpus with its own published scores is not on `main` yet (F2 holds it), so no job
was added to `.github/workflows/`. The gate runs today inside the ordinary suite: `tests/test_e1_evolution.py`
computes the current scores and compares them with the baseline through `score_diff`, so a push that lowers one of
the 77 numbers is red in the existing `test` job. When F2's `docs/scores.json` is on `main`, the next step is small:
`scores.py` reads it and adds its numbers to the same score file under their own prefix, each with its direction,
and the same test then guards them. That step was left undone on purpose, because the file's form is F2's to decide.

If a round's rule lowers one of the 77 numbers on purpose (more links found at the price of one wrong link), the
test is red until the baseline is changed in a commit that says why and that the founder said yes. That is the gate
doing what it is for.

A round that raises a score regenerates the baseline:
`python tools/evolution/scores.py --out tools/evolution/baseline/scores.json`.

**Not built**, in the order proposed: the re-count under a fix (S1 mechanism 4) that most cases depend on (F2 holds
it); the engine's writer of case records and the `cases.json` part; the share list and "What we have shared"; the flag on
cards; the store for shared cases; the `krusgraph.evolution` line and its allow list; evidence coverage and steps to a
first trusted model as scores.

## 6. Questions for the founder

1. Is 5 organisations the threshold, and 3 the cap per organisation?
2. May a pilot's cases become rules below the threshold, under the pilot's written consent, as part 2 proposes?
3. Opt-in names for standard systems: wanted at all, or leave names out entirely until asked for?
4. The store for shared cases (an Azure table in the service's region) and the three texts (DPA section 5, Case
   Sharing Terms, the privacy page): to a lawyer first, or drafted by a round first?
5. The `krusgraph.evolution` line: wanted now for pilots, or after the first cases have shown what is worth counting?
6. Which of the six routines to create first. The proposal: regression and scores, then the evolution review.

## Sources

Files in this repository as named above, read on `main` on 15 November 2026. No external page was opened for this
document. "In the manner of k-anonymity" refers to the general idea that a released record should be shared by at
least k subjects; no property is claimed beyond the thresholds stated.
