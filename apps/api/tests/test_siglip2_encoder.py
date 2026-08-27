"""Unit tests for the SigLIP2 query-time encoder."""

from __future__ import annotations

import io
from types import SimpleNamespace
from typing import Any

import torch
from PIL import Image

from app.services.encoders.registry import ENCODER_REGISTRY
from app.services.encoders.siglip2 import Siglip2Encoder


class FakeProcessor:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **kwargs: Any) -> dict[str, torch.Tensor]:
        self.calls.append(kwargs)
        if "text" in kwargs:
            return {"input_ids": torch.ones((len(kwargs["text"]), 3), dtype=torch.long)}
        return {"pixel_values": torch.ones((len(kwargs["images"]), 3, 4, 4))}


class FakeModel:
    def get_text_features(self, **kwargs: Any) -> SimpleNamespace:
        rows = kwargs["input_ids"].shape[0]
        values = torch.zeros((rows, 1152))
        values[:, :2] = torch.tensor([3.0, 4.0])
        return SimpleNamespace(pooler_output=values)

    def get_image_features(self, **kwargs: Any) -> SimpleNamespace:
        rows = kwargs["pixel_values"].shape[0]
        values = torch.zeros((rows, 1152))
        values[:, :2] = torch.tensor([5.0, 12.0])
        return SimpleNamespace(pooler_output=values)


def png_bytes() -> bytes:
    image = Image.new("RGB", (2, 2), color="red")
    with io.BytesIO() as buffer:
        image.save(buffer, format="PNG")
        return buffer.getvalue()


def loaded_encoder() -> Siglip2Encoder:
    encoder = Siglip2Encoder()
    encoder._device = "cpu"
    encoder._model = FakeModel()
    encoder._processor = FakeProcessor()
    return encoder


def test_siglip2_is_registered_with_its_milvus_collection() -> None:
    assert ENCODER_REGISTRY["siglip2"] is Siglip2Encoder
    assert Siglip2Encoder.collection_name == "data_frames_siglip2"
    assert Siglip2Encoder.embedding_dim == 1152


def test_siglip2_normalizes_text_features() -> None:
    encoder = loaded_encoder()
    values = encoder.embed_text(["a red square", "another red square"])

    assert values.shape == (2, 1152)
    assert torch.allclose(torch.linalg.vector_norm(torch.from_numpy(values), dim=1), torch.ones(2))
    assert encoder._processor.calls == [
        {
            "text": ["a red square", "another red square"],
            "padding": "max_length",
            "truncation": True,
            "max_length": 64,
            "return_tensors": "pt",
        }
    ]


def test_siglip2_normalizes_image_features() -> None:
    values = loaded_encoder().embed_images([png_bytes(), png_bytes()])

    assert values.shape == (2, 1152)
    assert torch.allclose(torch.linalg.vector_norm(torch.from_numpy(values), dim=1), torch.ones(2))
