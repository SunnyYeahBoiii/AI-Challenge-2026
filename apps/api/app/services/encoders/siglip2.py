import io
from typing import Any

import numpy as np
import torch
import torch.nn.functional as functional
from PIL import Image
from transformers import AutoModel, AutoProcessor

from app.services.encoders.base import Embeddings, Encoder, to_numpy

_MODEL_ID = "google/siglip2-so400m-patch14-384"
_TEXT_MAX_LENGTH = 64


class Siglip2Encoder(Encoder):
    """SigLIP2 text/image encoder aligned with the 1152-dim Batch-1 artifact."""

    model_id = "siglip2"
    collection_name = "data_frames_siglip2"
    embedding_dim = 1152

    def __init__(self) -> None:
        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        self._dtype = torch.float16 if self._device == "cuda" else torch.float32
        self._model: Any = None
        self._processor: Any = None

    def load(self) -> None:
        self._processor = AutoProcessor.from_pretrained(  # type: ignore[no-untyped-call]
            _MODEL_ID,
            use_fast=False,
        )
        self._model = AutoModel.from_pretrained(_MODEL_ID, dtype=self._dtype).to(self._device).eval()

    def unload(self) -> None:
        self._model = None
        self._processor = None
        if self._device == "cuda":
            torch.cuda.empty_cache()

    def embed_text(self, texts: list[str]) -> Embeddings:
        if not texts:
            return np.zeros((0, self.embedding_dim), dtype=np.float32)
        model, processor = self._loaded_components()
        inputs = processor(
            text=texts,
            padding="max_length",
            truncation=True,
            max_length=_TEXT_MAX_LENGTH,
            return_tensors="pt",
        )
        with torch.inference_mode():
            outputs = model.get_text_features(**self._to_device(inputs))
        return to_numpy(self._normalized_pooler_output(outputs))

    def embed_image(self, image_bytes: bytes) -> Embeddings:
        embedding: Embeddings = self.embed_images([image_bytes])[0]
        return embedding

    def embed_images(self, images: list[bytes]) -> Embeddings:
        if not images:
            return np.zeros((0, self.embedding_dim), dtype=np.float32)
        model, processor = self._loaded_components()
        pil_images = [self._decode_image(image_bytes) for image_bytes in images]
        inputs = processor(images=pil_images, return_tensors="pt")
        with torch.inference_mode():
            outputs = model.get_image_features(**self._to_device(inputs))
        return to_numpy(self._normalized_pooler_output(outputs))

    def _loaded_components(self) -> tuple[Any, Any]:
        if self._model is None or self._processor is None:
            raise RuntimeError("SigLIP2 encoder is not loaded")
        return self._model, self._processor

    def _to_device(self, inputs: dict[str, Any]) -> dict[str, Any]:
        return {
            name: value.to(self._device, non_blocking=True) if hasattr(value, "to") else value
            for name, value in inputs.items()
        }

    @staticmethod
    def _decode_image(image_bytes: bytes) -> Image.Image:
        with Image.open(io.BytesIO(image_bytes)) as image:
            return image.convert("RGB")

    @staticmethod
    def _normalized_pooler_output(outputs: Any) -> torch.Tensor:
        features = getattr(outputs, "pooler_output", outputs)
        if not isinstance(features, torch.Tensor):
            raise ValueError("SigLIP2 did not return a tensor pooler_output")
        if features.ndim != 2 or features.shape[1] != Siglip2Encoder.embedding_dim:
            raise ValueError(f"Unexpected SigLIP2 embedding shape: {tuple(features.shape)}")
        return functional.normalize(features.float(), p=2, dim=-1)
