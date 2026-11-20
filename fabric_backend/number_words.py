"""Numbers as a person reads them (round WB12, Gustav's chat test of 18 November 2026, issue #67).

The start card printed a doubled total as "22610.900000000016; once per products row: 1666.6000000000001": the float a
SUM over SQL returns, as Python prints it. Every answer that prints a sum goes through `amount()` instead: two decimals,
thousands grouped, locale-neutral (a thin space groups the thousands, as SI and ISO 80000 write them, and a full stop
marks the decimals, so neither a comma reader nor a full stop reader takes 22 610.90 for 22.61). `factor()` says how
many times one sum is the other ("about 13.6x"), from the two sums themselves.
"""
from __future__ import annotations

import math

GROUP = " "          # NARROW NO-BREAK SPACE: groups thousands and never breaks a number over two lines


def _float(v) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def rounded(v, places: int = 2):
    """The value to keep in an answer's JSON: an int when it is whole, else rounded to `places` decimals; None as is."""
    f = _float(v)
    if f is None:
        return v if v is None else None
    r = round(f, places)
    return int(r) if r == int(r) and abs(r) < 2 ** 53 else r


def amount(v, places: int = 2) -> str:
    """22610.900000000016 -> '22 610.90' (thin space); a whole count stays whole ('1 200'); None or text -> '(blank)'."""
    f = _float(v)
    if f is None:
        return "(blank)"
    if isinstance(v, int) and not isinstance(v, bool):
        return f"{v:,}".replace(",", GROUP)
    return f"{f:,.{places}f}".replace(",", GROUP)


def count(n) -> str:
    """A whole count with its thousands grouped: 12000 -> '12 000'."""
    f = _float(n)
    return "(blank)" if f is None else f"{int(round(f)):,}".replace(",", GROUP)


def factor(over, once) -> str:
    """'about 13.6x': how many times `over` is `once`; '' when it cannot be said (a zero, a blank, a negative)."""
    b, a = _float(over), _float(once)
    if b is None or a is None or a <= 0 or b < 0:
        return ""
    x = b / a
    return f"{x:.0f}x" if abs(x - round(x)) < 0.05 else f"about {x:.1f}x"
