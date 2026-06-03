"""Deterministic normalizers for the hostile catalog fields.

Prices arrive in ~15 formats (``$``, ``COP``, thousands-dot vs decimal-dot);
stock mixes integers with ``agotado``/``few``/blank; OEM codes carry ``OEM``
prefixes, spaces and dashes. Each function turns the raw text into a clean,
comparable value (or a typed "unknown"), and never guesses a number it can't
defend.
"""

from __future__ import annotations

import re

from .models import StockStatus

# A trailing dot followed by exactly two digits is decimal cents (15429.00).
# A dot followed by three digits is a thousands group ($238.400) — left alone here.
_CENTS_RE = re.compile(r"\.\d{2}$")


def normalize_price(raw: str | None) -> int | None:
    """Normalize a price string to an integer number of COP.

    ``'$238.400' -> 238400``, ``'15429.00' -> 15429``, ``'COP 67091' -> 67091``.
    Returns ``None`` if the value is blank or non-numeric (flag, don't invent).
    """
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return None
    s = re.sub(r"(?i)cop", "", s).replace("$", "").strip()
    s = _CENTS_RE.sub("", s)  # drop decimal cents if present
    s = s.replace(".", "").replace(" ", "")  # remove thousands separators
    return int(s) if s.isdigit() else None


def normalize_stock(raw: str | None) -> tuple[int | None, StockStatus]:
    """Map a messy stock cell into ``(quantity_or_None, status)``.

    Integers keep their count; ``agotado`` and ``0`` are out of stock; ``few`` is
    low with an unknown count; blank is genuinely unknown.
    """
    if raw is None:
        return (None, StockStatus.UNKNOWN)
    s = raw.strip().lower()
    if not s:
        return (None, StockStatus.UNKNOWN)
    if s == "agotado":
        return (0, StockStatus.OUT_OF_STOCK)
    if s == "few":
        return (None, StockStatus.LOW)
    if s.isdigit():
        n = int(s)
        return (0, StockStatus.OUT_OF_STOCK) if n == 0 else (n, StockStatus.IN_STOCK)
    return (None, StockStatus.UNKNOWN)


def normalize_oem(raw: str | None) -> str | None:
    """Collapse an OEM code to a comparable key.

    ``'OEM 98100' -> '98100'``, ``'90915-YZZD4' -> '90915YZZD4'``. Uppercases,
    strips an ``OEM`` marker, and drops every non-alphanumeric char so a catalog
    code and a customer-typed code reduce to the same key. ``None`` if empty.
    """
    if raw is None:
        return None
    s = re.sub(r"\bOEM\b", "", raw.upper())
    s = re.sub(r"[^A-Z0-9]", "", s)
    return s or None
