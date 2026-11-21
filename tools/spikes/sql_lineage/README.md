# SQL lineage spike (throwaway)

Mines equality join pairs and column lineage from SQL a customer already has, with two parsers, and scores them
against hand-written answers. The report is `docs/spikes/SQL-LINEAGE-SPIKE.md`. Nothing here is product code: the
server and the workload do not import it, and nothing here is a dependency of either (`pyproject.toml`,
`deploy/constraints.txt` and `workload/` are untouched).

- `corpus/*.sql` — 19 statements written for this spike over the repo's synthetic SAP-shaped and Salesforce-shaped
  tables (`fabric_backend/sap_demo.py`, `fabric_backend/salesforce_demo.py`). Each file's `-- ` header holds the
  dialect and the expected answer (`spike_corpus.py` documents the format).
- `run_sqlglot.py` — sqlglot (Python). Writes `schema.json` (from the two demos) and `results/sqlglot.json`;
  `--raw` writes `results/sqlglot-raw.json` without the workaround glue.
- `run_sqllens.mjs` — sqllens (TypeScript, npm `sqllens` 1.11.0, a separate open-source project, MIT). Reads
  `schema.json`, writes `results/sqllens.json`; `--raw` writes `results/sqllens-raw.json`.
- `score.py` — compares the four result files with the expected answers; writes `results/score.md` and `.json`.

## Run

Python 3.11+ with `sqlglot` (a test extra of this repo: `pip install -e ".[test]"`, or `pip install sqlglot`), and
Node >= 20. The npm install happens in this folder only:

```bash
cd tools/spikes/sql_lineage
npm ci                                   # sqllens 1.11.0 + antlr4ng, into ./node_modules (git-ignored)
python run_sqlglot.py && python run_sqlglot.py --raw
node run_sqllens.mjs && node run_sqllens.mjs --raw
python score.py
```

No network, no Fabric, no Azure: everything runs on the corpus files and the demo schema. The file names avoid
`test_*.py`, and `pyproject.toml` limits pytest to `tests/`, so the suite does not collect this folder.
