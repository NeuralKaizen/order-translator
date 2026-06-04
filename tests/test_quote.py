"""Tests for the deterministic quoting step."""

import pytest

from src.decide import Decision
from src.extract import LineItemIntent, Vehicle
from src.loader import load_catalog
from src.quote import build_line_item, format_cop, quote_total

CATALOG = load_catalog()


@pytest.mark.parametrize(
    "amount,expected",
    [(68000, "$68.000"), (1234567, "$1.234.567"), (9988, "$9.988"), (None, "—")],
)
def test_format_cop(amount, expected):
    assert format_cop(amount) == expected


def _intent(qty):
    return LineItemIntent(
        customer_text="pastillas de freno",
        part_query="brake pads Renault Duster 2016",
        vehicle=Vehicle(make="Renault", model="Duster", year="2016"),
        quantity=qty,
        oem_code=None,
        qualifiers=[],
        is_job=False,
    )


def _decision(**kw):
    base = dict(
        matched_sku=None,
        matched_name=None,
        confidence=0.5,
        decision="needs_clarification",
        reasoning="r",
        clarifying_question=None,
        question_stage=None,
    )
    base.update(kw)
    return Decision(**base)


def test_auto_matched_line_is_priced():
    sku = "SKU-1010"  # Pastillas de Freno Renault Duster 2016
    price = CATALOG.by_sku[sku].price
    line = build_line_item(
        _intent(qty=2),
        _decision(matched_sku=sku, decision="auto_matched", confidence=0.93),
        CATALOG,
    )
    assert line.unit_price == price
    assert line.line_total == price * 2
    assert line.quantity == 2


def test_unmatched_line_has_no_price():
    line = build_line_item(_intent(qty=None), _decision(), CATALOG)
    assert line.unit_price is None
    assert line.line_total is None
    assert line.quantity == 1  # None quantity defaults to 1


def test_unknown_sku_prices_to_none_gracefully():
    line = build_line_item(
        _intent(qty=1),
        _decision(matched_sku="SKU-DOES-NOT-EXIST", decision="auto_matched"),
        CATALOG,
    )
    assert line.unit_price is None
    assert line.line_total is None


def test_quote_total_sums_only_priced_lines():
    sku = "SKU-1010"
    price = CATALOG.by_sku[sku].price
    matched = build_line_item(
        _intent(qty=1), _decision(matched_sku=sku, decision="auto_matched"), CATALOG
    )
    unmatched = build_line_item(_intent(qty=1), _decision(), CATALOG)
    assert quote_total([matched, unmatched]) == price
