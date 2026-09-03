"""SigLIP2 query encoder matching the supplied SO400M 384px archive."""

import io
import math
from typing import Any, cast

import numpy as np
import torch
from PIL import Image
from transformers import AutoModel, AutoProcessor

from app.config import Config
from app.services.encoders.base import Embeddings, Encoder, to_numpy


class Siglip2Encoder(Encoder):
    model_id = "siglip2"
    collection_name = Config.SIGLIP2_COLLECTION
    embedding_dim = 1152

    def __init__(self) -> None:
        self._device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self._model: Any = None
        self._processor: Any = None
        self._text_logit_scale: float | None = None
        self._text_logit_bias: float | None = None

    def load(self) -> None:
        self._processor = AutoProcessor.from_pretrained(  # type: ignore[no-untyped-call]
            Config.SIGLIP2_MODEL_ID,
            revision=Config.SIGLIP2_REVISION,
            use_fast=False,
        )
        self._model = AutoModel.from_pretrained(
            Config.SIGLIP2_MODEL_ID,
            revision=Config.SIGLIP2_REVISION,
        ).to(self._device).eval()
        self._text_logit_scale = math.exp(float(self._model.logit_scale.detach().cpu().item()))
        self._text_logit_bias = float(self._model.logit_bias.detach().cpu().item())

    def unload(self) -> None:
        self._model = None
        self._processor = None
        self._text_logit_scale = None
        self._text_logit_bias = None
        if self._device.type == "cuda":
            torch.cuda.empty_cache()

    def _features_to_embeddings(self, features: torch.Tensor) -> Embeddings:
        normalized = features / features.norm(dim=-1, keepdim=True).clamp_min(
            torch.finfo(features.dtype).eps
        )
        return to_numpy(normalized)

    def _to_device(self, inputs: dict[str, torch.Tensor]) -> dict[str, torch.Tensor]:
        return {name: value.to(self._device) for name, value in inputs.items()}

    def embed_text(self, texts: list[str]) -> Embeddings:
        if not texts:
            return np.zeros((0, self.embedding_dim), dtype=np.float32)
        assert self._model is not None and self._processor is not None
        inputs = cast(
            dict[str, torch.Tensor],
            self._processor(
                text=texts,
                padding="max_length",
                truncation=True,
                max_length=64,
                return_tensors="pt",
            ),
        )
        with torch.inference_mode():
            features = cast(torch.Tensor, self._model.get_text_features(**self._to_device(inputs)))
        return self._features_to_embeddings(features)

    def embed_image(self, image_bytes: bytes) -> Embeddings:
        return cast(Embeddings, self.embed_images([image_bytes])[0])

    def embed_images(self, images: list[bytes]) -> Embeddings:
        if not images:
            return np.zeros((0, self.embedding_dim), dtype=np.float32)
        assert self._model is not None and self._processor is not None
        rgb_images = [Image.open(io.BytesIO(image)).convert("RGB") for image in images]
        inputs = cast(dict[str, torch.Tensor], self._processor(images=rgb_images, return_tensors="pt"))
        with torch.inference_mode():
            features = cast(torch.Tensor, self._model.get_image_features(**self._to_device(inputs)))
        return self._features_to_embeddings(features)

    def calibrate_text_similarity(self, similarity: float) -> float | None:
        """Map raw text-image cosine to SigLIP2's learned sigmoid confidence."""
        if (
            self._text_logit_scale is None
            or self._text_logit_bias is None
            or not math.isfinite(similarity)
        ):
            return None
        logit = self._text_logit_scale * similarity + self._text_logit_bias
        if logit >= 0:
            return 1.0 / (1.0 + math.exp(-logit))
        exp_logit = math.exp(logit)
        return exp_logit / (1.0 + exp_logit)
