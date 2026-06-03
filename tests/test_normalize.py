"""Unit tests for the field normalizers, using real catalog value shapes."""

import pytest

from src.models import StockStatus
from src.normalize import normalize_oem, normalize_price, normalize_stock


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("15008", 15008),  # plain integer
        ("9988", 9988),
        ("118517", 118517),
        ("$17.411", 17411),  # $ + thousands dot
        ("$ 46626", 46626),  # $ + space
        ("COP 67091", 67091),  # COP prefix
        ("$238.400", 238400),  # thousands dot, 3-digit group
        ("15429.00", 15429),  # decimal cents -> dropped
        ("118022.00", 118022),
        ("$9.564", 9564),
        ("COP 8961", 8961),
        ("8898.00", 8898),
    ],
)
def test_normalize_price_formats(raw, expected):
    assert normalize_price(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", None, "agotado", "n/a"])
def test_normalize_price_unparseable_returns_none(raw):
    assert normalize_price(raw) is None


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("27", (27, StockStatus.IN_STOCK)),
        ("2", (2, StockStatus.IN_STOCK)),
        ("0", (0, StockStatus.OUT_OF_STOCK)),
        ("agotado", (0, StockStatus.OUT_OF_STOCK)),
        ("few", (None, StockStatus.LOW)),
        ("", (None, StockStatus.UNKNOWN)),
        ("   ", (None, StockStatus.UNKNOWN)),
        (None, (None, StockStatus.UNKNOWN)),
    ],
)
def test_normalize_stock(raw, expected):
    assert normalize_stock(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("OEM 98100", "98100"),
        ("90915-YZZD4", "90915YZZD4"),
        ("94020-53450", "9402053450"),
        ("A9617", "A9617"),
        ("6215039", "6215039"),
        ("  oem  s2525 ", "S2525"),
        ("", None),
        (None, None),
    ],
)
def test_normalize_oem(raw, expected):
    assert normalize_oem(raw) == expected
