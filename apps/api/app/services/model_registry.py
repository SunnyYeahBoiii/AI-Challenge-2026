from __future__ import annotations

import json
import os
import gc
import math
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any, TypeAlias, cast

import numpy as np
from numpy.typing import NDArray

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "ensemble.json"
FloatArray: TypeAlias = NDArray[np.float32]


class ModelConfigurationError(ValueError):
    """Raised when an embedding model configuration is invalid."""


class ModelLoadError(RuntimeError):
    """Raised when an embedding model cannot be loaded."""


@dataclass(frozen=True)
class ModelSpec:
    """Versioned configuration for one image-text embedding model."""

    model_id: str
    adapter: str
    model_name: str
    dimension: int
    collection: str
    pretrained: str | None = None
    weight: float = 1.0
    is_enabled: bool = True
    device: str | None = None
    revision: str | None = None
    trust_remote_code: bool = False
    text_padding: str = "longest"
    text_max_length: int | None = None

    def __post_init__(self) -> None:
        if not self.model_id or not self.adapter or not self.model_name:
            raise ModelConfigurationError("model id, adapter and model_name are required")
        if self.dimension < 1:
            raise ModelConfigurationError("model dimension must be positive")
        if not self.collection:
            raise ModelConfigurationError("model collection is required")
        if self.weight < 0:
            raise ModelConfigurationError("model weight cannot be negative")
        if not math.isfinite(self.weight):
            raise ModelConfigurationError("model weight must be finite")
        if self.text_padding not in {"longest", "max_length"}:
            raise ModelConfigurationError("text_padding must be longest or max_length")
        if self.text_max_length is not None and self.text_max_length < 1:
            raise ModelConfigurationError("text_max_length must be positive")


class EmbeddingModel(ABC):
    """Adapter interface shared by all dual-encoder embedding models."""

    spec: ModelSpec

    @abstractmethod
    def encode_texts(self, texts: list[str]) -> FloatArray:
        """Encode and L2-normalize text inputs."""

    @abstractmethod
    def encode_images(self, images: list[object]) -> FloatArray:
        """Encode and L2-normalize PIL image inputs."""


def _normalize(features: Any) -> FloatArray:
    array = features.detach().float().cpu().numpy().astype(np.float32)
    norms = np.linalg.norm(array, axis=-1, keepdims=True)
    normalized = array / np.clip(norms, a_min=1e-12, a_max=None)
    return cast(FloatArray, normalized)


class OpenClipEmbeddingModel(EmbeddingModel):
    """OpenCLIP adapter used by the existing DFN5B baseline and MetaCLIP variants."""

    def __init__(self, spec: ModelSpec) -> None:
        import open_clip
        import torch

        self.spec = spec
        self._torch = torch
        self._device = spec.device or ("cuda" if torch.cuda.is_available() else "cpu")
        try:
            model, _, preprocess = open_clip.create_model_and_transforms(
                spec.model_name,
                pretrained=spec.pretrained,
            )
            tokenizer = open_clip.get_tokenizer(spec.model_name)
        except Exception as error:
            raise ModelLoadError(f"cannot load OpenCLIP model {spec.model_id}: {error}") from error
        self._model = model.to(self._device).eval()
        self._preprocess = preprocess
        self._tokenizer = tokenizer

    def encode_texts(self, texts: list[str]) -> FloatArray:
        tokens = self._tokenizer(texts).to(self._device)
        with self._torch.inference_mode():
            features = self._model.encode_text(tokens)
        return _normalize(features)

    def encode_images(self, images: list[object]) -> FloatArray:
        batch = self._torch.stack([self._preprocess(image) for image in images]).to(self._device)
        with self._torch.inference_mode():
            features = self._model.encode_image(batch)
        return _normalize(features)


def _feature_tensor(features: Any) -> Any:
    if hasattr(features, "pooler_output"):
        return features.pooler_output
    if isinstance(features, tuple):
        return features[0]
    return features


class HuggingFaceEmbeddingModel(EmbeddingModel):
    """Transformers adapter for SigLIP2, MetaCLIP2 and compatible dual encoders."""

    def __init__(self, spec: ModelSpec) -> None:
        import torch

        try:
            from transformers import AutoModel, AutoProcessor
        except ImportError as error:
            raise ModelLoadError(
                "Hugging Face models require the optional 'models' dependency group"
            ) from error

        self.spec = spec
        self._torch = torch
        self._device = spec.device or ("cuda" if torch.cuda.is_available() else "cpu")
        kwargs: dict[str, object] = {"trust_remote_code": spec.trust_remote_code}
        if spec.revision:
            kwargs["revision"] = spec.revision
        try:
            load_processor = cast(Callable[..., Any], AutoProcessor.from_pretrained)
            self._processor = load_processor(spec.model_name, **kwargs)
            self._model = AutoModel.from_pretrained(spec.model_name, **kwargs)
        except Exception as error:
            raise ModelLoadError(
                f"cannot load Hugging Face model {spec.model_id}: {error}"
            ) from error
        self._model = self._model.to(self._device).eval()

    def _to_device(self, inputs: Mapping[str, Any]) -> dict[str, Any]:
        return {key: value.to(self._device) for key, value in inputs.items()}

    def encode_texts(self, texts: list[str]) -> FloatArray:
        processor_kwargs: dict[str, object] = {
            "text": texts,
            "return_tensors": "pt",
            "padding": self.spec.text_padding,
            "truncation": True,
        }
        if self.spec.text_max_length is not None:
            processor_kwargs["max_length"] = self.spec.text_max_length
        inputs = self._processor(**processor_kwargs)
        with self._torch.inference_mode():
            features = self._model.get_text_features(**self._to_device(inputs))
        return _normalize(_feature_tensor(features))

    def encode_images(self, images: list[object]) -> FloatArray:
        inputs = self._processor(images=images, return_tensors="pt")
        with self._torch.inference_mode():
            features = self._model.get_image_features(**self._to_device(inputs))
        return _normalize(_feature_tensor(features))


ModelFactory = Callable[[ModelSpec], EmbeddingModel]


class ModelRegistry:
    """Lazily instantiate configured models and expose deterministic model selection."""

    def __init__(
        self,
        specs: Sequence[ModelSpec],
        *,
        factories: Mapping[str, ModelFactory] | None = None,
    ) -> None:
        self._specs = {spec.model_id: spec for spec in specs}
        if len(self._specs) != len(specs):
            raise ModelConfigurationError("model ids must be unique")
        self._factories: dict[str, ModelFactory] = {
            "open_clip": OpenClipEmbeddingModel,
            "huggingface": HuggingFaceEmbeddingModel,
        }
        if factories:
            self._factories.update(factories)
        self._models: dict[str, EmbeddingModel] = {}
        self._lock = RLock()

    def enabled_specs(self, model_ids: Sequence[str] | None = None) -> list[ModelSpec]:
        if model_ids is None:
            return [spec for spec in self._specs.values() if spec.is_enabled]
        if len(set(model_ids)) != len(model_ids):
            raise ModelConfigurationError("selected model ids must be unique")
        selected: list[ModelSpec] = []
        for model_id in model_ids:
            spec = self.spec(model_id)
            if not spec.is_enabled:
                raise ModelConfigurationError(f"model is disabled: {model_id}")
            selected.append(spec)
        return selected

    def spec(self, model_id: str) -> ModelSpec:
        try:
            return self._specs[model_id]
        except KeyError as error:
            raise ModelConfigurationError(f"unknown model: {model_id}") from error

    def get(self, model_id: str) -> EmbeddingModel:
        with self._lock:
            if model_id in self._models:
                return self._models[model_id]
            spec = self.spec(model_id)
            try:
                factory = self._factories[spec.adapter]
            except KeyError as error:
                raise ModelConfigurationError(
                    f"unknown model adapter: {spec.adapter}"
                ) from error
            model = factory(spec)
            self._models[model_id] = model
            return model

    def unload(self, model_id: str) -> None:
        """Release one loaded model so offline multi-model jobs do not accumulate VRAM."""
        with self._lock:
            model = self._models.pop(model_id, None)
        if model is None:
            return
        del model
        gc.collect()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            return


def _parse_model_spec(data: Mapping[str, object]) -> ModelSpec:
    raw_dimension = data["dimension"]
    raw_weight = data.get("weight", 1.0)
    raw_text_max_length = data.get("text_max_length")
    raw_enabled = data.get("enabled", True)
    raw_trust_remote_code = data.get("trust_remote_code", False)
    if not isinstance(raw_dimension, int) or isinstance(raw_dimension, bool):
        raise ModelConfigurationError("model dimension must be an integer")
    if not isinstance(raw_weight, (int, float)) or isinstance(raw_weight, bool):
        raise ModelConfigurationError("model weight must be numeric")
    if not isinstance(raw_enabled, bool):
        raise ModelConfigurationError("model enabled must be boolean")
    if not isinstance(raw_trust_remote_code, bool):
        raise ModelConfigurationError("model trust_remote_code must be boolean")
    if raw_text_max_length is not None and (
        not isinstance(raw_text_max_length, int)
        or isinstance(raw_text_max_length, bool)
    ):
        raise ModelConfigurationError("model text_max_length must be an integer")
    for field in ("id", "adapter", "model_name", "collection"):
        if not isinstance(data[field], str):
            raise ModelConfigurationError(f"model {field} must be a string")
    return ModelSpec(
        model_id=str(data["id"]),
        adapter=str(data["adapter"]),
        model_name=str(data["model_name"]),
        pretrained=str(data["pretrained"]) if data.get("pretrained") else None,
        dimension=int(raw_dimension),
        collection=str(data["collection"]),
        weight=float(raw_weight),
        is_enabled=raw_enabled,
        device=str(data["device"]) if data.get("device") else None,
        revision=str(data["revision"]) if data.get("revision") else None,
        trust_remote_code=raw_trust_remote_code,
        text_padding=str(data.get("text_padding", "longest")),
        text_max_length=(
            raw_text_max_length if isinstance(raw_text_max_length, int) else None
        ),
    )


def load_model_specs(config_path: Path) -> list[ModelSpec]:
    """Load model specifications from a version-controlled JSON configuration."""
    try:
        raw_config = json.loads(config_path.read_text(encoding="utf-8"))
        raw_models = raw_config["models"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise ModelConfigurationError(f"cannot read ensemble config {config_path}: {error}") from error
    if not isinstance(raw_models, list) or not raw_models:
        raise ModelConfigurationError("ensemble config must contain a non-empty models list")
    try:
        specs = [_parse_model_spec(model) for model in raw_models]
    except ModelConfigurationError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise ModelConfigurationError(f"invalid model entry: {error}") from error
    if not any(spec.is_enabled for spec in specs):
        raise ModelConfigurationError("at least one model must be enabled")
    if len({spec.model_id for spec in specs}) != len(specs):
        raise ModelConfigurationError("model ids must be unique")
    return specs


_registry: ModelRegistry | None = None
_registry_lock = RLock()


def get_model_registry() -> ModelRegistry:
    """Return the process-wide lazy model registry."""
    global _registry
    with _registry_lock:
        if _registry is None:
            config_path = Path(os.getenv("ENSEMBLE_CONFIG_PATH", str(DEFAULT_CONFIG_PATH)))
            _registry = ModelRegistry(load_model_specs(config_path))
        return _registry


def reset_model_registry() -> None:
    """Clear the cached registry for tests or configuration reloads."""
    global _registry
    with _registry_lock:
        _registry = None
