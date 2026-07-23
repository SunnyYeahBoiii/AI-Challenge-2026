from __future__ import annotations

import json
import sys
from contextlib import nullcontext
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import numpy as np
import pytest

from app.services import model_registry as module
from app.services.model_registry import (
    EmbeddingModel,
    HuggingFaceEmbeddingModel,
    ModelConfigurationError,
    ModelLoadError,
    ModelRegistry,
    ModelSpec,
    OpenClipEmbeddingModel,
    _normalize,
    load_model_specs,
)


class FakeModel(EmbeddingModel):
    def __init__(self, spec: ModelSpec) -> None:
        self.spec = spec

    def encode_texts(self, texts: list[str]) -> np.ndarray:
        return np.ones((len(texts), self.spec.dimension), dtype=np.float32)

    def encode_images(self, images: list[object]) -> np.ndarray:
        return np.ones((len(images), self.spec.dimension), dtype=np.float32)


def test_load_model_specs_keeps_legacy_collection_and_optional_models(tmp_path: Path) -> None:
    config = tmp_path / "ensemble.json"
    config.write_text(
        """
        {
          "models": [
            {
              "id": "dfn5b",
              "adapter": "open_clip",
              "model_name": "ViT-H-14",
              "pretrained": "dfn5b",
              "dimension": 1024,
              "collection": "data_frames",
              "weight": 1.0,
              "enabled": true
            },
            {
              "id": "siglip2",
              "adapter": "huggingface",
              "model_name": "google/siglip2-so400m-patch14-384",
              "dimension": 1152,
              "collection": "data_frames_siglip2",
              "enabled": false
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    specs = load_model_specs(config)

    assert specs[0].collection == "data_frames"
    assert specs[0].is_enabled is True
    assert specs[1].collection == "data_frames_siglip2"
    assert specs[1].is_enabled is False


def test_registry_loads_models_lazily_and_reuses_instances() -> None:
    spec = ModelSpec(
        model_id="fake",
        adapter="fake",
        model_name="fake/model",
        dimension=2,
        collection="data_frames_fake",
    )
    calls: list[str] = []

    def factory(model_spec: ModelSpec) -> EmbeddingModel:
        calls.append(model_spec.model_id)
        return FakeModel(model_spec)

    registry = ModelRegistry([spec], factories={"fake": factory})

    first = registry.get("fake")
    second = registry.get("fake")

    assert first is second
    assert calls == ["fake"]
    assert registry.enabled_specs() == [spec]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"model_id": ""}, "required"),
        ({"dimension": 0}, "positive"),
        ({"collection": ""}, "collection"),
        ({"weight": -1.0}, "negative"),
        ({"weight": float("nan")}, "finite"),
        ({"text_padding": "invalid"}, "text_padding"),
        ({"text_max_length": 0}, "text_max_length"),
        ({"image_size": 0}, "image_size"),
        ({"dtype": "float8"}, "dtype"),
        ({"pretrained_sha256": "invalid"}, "pretrained_sha256"),
    ],
)
def test_model_spec_rejects_invalid_configuration(
    kwargs: dict[str, object], message: str
) -> None:
    values: dict[str, object] = {
        "model_id": "fake",
        "adapter": "fake",
        "model_name": "fake/model",
        "dimension": 2,
        "collection": "frames_fake",
    }
    values.update(kwargs)
    with pytest.raises(ModelConfigurationError, match=message):
        ModelSpec(**values)  # type: ignore[arg-type]


def test_registry_selection_and_configuration_errors() -> None:
    enabled = ModelSpec("a", "fake", "a", 2, "a")
    disabled = ModelSpec("b", "fake", "b", 2, "b", is_enabled=False)
    registry = ModelRegistry([enabled, disabled], factories={"fake": FakeModel})

    assert registry.enabled_specs(("a",)) == [enabled]
    with pytest.raises(ModelConfigurationError, match="disabled"):
        registry.enabled_specs(("b",))
    with pytest.raises(ModelConfigurationError, match="unique"):
        registry.enabled_specs(("a", "a"))
    with pytest.raises(ModelConfigurationError, match="unknown model"):
        registry.spec("missing")
    with pytest.raises(ModelConfigurationError, match="adapter"):
        ModelRegistry([ModelSpec("x", "missing", "x", 2, "x")]).get("x")
    with pytest.raises(ModelConfigurationError, match="unique"):
        ModelRegistry([enabled, enabled])


def test_top2_embedding_specs_are_versioned() -> None:
    config = Path(__file__).resolve().parents[2] / "config" / "ensemble.json"

    specs = {spec.model_id: spec for spec in load_model_specs(config)}

    beit3 = specs["beit3-large-coco-retrieval-384"]
    assert beit3.adapter == "beit3"
    assert beit3.dimension == 1024
    assert beit3.image_size == 384
    assert beit3.text_max_length == 64
    assert beit3.pretrained == (
        "https://github.com/addf400/files/releases/download/beit3/"
        "beit3_large_patch16_384_coco_retrieval.pth"
    )
    assert beit3.tokenizer_url == (
        "https://github.com/addf400/files/releases/download/beit3/beit3.spm"
    )
    assert beit3.pretrained_sha256 == (
        "72a569be8a4c5396d82f7a4eab9dd3c9d6f11af731e9d86227450cde02a2fddb"
    )
    assert beit3.tokenizer_sha256 == (
        "6f5e2fefcf793761a76a6bfb8ad35489f9c203b25557673284b6d032f41043f4"
    )

    bge = specs["bge-vl-large"]
    assert bge.adapter == "bge_vl"
    assert bge.model_name == "BAAI/BGE-VL-large"
    assert bge.dimension == 768
    assert bge.revision == "40fb48217f521df22a2a5bf15edd52ed1146ef05"
    assert bge.trust_remote_code is True

    perception = specs["perception-core-l14-336"]
    assert perception.adapter == "perception"
    assert perception.model_name == "facebook/PE-Core-L14-336"
    assert perception.pretrained == "timm/PE-Core-L-14-336"
    assert perception.dimension == 1024
    assert perception.image_size == 336
    assert perception.text_max_length == 32
    assert perception.revision == "8eff41b3f687e50a323662c2dda5eb3588c6dd35"
    assert perception.pretrained_sha256 == (
        "b1fff7093c32a01d98a2d82098f9adf788b30f0efee639916520b3e4302f786b"
    )

    metaclip = specs["metaclip2-worldwide-huge"]
    assert metaclip.dtype == "float16"


def test_registry_contains_top2_builtin_factories() -> None:
    registry = ModelRegistry([ModelSpec("x", "fake", "x", 2, "x")])

    assert {"beit3", "bge_vl", "perception"} <= set(registry._factories)


def test_load_model_specs_reports_malformed_and_disabled_configs(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    with pytest.raises(ModelConfigurationError, match="cannot read"):
        load_model_specs(missing)

    empty = tmp_path / "empty.json"
    empty.write_text(json.dumps({"models": []}), encoding="utf-8")
    with pytest.raises(ModelConfigurationError, match="non-empty"):
        load_model_specs(empty)

    disabled = tmp_path / "disabled.json"
    disabled.write_text(
        json.dumps(
            {
                "models": [
                    {
                        "id": "x",
                        "adapter": "fake",
                        "model_name": "x",
                        "dimension": 2,
                        "collection": "x",
                        "enabled": False,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ModelConfigurationError, match="one model"):
        load_model_specs(disabled)

    invalid_type = tmp_path / "invalid-type.json"
    invalid_type.write_text(
        json.dumps(
            {
                "models": [
                    {
                        "id": "x",
                        "adapter": "fake",
                        "model_name": "x",
                        "dimension": [],
                        "collection": "x",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ModelConfigurationError, match="integer"):
        load_model_specs(invalid_type)

    missing_field = tmp_path / "missing-field.json"
    missing_field.write_text(json.dumps({"models": [{"id": "x"}]}), encoding="utf-8")
    with pytest.raises(ModelConfigurationError, match="invalid model entry"):
        load_model_specs(missing_field)

    duplicate = tmp_path / "duplicate.json"
    model = {
        "id": "x",
        "adapter": "fake",
        "model_name": "x",
        "dimension": 2,
        "collection": "x",
    }
    duplicate.write_text(json.dumps({"models": [model, model]}), encoding="utf-8")
    with pytest.raises(ModelConfigurationError, match="unique"):
        load_model_specs(duplicate)

    string_boolean = tmp_path / "string-boolean.json"
    string_boolean.write_text(
        json.dumps({"models": [{**model, "enabled": "false"}]}),
        encoding="utf-8",
    )
    with pytest.raises(ModelConfigurationError, match="enabled must be boolean"):
        load_model_specs(string_boolean)


class FakeTensor:
    def __init__(self, values: object) -> None:
        self.values = np.asarray(values, dtype=np.float32)
        self.device: str | None = None

    def to(self, device: str) -> FakeTensor:
        self.device = device
        return self

    def detach(self) -> FakeTensor:
        return self

    def float(self) -> FakeTensor:
        return self

    def cpu(self) -> FakeTensor:
        return self

    def numpy(self) -> np.ndarray:
        return self.values


class FakeDualEncoder:
    def __init__(self) -> None:
        self.device = ""

    def to(self, device: str) -> FakeDualEncoder:
        self.device = device
        return self

    def eval(self) -> FakeDualEncoder:
        return self

    def encode_text(self, tokens: FakeTensor) -> FakeTensor:
        return FakeTensor([[3.0, 4.0] for _ in tokens.values])

    def encode_image(self, batch: FakeTensor) -> FakeTensor:
        return FakeTensor([[0.0, 2.0] for _ in batch.values])

    def get_text_features(self, **inputs: Any) -> SimpleNamespace:
        return SimpleNamespace(pooler_output=FakeTensor([[3.0, 4.0]]))

    def get_image_features(self, **inputs: Any) -> tuple[FakeTensor]:
        return (FakeTensor([[0.0, 5.0]]),)


def _fake_torch() -> ModuleType:
    torch = ModuleType("torch")
    setattr(torch, "float16", "fake-float16")
    setattr(torch, "cuda", SimpleNamespace(is_available=lambda: False, empty_cache=lambda: None))
    setattr(torch, "inference_mode", nullcontext)
    setattr(torch, "stack", lambda tensors: FakeTensor([tensor.values for tensor in tensors]))
    return torch


def test_openclip_adapter_encodes_and_normalizes(monkeypatch: Any) -> None:
    model = FakeDualEncoder()
    open_clip = ModuleType("open_clip")
    setattr(
        open_clip,
        "create_model_and_transforms",
        lambda *args, **kwargs: (model, None, lambda image: FakeTensor([1.0, 2.0])),
    )
    setattr(
        open_clip,
        "get_tokenizer",
        lambda name: lambda texts: FakeTensor([[1.0] for _ in texts]),
    )
    monkeypatch.setitem(sys.modules, "torch", _fake_torch())
    monkeypatch.setitem(sys.modules, "open_clip", open_clip)
    spec = ModelSpec("open", "open_clip", "ViT", 2, "open", pretrained="weights")

    adapter = OpenClipEmbeddingModel(spec)

    np.testing.assert_allclose(adapter.encode_texts(["a", "b"]), [[0.6, 0.8], [0.6, 0.8]])
    np.testing.assert_allclose(adapter.encode_images([object()]), [[0.0, 1.0]])
    assert adapter.encode_texts([]).shape == (0, 2)
    assert adapter.encode_images([]).shape == (0, 2)
    assert model.device == "cpu"


@pytest.mark.parametrize(
    "values",
    [
        [[0.0, 0.0]],
        [[float("nan"), 1.0]],
        [[float("inf"), 1.0]],
    ],
)
def test_normalize_rejects_invalid_features(values: list[list[float]]) -> None:
    with pytest.raises(RuntimeError, match="non-finite|zero-norm"):
        _normalize(FakeTensor(values))


def test_model_adapters_wrap_load_failures(monkeypatch: Any) -> None:
    open_clip = ModuleType("open_clip")
    setattr(
        open_clip,
        "create_model_and_transforms",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("bad weights")),
    )
    monkeypatch.setitem(sys.modules, "torch", _fake_torch())
    monkeypatch.setitem(sys.modules, "open_clip", open_clip)
    spec = ModelSpec("open", "open_clip", "ViT", 2, "open")

    with pytest.raises(ModelLoadError, match="cannot load"):
        OpenClipEmbeddingModel(spec)


def test_huggingface_adapter_passes_padding_revision_and_normalizes(monkeypatch: Any) -> None:
    calls: dict[str, Any] = {}
    encoder = FakeDualEncoder()

    class Processor:
        @staticmethod
        def from_pretrained(name: str, **kwargs: Any) -> Processor:
            calls["processor_load"] = (name, kwargs)
            return Processor()

        def __call__(self, **kwargs: Any) -> dict[str, FakeTensor]:
            calls["processor_call"] = kwargs
            return {"input": FakeTensor([[1.0]])}

    class AutoModel:
        @staticmethod
        def from_pretrained(name: str, **kwargs: Any) -> FakeDualEncoder:
            calls["model_load"] = (name, kwargs)
            return encoder

    transformers = ModuleType("transformers")
    setattr(transformers, "AutoProcessor", Processor)
    setattr(transformers, "AutoModel", AutoModel)
    monkeypatch.setitem(sys.modules, "torch", _fake_torch())
    monkeypatch.setitem(sys.modules, "transformers", transformers)
    spec = ModelSpec(
        "hf",
        "huggingface",
        "hf/model",
        2,
        "hf",
        revision="commit",
        dtype="float16",
        text_padding="max_length",
        text_max_length=64,
    )

    adapter = HuggingFaceEmbeddingModel(spec)

    np.testing.assert_allclose(adapter.encode_texts(["query"]), [[0.6, 0.8]])
    assert calls["processor_load"][1]["revision"] == "commit"
    assert "dtype" not in calls["processor_load"][1]
    assert calls["model_load"][1]["dtype"] == "fake-float16"
    assert calls["processor_call"]["max_length"] == 64
    np.testing.assert_allclose(adapter.encode_images([object()]), [[0.0, 1.0]])
    assert adapter.encode_texts([]).shape == (0, 2)
    assert adapter.encode_images([]).shape == (0, 2)


def test_registry_global_cache_and_unload(tmp_path: Path, monkeypatch: Any) -> None:
    config = tmp_path / "ensemble.json"
    config.write_text(
        json.dumps(
            {
                "models": [
                    {
                        "id": "x",
                        "adapter": "fake",
                        "model_name": "x",
                        "dimension": 2,
                        "collection": "x",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("ENSEMBLE_CONFIG_PATH", str(config))
    module.reset_model_registry()
    registry = module.get_model_registry()
    assert module.get_model_registry() is registry
    registry._factories["fake"] = FakeModel
    registry.get("x")
    registry.unload("x")
    registry.unload("x")
    assert registry._models == {}
    module.reset_model_registry()
