"""Tests for the embedding index and semantic retrieval.

These need the model2vec model available locally (downloaded once). If it can't
be loaded (offline / not cached), the whole module is skipped rather than failing.
"""

import numpy as np
import pytest

from src.retriever import CatalogIndex


@pytest.fixture(scope="module")
def index():
    try:
        return CatalogIndex.load_or_build()
    except Exception as exc:  # offline / model not cached
        pytest.skip(f"embedding model unavailable: {exc}")


def test_matrix_shape_aligned_with_catalog(index):
    assert index.embeddings.shape[0] == len(index.catalog) == 874
    assert index.embeddings.ndim == 2


def test_embeddings_are_unit_normalized(index):
    norms = np.linalg.norm(index.embeddings, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-5)


def test_retrieve_returns_k_sorted_candidates(index):
    cands = index.retrieve("oil filter Toyota Corolla 2015", k=10)
    assert len(cands) == 10
    scores = [c.score for c in cands]
    assert scores == sorted(scores, reverse=True)  # descending


def test_retrieve_candidates_are_catalog_items(index):
    # Each returned item must be the actual aligned catalog object.
    for c in index.retrieve("brake pads", k=5):
        assert index.catalog.by_sku[c.item.sku] is c.item


def test_cross_language_match_oil_filter(index):
    # Spanish query, English-named SKU: the right item lands in the top-k.
    skus = [c.item.sku for c in index.retrieve("filtro de aceite corolla 2015", k=15)]
    assert "SKU-1001" in skus  # Oil Filter Toyota Corolla 2015


def test_slang_match_wheel_bearing(index):
    # Regional slang ('balineras' = wheel bearings) with enough context.
    skus = [
        c.item.sku
        for c in index.retrieve("balineras ruedas de adelante logan 2014", k=15)
    ]
    assert "SKU-1030" in skus  # Rodamiento de Rueda Delantera Logan 2014


def test_cache_is_stable(index):
    # Rebuilding hits the .npy cache and yields an identical matrix.
    rebuilt = CatalogIndex.load_or_build()
    assert np.array_equal(rebuilt.embeddings, index.embeddings)
