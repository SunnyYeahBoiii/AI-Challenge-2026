"""Tests for reduced-precision MetaCLIP loading and inference inputs."""

import io
from typing import Any

import numpy as np
import torch
from PIL import Image

from app.services.encoders import metaclip
from app.services.encoders.metaclip import MetaClipEncoder


class FakeModel:
    def eval(self) -> "FakeModel":
        return self


def test_cpu_loader_requests_bf16_from_open_clip(monkeypatch: Any) -> None:
    calls: dict[str, object] = {}
    fake_model = FakeModel()

    monkeypatch.setattr(metaclip.torch.cuda, "is_available", lambda: False)

    def fake_create(*args: object, **kwargs: object) -> tuple[FakeModel, None, str]:
        calls["args"] = args
        calls["kwargs"] = kwargs
        return fake_model, None, "preprocess"

    monkeypatch.setattr(metaclip.open_clip, "create_model_and_transforms", fake_create)
    monkeypatch.setattr(metaclip.open_clip, "get_tokenizer", lambda _arch: "tokenizer")

    encoder = MetaClipEncoder()
    encoder.load()

    kwargs = calls["kwargs"]
    assert isinstance(kwargs, dict)
    assert kwargs["precision"] == "bf16"
    assert kwargs["device"] == "cpu"
    assert encoder._model is fake_model


def test_image_input_matches_cpu_model_dtype() -> None:
    seen: dict[str, torch.dtype] = {}

    class ImageModel:
        def encode_image(self, batch: torch.Tensor) -> torch.Tensor:
            seen["dtype"] = batch.dtype
            return torch.ones((len(batch), MetaClipEncoder.embedding_dim), dtype=batch.dtype)

    encoder = MetaClipEncoder()
    encoder._model = ImageModel()
    encoder._preprocess = lambda _image: torch.ones((3, 2, 2), dtype=torch.float32)
    image_bytes = io.BytesIO()
    Image.new("RGB", (2, 2)).save(image_bytes, format="PNG")

    result = encoder.embed_image(image_bytes.getvalue())

    assert seen["dtype"] == torch.bfloat16
    assert result.dtype == np.float32
