"""Tests for the hour-5 margin + alternative logic."""

import pytest

from src.loader import load_catalog
from src.margin import is_fluid, suggest_alternative, unit_cost
from src.models import StockStatus
from src.retriever import CatalogIndex

CATALOG = load_catalog()


def _first(pred):
    return next(i for i in CATALOG.items if pred(i))


# --- classification (pure, no model) ---

def test_fluid_by_category():
    assert is_fluid(_first(lambda i: i.category == "engine_oil"))
    assert is_fluid(_first(lambda i: i.category == "brake_fluid"))
    assert is_fluid(_first(lambda i: i.category == "coolant"))


def test_part_by_category():
    assert not is_fluid(_first(lambda i: i.category == "brake_pad"))
    # an oil FILTER is a part, not a fluid, even though the category contains "oil".
    assert not is_fluid(_first(lambda i: i.category == "oil_filter"))


def test_oil_filter_with_blank_category_is_part():
    item = _first(
        lambda i: not i.category
        and ("filtro de aceite" in i.name.lower() or "oil filter" in i.name.lower())
    )
    assert not is_fluid(item)


# --- cost / margin ratios ---

def test_cost_ratio_part_vs_fluid():
    oil = _first(lambda i: i.category == "engine_oil" and i.price)
    pad = _first(lambda i: i.category == "brake_pad" and i.price)
    assert unit_cost(oil) == round(oil.price * 0.85)  # fluid -> 15% margin
    assert unit_cost(pad) == round(pad.price * 0.70)  # part  -> 30% margin


# --- alternative suggestion (needs the embedding index) ---

@pytest.fixture(scope="module")
def index():
    try:
        return CatalogIndex.load_or_build()
    except Exception as exc:
        pytest.skip(f"embedding model unavailable: {exc}")


def test_alternative_is_in_stock_and_same_category(index):
    # An out-of-stock SKU WITH a category should get a same-category, in-stock alt.
    out_of_stock = next(
        i for i in index.catalog.items
        if i.stock_status == StockStatus.OUT_OF_STOCK and i.category
    )
    alt = suggest_alternative(out_of_stock, index)
    assert alt is not None
    assert alt.sku != out_of_stock.sku
    cand = index.catalog.by_sku[alt.sku]
    assert cand.stock_status == StockStatus.IN_STOCK
    assert cand.category == out_of_stock.category  # hard category filter
