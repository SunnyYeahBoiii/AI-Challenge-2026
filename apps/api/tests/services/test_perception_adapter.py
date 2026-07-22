from __future__ import annotations

import json
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from app.services import perception_adapter as module
from app.services.model_registry import ModelLoadError, ModelSpec
from app.services.perception_adapter import PerceptionEmbeddingModel


class FakeTensor:
    def __init__(self, values: object) -> None:
        self.values = np.asarray(values, dtype=np.float32)

    def to(self, device: str) -> FakeTensor:
        del device
        return self

    def detach(self) -> FakeTensor:
        return self

    def float(self) -> FakeTensor:
        return self

    def cpu(self) -> FakeTensor:
        return self

    def numpy(self) -> np.ndarray:
        return self.values


class FakeTorch:
    inference_mode = nullcontext

    @staticmethod
    def stack(tensors: list[FakeTensor]) -> FakeTensor:
        return FakeTensor([tensor.values for tensor in tensors])


class FakeModel:
    def encode_text(self, tokens: FakeTensor) -> FakeTensor:
        return FakeTensor([[3.0, 4.0] for _ in tokens.values])

    def encode_image(self, images: FakeTensor) -> FakeTensor:
        return FakeTensor([[0.0, 5.0] for _ in images.values])


def _spec() -> ModelSpec:
    return ModelSpec(
        "perception-core-l14-336",
        "perception",
        "facebook/PE-Core-L14-336",
        2,
        "frames_perception",
        pretrained="timm/PE-Core-L-14-336",
        revision="commit",
        image_size=336,
        text_max_length=32,
        pretrained_sha256="a" * 64,
    )


def _runtime() -> module._PerceptionRuntime:
    return module._PerceptionRuntime(
        torch=FakeTorch(),
        model=FakeModel(),
        tokenizer=lambda texts: FakeTensor([[1.0] for _ in texts]),
        preprocess=lambda image: FakeTensor([1.0, 2.0]),
        device="cpu",
    )


def test_perception_encodes_and_normalizes(monkeypatch: Any) -> None:
    monkeypatch.setattr(module, "_create_runtime", lambda spec: _runtime())
    adapter = PerceptionEmbeddingModel(_spec())

    np.testing.assert_allclose(adapter.encode_texts(["a", "b"]), [[0.6, 0.8], [0.6, 0.8]])
    np.testing.assert_allclose(adapter.encode_images([object()]), [[0.0, 1.0]])
    assert adapter.encode_texts([]).shape == (0, 2)
    assert adapter.encode_images([]).shape == (0, 2)


def test_perception_wraps_load_failures(monkeypatch: Any) -> None:
    def fail(spec: ModelSpec) -> module._PerceptionRuntime:
        del spec
        raise RuntimeError("weights unavailable")

    monkeypatch.setattr(module, "_create_runtime", fail)
    with pytest.raises(ModelLoadError, match="cannot load Perception Encoder"):
        PerceptionEmbeddingModel(_spec())


def test_perception_rejects_wrong_output_shape(monkeypatch: Any) -> None:
    runtime = _runtime()
    runtime.model = SimpleNamespace(
        encode_text=lambda tokens: FakeTensor([[1.0, 2.0, 3.0] for _ in tokens.values]),
        encode_image=lambda images: FakeTensor([[1.0, 2.0, 3.0] for _ in images.values]),
    )
    monkeypatch.setattr(module, "_create_runtime", lambda spec: runtime)
    adapter = PerceptionEmbeddingModel(_spec())

    with pytest.raises(RuntimeError, match="returned shape"):
        adapter.encode_texts(["query"])
    with pytest.raises(RuntimeError, match="returned shape"):
        adapter.encode_images([object()])


def test_perception_reads_official_preprocess_config(tmp_path: Path) -> None:
    config_path = tmp_path / "open_clip_config.json"
    config_path.write_text(
        json.dumps(
            {
                "model_cfg": {
                    "embed_dim": 2,
                    "vision_cfg": {"image_size": 336},
                },
                "preprocess_cfg": {
                    "mean": [0.5, 0.5, 0.5],
                    "std": [0.5, 0.5, 0.5],
                    "interpolation": "bilinear",
                    "resize_mode": "squash",
                },
            }
        ),
        encoding="utf-8",
    )

    model_config, preprocess_kwargs = module._read_open_clip_config(
        config_path,
        _spec(),
    )

    assert model_config["embed_dim"] == 2
    assert preprocess_kwargs == {
        "image_mean": (0.5, 0.5, 0.5),
        "image_std": (0.5, 0.5, 0.5),
        "image_interpolation": "bilinear",
        "image_resize_mode": "squash",
    }
