from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from app.services.model_registry import EmbeddingModel, ModelRegistry, ModelSpec
from scripts import generate_retrieval_runs as module


class FakeModel(EmbeddingModel):
    def __init__(self, spec: ModelSpec, embeddings: np.ndarray) -> None:
        self.spec = spec
        self.embeddings = embeddings

    def encode_texts(self, texts: list[str]) -> np.ndarray:
        return self.embeddings[: len(texts)]

    def encode_images(self, images: list[object]) -> np.ndarray:
        return np.empty((len(images), self.spec.dimension), dtype=np.float32)


class FakeBackend:
    def search(
        self,
        spec: ModelSpec,
        embedding: list[float],
        top_k: int,
        expression: str | None = None,
    ) -> list[dict[str, object]]:
        del spec, embedding, top_k, expression
        return [{"frame_uid": "V1:00000001"}]


def _registry(embeddings: np.ndarray) -> ModelRegistry:
    spec = ModelSpec("fake", "fake", "fake", 2, "frames_fake")
    return ModelRegistry(
        [spec],
        factories={"fake": lambda model_spec: FakeModel(model_spec, embeddings)},
    )


def test_queries_normalize_and_reject_duplicate_or_empty_ids(tmp_path: Path) -> None:
    valid = tmp_path / "valid.jsonl"
    valid.write_text(
        json.dumps({"query_id": " q1 ", "text": " person walking "}) + "\n",
        encoding="utf-8",
    )
    assert module._queries(valid) == [
        {"query_id": "q1", "text": "person walking"}
    ]

    duplicate = tmp_path / "duplicate.jsonl"
    duplicate.write_text(
        "\n".join(
            [
                json.dumps({"query_id": "q1", "text": "first"}),
                json.dumps({"query_id": " q1 ", "text": "second"}),
            ]
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate query_id"):
        module._queries(duplicate)

    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="cannot be empty"):
        module._queries(empty)


@pytest.mark.parametrize(
    ("embeddings", "message"),
    [
        (np.ones((1, 2), dtype=np.float32), "returned shape"),
        (np.full((2, 2), np.nan, dtype=np.float32), "non-finite"),
    ],
)
def test_generate_runs_rejects_invalid_embedding_batches(
    monkeypatch: Any,
    embeddings: np.ndarray,
    message: str,
) -> None:
    monkeypatch.setattr(module, "get_vector_backend", lambda: FakeBackend())
    queries = [
        {"query_id": "q1", "text": "first"},
        {"query_id": "q2", "text": "second"},
    ]

    with pytest.raises(RuntimeError, match=message):
        module.generate_runs(
            queries=queries,
            registry=_registry(embeddings),
            model_ids=["fake"],
            top_k=10,
            query_batch_size=2,
        )
