"""A reader for a Qlik load script (.qvs) and a Tableau workbook (.twb, .twbx): the proof in docs/MIGRATION-DESIGN.md (W7).

It lists what a migration starts from: tables, the fields that link them, synthetic keys or joins, and calculated
fields. It is a reader for a design round and not a tool: nothing in server.py calls it. It reads text it is given,
opens no connection, runs no expression, and uses no AI model. Tested on synthetic files only (tests/fixtures/w7/);
it has not read a file from a real Qlik or Tableau installation.

What the rules rest on. help.qlik.com, qlik.dev and help.tableau.com could not be opened from the session that wrote
this (15 November 2026), so every rule about Qlik and most about Tableau is **Unverified**: written from public
knowledge of the vendors' documentation, to be read on the page before anything public rests on it.
- Qlik (Unverified): tables associate on fields with the same name; two tables that share two or more fields get a
  synthetic key; a loop of associations is a circular reference; field names are case-sensitive; a load with the same
  set of fields as an earlier table is appended to it unless NoConcatenate; Join without a field list joins on the
  common fields; a mapping table is not part of the data model; an unlabelled table is named after its source.
- Tableau, opened on 15 November 2026 in Tableau's own public repository tableau/document-api-python (README,
  tableaudocumentapi/field.py and xfile.py, test/assets/*.tds): a .twb is XML; a .twbx is a zip that holds it; a
  data source has <connection> and <relation> elements; a field is a <column> with caption, datatype and role, and a
  calculated field carries <calculation formula="...">.
- Tableau (Unverified): the layout of a join (<relation type="join"> with a <clause> of nested <expression op>), of
  relationships (<object-graph>), of an extract (<extract enabled>), of worksheet filters (<filter context>), the
  `_.fcp.` prefix on newer tag names, and that a FIXED level of detail expression is computed before dimension filters
  unless the filter is in context.

Everything the reader does not understand is listed under `not_read` with its line, never skipped silently.

What it keeps out of its answer: the rows of an inline table (only the header and a row count), connection strings
(`LIB CONNECT` is counted, not returned), a Tableau connection's server and user name (only its class), custom SQL
(only its length in lines), and the value of a variable whose name looks like a secret.
"""
from __future__ import annotations

import fnmatch
import io
import re
import zipfile
from xml.etree import ElementTree

MAX_CHARS = 2_000_000          # a script or workbook longer than this is refused, not cut
_NAME = r'(?:\[[^\]]+\]|"[^"]+"|[A-Za-z_@#$%][\w.@#$%]*)'
_CONTROL = re.compile(r"\s*(?:if|elseif|else|end\s*if|endif|for|next|do|loop|sub|end\s*sub|endsub|call|switch|case|"
                      r"default|end\s*switch|endswitch|exit\s+(?:for|do|sub))\b", re.I)
_NO_EFFECT = re.compile(r"(?:store|lib\s+connect|connect|odbc\s+connect|oledb\s+connect|disconnect|trace|sleep|tag|untag|"
                        r"comment|directory|exit\s+script|null\w*|star|declare|derive|search|alias)\b", re.I)
_SHAPING = re.compile(r"(?:crosstable|generic|hierarchy\w*|intervalmatch|buffer|first|sample|add|replace|merge|semantic|"
                      r"binary|bundle|info|image_size|unless|when)\b", re.I)


class ReadError(ValueError):
    """The input is not something this reader takes; the message says why in plain words."""


def _unquote(name: str) -> str:
    name = name.strip()
    if len(name) >= 2 and (name[0], name[-1]) in (("[", "]"), ('"', '"'), ("'", "'"), ("`", "`")):
        return name[1:-1]
    return name


# ------------------------------------------------------------------ Qlik: statements ---------------------------------

def _statements(text: str) -> tuple[list[tuple[int, str]], list[dict]]:
    """The script as (line, statement) without comments, and its tabs. A statement ends at `;` outside quotes and
    brackets; a control statement (If, For, Sub...) ends at its line's end, as it has no semicolon."""
    out, tabs, buf, start, line = [], [], [], 1, 1
    i, n, quote = 0, len(text), ""
    closing = {"'": "'", '"': '"', "[": "]"}
    while i < n:
        ch = text[i]
        if quote:
            buf.append(ch)
            if ch == closing[quote]:
                quote = ""
        elif text.startswith("///$tab", i):
            end = text.find("\n", i)
            end = n if end < 0 else end
            tabs.append({"name": text[i + 7:end].strip(), "line": line})
            i = end
            continue
        elif text.startswith("//", i):
            end = text.find("\n", i)
            i = n if end < 0 else end
            continue
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            end = n if end < 0 else end + 2
            line += text.count("\n", i, end)
            i = end
            continue
        elif ch in closing:
            quote = ch
            if not buf:
                start = line
            buf.append(ch)
        elif ch == ";":
            s = "".join(buf).strip()
            if s:
                out.append((start, s))
            buf = []
        elif ch == "\n" and _CONTROL.match("".join(buf)):
            out.append((start, "".join(buf).strip()))
            buf = []
        elif buf or not ch.isspace():
            if not buf:
                start = line
            buf.append(ch)
        if ch == "\n":
            line += 1
        i += 1
    s = "".join(buf).strip()
    if s:
        out.append((start, s))
    return [(ln, st) for ln, st in out if not re.match(r"rem\b", st, re.I)], tabs


def _top_level(s: str):
    """Yields (index, char) for the characters of `s` outside quotes, brackets and parentheses."""
    depth, quote = 0, ""
    closing = {"'": "'", '"': '"', "[": "]"}
    for i, ch in enumerate(s):
        if quote:
            if ch == closing[quote]:
                quote = ""
        elif ch in closing:
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif depth == 0:
            yield i, ch


def _find_keyword(s: str, words: tuple[str, ...], start: int = 0) -> tuple[int, str] | None:
    """The first of `words` that stands as a word at top level, at or after `start`: (index, the word as written)."""
    top = {i for i, _ in _top_level(s)}
    pattern = re.compile(r"\b(?:" + "|".join(w.replace(" ", r"\s+") for w in words) + r")\b", re.I)
    for m in pattern.finditer(s, start):
        if m.start() in top:
            return m.start(), m.group(0)
    return None


def _split_commas(s: str) -> list[str]:
    cuts = [i for i, ch in _top_level(s) if ch == ","]
    parts, last = [], 0
    for c in cuts:
        parts.append(s[last:c])
        last = c + 1
    parts.append(s[last:])
    return [p.strip() for p in parts if p.strip()]


def _field_item(item: str, line: int) -> dict:
    """One entry of a field list: a field, a renamed field (`a AS b`) or a calculated one (`expression AS b`)."""
    alias = None
    for m in re.finditer(r"\s+as\s+", item, re.I):
        if m.start() in {i for i, _ in _top_level(item)}:
            alias = m
    expr, name = (item[:alias.start()].strip(), _unquote(item[alias.end():])) if alias else (item, None)
    if expr == "*":
        return {"wildcard": True}
    plain = re.fullmatch(_NAME, expr)
    if plain:
        src = _unquote(expr)
        out = {"name": name or src}
        if name and name != src:
            out["renamed_from"] = src
        return out
    return {"name": name or expr, "expression": " ".join(expr.split()), "line": line, "unnamed": name is None}


def _parse_load(body: str, line: int) -> dict:
    """`LOAD [DISTINCT] fields [FROM | RESIDENT | INLINE | AUTOGENERATE ...] [WHERE ...] [GROUP BY ...]`."""
    rest = re.sub(r"^load\s+", "", body, flags=re.I)
    distinct = bool(re.match(r"distinct\b", rest, re.I))
    rest = re.sub(r"^distinct\s+", "", rest, flags=re.I)
    cut = _find_keyword(rest, ("from", "resident", "inline", "autogenerate", "where", "while", "group by", "order by"))
    fields, tail = (rest[:cut[0]], rest[cut[0]:]) if cut else (rest, "")
    out = {"fields": [_field_item(f, line) for f in _split_commas(fields)], "distinct": distinct, "line": line,
           "where": bool(_find_keyword(tail, ("where",))), "group_by": bool(_find_keyword(tail, ("group by",))), "source": None}
    m = re.match(r"(from|resident|inline|autogenerate)\b\s*", tail, re.I)
    if not m:
        return out
    kind, after = m.group(1).lower(), tail[m.end():]
    end = _find_keyword(after, ("where", "while", "group by", "order by"))
    after = (after[:end[0]] if end else after).strip()
    if kind == "from":
        path = re.match(r"""\[[^\]]+\]|"[^"]+"|'[^']*'|[^\s(]+""", after)
        out["source"] = {"kind": "file", "name": _unquote(path.group(0)) if path else after}
    elif kind == "resident":
        out["source"] = {"kind": "resident", "name": _unquote(after)}
    elif kind == "autogenerate":
        out["source"] = {"kind": "autogenerate", "name": after}
    else:
        block = re.match(r"\[(.*)\]", after, re.S)
        rows = [r.strip() for r in (block.group(1) if block else "").splitlines() if r.strip()]
        out["source"] = {"kind": "inline", "name": "", "rows": max(0, len(rows) - 1),
                         "header": [h.strip() for h in rows[0].split(",")] if rows else []}
    return out


def _parse_select(body: str, line: int) -> dict:
    rest = re.sub(r"^(?:sql\s+)?select\s+", "", body, flags=re.I)
    distinct = bool(re.match(r"distinct\b", rest, re.I))
    rest = re.sub(r"^distinct\s+", "", rest, flags=re.I)
    cut = _find_keyword(rest, ("from",))
    fields, tail = (rest[:cut[0]], rest[cut[0] + 4:]) if cut else (rest, "")
    end = _find_keyword(tail, ("where", "group by", "order by", "having"))
    source = " ".join((tail[:end[0]] if end else tail).split())
    return {"fields": [_field_item(f, line) for f in _split_commas(fields)], "distinct": distinct, "line": line,
            "where": bool(_find_keyword(tail, ("where",))), "group_by": bool(_find_keyword(tail, ("group by",))),
            "source": {"kind": "sql", "name": source, "sql_join": bool(re.search(r"\bjoin\b", source, re.I))}}


# ------------------------------------------------------------------ Qlik: the model -----------------------------------

class _Script:
    def __init__(self):
        self.tables: dict[str, dict] = {}
        self.mapping: list[dict] = []
        self.access: list[dict] = []
        self.dropped: list[dict] = []
        self.variables: list[dict] = []
        self.calculated: list[dict] = []
        self.not_read: list[dict] = []
        self.other: dict[str, int] = {}
        self.qualify: list[tuple[bool, str]] = []
        self.pending: dict | None = None
        self.last: str | None = None
        self.in_access = False

    # -- helpers
    def skip(self, line: int, statement: str, why: str):
        self.not_read.append({"line": line, "statement": " ".join(statement.split())[:160], "why": why})

    def _qualified(self, field: str) -> bool:
        hit = False
        for on, pattern in self.qualify:
            if fnmatch.fnmatchcase(field, pattern):
                hit = on
        return hit

    def _source_fields(self, source: dict | None) -> list[str] | None:
        if not source:
            return None
        if source["kind"] == "inline":
            return list(source["header"])
        if source["kind"] == "resident":
            t = self.tables.get(source["name"])
            return list(t["fields"]) if t and not t["fields_unknown"] else None
        return None                                   # a file or a database table: its columns are not in the script

    def _resolve(self, levels: list[dict]) -> tuple[list[str], bool]:
        """The fields of a (preceding) load chain, top level first in `levels`; `*` takes the level below."""
        below, unknown = self._source_fields(levels[-1]["source"]), False
        for level in reversed(levels):
            names = []
            for f in level["fields"]:
                if f.get("wildcard"):
                    if below is None:
                        unknown = True
                    names += [b for b in (below or []) if b not in names]
                elif f["name"] not in names:
                    names.append(f["name"])
            below = names
        return below or [], unknown

    # -- loads
    def load(self, label: str | None, prefixes: dict, parsed: dict):
        chain = self.pending or {"label": label, "prefixes": prefixes, "levels": [], "line": parsed["line"]}
        chain["levels"].append(parsed)
        if parsed["source"] is None:                  # a preceding load: the next statement is its source
            self.pending = chain
            return
        self.pending = None
        fields, unknown = self._resolve(chain["levels"])
        source, label, prefixes, line = parsed["source"], chain["label"], chain["prefixes"], chain["line"]
        info = {"line": line, "source": {k: v for k, v in source.items() if k != "header"},
                "distinct": any(lv["distinct"] for lv in chain["levels"]), "where": any(lv["where"] for lv in chain["levels"]),
                "group_by": any(lv["group_by"] for lv in chain["levels"]), "preceding_loads": len(chain["levels"]) - 1}
        if prefixes.get("mapping"):
            self.mapping.append({"name": label or "(unnamed)", "fields": fields, "line": line})
            return
        if self.in_access:
            self.access.append({"name": label or "(unnamed)", "fields": fields, "line": line})
            return
        target = prefixes.get("target") or self.last
        name = label or self._source_name(source)
        calcs = [f for lv in chain["levels"] for f in lv["fields"] if "expression" in f]
        if prefixes.get("join") and target in self.tables:
            t = self.tables[target]
            on = [f for f in fields if f in t["fields"]]
            t["fields"] += [f for f in fields if f not in t["fields"]]
            t["fields_unknown"] = t["fields_unknown"] or unknown
            t["joins"].append({**info, "kind": prefixes["join"], "on": on})
            name = target
        elif prefixes.get("concatenate") and target in self.tables:
            name = self._append(target, fields, unknown, info, auto=False)
        else:
            same = None if prefixes.get("noconcatenate") or prefixes.get("keep") or unknown else next(
                (n for n, t in self.tables.items() if not t["fields_unknown"] and set(t["fields"]) == set(fields)), None)
            if same:
                name = self._append(same, fields, unknown, info, auto=True)
            else:
                name = self._unique(name)
                qualified = [f"{name}.{f}" if self._qualified(f) else f for f in fields]
                self.tables[name] = {"name": name, "fields": qualified, "fields_unknown": unknown, "loads": [info],
                                     "joins": [], "concatenated": [], "labelled": bool(label)}
                if prefixes.get("keep"):
                    self.tables[name]["keep"] = {"kind": prefixes["keep"], "with": target}
        self.calculated += [{"table": name, "field": f["name"], "expression": f["expression"], "line": f["line"],
                             **({"unnamed": True} if f["unnamed"] else {})} for f in calcs]
        self.last = name

    def _append(self, target: str, fields: list[str], unknown: bool, info: dict, auto: bool) -> str:
        t = self.tables[target]
        t["fields"] += [f for f in fields if f not in t["fields"]]
        t["fields_unknown"] = t["fields_unknown"] or unknown
        t["concatenated"].append({**info, "automatic": auto})
        return target

    def _source_name(self, source: dict) -> str:
        if source["kind"] in ("file", "sql", "resident"):
            base = re.split(r"[/\\]", source["name"].split()[0] if source["name"] else "table")[-1]
            return _unquote(base.rsplit(".", 1)[0] if source["kind"] == "file" else base.split(".")[-1]) or "table"
        return "table"

    def _unique(self, name: str) -> str:
        if name not in self.tables:
            return name
        n = 1
        while f"{name}-{n}" in self.tables:
            n += 1
        return f"{name}-{n}"


def _names(text: str) -> list[str]:
    return [_unquote(x) for x in _split_commas(text)]


def _prefixes(body: str) -> tuple[dict, str]:
    """Strips the prefixes this reader applies (Join, Keep, Concatenate, NoConcatenate, Mapping) off a statement."""
    out: dict = {}
    while True:
        m = re.match(r"(noconcatenate|mapping)\b\s*", body, re.I)
        if m:
            out[m.group(1).lower()] = True
            body = body[m.end():]
            continue
        m = re.match(rf"(?:(left|right|inner|outer)\s+)?(join|keep|concatenate)\b\s*(?:\(\s*({_NAME})\s*\))?\s*", body, re.I)
        if m and (m.group(2).lower() != "concatenate" or not m.group(1)):
            kind = m.group(2).lower()
            out[kind] = True if kind == "concatenate" else (m.group(1) or ("outer" if kind == "join" else "inner")).lower()
            if m.group(3):
                out["target"] = _unquote(m.group(3))
            body = body[m.end():]
            continue
        return out, body


def read_qvs(text: str) -> dict:
    """A Qlik load script as data: tables with their fields and loads, the fields that associate tables, synthetic
    keys, circular references, link table candidates, calculated fields, variables, and every statement not read."""
    if not isinstance(text, str):
        raise ReadError("The load script must be text.")
    if len(text) > MAX_CHARS:
        raise ReadError(f"The load script is longer than {MAX_CHARS} characters; it was not read.")
    statements, tabs = _statements(text.replace("\r\n", "\n"))
    s = _Script()
    for line, st in statements:
        if _CONTROL.match(st):
            s.skip(line, st, "a control statement: the loads inside it are read as if each ran once")
            continue
        m = re.match(rf"({_NAME})\s*:\s*(?=\S)", st)
        label, body = (_unquote(m.group(1)), st[m.end():]) if m and not re.match(r"(set|let)\b", st, re.I) else (None, st)
        prefixes, body = _prefixes(body)
        if re.match(r"load\b", body, re.I):
            s.load(label, prefixes, _parse_load(body, line))
        elif re.match(r"(sql\s+)?select\b", body, re.I):
            s.load(label, prefixes, _parse_select(body, line))
        elif s.pending is not None:
            s.skip(s.pending["line"], "LOAD ...", "a load without a source, and the next statement is not a load or a select")
            s.pending = None
            s.skip(line, st, "it follows a load without a source")
        elif (m := re.match(r"(set|let)\s+([\w.@#$]+)\s*=\s*(.*)", body, re.I | re.S)):
            secret = re.search(r"pass|pwd|secret|token|apikey|api_key|credential", m.group(2), re.I)
            s.variables.append({"name": m.group(2), "kind": m.group(1).lower(), "line": line,
                                "value": "(not shown: the name looks like a secret)" if secret else " ".join(m.group(3).split())[:200]})
        elif (m := re.match(r"(un)?qualify\s+(.*)", body, re.I | re.S)):
            s.qualify += [(not m.group(1), p) for p in _names(m.group(2))]
        elif (m := re.match(r"drop\s+tables?\s+(.*)", body, re.I | re.S)):
            for name in _names(m.group(1)):
                if s.tables.pop(name, None) is not None:
                    s.dropped.append({"table": name, "line": line})
                else:
                    s.skip(line, st, f"no table named {name} was loaded before this line")
        elif (m := re.match(r"drop\s+fields?\s+(.*?)(?:\s+from\s+(.*))?$", body, re.I | re.S)):
            only = _names(m.group(2)) if m.group(2) else list(s.tables)
            for f in _names(m.group(1)):
                for name in only:
                    if name in s.tables and f in s.tables[name]["fields"]:
                        s.tables[name]["fields"].remove(f)
                s.dropped.append({"field": f, "line": line, **({"tables": only} if m.group(2) else {})})
        elif (m := re.match(r"rename\s+(field|table)s?\s+(.*)", body, re.I | re.S)):
            for pair in _split_commas(m.group(2)):
                ends = re.split(r"\s+to\s+", pair, maxsplit=1, flags=re.I)
                old, new = _unquote(ends[0]), _unquote(ends[1]) if len(ends) == 2 else ""
                if not new:
                    s.skip(line, st, "a rename without `to`")
                elif m.group(1).lower() == "table" and old in s.tables:
                    s.tables = {(new if k == old else k): ({**v, "name": new} if k == old else v) for k, v in s.tables.items()}
                    s.last = new if s.last == old else s.last
                elif m.group(1).lower() == "field":
                    for t in s.tables.values():
                        t["fields"] = [new if f == old else f for f in t["fields"]]
        elif (m := re.match(r"section\s+(access|application)\b", body, re.I)):
            s.in_access = m.group(1).lower() == "access"
        elif (m := _NO_EFFECT.match(body)):
            word = " ".join(m.group(0).lower().split())
            s.other[word] = s.other.get(word, 0) + 1
        elif _SHAPING.match(body):
            s.skip(line, st, "a prefix or statement that changes the shape of a table; this reader does not apply it")
        else:
            s.skip(line, st, "not a statement this reader knows")
    if s.pending is not None:
        s.skip(s.pending["line"], "LOAD ...", "a load without a source at the end of the script")
    return _qlik_model(s, tabs, text)


def _loops(tables: dict[str, list[str]], shared: dict[str, list[str]]) -> list[dict]:
    """Circular references: loops of three or more tables through different link fields. Fields that the same pair of
    tables shares are one link (their synthetic key), so two tables with two common fields are not a loop."""
    parent = {f: f for f in shared}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    names = sorted(tables)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            common = sorted(f for f in shared if a in shared[f] and b in shared[f])
            for f in common[1:]:
                parent[find(f)] = find(common[0])
    link_of = {f: find(f) for f in shared}
    edges = sorted({(t, link_of[f]) for f, ts in shared.items() for t in ts})
    adjacency: dict[tuple, list[tuple]] = {}
    seen: dict[tuple, tuple] = {}

    def root(x):
        while seen[x] != x:
            x = seen[x]
        return x

    def path(a, b):
        prev, queue = {a: None}, [a]
        while queue:
            x = queue.pop(0)
            if x == b:
                break
            for y in adjacency.get(x, []):
                if y not in prev:
                    prev[y] = x
                    queue.append(y)
        out, x = [], b
        while x is not None:
            out.append(x)
            x = prev[x]
        return out

    out = []
    for t, link in edges:
        a, b = ("table", t), ("link", link)
        seen.setdefault(a, a)
        seen.setdefault(b, b)
        if root(a) == root(b):
            walk = path(a, b)
            fields = set()
            for i, x in enumerate(walk):                          # a link's fields: those its two neighbours share
                if x[0] == "link":
                    near = (walk[i - 1][1], walk[(i + 1) % len(walk)][1])
                    fields |= {f for f in shared if link_of[f] == x[1] and all(t in shared[f] for t in near)}
            out.append({"tables": sorted(x[1] for x in walk if x[0] == "table"), "fields": sorted(fields)})
        else:
            seen[root(a)] = root(b)
            adjacency.setdefault(a, []).append(b)
            adjacency.setdefault(b, []).append(a)
    return out


def _qlik_model(s: _Script, tabs: list[dict], text: str) -> dict:
    tables = {n: t["fields"] for n, t in s.tables.items()}
    shared: dict[str, list[str]] = {}
    for n in sorted(tables):
        for f in tables[n]:
            shared.setdefault(f, []).append(n)
    shared = {f: ts for f, ts in sorted(shared.items()) if len(ts) > 1}
    names = sorted(tables)
    synthetic = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            common = sorted(f for f in shared if a in shared[f] and b in shared[f])
            if len(common) > 1:
                synthetic.append({"tables": [a, b], "fields": common})
    links = []
    for n in names:
        others = sorted({o for f in tables[n] for o in shared.get(f, []) if o != n})
        if len(tables[n]) > 1 and len(others) > 1 and all(f in shared for f in tables[n]) and not s.tables[n]["fields_unknown"]:
            links.append({"table": n, "fields": list(tables[n]), "links": others})
    by_fold: dict[str, set] = {}
    for fields in tables.values():
        for f in fields:
            by_fold.setdefault(f.lower(), set()).add(f)
    out_tables = []
    for n in s.tables:
        t = s.tables[n]
        row = {"name": n, "fields": list(t["fields"]), "keys": [f for f in t["fields"] if f in shared], "loads": t["loads"]}
        for k in ("joins", "concatenated"):
            if t[k]:
                row[k] = t[k]
        if t["fields_unknown"]:
            row["fields_unknown"] = "a `*` over a file or a database table: its columns are not in the script"
        if "keep" in t:
            row["keep"] = t["keep"]
        out_tables.append(row)
    return {
        "kind": "qlik_load_script",
        "read_by": "fixed rules on the script's text; nothing was run and Qlik was not asked",
        "tabs": tabs,
        "tables": out_tables,
        "associations": [{"field": f, "tables": ts} for f, ts in shared.items()],
        "synthetic_keys": synthetic,
        "circular_references": _loops(tables, shared),
        "link_table_candidates": links,
        "unlinked_tables": [n for n in names if not any(f in shared for f in tables[n])],
        "names_that_differ_only_by_case": [sorted(v) for _, v in sorted(by_fold.items()) if len(v) > 1],
        "calculated_fields": s.calculated,
        "variables": s.variables,
        "mapping_tables": s.mapping,
        "section_access": {"present": bool(s.access) or bool(re.search(r"\bsection\s+access\b", text, re.I)), "tables": s.access},
        "dropped": s.dropped,
        "dollar_expansions": sum(1 for _ in re.finditer(r"\$\(", text)),
        "other_statements": dict(sorted(s.other.items())),
        "not_read": s.not_read,
    }


# ------------------------------------------------------------------ Tableau ------------------------------------------

_LOD = re.compile(r"\{\s*(fixed|include|exclude)\b([^:{}]*):", re.I)
_LOD_BARE = re.compile(r"\{\s*(?!fixed\b|include\b|exclude\b)[A-Za-z_]+\s*\(", re.I)
_TABLE_CALC = re.compile(r"\b(window_\w+|running_\w+|lookup|index|first|last|size|total|rank\w*|previous_value)\s*\(", re.I)
_AGGREGATE = re.compile(r"\b(sum|avg|min|max|count|countd|median|attr|stdev\w*|var\w*|percentile)\s*\(", re.I)
_REF = re.compile(r"\[([^\]]+)\]")


def _tag(el) -> str:
    """The element's name without the feature prefix newer workbooks put on some tags (`_.fcp.<Feature>.true...name`)."""
    return el.tag.rsplit("...", 1)[-1] if isinstance(el.tag, str) else ""


def _children(el, name: str):
    return [c for c in el if _tag(c) == name]


def _descendants(el, name: str):
    return [c for c in el.iter() if _tag(c) == name]


def _formula_kind(formula: str) -> tuple[str, list[dict]]:
    lods = [{"scope": m.group(1).upper(), "dimensions": [d for d in _REF.findall(m.group(2))]} for m in _LOD.finditer(formula)]
    if _LOD_BARE.search(formula):
        lods.append({"scope": "FIXED", "dimensions": [], "note": "written without a keyword: computed over the whole table"})
    if lods:
        return "level_of_detail", lods
    if _TABLE_CALC.search(formula):
        return "table_calculation", []
    return ("aggregate" if _AGGREGATE.search(formula) else "row_level"), []


def _join(rel, joins: list, tables: list):
    """Walks a <relation>: a table, custom SQL, or a join of two relations with its clauses."""
    kind = rel.get("type", "")
    if kind == "join":
        sides = _children(rel, "relation")
        for side in sides:
            _join(side, joins, tables)
        clauses = []
        for clause in _children(rel, "clause"):
            for ex in _children(clause, "expression"):
                ops = [e.get("op", "") for e in _children(ex, "expression")]
                if len(ops) == 2:
                    clauses.append({"left": ops[0], "right": ops[1], "op": ex.get("op", "=")})
        named = [m.group(1) for c in clauses for side in (c["left"], c["right"]) if (m := re.match(r"\[([^\]]+)\]\.\[", side))]
        joins.append({"type": rel.get("join", "inner"), "clauses": clauses,
                      "tables": list(dict.fromkeys(named)) or [x.get("name", "") for x in sides if x.get("type") != "join"]})
    elif kind in ("table", "text", "union"):
        row = {"name": rel.get("name", ""), "kind": {"table": "table", "text": "custom_sql", "union": "union"}[kind]}
        if kind == "table":
            row["table"] = rel.get("table", "")
        if kind == "text":
            row["sql_lines"] = len((rel.text or "").strip().splitlines())
        if not any(t["name"] == row["name"] for t in tables):
            tables.append(row)
    elif kind == "collection":
        for side in _children(rel, "relation"):
            _join(side, joins, tables)


def _datasource(ds) -> dict:
    tables, joins, relationships = [], [], []
    classes = sorted({c.get("class", "") for c in _descendants(ds, "connection") if c.get("class") not in (None, "", "federated")})
    for conn in _children(ds, "connection"):
        for rel in _children(conn, "relation"):
            _join(rel, joins, tables)
    for graph in _descendants(ds, "object-graph"):
        ids = {}
        for obj in _descendants(graph, "object"):
            ids[obj.get("id", "")] = obj.get("caption") or obj.get("id", "")
            for rel in _descendants(obj, "relation"):
                _join(rel, joins, tables)
        for r in _descendants(graph, "relationship"):
            ends = [ids.get(e.get("object-id", ""), e.get("object-id", "")) for e in r if _tag(e) in ("first-end-point", "second-end-point")]
            clauses = []
            for ex in _children(r, "expression"):
                ops = [e.get("op", "") for e in _children(ex, "expression")]
                if len(ops) == 2:
                    clauses.append({"left": ops[0], "right": ops[1], "op": ex.get("op", "=")})
            row = {"tables": ends, "clauses": clauses}
            if row not in relationships:
                relationships.append(row)
    unique_joins = []
    for j in joins:
        if j not in unique_joins:
            unique_joins.append(j)
    calculated, columns = [], 0
    for col in _children(ds, "column"):
        columns += 1
        calc = next(iter(_children(col, "calculation")), None)
        if calc is None or calc.get("formula") is None:
            continue
        formula = calc.get("formula", "")
        kind, lods = _formula_kind(formula)
        row = {"name": col.get("name", ""), "caption": col.get("caption") or _unquote(col.get("name", "")),
               "datatype": col.get("datatype", ""), "role": col.get("role", ""), "formula": formula, "kind": kind,
               "references": sorted(set(_REF.findall(formula)))}
        if lods:
            row["level_of_detail"] = lods
        calculated.append(row)
    extracts = [{"enabled": e.get("enabled", "").lower() == "true", "filters": len(_descendants(e, "filter"))}
                for e in _children(ds, "extract")]
    keys = sorted({side for j in unique_joins + relationships for c in j["clauses"] for side in (c["left"], c["right"])})
    return {"name": ds.get("name", ""), "caption": ds.get("caption") or ds.get("name", ""), "connection_classes": classes,
            "tables": tables, "joins": unique_joins, "relationships": relationships, "keys": keys, "columns": columns,
            "calculated_fields": calculated, "extract": extracts[0] if extracts else {"enabled": False, "filters": 0}}


def read_twb(text: str | bytes) -> dict:
    """A Tableau workbook's XML as data: data sources with their tables, joins, relationships and extract, calculated
    fields with their kind (row level, aggregate, level of detail, table calculation), parameters, worksheets with
    their filters, and the traps the rules find."""
    if isinstance(text, bytes):
        text = text.decode("utf-8-sig", errors="replace")
    if len(text) > MAX_CHARS:
        raise ReadError(f"The workbook is longer than {MAX_CHARS} characters; it was not read.")
    if re.search(r"<!\s*(DOCTYPE|ENTITY)", text, re.I):
        raise ReadError("The workbook declares a DOCTYPE or an entity; it was not read.")
    try:
        root = ElementTree.fromstring(text.lstrip("﻿").encode("utf-8"))
    except ElementTree.ParseError as e:
        raise ReadError(f"The workbook is not well-formed XML ({e}).") from None
    if _tag(root) != "workbook":
        raise ReadError(f"The root element is <{_tag(root)}>, not <workbook>.")
    datasources, parameters = [], []
    for holder in _children(root, "datasources"):
        for ds in _children(holder, "datasource"):
            if ds.get("name") == "Parameters":
                parameters = [{"name": c.get("name", ""), "caption": c.get("caption") or _unquote(c.get("name", "")),
                               "datatype": c.get("datatype", ""), "value": c.get("value", "")} for c in _children(ds, "column")]
            else:
                datasources.append(_datasource(ds))
    calc_by_name = {(d["name"], c["name"]): c for d in datasources for c in d["calculated_fields"]}
    worksheets, traps = [], []
    for ws in _descendants(root, "worksheet"):
        used: list[tuple[str, str]] = []
        for dep in _descendants(ws, "datasource-dependencies"):
            used += [(dep.get("datasource", ""), c.get("name", "")) for c in _children(dep, "column")]
        filters = [{"column": f.get("column", ""), "class": f.get("class", ""), "context": f.get("context", "").lower() == "true"}
                   for f in _descendants(ws, "filter")]
        calcs = [calc_by_name[u] for u in used if u in calc_by_name]
        worksheets.append({"name": ws.get("name", ""), "datasources": sorted({u[0] for u in used}),
                           "calculated_fields": [c["caption"] for c in calcs], "filters": filters})
        outside = [f["column"] for f in filters if not f["context"]]
        for c in calcs:
            if outside and any(l["scope"] == "FIXED" for l in c.get("level_of_detail", [])):
                traps.append({"trap": "fixed_lod_with_filter_outside_context", "worksheet": ws.get("name", ""),
                              "field": c["caption"], "filters": outside,
                              "why": "A FIXED expression is computed before a dimension filter that is not in context, so "
                                     "this field keeps the unfiltered value while the rest of the sheet is filtered "
                                     "(Unverified: Tableau's order of operations was not opened)."})
    for d in datasources:
        for c in d["calculated_fields"]:
            for l in c.get("level_of_detail", []):
                if l["scope"] in ("INCLUDE", "EXCLUDE"):
                    traps.append({"trap": "lod_depends_on_the_view", "datasource": d["caption"], "field": c["caption"],
                                  "why": f"{l['scope']} is relative to the dimensions of each sheet; one DAX measure "
                                         "cannot stand for it on every page."})
            if c["kind"] == "table_calculation":
                traps.append({"trap": "table_calculation", "datasource": d["caption"], "field": c["caption"],
                              "why": "A table calculation runs over the rows of one view; its result depends on the "
                                     "view's layout."})
        for j in d["joins"]:
            if j["clauses"]:
                traps.append({"trap": "physical_join", "datasource": d["caption"], "tables": j["tables"], "join": j["type"],
                              "why": "A join is made before any aggregation: a measure of the table on the one side is "
                                     "repeated per matching row."})
        for t in d["tables"]:
            if t["kind"] == "custom_sql":
                traps.append({"trap": "custom_sql", "datasource": d["caption"], "table": t["name"],
                              "why": "Custom SQL is read as text only; the tables inside it are not listed."})
    known = {"datasources", "worksheets", "dashboards", "windows", "preferences", "repository-location", "style",
             "document-format-change-manifest", "thumbnails", "actions", "mapsources", "datagraph", "external", "shared-views"}
    not_read = sorted({_tag(c) for c in root if _tag(c) and _tag(c) not in known})
    return {"kind": "tableau_workbook", "read_by": "fixed rules on the workbook's XML; nothing was run and Tableau was not asked",
            "version": root.get("version", ""), "datasources": datasources, "parameters": parameters,
            "worksheets": worksheets, "dashboards": [d.get("name", "") for d in _descendants(root, "dashboard")],
            "traps": traps, "not_read": [{"element": n, "why": "not an element this reader knows"} for n in not_read]}


def read_twbx(data: bytes) -> dict:
    """A packaged workbook: the one .twb inside the zip is read; data files and images in it are not opened."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = [n for n in z.namelist() if n.lower().endswith(".twb") and "/" not in n.strip("/")]
            if len(names) != 1:
                raise ReadError(f"Expected one .twb at the top of the package, found {len(names)}.")
            if z.getinfo(names[0]).file_size > MAX_CHARS:
                raise ReadError(f"The workbook is longer than {MAX_CHARS} characters; it was not read.")
            out = read_twb(z.read(names[0]))
            out["package"] = {"workbook": names[0], "other_files": len(z.namelist()) - 1}
            return out
    except zipfile.BadZipFile:
        raise ReadError("The file is not a zip package.") from None


# ------------------------------------------------------------------ the list -----------------------------------------

def listing(read: dict) -> str:
    """What was read as plain lines: tables, keys, synthetic keys or joins, calculated fields, and what was not read."""
    lines = []
    if read["kind"] == "qlik_load_script":
        lines.append(f"Qlik load script: {len(read['tables'])} table(s), {len(read['associations'])} linking field(s), "
                     f"{len(read['synthetic_keys'])} synthetic key(s), {len(read['circular_references'])} circular reference(s), "
                     f"{len(read['calculated_fields'])} calculated field(s), {len(read['not_read'])} statement(s) not read.")
        for t in read["tables"]:
            lines.append(f"table {t['name']}: {', '.join(t['fields']) or '(fields unknown)'}"
                         + (f" | keys: {', '.join(t['keys'])}" if t["keys"] else " | no key shared with another table"))
        for k in read["synthetic_keys"]:
            lines.append(f"synthetic key: {k['tables'][0]} and {k['tables'][1]} share {', '.join(k['fields'])}")
        for c in read["circular_references"]:
            lines.append(f"circular reference: {' - '.join(c['tables'])} through {', '.join(c['fields'])}")
        for k in read["link_table_candidates"]:
            lines.append(f"link table candidate: {k['table']} links {', '.join(k['links'])}")
        for c in read["calculated_fields"]:
            lines.append(f"calculated field {c['table']}.{c['field']} = {c['expression']} (line {c['line']})")
        for n in read["not_read"]:
            lines.append(f"not read, line {n['line']}: {n['statement']} ({n['why']})")
        return "\n".join(lines)
    calcs = sum(len(d["calculated_fields"]) for d in read["datasources"])
    lines.append(f"Tableau workbook: {len(read['datasources'])} data source(s), {sum(len(d['tables']) for d in read['datasources'])} "
                 f"table(s), {sum(len(d['joins']) for d in read['datasources'])} join(s), "
                 f"{sum(len(d['relationships']) for d in read['datasources'])} relationship(s), {calcs} calculated field(s), "
                 f"{len(read['traps'])} trap(s).")
    for d in read["datasources"]:
        lines.append(f"data source {d['caption']}: extract {'on' if d['extract']['enabled'] else 'off'}")
        for t in d["tables"]:
            lines.append(f"  table {t['name']}" + (f" = {t['table']}" if t.get("table") else f" ({t['kind']})"))
        for j in d["joins"]:
            lines.append(f"  {j['type']} join: " + " and ".join(f"{c['left']} {c['op']} {c['right']}" for c in j["clauses"]))
        for r in d["relationships"]:
            lines.append(f"  relationship {' - '.join(r['tables'])}: " + " and ".join(f"{c['left']} {c['op']} {c['right']}" for c in r["clauses"]))
        if d["keys"]:
            lines.append(f"  keys: {', '.join(d['keys'])}")
        for c in d["calculated_fields"]:
            lines.append(f"  calculated field {c['caption']} ({c['kind']}) = {c['formula']}")
    for t in read["traps"]:
        lines.append(f"trap {t['trap']}: {t.get('field') or ', '.join(t.get('tables', [])) or t.get('table', '')}. {t['why']}")
    for n in read["not_read"]:
        lines.append(f"not read: <{n['element']}> ({n['why']})")
    return "\n".join(lines)
