"""Offline embedding index over the catalog for candidate retrieval.

Builds a unit-normalized embedding matrix aligned row-for-row with
``Catalog.items`` (row ``i`` is the embedding of ``items[i]``), so cosine
similarity is a single matmul and the top-k indices map straight back to items.
The matrix is cached to ``.npy`` keyed by a fingerprint of the model + the exact
texts, so we embed the catalog once and rebuild only when either changes.

This is the *semantic* half of retrieval. It bridges the ES/EN gap by meaning,
but static embeddings have a ceiling on regional slang and near-duplicates — the
lexical layer ([[busqueda-hibrida]]) and the LLM rank-and-decide step cover that.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from model2vec import StaticModel

from .loader import load_catalog
from .models import Catalog, CatalogItem

DEFAULT_MODEL = "minishlab/potion-multilingual-128M"
CACHE_DIR = Path(__file__).resolve().parents[1] / ".cache"


@dataclass
class Candidate:
    """A retrieved catalog item with its cosine score (the LLM's input later)."""

    item: CatalogItem
    score: float


def _l2_normalize(matrix: np.ndarray) -> np.ndarray:
    """Scale rows to unit length so cosine similarity reduces to a dot product."""
    norms = np.linalg.norm(matrix, axis=-1, keepdims=True)
    norms[norms == 0] = 1.0  # guard against an all-zero (empty-text) row
    return matrix / norms


def _fingerprint(model_name: str, texts: list[str]) -> str:
    """Stable hash of (model, exact texts) — the cache key for the .npy."""
    h = hashlib.sha256(model_name.encode("utf-8"))
    for t in texts:
        h.update(t.encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()[:16]


class CatalogIndex:
    """Embedding index + semantic retrieval over a loaded catalog."""

    def __init__(self, catalog: Catalog, model: StaticModel, embeddings: np.ndarray):
        self.catalog = catalog
        self.model = model
        self.embeddings = embeddings  # (N, dim), L2-normalized, aligned with items

    @classmethod
    def load_or_build(
        cls,
        catalog: Catalog | None = None,
        model_name: str = DEFAULT_MODEL,
        cache_dir: Path = CACHE_DIR,
    ) -> "CatalogIndex":
        """Load the cached matrix if present and current, else embed and cache it."""
        catalog = catalog or load_catalog()
        texts = [it.embed_text for it in catalog.items]
        model = StaticModel.from_pretrained(model_name)  # fast after first download

        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = cache_dir / f"catalog_emb_{_fingerprint(model_name, texts)}.npy"
        if cache_file.exists():
            embeddings = np.load(cache_file)
        else:
            embeddings = _l2_normalize(model.encode(texts).astype(np.float32))
            np.save(cache_file, embeddings)

        return cls(catalog, model, embeddings)

    def embed_query(self, query: str) -> np.ndarray:
        """Embed a single query string into a unit vector in the catalog space."""
        vec = self.model.encode([query])[0].astype(np.float32)
        return _l2_normalize(vec)

    def retrieve(self, query: str, k: int = 15) -> list[Candidate]:
        """Return the top-``k`` catalog items most similar to ``query``."""
        sims = self.embeddings @ self.embed_query(query)
        top = np.argsort(-sims)[:k]  # 874 rows: full argsort is microseconds
        return [Candidate(self.catalog.items[i], float(sims[i])) for i in top]


if __name__ == "__main__":  # quick manual probe: python -m src.retriever "bujia ngk"
    import sys

    index = CatalogIndex.load_or_build()
    q = " ".join(sys.argv[1:]) or "filtro de aceite corolla 2015"
    print(f"Q: {q!r}\n")
    for c in index.retrieve(q, k=10):
        print(f"  {c.score:>6.3f}  {c.item.sku:9}  {c.item.name}")
