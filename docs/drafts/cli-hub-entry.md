# DRAFT: a CLI-Hub registry entry for krusgraph (not submitted)

Status: draft, round CL1, 20 November 2026. Nothing has been sent to HKUDS/CLI-Anything, CLI-Hub or PyPI. Submitting
is the maintainer's decision; this file only prepares it.

CLI-Anything accepts a standalone repository with a registry-only pull request that adds one entry to their
`registry.json` (their `CONTRIBUTING.md`, "Option 2: Standalone repository", read at commit
`34f519533bc175d2fe287ab8316b0dd99bb9cc43` on 20 November 2026). Its requirements and where we stand:

| Their requirement | Status |
| --- | --- |
| Installable with `pip install <name>` or `pip install git+https://...` | `pip install git+https://github.com/Krusmaster/fabric-backend` works today; there is no PyPI package (`fabric-backend` on PyPI is not ours to assume; not checked) |
| A `SKILL.md` somewhere in the repository | `fabric_backend/skills/SKILL.md` |
| Its own test suite | `tests/test_cl1_cli.py`, run in CI |
| An entry with `source_url` and `skill_md` pointing at the repository | below |

## The entry

```json
{
  "name": "krusgraph",
  "display_name": "Krusgraph",
  "version": "0.8.0",
  "description": "Read-only keys, relationships and row checks for Microsoft Fabric and SAP-shaped tables; SAP pack and analysis readiness by rules",
  "requires": "Python 3.12+; pyodbc and ODBC Driver 18 only for live SQL endpoints",
  "homepage": "https://krusgraph.com",
  "source_url": "https://github.com/Krusmaster/fabric-backend",
  "install_cmd": "pip install git+https://github.com/Krusmaster/fabric-backend",
  "entry_point": "krusgraph",
  "skill_md": "https://github.com/Krusmaster/fabric-backend/blob/main/fabric_backend/skills/SKILL.md",
  "category": "database",
  "contributors": [
    {"name": "Krusmaster", "url": "https://github.com/Krusmaster"}
  ]
}
```

Notes on the fields: `homepage` is meant to be the target software's own homepage, which for Krusgraph is our site.
`category` is one of theirs (`database`; `knowledge` would also fit). `version` follows `pyproject.toml`.

## What Gustav must approve before anyone submits it

1. **Repository link**: list `https://github.com/Krusmaster/fabric-backend` (public) as `source_url`, and its `main`
   as the install source, or wait for a PyPI package first (a separate decision: a package name and an upload, which
   CONTRIBUTING.md reserves for the maintainer).
2. **Name**: `krusgraph` as the registry `name` and command, `Krusgraph` as `display_name`.
3. **Description**: the one line above, or a rewrite. It must stay within what the product backs (no "partner",
   "certified" or Microsoft endorsement).
4. **Licence**: the repository is MIT; CLI-Hub lists the entry, it does not relicense. Our CLI contains no
   CLI-Anything code, so no Apache-2.0 notice is needed (THIRD_PARTY_NOTICES.md unchanged).
5. **Who submits**: a pull request from the maintainer's own GitHub account to HKUDS/CLI-Anything adding only this
   entry; their `main` is read by the hub as soon as it is merged, so the listing is public from that moment.
6. **Contributors**: which GitHub account(s) to list.
