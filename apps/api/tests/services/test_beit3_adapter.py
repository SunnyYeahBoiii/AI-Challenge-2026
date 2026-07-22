from __future__ import annotations

from contextlib import nullcontext
import hashlib
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from app.services import beit3_adapter as module
from app.services.beit3_adapter import BEiT3EmbeddingModel
from app.services.model_registry import ModelLoadError, ModelSpec


class FakeTensor:
    def __init__(self, values: object) -> None:
        self.values = np.asarray(values, dtype=np.float32)
        self.device = ""

    def to(self, device: str) -> FakeTensor:
        self.device = device
        return self

    def eq(self, value: int) -> FakeTensor:
        return FakeTensor(self.values == value)

    def detach(self) -> FakeTensor:
        return self

    def float(self) -> FakeTensor:
        return self

    def cpu(self) -> FakeTensor:
        return self

    def numpy(self) -> np.ndarray:
        return self.values


class FakeTokenizer:
    def __call__(self, texts: list[str], **kwargs: object) -> dict[str, FakeTensor]:
        assert kwargs["padding"] == "max_length"
        assert kwargs["max_length"] == 64
        return {
            "input_ids": FakeTensor([[1, 2, 0] for _ in texts]),
            "attention_mask": FakeTensor([[1, 1, 0] for _ in texts]),
        }


class FakeRetrievalModel:
    def __call__(self, **kwargs: object) -> tuple[FakeTensor | None, FakeTensor | None]:
        if "image" in kwargs:
            return FakeTensor([[0.0, 2.0]]), None
        return None, FakeTensor([[3.0, 4.0]])


def _spec(**changes: object) -> ModelSpec:
    values: dict[str, object] = {
        "model_id": "beit3",
        "adapter": "beit3",
        "model_name": "beit3_large_patch16_384_retrieval",
        "dimension": 2,
        "collection": "frames_beit3",
        "pretrained": "https://example.test/model.pth",
        "tokenizer_url": "https://example.test/beit3.spm",
        "image_size": 384,
        "text_max_length": 64,
        "pretrained_sha256": "a" * 64,
        "tokenizer_sha256": "b" * 64,
    }
    values.update(changes)
    return ModelSpec(**values)  # type: ignore[arg-type]


def test_beit3_adapter_encodes_official_text_and_image_paths(monkeypatch: Any) -> None:
    torch = SimpleNamespace(
        inference_mode=nullcontext,
        stack=lambda tensors: FakeTensor([tensor.values for tensor in tensors]),
    )
    runtime = module._BEiT3Runtime(
        torch=torch,
        model=FakeRetrievalModel(),
        tokenizer=FakeTokenizer(),
        preprocess=lambda image: FakeTensor([1.0, 2.0]),
        device="cpu",
    )
    monkeypatch.setattr(module, "_create_runtime", lambda spec: runtime)
    adapter = BEiT3EmbeddingModel(_spec())

    np.testing.assert_allclose(adapter.encode_texts(["query"]), [[0.6, 0.8]])
    np.testing.assert_allclose(adapter.encode_images([object()]), [[0.0, 1.0]])
    assert adapter.encode_texts([]).shape == (0, 2)
    assert adapter.encode_images([]).shape == (0, 2)


def test_beit3_adapter_wraps_runtime_loading_error(monkeypatch: Any) -> None:
    def fail(spec: ModelSpec) -> module._BEiT3Runtime:
        raise RuntimeError("checkpoint mismatch")

    monkeypatch.setattr(module, "_create_runtime", fail)
    with pytest.raises(ModelLoadError, match="cannot load BEiT-3"):
        BEiT3EmbeddingModel(_spec())


def test_beit3_runtime_rejects_wrong_dimension_and_missing_assets() -> None:
    with pytest.raises(ModelLoadError, match="dimension 1024"):
        module._create_runtime(_spec())
    with pytest.raises(ModelLoadError, match="requires image_size"):
        module._create_runtime(
            _spec(dimension=1024, image_size=None, tokenizer_url=None, pretrained=None)
        )


def test_beit3_tokenizer_preserves_xlm_roberta_fairseq_ids() -> None:
    class Processor:
        def encode(self, text: str, *, out_type: type[str]) -> list[str]:
            assert out_type is str
            return [] if not text else ["known", "<unk>"]

        def piece_to_id(self, piece: str) -> int:
            return 9 if piece == "known" else 0

    torch = SimpleNamespace(
        long="long",
        tensor=lambda values, dtype: np.asarray(values, dtype=np.int64),
    )
    tokenizer = module._BEiT3Tokenizer(torch, Processor())

    encoded = tokenizer(
        ["query"],
        padding="max_length",
        truncation=True,
        max_length=6,
        return_tensors="pt",
    )

    assert encoded["input_ids"].tolist() == [[0, 10, 3, 2, 1, 1]]
    assert encoded["attention_mask"].tolist() == [[1, 1, 1, 1, 0, 0]]
    with pytest.raises(ValueError, match="at least one token"):
        tokenizer(
            [""],
            padding="max_length",
            truncation=True,
            max_length=6,
            return_tensors="pt",
        )
    with pytest.raises(ValueError, match="at least 2"):
        tokenizer(
            ["query"],
            padding="max_length",
            truncation=True,
            max_length=1,
            return_tensors="pt",
        )


def test_beit3_cached_assets_are_verified(tmp_path: Path) -> None:
    checkpoints = tmp_path / "checkpoints"
    checkpoints.mkdir()
    asset = checkpoints / "asset.bin"
    asset.write_bytes(b"official")
    digest = hashlib.sha256(b"official").hexdigest()
    torch = SimpleNamespace(hub=SimpleNamespace(get_dir=lambda: str(tmp_path)))

    assert module._cache_asset(
        torch, "https://example.test/asset.bin", expected_sha256=digest
    ) == asset
    with pytest.raises(ModelLoadError, match="checksum"):
        module._cache_asset(
            torch, "https://example.test/asset.bin", expected_sha256="0" * 64
        )
