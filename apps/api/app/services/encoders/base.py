import abc
from typing import Any

import numpy as np
import numpy.typing as npt
import torch

Embeddings = npt.NDArray[np.float32]


class Encoder(abc.ABC):
    """One query-time embedding backend.

    Exactly one `Encoder` is loaded at a time — see `app.services.encoders.manager`,
    which owns the swap lock and never holds two encoders' weights at once. Each
    concrete encoder also declares the Milvus collection its embeddings belong in and
    their dimension, so a model swap does not implicitly search another model's index.
    """

    model_id: str
    collection_name: str
    embedding_dim: int

    @abc.abstractmethod
    def load(self) -> None:
        """Load weights onto the device. Called at most once per swap-in."""

    @abc.abstractmethod
    def unload(self) -> None:
        """Release weights and free device memory. Called before any subsequent load."""

    @abc.abstractmethod
    def embed_text(self, texts: list[str]) -> Embeddings:
        """Encode a batch of texts in one forward pass, L2-normalized."""

    @abc.abstractmethod
    def embed_image(self, image_bytes: bytes) -> Embeddings:
        """Encode one image, L2-normalized."""

    @abc.abstractmethod
    def embed_images(self, images: list[bytes]) -> Embeddings:
        """Encode a batch of images in one forward pass, L2-normalized."""

    def calibrate_text_similarity(self, similarity: float) -> float | None:
        """Return a model-specific display confidence for text-to-image similarity."""
        del similarity
        return None


def to_numpy(features: Any) -> Embeddings:
    array: Embeddings = features.detach().to(torch.float32).cpu().numpy()
    return array
