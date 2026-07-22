from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace
from typing import Any

import numpy as np
import pytest

from app.services.bge_vl_adapter import BGEVLEmbeddingModel
from app.services.model_registry import ModelLoadError, ModelSpec


def _spec() -> ModelSpec:
    return ModelSpec(
        "bge-vl-large",
        "bge_vl",
        "BAAI/BGE-VL-large",
        2,
        "frames_bge",
        revision="commit",
        trust_remote_code=True,
    )


def test_bge_vl_encodes_text_image_and_native_composed(monkeypatch: Any) -> None:
    calls: dict[str, Any] = {"encoded": []}

    class SentenceTransformer:
        def __init__(self, model_name: str, **kwargs: object) -> None:
            calls["load"] = (model_name, kwargs)

        def encode(self, inputs: list[object], **kwargs: object) -> np.ndarray:
            calls["encoded"].append((inputs, kwargs))
            return np.asarray([[3.0, 4.0] for _ in inputs], dtype=np.float32)

    sentence_transformers = ModuleType("sentence_transformers")
    setattr(sentence_transformers, "SentenceTransformer", SentenceTransformer)
    torch = ModuleType("torch")
    setattr(torch, "cuda", SimpleNamespace(is_available=lambda: False))
    monkeypatch.setitem(sys.modules, "sentence_transformers", sentence_transformers)
    monkeypatch.setitem(sys.modules, "torch", torch)

    adapter = BGEVLEmbeddingModel(_spec())

    np.testing.assert_allclose(adapter.encode_texts(["a", "b"]), [[0.6, 0.8], [0.6, 0.8]])
    image = object()
    np.testing.assert_allclose(adapter.encode_images([image]), [[0.6, 0.8]])
    composed = adapter.encode_composed([image], ["change"])
    assert composed is not None
    np.testing.assert_allclose(composed, np.asarray([[0.6, 0.8]], dtype=np.float32))
    assert calls["load"] == (
        "BAAI/BGE-VL-large",
        {"device": "cpu", "trust_remote_code": True, "revision": "commit"},
    )
    assert calls["encoded"][2][0] == [{"image": image, "text": "change"}]
    assert calls["encoded"][2][1]["normalize_embeddings"] is True


def test_bge_vl_validates_batches_shapes_and_loading(monkeypatch: Any) -> None:
    class WrongShapeSentenceTransformer:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def encode(self, inputs: list[object], **kwargs: object) -> np.ndarray:
            return np.ones((len(inputs), 3), dtype=np.float32)

    sentence_transformers = ModuleType("sentence_transformers")
    setattr(sentence_transformers, "SentenceTransformer", WrongShapeSentenceTransformer)
    torch = ModuleType("torch")
    setattr(torch, "cuda", SimpleNamespace(is_available=lambda: False))
    monkeypatch.setitem(sys.modules, "sentence_transformers", sentence_transformers)
    monkeypatch.setitem(sys.modules, "torch", torch)
    adapter = BGEVLEmbeddingModel(_spec())

    assert adapter.encode_texts([]).shape == (0, 2)
    with pytest.raises(ValueError, match="batch sizes"):
        adapter.encode_composed([object()], [])
    with pytest.raises(RuntimeError, match="returned shape"):
        adapter.encode_texts(["query"])

    class ZeroSentenceTransformer(WrongShapeSentenceTransformer):
        def encode(self, inputs: list[object], **kwargs: object) -> np.ndarray:
            return np.zeros((len(inputs), 2), dtype=np.float32)

    setattr(sentence_transformers, "SentenceTransformer", ZeroSentenceTransformer)
    zero_adapter = BGEVLEmbeddingModel(_spec())
    with pytest.raises(RuntimeError, match="zero-norm"):
        zero_adapter.encode_texts(["query"])

    class BrokenSentenceTransformer:
        def __init__(self, *args: object, **kwargs: object) -> None:
            raise RuntimeError("weights unavailable")

    setattr(sentence_transformers, "SentenceTransformer", BrokenSentenceTransformer)
    with pytest.raises(ModelLoadError, match="cannot load BGE-VL"):
        BGEVLEmbeddingModel(_spec())
