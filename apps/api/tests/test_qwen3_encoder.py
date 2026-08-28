"""Unit tests for the Qwen3-VL-Embedding query-time encoder."""

from __future__ import annotations

import io
from types import SimpleNamespace
from typing import Any

import torch
from PIL import Image

from app.services.encoders.qwen3 import Qwen3Encoder, _Qwen3VLForEmbedding
from app.services.encoders.registry import ENCODER_REGISTRY


class FakeProcessor:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def apply_chat_template(self, conversations: Any, **kwargs: Any) -> str:
        self.batch_size = len(conversations)
        self.template_call = (conversations, kwargs)
        return "formatted conversation"

    def __call__(self, **kwargs: Any) -> dict[str, torch.Tensor]:
        self.calls.append(kwargs)
        batch_size = self.batch_size
        return {
            "input_ids": torch.ones((batch_size, 4), dtype=torch.long),
            "attention_mask": torch.tensor([[1, 1, 1, 0]], dtype=torch.long).repeat(batch_size, 1),
        }


class FakeModel:
    device = torch.device("cpu")

    def __call__(self, **kwargs: Any) -> SimpleNamespace:
        rows = kwargs["input_ids"].shape[0]
        hidden = torch.zeros((rows, 4, 2048))
        hidden[:, 2, :2] = torch.tensor([3.0, 4.0])
        return SimpleNamespace(last_hidden_state=hidden)


def png_bytes() -> bytes:
    image = Image.new("RGB", (2, 2), color="red")
    with io.BytesIO() as buffer:
        image.save(buffer, format="PNG")
        return buffer.getvalue()


def loaded_encoder() -> Qwen3Encoder:
    encoder = Qwen3Encoder()
    encoder._device = torch.device("cpu")
    encoder._model = FakeModel()
    encoder._processor = FakeProcessor()
    return encoder


def test_qwen3_is_registered_with_its_milvus_collection() -> None:
    assert ENCODER_REGISTRY["qwen3"] is Qwen3Encoder
    assert Qwen3Encoder.collection_name == "data_frames_qwen3"
    assert Qwen3Encoder.embedding_dim == 2048
    assert _Qwen3VLForEmbedding.config_class.__name__ == "Qwen3VLConfig"


def test_qwen3_normalizes_text_with_official_preprocessing_defaults(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        "app.services.encoders.qwen3._process_vision_info",
        lambda conversations: (None, None, {}),
    )
    encoder = loaded_encoder()
    values = encoder.embed_text(["a red square"])

    assert values.shape == (1, 2048)
    assert torch.allclose(torch.linalg.vector_norm(torch.from_numpy(values), dim=1), torch.ones(1))
    processor = encoder._processor
    assert processor.calls[0]["padding"] is True
    assert processor.calls[0]["max_length"] == 8192
    assert processor.calls[0]["truncation"] is True
    assert processor.calls[0]["do_resize"] is False
    user_content = processor.template_call[0][0][1]["content"]
    assert user_content == [{"type": "text", "text": "a red square"}]
    assert processor.template_call[0][0][0]["content"][0]["text"] == (
        "Represent the user's input."
    )


def test_qwen3_normalizes_image_features(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        "app.services.encoders.qwen3._process_vision_info",
        lambda conversations: ([conversations[0][1]["content"][0]["image"]], None, {}),
    )
    encoder = loaded_encoder()
    values = encoder.embed_images([png_bytes()])

    assert values.shape == (1, 2048)
    assert torch.allclose(torch.linalg.vector_norm(torch.from_numpy(values), dim=1), torch.ones(1))
    image_content = encoder._processor.template_call[0][0][1]["content"][0]
    assert image_content["min_pixels"] == 4 * 32 * 32
    assert image_content["max_pixels"] == 921600
    assert isinstance(encoder._processor.calls[0]["images"][0], Image.Image)
