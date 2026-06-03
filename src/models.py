"""In-memory representation of the parts catalog.

A ``CatalogItem`` keeps both the raw CSV value and the normalized value for the
fields that need cleaning (price, stock, OEM), so every downstream decision can
be audited back to the source text. ``Catalog`` bundles the canonical ordered
list with two exact-lookup indexes built on top of it.

The list order is meaningful: ``items[i]`` lines up with row ``i`` of the
embedding matrix, so the retrieval step can map a vector index straight back to
its item.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class StockStatus(str, Enum):
    """Typed stock state, because the raw column mixes ints with words/blanks."""

    IN_STOCK = "in_stock"
    LOW = "low"  # 'few' — some units, exact count unknown
    OUT_OF_STOCK = "out_of_stock"  # 'agotado' or 0
    UNKNOWN = "unknown"  # blank — we don't promise what we can't confirm


@dataclass
class CatalogItem:
    """One catalog row: raw fields preserved, hostile fields normalized."""

    row_index: int  # position in Catalog.items == row in the embedding matrix
    sku: str
    name: str
    brand: str | None
    category: str | None  # from category_hint
    make: str | None
    model: str | None
    year: str | None
    oem_raw: str | None
    oem_norm: str | None  # comparable key: uppercased, no 'OEM'/spaces/dashes
    replaced_by: str | None
    price: int | None  # normalized COP integer; None if unparseable
    price_raw: str
    stock_qty: int | None  # known units; None when unknown or merely 'few'
    stock_status: StockStatus
    stock_raw: str
    notes: str | None

    @property
    def embed_text(self) -> str:
        """Present-fields-only text that gets embedded for semantic retrieval.

        Blank columns are skipped (you can't rely on them), and the category
        hint's underscores are spaced out so 'spark_plug' reads as words.
        """
        category = self.category.replace("_", " ") if self.category else None
        parts = [
            self.name,
            self.brand,
            category,
            self.make,
            self.model,
            self.year,
            self.oem_norm,
        ]
        return " ".join(p for p in parts if p)


@dataclass
class Catalog:
    """Canonical ordered list + exact-lookup indexes derived from it."""

    items: list[CatalogItem]
    by_sku: dict[str, CatalogItem]
    by_oem: dict[str, list[CatalogItem]]  # one-to-many: SKUs can share an OEM

    def __len__(self) -> int:
        return len(self.items)
