from __future__ import annotations

from typing import Any, cast

import numpy as np

from app.services.model_registry import (
    EmbeddingModel,
    FloatArray,
    ModelLoadError,
    ModelSpec,
)


class BGEVLEmbeddingModel(EmbeddingModel):
    """BGE-VL adapter with native image, text and joint image-text encoding."""

    def __init__(self, spec: ModelSpec) -> None:
        try:
            import torch
            from sentence_transformers import SentenceTransformer
        except ImportError as error:
            raise ModelLoadError(
                "BGE-VL requires the optional 'models' dependency group"
            ) from error

        self.spec = spec
        device = spec.device or ("cuda" if torch.cuda.is_available() else "cpu")
        kwargs: dict[str, object] = {
            "device": device,
            "trust_remote_code": spec.trust_remote_code,
        }
        if spec.revision:
            kwargs["revision"] = spec.revision
        try:
            self._model = SentenceTransformer(spec.model_name, **kwargs)
        except Exception as error:
            raise ModelLoadError(f"cannot load BGE-VL model {spec.model_id}: {error}") from error

    def _encode(self, inputs: list[Any]) -> FloatArray:
        if not inputs:
            return np.empty((0, self.spec.dimension), dtype=np.float32)
        features = self._model.encode(
            inputs,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        array = np.asarray(features, dtype=np.float32)
        expected_shape = (len(inputs), self.spec.dimension)
        if array.shape != expected_shape:
            raise RuntimeError(
                f"{self.spec.model_id} returned shape {array.shape}; expected {expected_shape}"
            )
        if not np.isfinite(array).all():
            raise RuntimeError(f"{self.spec.model_id} returned non-finite embeddings")
        norms = np.linalg.norm(array, axis=-1, keepdims=True)
        if np.any(norms <= 1e-12):
            raise RuntimeError(f"{self.spec.model_id} returned zero-norm embeddings")
        return cast(FloatArray, array / np.clip(norms, a_min=1e-12, a_max=None))

    def encode_texts(self, texts: list[str]) -> FloatArray:
        return self._encode(cast(list[Any], texts))

    def encode_images(self, images: list[object]) -> FloatArray:
        return self._encode(cast(list[Any], images))

    def encode_composed(
        self,
        images: list[object],
        texts: list[str],
    ) -> FloatArray | None:
        if len(images) != len(texts):
            raise ValueError("BGE-VL composed image and text batch sizes must match")
        inputs = [
            {"image": image, "text": text}
            for image, text in zip(images, texts, strict=True)
        ]
        return self._encode(inputs)
