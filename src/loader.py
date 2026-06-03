"""Load the catalog CSV into the in-memory representation.

One pass over the file builds the canonical ``items`` list (CSV order preserved,
so it stays aligned with the embedding matrix) and the ``by_sku`` / ``by_oem``
indexes on top of it.
"""

from __future__ import annotations

import csv
from pathlib import Path

from .models import Catalog, CatalogItem
from .normalize import normalize_oem, normalize_price, normalize_stock

DEFAULT_CATALOG_PATH = (
    Path(__file__).resolve().parents[1] / "info" / "data" / "catalog.csv"
)


def _blank_to_none(value: str | None) -> str | None:
    """Trim a cell; treat empty as missing rather than an empty string."""
    if value is None:
        return None
    v = value.strip()
    return v or None


def load_catalog(path: str | Path = DEFAULT_CATALOG_PATH) -> Catalog:
    """Read ``catalog.csv`` and return a populated :class:`Catalog`."""
    items: list[CatalogItem] = []
    by_sku: dict[str, CatalogItem] = {}
    by_oem: dict[str, list[CatalogItem]] = {}

    with open(path, newline="", encoding="utf-8") as f:
        for i, row in enumerate(csv.DictReader(f)):
            oem_raw = _blank_to_none(row.get("oem_cross_ref"))
            stock_qty, stock_status = normalize_stock(row.get("stock", ""))
            item = CatalogItem(
                row_index=i,
                sku=row["sku"].strip(),
                name=row["name"].strip(),
                brand=_blank_to_none(row.get("brand")),
                category=_blank_to_none(row.get("category_hint")),
                make=_blank_to_none(row.get("vehicle_make")),
                model=_blank_to_none(row.get("vehicle_model")),
                year=_blank_to_none(row.get("year")),
                oem_raw=oem_raw,
                oem_norm=normalize_oem(oem_raw),
                replaced_by=_blank_to_none(row.get("replaced_by")),
                price=normalize_price(row.get("price", "")),
                price_raw=row.get("price", ""),
                stock_qty=stock_qty,
                stock_status=stock_status,
                stock_raw=row.get("stock", ""),
                notes=_blank_to_none(row.get("notes")),
            )
            items.append(item)
            by_sku[item.sku] = item
            if item.oem_norm:
                by_oem.setdefault(item.oem_norm, []).append(item)

    return Catalog(items=items, by_sku=by_sku, by_oem=by_oem)
