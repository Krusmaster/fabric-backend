"""Names written into generated code: one place that makes them safe where they are not inside a quoted literal.

The generators (silver, gold, the pipeline's check notebook, dbt, the Databricks drafts, the SodaCL and ODCS drafts)
write table and column names into comment lines (`# ...` in Python and YAML, `-- ...` in SQL) so a reader sees which
rule produced a line. A comment ends at the end of its line, so a name that carries a line break (a column named
`id\\nimport os #`, which a Delta table with column mapping or a `keys=` argument can hold) would end the comment and
start a statement that runs under the identity of whoever runs the notebook (review of 8 November 2026, H1).

`one_line()` escapes every character that is not printable, which covers every way a line can end: `\\n`, `\\r`,
the ones `str.splitlines()` also splits on (`\\v`, `\\f`, `\\x1c`-`\\x1e`, `\\x85`, `\\u2028`, `\\u2029`, which
`notebook.fabric_source` uses to lay out a cell) and the other control characters. A printable name stays exactly as
it is, so the comments read the same for every name that was safe before.
"""
from __future__ import annotations


def _escape(ch: str) -> str:
    o = ord(ch)
    if o < 0x100:
        return {"\n": "\\n", "\r": "\\r", "\t": "\\t"}.get(ch, f"\\x{o:02x}")
    return f"\\u{o:04x}" if o < 0x10000 else f"\\U{o:08x}"


def one_line(text) -> str:
    """`text` as one line: every non-printable character (line breaks, control characters) as its escape."""
    s = str(text)
    return s if s.isprintable() else "".join(ch if ch.isprintable() else _escape(ch) for ch in s)


def comment(text, prefix: str = "# ") -> str:
    """A comment line with `text` in it that cannot end before the end of the line."""
    return prefix + one_line(text)


def sql_comment(text, prefix: str = "-- ") -> str:
    return prefix + one_line(text)

