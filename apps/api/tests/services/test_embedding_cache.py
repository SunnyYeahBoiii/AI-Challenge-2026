from __future__ import annotations

import numpy as np
import pytest

from app.services.embedding_cache import TextEmbeddingCache


def test_text_embedding_cache_reuses_and_isolates_cached_arrays() -> None:
    cache = TextEmbeddingCache(max_entries=2)
    calls = 0

    def compute() -> np.ndarray:
        nonlocal calls
        calls += 1
        return np.asarray([[1.0, 2.0]], dtype=np.float32)

    first = cache.get_or_compute("model", ["query"], compute)
    first[0, 0] = 99.0
    second = cache.get_or_compute("model", ["query"], compute)

    assert calls == 1
    assert second.tolist() == [[1.0, 2.0]]


def test_cache_rejects_invalid_size_evicts_lru_and_clears() -> None:
    with pytest.raises(ValueError, match="positive"):
        TextEmbeddingCache(0)
    cache = TextEmbeddingCache(2)
    calls: list[str] = []

    def compute(label: str) -> np.ndarray:
        calls.append(label)
        return np.asarray([[1.0]], dtype=np.float64)

    cache.get_or_compute("a", ["x"], lambda: compute("a:x"))
    cache.get_or_compute("b", ["x"], lambda: compute("b:x"))
    cache.get_or_compute("a", ["y"], lambda: compute("a:y"))
    value = cache.get_or_compute("a", ["x"], lambda: compute("a:x-again"))
    assert value.dtype == np.float32
    assert calls == ["a:x", "b:x", "a:y", "a:x-again"]
    cache.clear()
    cache.get_or_compute("a", ["x"], lambda: compute("after-clear"))
    assert calls[-1] == "after-clear"
