from __future__ import annotations

import io
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
from PIL import Image

from app.services import embed as module


class FakeModel:
    def encode_texts(self, texts: list[str]) -> np.ndarray:
        return np.ones((len(texts), 2), dtype=np.float32)

    def encode_images(self, images: list[object]) -> np.ndarray:
        return np.asarray([[0.25, 0.75]], dtype=np.float32)


class FakeRegistry:
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self.model = FakeModel()

    def enabled_specs(self) -> list[object]:
        return [SimpleNamespace(model_id="fake")] if self.enabled else []

    def get(self, model_id: str) -> FakeModel:
        assert model_id == "fake"
        return self.model


def _png_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (2, 2), (255, 0, 0)).save(output, format="PNG")
    return output.getvalue()


def test_embedding_helpers_select_model_and_decode_rgb(monkeypatch: Any) -> None:
    registry = FakeRegistry()
    monkeypatch.setattr(module, "get_model_registry", lambda: registry)

    assert module.embed_text(["q"]).shape == (1, 2)
    assert module.embed_text(["q"], "fake").shape == (1, 2)
    assert module.embed_image(_png_bytes()).tolist() == [0.25, 0.75]
    assert module.decode_image(_png_bytes()).mode == "RGB"


def test_embedding_helpers_reject_missing_model_and_bad_image(monkeypatch: Any) -> None:
    monkeypatch.setattr(module, "get_model_registry", lambda: FakeRegistry(enabled=False))
    with pytest.raises(RuntimeError, match="no embedding"):
        module.embed_text(["q"])
    with pytest.raises(ValueError, match="invalid image"):
        module.decode_image(b"not-an-image")


def test_query_enhancement_fallback_success_and_error(monkeypatch: Any) -> None:
    module._client = None
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert module.enhance_query("xin chao") == "xin chao"

    class Responses:
        def __init__(self, output: str = "enhanced", error: bool = False) -> None:
            self.output = output
            self.error = error

        def create(self, **kwargs: Any) -> object:
            if self.error:
                raise RuntimeError("offline")
            return SimpleNamespace(output_text=self.output)

    module._client = SimpleNamespace(responses=Responses("enhanced"))
    monkeypatch.setenv("OPENAI_API_KEY", "key")
    assert module.enhance_query("raw") == "enhanced"
    module._client = SimpleNamespace(responses=Responses("", error=False))
    assert module.enhance_query("raw") == "raw"
    module._client = SimpleNamespace(responses=Responses(error=True))
    assert module.enhance_query("raw") == "raw"
    module._client = None

