"""Hour-5 additions: estimated margin, and an in-stock alternative for stockouts.

Margin model (given): cost = 70% of price for parts, 85% for fluids/oils. So the
margin is 30% of price on parts and 15% on fluids. Classification leans on the
category hint when present and falls back to keywords — taking care that an "oil
FILTER" is a part, not a fluid.

The alternative for an out-of-stock SKU is its nearest in-stock neighbor in the
embedding space (same part type + vehicle fall out of that similarity naturally),
which is robust to the catalog's many blank category/vehicle fields.
"""

from __future__ import annotations

import numpy as np
from pydantic import BaseModel

from .models import CatalogItem, StockStatus
from .retriever import CatalogIndex

COST_RATIO_PART = 0.70  # -> 30% margin
COST_RATIO_FLUID = 0.85  # -> 15% margin

_FLUID_CATEGORIES = {"engine_oil", "brake_fluid", "coolant"}
_FLUID_KW = (
    "oil", "aceite", "coolant", "refriger", "anticongel", "fluid", "fluido",
    "dot3", "dot4", "grasa", "grease", "lubric", "liquido", "líquido",
)
_FILTER_KW = ("filter", "filtro")  # an oil filter is a PART, not a fluid


def is_fluid(item: CatalogItem) -> bool:
    """Classify a SKU as a fluid/oil (vs a solid part) for the cost ratio."""
    cat = (item.category or "").lower()
    if cat:
        if cat in _FLUID_CATEGORIES:
            return True
        return ("oil" in cat or "fluid" in cat or "coolant" in cat) and "filter" not in cat
    blob = item.name.lower()
    if any(f in blob for f in _FILTER_KW):
        return False
    return any(k in blob for k in _FLUID_KW)


def unit_cost(item: CatalogItem) -> int | None:
    """Estimated unit cost in COP, or None if the price is unknown."""
    if item.price is None:
        return None
    ratio = COST_RATIO_FLUID if is_fluid(item) else COST_RATIO_PART
    return round(item.price * ratio)


class AlternativeSuggestion(BaseModel):
    sku: str
    name: str
    price: int | None
    reason: str


def suggest_alternative(
    item: CatalogItem, index: CatalogIndex
) -> AlternativeSuggestion | None:
    """Closest in-stock alternative to an out-of-stock SKU: same category + vehicle.

    Category (part type) is a hard filter when known — otherwise the nearest
    embedding neighbor drifts to a same-vehicle item of the WRONG type (a battery
    suggesting an air filter). Within the category pool, embedding similarity ranks
    by closeness, which favors the same vehicle. Falls back to a pure semantic
    neighbor only when the item has no category to filter on.
    """
    items = index.catalog.items
    sims = index.embeddings @ index.embeddings[item.row_index]

    eligible = [
        i
        for i in range(len(items))
        if items[i].sku != item.sku
        and items[i].stock_status == StockStatus.IN_STOCK
    ]
    same_category = "same category + vehicle"
    if item.category:
        pool = [i for i in eligible if items[i].category == item.category]
        if not pool:  # nothing of that type in stock — relax to semantic neighbor
            pool, same_category = eligible, "closest in-stock (no same-category stock)"
    else:
        pool, same_category = eligible, "closest in-stock (original has no category)"

    if not pool:
        return None

    best = max(pool, key=lambda i: sims[i])
    cand = items[best]
    return AlternativeSuggestion(
        sku=cand.sku,
        name=cand.name,
        price=cand.price,
        reason=f"alternativa en stock ({same_category})",
    )
