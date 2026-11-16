"""Decision rules (round L1): a decision a team made once about a proposed key or link becomes a rule for that tenant,
so the next plan proposes the right thing directly and says why. Layer 3 of the integration strategy; the design is
docs/DOMAINS-DESIGN.md part 5 ("Smarter from use, without AI") and docs/DECISION-RULES.md says what was built.

No AI and no statistics: a rule is a stored decision, matched by names, applied in a fixed order, and every effect is
shown with the decision it rests on. Rows outrank rules: an accepted key or link goes into the plan with the rule
DECIDED and is counted by validate_plan like any other; when the rows contradict it, contradictions() says so and the
decision is never trusted silently.

What a decision record holds (one row in the tenant's store):
  tenant       a SHA-256 digest of the tenant id, never the id itself; every read and write names it, nothing crosses
  scope        where the decision was made: platform / database / schema, lower case
  kind         "key" or "link"
  item         the id review.py and coverage.py use: key:<table>, rel:<source>.<cols>><target>
  names        table and columns (key), or source, source_cols, target, target_cols (link)
  fingerprint  a digest of the column names of the tables involved, at the time: the decision says when they changed
  decision     "accepted" or "rejected"
  role         who decided, as a role from ROLES; never a person's name or id
  reason       short free text (at most 300 characters; not for personal data)
  at           when (UTC, ISO 8601)
  evidence     what the rows said at the time, counts only (rows, nulls, distinct; rows_with_value, orphans), or None
  undone_at    when the decision was undone (and by which role); an undone decision is history, not a rule

Where: SQLite, one file. The local MCP server keeps it at KRUSGRAPH_DECISIONS (default ~/.krusgraph/decisions.sqlite,
written only when a decision is recorded); tests use ":memory:". The hosted service keeps no customer content, so it
does not store decisions (docs/DECISION-RULES.md, "Where decisions are kept").

Generalisation is by name only and always shown: a rejected link also suppresses the same link from its source table
renamed (the original table is gone and exactly one table has exactly its columns), with how="pattern"
and the decision it comes from. Nothing else generalises.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

RULE = "decided"
PROVENANCE = "decided by your team"
DECISIONS = ("accepted", "rejected")
ROLES = ("steward", "owner", "engineer", "analyst", "reviewer")
REASON_LIMIT = 300
ENV = "KRUSGRAPH_DECISIONS"
TENANT_ENV = "KRUSGRAPH_TENANT"
DEFAULT_PATH = Path.home() / ".krusgraph" / "decisions.sqlite"
DECLARED = ("K0", "R0")                         # what the source itself declares: shown with the conflict, never removed


class DecisionError(ValueError):
    """A decision that cannot be recorded or undone as asked: an unknown item, role or decision, another tenant's id."""


# ------------------------------------------------------------------ ids, names, fingerprints --------------------------

def tenant_key(tenant: str) -> str:
    t = str(tenant or "").strip().lower()
    if not t:
        raise DecisionError("a decision needs a tenant")
    return "sha256:" + hashlib.sha256(t.encode()).hexdigest()[:32]


def scope_of(platform: str = "", database: str = "", schema: str = "") -> str:
    return "/".join(str(x or "").strip().lower() for x in (platform, database, schema))


def key_item(table: str) -> str:
    return f"key:{table}"


def link_item(source: str, cols, target: str) -> str:
    return f"rel:{source}.{'+'.join(cols)}>{target}"


def fingerprint(schema, tables) -> str:
    """A digest of the column names of `tables` as the schema has them now ("" for a table that is not there)."""
    parts = []
    for name in sorted({str(t).lower() for t in tables}):
        t = _table(schema, name)
        parts.append([name, sorted(c.lower() for c in t.column_names) if t else None])
    return "sha256:" + hashlib.sha256(json.dumps(parts, separators=(",", ":")).encode()).hexdigest()[:16]


def shape(table) -> str:
    """A digest of one table's column names (lower case, sorted): the same columns under another table name read as
    that table renamed."""
    cols = sorted(c.lower() for c in table.column_names)
    return "sha256:" + hashlib.sha256(json.dumps(cols, separators=(",", ":")).encode()).hexdigest()[:16]


def _table(schema, name: str):
    name = str(name).lower()
    return next((t for t in schema if t.name.lower() == name), None)


def _col(table, name: str):
    return next((c for c in table.column_names if c.lower() == str(name).lower()), None)


def _low(cols) -> tuple:
    return tuple(str(c).lower() for c in cols)


def _date(at: str) -> str:
    """'2026-11-16T09:30:00Z' -> '16 November 2026'."""
    try:
        d = datetime.fromisoformat(str(at).replace("Z", "+00:00"))
    except ValueError:
        return str(at)
    return f"{d.day} {d.strftime('%B')} {d.year}"


def describe(d: dict) -> str:
    """'decided by your team on 16 November 2026 (steward): rejected; status is a code list per module'."""
    why = f"; {d['reason']}" if d.get("reason") else ""
    return f"{PROVENANCE} on {_date(d['at'])} ({d['role']}): {d['decision']}{why}"


def _what(d: dict) -> str:
    n = d["names"]
    if d["kind"] == "key":
        return f"key of {n['table']}: {' + '.join(n['columns'])}"
    return f"{n['source']}.{'+'.join(n['source_cols'])} -> {n['target']}.{'+'.join(n['target_cols'])}"


# ------------------------------------------------------------------ the store -----------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tenant TEXT NOT NULL,
  scope TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('key', 'link')),
  item TEXT NOT NULL,
  names TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  decision TEXT NOT NULL CHECK (decision IN ('accepted', 'rejected')),
  role TEXT NOT NULL,
  reason TEXT NOT NULL DEFAULT '',
  at TEXT NOT NULL,
  evidence TEXT,
  undone_at TEXT,
  undone_role TEXT
);
CREATE INDEX IF NOT EXISTS decisions_tenant_scope ON decisions (tenant, scope);
"""
_COLS = ("id", "tenant", "scope", "kind", "item", "names", "fingerprint", "decision", "role", "reason", "at", "evidence",
         "undone_at", "undone_role")


class Store:
    """Decision records in SQLite. Every method takes the tenant and every query filters on it: one tenant's decisions
    are never read, counted, undone or applied for another."""

    def __init__(self, path: str | os.PathLike = ":memory:"):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._db.executescript(_SCHEMA)
            self._db.commit()

    def close(self) -> None:
        self._db.close()

    def _rows(self, sql: str, args: tuple) -> list[dict]:
        with self._lock:
            cur = self._db.execute(sql, args)
            out = [dict(zip(_COLS, r)) for r in cur.fetchall()]
        for d in out:
            d["names"] = json.loads(d["names"])
            d["evidence"] = json.loads(d["evidence"]) if d["evidence"] else None
            d.pop("tenant")                                       # the caller knows its tenant; the digest is not shown
        return out

    def add(self, tenant: str, scope: str, kind: str, names: dict, decision: str, role: str, *, fingerprint: str,
            reason: str = "", evidence: dict | None = None, at: str | None = None) -> dict:
        if kind not in ("key", "link"):
            raise DecisionError("kind is 'key' or 'link'")
        if decision not in DECISIONS:
            raise DecisionError(f"decision is one of {', '.join(DECISIONS)}")
        if role not in ROLES:
            raise DecisionError(f"role is one of {', '.join(ROLES)} (a role, never a person's name)")
        item = key_item(names["table"]) if kind == "key" else link_item(names["source"], names["source_cols"], names["target"])
        at = at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        reason = " ".join(str(reason or "").split())[:REASON_LIMIT]
        with self._lock:
            cur = self._db.execute(
                "INSERT INTO decisions (tenant, scope, kind, item, names, fingerprint, decision, role, reason, at, evidence) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (tenant_key(tenant), scope, kind, item, json.dumps(names, sort_keys=True), fingerprint, decision, role,
                 reason, at, json.dumps(evidence, sort_keys=True) if evidence is not None else None))
            self._db.commit()
            new = cur.lastrowid
        return self.get(tenant, new)

    def get(self, tenant: str, decision_id: int) -> dict | None:
        rows = self._rows(f"SELECT {', '.join(_COLS)} FROM decisions WHERE tenant = ? AND id = ?", (tenant_key(tenant), int(decision_id)))
        return rows[0] if rows else None

    def history(self, tenant: str, scope: str | None = None) -> list[dict]:
        """Every decision of the tenant (of one scope), undone ones too, oldest first."""
        if scope is None:
            return self._rows(f"SELECT {', '.join(_COLS)} FROM decisions WHERE tenant = ? ORDER BY id", (tenant_key(tenant),))
        return self._rows(f"SELECT {', '.join(_COLS)} FROM decisions WHERE tenant = ? AND scope = ? ORDER BY id",
                          (tenant_key(tenant), scope))

    def active(self, tenant: str, scope: str) -> list[dict]:
        """The rules: per item the latest decision that is not undone, in the order they were made."""
        latest: dict[str, dict] = {}
        for d in self.history(tenant, scope):
            if d["undone_at"]:
                continue
            latest.pop(d["item"].lower(), None)
            latest[d["item"].lower()] = d
        # one accepted link per source column(s): a later accepted link to another target replaces the earlier one
        out, linked = [], set()
        for d in reversed(list(latest.values())):
            if d["kind"] == "link" and d["decision"] == "accepted":
                col = (d["names"]["source"].lower(), _low(d["names"]["source_cols"]))
                if col in linked:
                    continue
                linked.add(col)
            out.append(d)
        return out[::-1]

    def undo(self, tenant: str, decision_id: int, role: str, at: str | None = None) -> dict:
        """Undo one decision of this tenant: it stays in the history, it is no longer a rule. Another tenant's id is
        answered exactly as an id that does not exist."""
        if role not in ROLES:
            raise DecisionError(f"role is one of {', '.join(ROLES)} (a role, never a person's name)")
        d = self.get(tenant, decision_id)
        if d is None:
            raise DecisionError(f"no decision {decision_id} for this tenant")
        if d["undone_at"]:
            raise DecisionError(f"decision {decision_id} was already undone on {_date(d['undone_at'])}")
        at = at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with self._lock:
            self._db.execute("UPDATE decisions SET undone_at = ?, undone_role = ? WHERE tenant = ? AND id = ?",
                             (at, role, tenant_key(tenant), int(decision_id)))
            self._db.commit()
        return self.get(tenant, decision_id)


def store_from_env(create: bool = False) -> Store | None:
    """The local store: KRUSGRAPH_DECISIONS (a path; "off" turns decisions off), else ~/.krusgraph/decisions.sqlite.
    Without create, a store that does not exist yet is None (nothing decided, nothing written)."""
    raw = os.environ.get(ENV, "").strip()
    if raw.lower() in ("off", "0", "false", "no"):
        return None
    path = Path(raw).expanduser() if raw else DEFAULT_PATH
    if raw == ":memory:":
        return Store(":memory:")
    if not create and not path.exists():
        return None
    return Store(path)


def tenant_from_env() -> str:
    return os.environ.get(TENANT_ENV, "").strip() or "local"


# ------------------------------------------------------------------ recording a decision ------------------------------

def names_for(plan, item: str | None = None, key: dict | None = None, link: dict | None = None) -> tuple[str, dict]:
    """(kind, names) for an item of the plan (key:<table>, rel:<source>.<cols>><target>, also a proposed or ambiguous
    candidate), or an explicit key {table, columns} or link {source, source_cols, target, target_cols}; every name in
    the schema's own spelling."""
    s = plan.schema
    if key:
        t = _table(s, key.get("table", ""))
        cols = [_col(t, c) for c in key.get("columns") or []] if t else []
        if t is None or not cols or None in cols:
            raise DecisionError(f"key {key!r}: the table or a column is not in the schema")
        return "key", {"table": t.name, "columns": cols}
    if link:
        src, tgt = _table(s, link.get("source", "")), _table(s, link.get("target", ""))
        if src is None or tgt is None:
            raise DecisionError(f"link {link!r}: the source or target table is not in the schema")
        sc = [_col(src, c) for c in link.get("source_cols") or []]
        tc = [_col(tgt, c) for c in (link.get("target_cols") or plan.keys.get(tgt.name, ([], ""))[0])]
        if not sc or None in sc or len(tc) != len(sc) or None in tc:
            raise DecisionError(f"link {link!r}: give source_cols and target_cols that are in the tables, as many on each side")
        return "link", {"source": src.name, "source_cols": sc, "target": tgt.name, "target_cols": tc}
    item = str(item or "")
    if item.lower().startswith("key:"):
        t = item[4:]
        found = next(((n, k) for n, k in plan.keys.items() if n.lower() == t.lower()), None)
        if found is None:
            raise DecisionError(f"{item}: the plan has no key for that table; give key={{table, columns}} to decide one")
        return "key", {"table": found[0], "columns": list(found[1][0])}
    if item.lower().startswith("rel:"):
        cands = [(r.source, r.source_cols, r.target, r.target_cols) for r in plan.relationships]
        cands += [(x["source"], x["source_cols"], x["target"], x.get("target_cols") or []) for x in plan.proposed or []
                  if x.get("source") and x.get("target")]
        for a in plan.ambiguous or []:
            for t in a.get("candidates", []):
                tk = plan.keys.get(t, ([], ""))[0]
                if len(tk) == 1:
                    cands.append((a["table"], [a["column"]], t, list(tk)))
        for src, sc, tgt, tc in cands:
            if link_item(src, sc, tgt).lower() == item.lower() and tc:
                return "link", {"source": src, "source_cols": list(sc), "target": tgt, "target_cols": list(tc)}
        raise DecisionError(f"{item}: no such link or candidate in the plan; give link={{source, source_cols, target, target_cols}}")
    raise DecisionError("name the item as key:<table> or rel:<source>.<columns>><target>, or give key= or link=")


def evidence_now(plan, execute, kind: str, names: dict) -> dict:
    """What the rows say about this one key or link now, counts only (one counting query; validate_plan's SQL)."""
    from . import evidence as ev
    schema, dialect = plan.schema.schema, ev.dialect_of(execute)
    if kind == "key":
        row = execute(ev.key_sql(schema, names["table"], names["columns"], dialect))[0]
        n, nulls, distinct = (int(row.get(k) or 0) for k in ("n", "nulls", "distinct_keys"))
        return {"rows": n, "nulls": nulls, "distinct": distinct, "verdict": ev.key_verdict(n, nulls, distinct)}
    row = execute(ev.relationship_sql(schema, names["source"], names["source_cols"], names["target"], names["target_cols"], dialect))[0]
    wv, orph = int(row.get("with_value") or 0), int(row.get("orphans") or 0)
    return {"rows_with_value": wv, "orphans": orph, "verdict": ev.relationship_verdict(wv, orph)}


def record(store: Store, tenant: str, scope: str, plan, decision: str, role: str, *, item: str | None = None,
           key: dict | None = None, link: dict | None = None, reason: str = "", evidence: dict | None = None,
           at: str | None = None) -> dict:
    kind, names = names_for(plan, item, key, link)
    tables = [names["table"]] if kind == "key" else [names["source"], names["target"]]
    if kind == "link":                       # what the source table looked like: recognises it renamed (rejected links)
        names["source_shape"] = shape(_table(plan.schema, names["source"]))
    return store.add(tenant, scope, kind, names, decision, role, fingerprint=fingerprint(plan.schema, tables),
                     reason=reason, evidence=evidence, at=at)


# ------------------------------------------------------------------ rules applied to a plan ---------------------------

def _decided_link(r, links: dict) -> dict | None:
    return links.get((r.source.lower(), _low(r.source_cols), r.target.lower()))


def plan(schema, rules: list[dict], planner, keys: dict | None = None, confirmed: list | None = None):
    """planner(schema, keys, confirmed) -> Plan, with the tenant's rules applied around it:

      accepted key   -> keys (rule DECIDED), unless the caller gives that table's key
      accepted link  -> confirmed (rule DECIDED), unless the caller confirms that source column
      rejected link  -> taken out of the plan (and out of plan.proposed); the same link from another table of the scope
                        too, as how="pattern"; a declared foreign key (R0) stays, under conflicts
      rejected key   -> taken out with the links into it; a declared key (K0) stays, under conflicts

    A rule whose table or column is gone is listed under not_applied with why. A rule whose tables changed since it
    was made says so (changed_since). plan.decisions is the report; nothing here counts rows."""
    keys, confirmed = dict(keys or {}), list(confirmed or [])
    given_keys = {str(t).lower() for t in keys}
    given_links = {(str(c.get("source", "")).lower(), _low(c.get("source_cols") or [])) for c in confirmed}
    applied, not_applied, suppressed, conflicts = [], [], [], []
    acc_keys, acc_links, rej_keys, rej_links = {}, {}, {}, []

    def changed(d: dict, tables: list[str]) -> dict:
        return {"changed_since": True} if fingerprint(schema, tables) != d["fingerprint"] else {}

    for d in rules:
        n = d["names"]
        tables = [n["table"]] if d["kind"] == "key" else [n["source"], n["target"]]
        missing = [t for t in tables if _table(schema, t) is None]
        if d["kind"] == "link" and d["decision"] == "rejected" and missing == [n["source"]] and n.get("source_shape"):
            renamed = _renamed(schema, n)
            if renamed is not None:
                tgt = _table(schema, n["target"])
                tc = [_col(tgt, c) for c in n["target_cols"]]
                if None not in tc:
                    rej_links.append((d, renamed.name, [_col(renamed, c) for c in n["source_cols"]], tgt.name, tc, n["source"]))
                    continue
        if not missing:
            if d["kind"] == "key":
                cols = [(n["table"], c) for c in n["columns"]]
            else:
                cols = [(n["source"], c) for c in n["source_cols"]] + [(n["target"], c) for c in n["target_cols"]]
            gone = [f"{t}.{c}" for t, c in cols if _col(_table(schema, t), c) is None]
        if missing or gone:
            not_applied.append({"decision": d["id"], "item": d["item"], "decision_was": d["decision"],
                                "why": (f"table {', '.join(missing)} is not in the schema now" if missing
                                        else f"column {', '.join(gone)} is not in the schema now"), "provenance": describe(d)})
            continue
        if d["kind"] == "key":
            t = _table(schema, n["table"])
            cols = [_col(t, c) for c in n["columns"]]
            if d["decision"] == "accepted":
                if t.name.lower() in given_keys:
                    not_applied.append({"decision": d["id"], "item": d["item"], "decision_was": "accepted",
                                        "why": "the call gives this table's key", "provenance": describe(d)})
                    continue
                keys[t.name] = cols
                acc_keys[t.name] = (d, cols)
            else:
                rej_keys[t.name] = (d, cols)
        else:
            src, tgt = _table(schema, n["source"]), _table(schema, n["target"])
            sc, tc = [_col(src, c) for c in n["source_cols"]], [_col(tgt, c) for c in n["target_cols"]]
            if d["decision"] == "accepted":
                if (src.name.lower(), _low(sc)) in given_links:
                    not_applied.append({"decision": d["id"], "item": d["item"], "decision_was": "accepted",
                                        "why": "the call confirms this column itself", "provenance": describe(d)})
                    continue
                confirmed.append({"source": src.name, "source_cols": sc, "target": tgt.name, "target_cols": tc})
                acc_links[(src.name.lower(), _low(sc), tgt.name.lower())] = (d, sc, tc)
            else:
                rej_links.append((d, src.name, sc, tgt.name, tc, None))

    p = planner(schema, keys or None, confirmed or None)

    # accepted: relabel what went in as K1 / confirmed
    for t, (d, cols) in acc_keys.items():
        if t in p.keys and _low(p.keys[t][0]) == _low(cols) and p.keys[t][1] == "K1":
            p.keys[t] = (p.keys[t][0], RULE)
            applied.append({"decision": d["id"], "item": d["item"], "decision_was": "accepted", "what": _what(d),
                            "provenance": describe(d), **changed(d, [t])})
    for r in p.relationships:
        hit = _decided_link(r, acc_links)
        if hit is not None and r.rule == "confirmed":
            d = hit[0]
            r.rule = RULE
            r.note = describe(d)
            applied.append({"decision": d["id"], "item": d["item"], "decision_was": "accepted", "what": _what(d),
                            "provenance": describe(d), **changed(d, [r.source, r.target])})

    # rejected keys: out, with the links into them
    for t, (d, cols) in rej_keys.items():
        if t not in p.keys or _low(p.keys[t][0]) != _low(cols):
            continue
        rule = p.keys[t][1]
        if rule in DECLARED or rule in ("K1", RULE):
            conflicts.append({"decision": d["id"], "item": d["item"], "decision_was": "rejected", "what": _what(d),
                              "kept_because": "the source declares this key (K0)" if rule == "K0" else "the call gives this key",
                              "provenance": describe(d)})
            continue
        del p.keys[t]
        if t not in p.keyless:
            p.keyless.append(t)
        suppressed.append({"decision": d["id"], "item": d["item"], "decision_was": "rejected", "how": "exact",
                           "what": f"key of {t}: {' + '.join(cols)} ({rule})", "provenance": describe(d), **changed(d, [t])})
        for r in [r for r in p.relationships if r.target == t and _low(r.target_cols) == _low(cols)]:
            if r.rule in DECLARED or r.rule in ("confirmed", RULE):
                continue
            p.relationships.remove(r)
            suppressed.append({"decision": d["id"], "item": link_item(r.source, r.source_cols, r.target), "decision_was": "rejected",
                               "how": "key rejected", "what": f"{r.source}.{'+'.join(r.source_cols)} -> {t} ({r.rule}), into the rejected key",
                               "provenance": describe(d)})

    # rejected links: the link itself, or the same link from the table renamed (shown as a pattern)
    for d, s, sc, t, tc, was in rej_links:
        how = "pattern" if was else "exact"
        for r in list(p.relationships):
            if (r.source.lower(), _low(r.source_cols), r.target.lower()) != (s.lower(), _low(sc), t.lower()):
                continue
            if r.rule in DECLARED or r.rule in ("confirmed", RULE):
                conflicts.append({"decision": d["id"], "item": d["item"], "decision_was": "rejected", "what": _what(d),
                                  "kept_because": ("the source declares this foreign key (R0)" if r.rule == "R0"
                                                   else "the call confirms this link"), "provenance": describe(d)})
                continue
            p.relationships.remove(r)
            entry = {"decision": d["id"], "item": link_item(r.source, r.source_cols, r.target), "decision_was": "rejected",
                     "how": how, "what": f"{r.source}.{'+'.join(r.source_cols)} -> {r.target}.{'+'.join(r.target_cols)} ({r.rule})",
                     "provenance": describe(d), **({} if was else changed(d, [s, t]))}
            if was:
                entry["pattern"] = (f"{was} is not in the schema now and {s} has exactly the columns {was} had when the decision "
                                    f"was made: read as {was} renamed, so the rejected {was}.{'+'.join(sc)} -> {t} applies to it")
            suppressed.append(entry)
        before = len(p.proposed or [])
        p.proposed = [x for x in p.proposed or [] if not ((str(x.get("source", "")).lower(), _low(x.get("source_cols") or []),
                                                          str(x.get("target", "")).lower()) == (s.lower(), _low(sc), t.lower()))]
        if len(p.proposed) < before:
            suppressed.append({"decision": d["id"], "item": d["item"], "decision_was": "rejected", "how": how,
                               "what": f"{s}.{'+'.join(sc)} -> {t} (a candidate in plan.proposed)", "provenance": describe(d)})

    p.decisions = {
        "rule": RULE, "provenance": PROVENANCE,
        "status": "decided by your team, not proven: validate_plan counts accepted keys and links against the rows like any other",
        "rules": len(rules), "applied": applied, "suppressed": suppressed, "not_applied": not_applied, "conflicts": conflicts,
    }
    return p


def _renamed(schema, n: dict):
    """The one table of the schema with exactly the columns the decided source table had, the source columns among
    them; None when there is none or more than one (then nothing generalises)."""
    hits = [t for t in schema if shape(t) == n["source_shape"] and all(_col(t, c) for c in n["source_cols"])]
    return hits[0] if len(hits) == 1 else None


def contradictions(p, checks: dict | None) -> list[dict]:
    """The decided keys and links validate_plan's counts contradict now: flagged, never trusted silently. checks is
    evidence.validate's full answer (keys and relationships with their verdicts)."""
    if not checks or not getattr(p, "decisions", None):
        return []
    by_item = {a["item"].lower(): a for a in p.decisions["applied"]}
    out = []
    for k in checks.get("keys", []):
        a = by_item.get(key_item(k["table"]).lower())
        if a and not str(k.get("verdict", "")).startswith(("unique", "empty")):
            out.append({"item": a["item"], "decision": a["decision"], "provenance": a["provenance"], "now": k["verdict"],
                        "what": f"Your team accepted this key, but the rows now say: {k['verdict']}. Check it, then record the "
                                f"decision again or undo it (undo_decision={a['decision']})."})
    for r in checks.get("relationships", []):
        a = by_item.get(link_item(r["source"], r["columns"], r["target"]).lower())
        v = str(r.get("verdict", ""))
        if a and not v.startswith(("holds", "no rows")):
            out.append({"item": a["item"], "decision": a["decision"], "provenance": a["provenance"], "now": v,
                        "what": f"Your team accepted this link, but the rows now say: {v}. Check it, then record the "
                                f"decision again or undo it (undo_decision={a['decision']})."})
    return out


def answer(p) -> dict | None:
    """plan.decisions for a tool's answer: what came from earlier decisions, in words, plus the report."""
    d = getattr(p, "decisions", None)
    if not d or not d["rules"]:
        return None
    lines = [f"{a['what']}: {a['provenance']}" + (" (its tables changed since)" if a.get("changed_since") else "") for a in d["applied"]]
    lines += [f"Not proposed: {s['what']}: {s['provenance']}" + (f" ({s['pattern']})" if s.get("pattern") else "") for s in d["suppressed"]]
    lines += [f"Kept although rejected: {c['what']}: {c['kept_because']}; {c['provenance']}" for c in d["conflicts"]]
    lines += [f"Not applied: {n['item']} ({n['decision_was']}): {n['why']}" for n in d["not_applied"]]
    return {**d, "lines": lines,
            "undo": "list_decisions shows every decision with its id; record_decision(undo=<id>) undoes one"}


def summary_line(d: dict) -> str:
    return (f"{d['rules']} decision(s) of your team applied as rules (rule \"{RULE}\"): {len(d['applied'])} accepted key(s)/link(s) "
            f"proposed directly, {len(d['suppressed'])} rejected one(s) not proposed, {len(d['conflicts'])} kept against a "
            f"decision, {len(d['not_applied'])} not applicable — see plan.decisions")
