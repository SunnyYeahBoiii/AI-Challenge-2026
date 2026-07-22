from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import numpy as np

from app.services.model_registry import FloatArray, EmbeddingModel, ModelLoadError, ModelSpec

CHECKPOINT_FILENAME = "open_clip_model.safetensors"
CONFIG_FILENAME = "open_clip_config.json"
SNAPSHOT_PATTERNS = (
    CHECKPOINT_FILENAME,
    CONFIG_FILENAME,
)


@dataclass
class _PerceptionRuntime:
    torch: Any
    model: Any
    tokenizer: Any
    preprocess: Any
    device: str


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_open_clip_config(
    path: Path,
    spec: ModelSpec,
) -> tuple[dict[str, object], dict[str, object]]:
    try:
        raw_config = json.loads(path.read_text(encoding="utf-8"))
        model_config = raw_config["model_cfg"]
        preprocess_config = raw_config["preprocess_cfg"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise ModelLoadError(f"invalid Perception Encoder config: {error}") from error
    if not isinstance(model_config, dict):
        raise ModelLoadError("Perception Encoder model_cfg must be an object")
    if not isinstance(preprocess_config, dict):
        raise ModelLoadError("Perception Encoder preprocess_cfg must be an object")
    if model_config.get("embed_dim") != spec.dimension:
        raise ModelLoadError("Perception Encoder dimension does not match model config")
    vision_config = model_config.get("vision_cfg")
    if not isinstance(vision_config, dict):
        raise ModelLoadError("Perception Encoder vision_cfg must be an object")
    if spec.image_size is not None and vision_config.get("image_size") != spec.image_size:
        raise ModelLoadError("Perception Encoder image size does not match model config")
    try:
        mean = tuple(float(value) for value in preprocess_config["mean"])
        std = tuple(float(value) for value in preprocess_config["std"])
        interpolation = str(preprocess_config["interpolation"])
        resize_mode = str(preprocess_config["resize_mode"])
    except (KeyError, TypeError, ValueError) as error:
        raise ModelLoadError(
            f"invalid Perception Encoder preprocess_cfg: {error}"
        ) from error
    if len(mean) != 3 or len(std) != 3:
        raise ModelLoadError("Perception Encoder mean and std must have three channels")
    if not all(np.isfinite(value) for value in (*mean, *std)) or any(
        value <= 0 for value in std
    ):
        raise ModelLoadError("Perception Encoder mean/std must be finite and std positive")
    if not interpolation or not resize_mode:
        raise ModelLoadError(
            "Perception Encoder interpolation and resize_mode must be non-empty"
        )
    preprocess_kwargs: dict[str, object] = {
        "image_mean": mean,
        "image_std": std,
        "image_interpolation": interpolation,
        "image_resize_mode": resize_mode,
    }
    return cast(dict[str, object], model_config), preprocess_kwargs


def _cache_file(
    torch: Any,
    url: str,
    destination: Path,
    *,
    expected_sha256: str | None = None,
) -> Path:
    if destination.is_file():
        if expected_sha256 is not None and _sha256(destination) != expected_sha256.lower():
            raise ModelLoadError(f"Perception Encoder asset checksum mismatch: {destination}")
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".partial",
        dir=destination.parent,
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        torch.hub.download_url_to_file(url, str(temporary_path), progress=True)
        if expected_sha256 is not None and _sha256(temporary_path) != expected_sha256.lower():
            raise ModelLoadError(f"Perception Encoder asset checksum mismatch: {temporary_path}")
        temporary_path.replace(destination)
    finally:
        temporary_path.unlink(missing_ok=True)
    return destination


def _cache_snapshot(torch: Any, spec: ModelSpec) -> Path:
    if not spec.pretrained or not spec.revision:
        raise ModelLoadError("Perception Encoder checkpoint repo and revision are required")
    snapshot = (
        Path(torch.hub.get_dir())
        / "checkpoints"
        / "frameseeker"
        / spec.model_id
        / spec.revision
    )
    base_url = f"https://huggingface.co/{spec.pretrained}/resolve/{spec.revision}"
    for filename in SNAPSHOT_PATTERNS:
        _cache_file(
            torch,
            f"{base_url}/{filename}?download=true",
            snapshot / filename,
            expected_sha256=(
                spec.pretrained_sha256 if filename == CHECKPOINT_FILENAME else None
            ),
        )
    return snapshot


def _create_runtime(spec: ModelSpec) -> _PerceptionRuntime:
    if not spec.pretrained or not spec.revision or not spec.pretrained_sha256:
        raise ModelLoadError(
            "Perception Encoder requires a converted checkpoint repo, revision and SHA-256"
        )
    try:
        import open_clip
        import torch
        from open_clip.tokenizer import SimpleTokenizer
    except ImportError as error:
        raise ModelLoadError(
            "Perception Encoder requires the optional 'models' dependency group"
        ) from error

    snapshot = _cache_snapshot(torch, spec)
    checkpoint = snapshot / CHECKPOINT_FILENAME
    # _cache_snapshot already verifies the configured SHA-256. Avoid hashing the
    # 2.68 GB checkpoint a second time during every cold model load.
    if not checkpoint.is_file():
        raise ModelLoadError(f"Perception Encoder checkpoint is missing: {checkpoint}")

    model_config, preprocess_kwargs = _read_open_clip_config(
        snapshot / CONFIG_FILENAME,
        spec,
    )
    local_config = snapshot / f"frameseeker-{spec.model_id}.json"
    serialized_config = json.dumps(model_config, sort_keys=True)
    if not local_config.is_file() or local_config.read_text(encoding="utf-8") != serialized_config:
        local_config.write_text(serialized_config, encoding="utf-8")
    open_clip.add_model_config(local_config)

    device = spec.device or ("cuda" if torch.cuda.is_available() else "cpu")
    model, _, preprocess = open_clip.create_model_and_transforms(
        local_config.stem,
        pretrained=str(checkpoint),
        **preprocess_kwargs,
    )
    model = model.to(device).eval()
    tokenizer = SimpleTokenizer(
        context_length=spec.text_max_length or 32,
    )
    return _PerceptionRuntime(torch, model, tokenizer, preprocess, device)


class PerceptionEmbeddingModel(EmbeddingModel):
    """PE-Core image-text adapter backed by a revision-pinned OpenCLIP conversion."""

    def __init__(self, spec: ModelSpec) -> None:
        self.spec = spec
        try:
            self._runtime = _create_runtime(spec)
        except Exception as error:
            if isinstance(error, ModelLoadError):
                raise
            raise ModelLoadError(
                f"cannot load Perception Encoder model {spec.model_id}: {error}"
            ) from error

    def _normalize(self, features: Any, batch_size: int) -> FloatArray:
        array = features.detach().float().cpu().numpy().astype(np.float32)
        expected_shape = (batch_size, self.spec.dimension)
        if array.shape != expected_shape:
            raise RuntimeError(
                f"Perception Encoder returned shape {array.shape}, expected {expected_shape}"
            )
        norms = np.linalg.norm(array, axis=-1, keepdims=True)
        if not np.all(np.isfinite(norms)) or np.any(norms <= 1e-12):
            raise RuntimeError("Perception Encoder returned zero-norm or non-finite features")
        return cast(FloatArray, array / norms)

    def encode_texts(self, texts: list[str]) -> FloatArray:
        if not texts:
            return np.empty((0, self.spec.dimension), dtype=np.float32)
        tokens = self._runtime.tokenizer(texts).to(self._runtime.device)
        with self._runtime.torch.inference_mode():
            features = self._runtime.model.encode_text(tokens)
        return self._normalize(features, len(texts))

    def encode_images(self, images: list[object]) -> FloatArray:
        if not images:
            return np.empty((0, self.spec.dimension), dtype=np.float32)
        batch = self._runtime.torch.stack(
            [self._runtime.preprocess(image) for image in images]
        ).to(self._runtime.device)
        with self._runtime.torch.inference_mode():
            features = self._runtime.model.encode_image(batch)
        return self._normalize(features, len(images))
