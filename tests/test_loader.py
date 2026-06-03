"""Integration tests for loading the real catalog.csv."""

from src.loader import load_catalog
from src.models import StockStatus

CATALOG = load_catalog()


def test_row_count():
    assert len(CATALOG) == 874


def test_index_alignment():
    # items[i].row_index == i is the invariant the embedding matrix relies on.
    for i, item in enumerate(CATALOG.items):
        assert item.row_index == i


def test_by_sku_complete_and_unique():
    assert len(CATALOG.by_sku) == 874  # SKUs are unique in this catalog
    assert CATALOG.by_sku["REF0336"].name.startswith("SPARK PLUG")


def test_first_row_fully_normalized():
    item = CATALOG.items[0]
    assert item.sku == "REF0336"
    assert item.price == 118517
    assert item.stock_qty == 27
    assert item.stock_status == StockStatus.IN_STOCK
    assert item.oem_norm == "A9617"


def test_by_oem_groups_items():
    assert any(it.sku == "REF0336" for it in CATALOG.by_oem["A9617"])


def test_all_prices_parsed():
    # price is never blank in this catalog, so none should fail to parse.
    assert [it.sku for it in CATALOG.items if it.price is None] == []


def test_every_status_present():
    statuses = {it.stock_status for it in CATALOG.items}
    assert StockStatus.OUT_OF_STOCK in statuses  # 'agotado' / 0
    assert StockStatus.LOW in statuses  # 'few'
    assert StockStatus.UNKNOWN in statuses  # blank
    assert StockStatus.IN_STOCK in statuses


def test_embed_text_skips_blanks():
    # An item with blank vehicle fields must not leak 'None' into embed text.
    item = CATALOG.items[0]
    assert "None" not in item.embed_text
    assert "Sandero" in item.embed_text  # present field folded in
