# Knowledge packs: the manifest, how a pack is added, and what a pack is not

Round n77, 2 November 2026. A knowledge pack is what Krusgraph knows about a named source system before it has seen
a row: the tables, their keys, the relationships between them, the amounts and their levels, and the traps a person
falls into when joining them. Two packs exist: `sap` ([SAP.md](SAP.md), six modules) and `younium_salesforce`
([YOUNIUM-SALESFORCE.md](YOUNIUM-SALESFORCE.md), two modules). Each lives in `fabric_backend/packs/<pack>/`, one JSON
file per module (`pack.schema.json` is their schema, `sap_pack.py` their loader), and since this round one
**manifest** per pack, `fabric_backend/packs/<pack>/manifest.yaml`, in one shape for every pack.

The module files are what the engine runs on. The manifest is the same knowledge laid out for a person to review:
what the pack claims, where each claim comes from and whether that source was actually read, which check on the rows
can confirm each claim, which synthetic fixture exercises the pack, and whether anyone has reviewed it. A test keeps
the two in step, so a rule cannot exist in the code without a row in the manifest, or the other way round.

## The format

`packs/manifest.schema.json` (JSON Schema draft 7) is the authority; this is the reading of it. The loader is
`fabric_backend/pack_manifest.py`.

| Field | Kept by | What it holds |
| --- | --- | --- |
| `id`, `version`, `title` | hand | The pack's directory name; `major.minor.patch` of the manifest's content, `0.x` while the review status is `proposed`; a title in plain words. |
| `source_systems`, `scope` | hand | The systems the pack describes by their public names (`SAP ERP 6.0 (ECC)`, `SAP S/4HANA`; `Younium (API v2)`, `Salesforce (standard objects)`) and the business processes covered (`order-to-cash`, `procure-to-pay`, `finance`, `subscription-billing`, ...). |
| `sharing` | hand | `public-synthetic`, the only value: the pack rests on public sources and its fixtures are synthetic rows. Nothing from a customer, an employer or an installation. |
| `rule`, `variants`, `modules` | derived | The rule label the engine writes on a relationship from this pack (`SAP pack`, `Younium + Salesforce pack`), the variants of the system the pack distinguishes (`ecc`, `s4hana`; `api_v2`), and the module files with their status (`documented`, `verified`). |
| `sources` | derived | One row per source: `id`, `title`, `url`, `publisher`, `accessed` (the date the page was read, or `null`) and `verified` (`true` only when the page was read and the claims checked against it; it is the module file's `fetched`). Today one source of the SAP pack is verified (Microsoft's page on mirroring SAP, read 28 October 2026; it names no tables) and none of the Younium or Salesforce pages: round n72 wrote them as unverified, and the manifest says `verified: false` wherever the files say so. The `note` says why. |
| `entities` | derived | One row per table or object: `name`, `module`, `level` (header, item, master, version, ...), `title`, `key` (the key candidate the pack applies), `unique_keys` (further candidates, unique in the table besides the key: `VBAK.MANDT+KNUMV`, `ACCOUNTS.ACCOUNT_NUMBER`), `amounts` with their level and currency column, `variants`, `area`, `note`, `sources`. |
| `candidate_relationships` | derived | One row per relationship in the module files: `from` and `to` as `TABLE.COLUMN+COLUMN`, `cardinality`, `kind` (`key`, `unique`, `valid_on`), `module`, `rule`, `applied` (`false`: listed with its `condition`, not planned, because applying it would show orphans by design), `role`, `condition`, `variants`, `where`, `valid_on`, `verified` (runs on real systems recorded by `sap-verify --write`; none yet), `sources`, and `validation`: which of `validate_plan`'s checks can confirm the row on the rows. `referential_integrity` for every relationship (orphans), `cardinality` for every one that is not many-to-many (rows matching more than one target row), `amount_level` for a many-to-one relationship to a table whose amounts the pack names (the header amounts a join repeats, *the total that doubles*). |
| `traps` | derived, `check` by hand | One row per trap: `name`, `title`, `description` (the module file's text), `module`, `sources`, and `check`: the automated check that shows the trap on the rows. `referential_integrity` when a pack relationship encodes it (the client in every key, the address versions, the 15-character Salesforce id), `amount_level` (the header amount summed over its lines), `privacy` (the columns the pack names as personal data, which `sample_rows` masks), or `manual`: no automated check; the description is the check, and the person reads it before summing or joining. |
| `fixtures` | hand | The synthetic module that builds the pack's tables with rows (`fabric_backend.sap_demo`, `fabric_backend.younium_demo`): the functions that build the tables and the SQLite schema, the `EXPECTED` dict that says what each check should find, and the set in `examples/benchmark/facit.json` the pack's relationships are compared with. |
| `review_status`, `reviewed_by`, `reviewed_at` | hand | `proposed` with both review fields empty until the maintainer has read the manifest against its sources; then `reviewed`, with a name and a date. Both packs are `proposed`. |

In the file, the header and the tail are plain YAML and every row of the four derived sections is one line (a JSON
object, which YAML reads as a flow mapping), so a row can be found with `grep` and a change shows as one line in a
diff. `python -m fabric_backend.pack_manifest sap` prints the manifest as it would be regenerated from the module
files; with `--write` it writes it, keeping the hand-kept fields and every trap's `check`. A trap that is new to the
files gets `check: manual` until a person sets it.

What the test (`tests/test_pack_manifest.py`) checks, for every pack that has a manifest:

- the manifest follows `manifest.schema.json`;
- every source, entity, relationship and trap in the module files has a row in the manifest and the other way round,
  with the same content (`pack_manifest.problems`); a `verified: true` can never appear where the files say
  `fetched: false`;
- the file is in the canonical layout, and regenerating it changes nothing;
- the fixtures build: the fixture module's tables are entities of the manifest, their number is the one `EXPECTED`
  states, the SQLite schema builds, and the pack recognises every fixture table (`sap_pack.match`);
- the benchmark facit and the candidate relationships agree: every facit relationship is a candidate, every applied
  candidate the fixture's tables and columns allow is in the facit, and what the facit holds beyond that is a
  candidate listed as not applied (the three links by number of the younium set, which round n72 wrote as
  unverified);
- `sap_pack_draft` answers with `pack_manifest` (`id`, `version`, `review_status`) and nothing else in its answer
  changed. The field is read from the manifest's first lines without a YAML library, so the hosted server needs no
  new dependency; the full manifest needs PyYAML, which the `test` extra installs.

The benchmark table in `examples/benchmark/README.md` is unchanged by the manifests: they describe, they do not plan.

## Adding a pack

1. **Only public sources.** The vendor's own documentation, public API references, public material from Microsoft on
   the system in Fabric. Table and field names are facts; write every description in your own words, never copy a
   vendor's texts. Add every page to `sources` of the module file with `fetched: true` only if you read it, and a
   `note` with the date; if a page could not be opened from your session, say so in the note, as rounds n20 to n72
   did. Every table, relationship and trap names at least one source.
2. **Synthetic fixtures, never customer data.** A pack comes with a fixture module (`fabric_backend/<pack>_demo.py`)
   whose rows are made up and written from the pack, with the traps planted on purpose and an `EXPECTED` dict that
   says what each check should find. No names, numbers, table names, ids or figures from any installation, tenant or
   org; no `Z*`/`Y*` tables. A run on the fixture shows that the tools work on such tables; it proves nothing about
   the system (`sap-verify` refuses to record one).
3. **Module files first.** `fabric_backend/packs/<pack>/<module>.json` after `pack.schema.json`; `sap_pack.problems`
   must be empty (`tests/test_sap_pack.py` runs it on every file). A relationship that holds for some rows only gets a
   `condition`, and `"apply": false` when applying it would show orphans by design. A relationship the engine cannot
   express as a key join is `unique` or `valid_on`, or carries `where`.
4. **The manifest.** `python -m fabric_backend.pack_manifest <pack> --write` creates `manifest.yaml` from the module
   files with the hand-kept fields empty; fill in `title`, `source_systems`, `scope`, `fixtures`, and `check` per
   trap; leave `review_status: proposed` and the review fields empty. Add the fixture to `examples/benchmark` (a facit
   set and a row of the table) when it is meant to be measured; the test then compares the facit with the manifest.
5. **Run the suite** (`python -m pytest -q`). `tests/test_pack_manifest.py` says what is out of step; the numbers in
   `tests/test_sap_inference.py` are asserted exactly, so a change to the SAP pack shows up there.
6. **The engine.** `infer._pack` reads every pack through `sap_pack.match_any` since round n78: the pack that
   recognises most of a schema's tables, of those that recognise at least one table whose name is the system's own.
   Mark a table `common_name` in the module file when its name is an ordinary word another system's table can carry
   (`ACCOUNTS`, `INVOICES`, `Contact`): tables of that kind alone never light the pack. A manifest does not change
   what the engine reads.

## The review step

A pack starts as `proposed`: written from public sources, some of them not opened, and from nothing else. The
maintainer reviews it by reading the manifest against its sources: for each source, whether the page says what the
pack says (then `fetched: true` in the module file, and `verified: true` follows in the manifest); for each entity,
that the key is the documented key; for each candidate relationship, that the columns, the cardinality and the
condition are right and the `validation` names a check that can show it on rows; for each trap, that the `check` is
the one that shows it or honestly `manual`. What is wrong is corrected in the module file, the manifest regenerated,
and the suite run. Then `review_status: reviewed`, `reviewed_by` and `reviewed_at` (YYYY-MM-DD), and the version goes
to `1.0.0`. A pack that has been checked against rows of a real system, with `validate_plan` on a system you may
describe without naming a company, records that per relationship in `verified` (`sap-verify --write`,
[LIVE-TEST-SAP.md](LIVE-TEST-SAP.md)); the manifest carries those entries too. Review is not verification against
data: the first says the pack reads its sources right, the second that a system agreed with it.

## What a pack is, and is not

- **A pack is knowledge.** Tables, keys, relationships, amounts, traps, with a public source per claim and a status
  per source. It is independent of how the data arrives: the same pack reads a Fabric mirror, a Databricks catalog,
  a pipeline's landing or a Data API builder configuration, by table and column names alone. It never connects to
  anything and holds no credentials, endpoints or extraction logic.
- **A connector is transport.** A Fabric mirroring, a pipeline over an API, a Salesforce or SAP connector in Fabric or
  Lovable, Younium's own Salesforce connector: something that moves rows from a system into a lakehouse or an app,
  with credentials and a schedule. Krusgraph is not a connector and the packs are not connectors; the hosted MCP
  server reads what a connector has already landed. A pack tells the engine what the landed tables mean; a
  connector tells nothing of the kind.
- **A finished analysis is neither.** A semantic model, a report, a gold view, an MRR measure or a domain proposal
  is what the engine drafts from a plan, for a person to review, over one customer's tables. The pack feeds the
  plan (keys, relationships, amount levels, the traps the drafts avoid) and stops there; the figures, the measures
  and the domains belong to that customer and never flow back into a pack. A pack can be shared because it
  contains nothing of theirs; an analysis cannot.

Nothing in this round deploys or calls Azure, Entra, DNS or Fabric; tools and their answers are unchanged apart from
the `pack_manifest` field of `sap_pack_draft`.
