from __future__ import annotations

import gc
import hashlib
import os
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import numpy as np
from torch import nn

from app.services.model_registry import (
    EmbeddingModel,
    FloatArray,
    ModelLoadError,
    ModelSpec,
    _normalize,
)


@dataclass(frozen=True)
class _BEiT3Runtime:
    torch: Any
    model: Any
    tokenizer: Any
    preprocess: Callable[[object], Any]
    device: str


class _BEiT3Tokenizer:
    """Reproduce the fairseq/XLM-R token-id alignment used by BEiT-3."""

    def __init__(self, torch: Any, sentencepiece_processor: Any) -> None:
        self._torch = torch
        self._processor = sentencepiece_processor

    def __call__(
        self,
        texts: list[str],
        *,
        padding: str,
        truncation: bool,
        max_length: int,
        return_tensors: str,
    ) -> dict[str, Any]:
        if padding != "max_length" or not truncation or return_tensors != "pt":
            raise ValueError("BEiT-3 tokenizer requires max-length PyTorch batches")
        if max_length < 2:
            raise ValueError("BEiT-3 max_length must be at least 2")
        input_ids: list[list[int]] = []
        attention_masks: list[list[int]] = []
        for text in texts:
            pieces = self._processor.encode(text, out_type=str)
            if not pieces:
                raise ValueError("BEiT-3 text input must contain at least one token")
            token_ids: list[int] = []
            for piece in pieces[: max_length - 2]:
                sentencepiece_id = int(self._processor.piece_to_id(piece))
                token_ids.append(3 if sentencepiece_id == 0 else sentencepiece_id + 1)
            sequence = [0, *token_ids, 2]
            padding_length = max_length - len(sequence)
            input_ids.append([*sequence, *([1] * padding_length)])
            attention_masks.append(
                [*([1] * len(sequence)), *([0] * padding_length)]
            )
        return {
            "input_ids": self._torch.tensor(input_ids, dtype=self._torch.long),
            "attention_mask": self._torch.tensor(
                attention_masks, dtype=self._torch.long
            ),
        }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as input_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_checksum(path: Path, expected_sha256: str | None) -> None:
    if expected_sha256 is not None and _sha256(path) != expected_sha256.lower():
        raise ModelLoadError(f"BEiT-3 asset checksum mismatch: {path}")


def _cache_asset(
    torch: Any,
    url: str,
    *,
    expected_sha256: str | None = None,
) -> Path:
    filename = Path(urlparse(url).path).name
    if not filename:
        raise ModelLoadError(f"cannot determine filename for BEiT-3 asset: {url}")
    cache_dir = Path(torch.hub.get_dir()) / "checkpoints"
    cache_dir.mkdir(parents=True, exist_ok=True)
    destination = cache_dir / filename
    if destination.is_file():
        _verify_checksum(destination, expected_sha256)
        return destination

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{filename}.", suffix=".partial", dir=cache_dir
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        torch.hub.download_url_to_file(url, str(temporary_path), progress=True)
        _verify_checksum(temporary_path, expected_sha256)
        temporary_path.replace(destination)
    finally:
        temporary_path.unlink(missing_ok=True)
    return destination


def _build_retrieval_model(torch: Any, *, image_size: int, dimension: int) -> Any:
    try:
        from torchscale.architecture.config import EncoderConfig
        from torchscale.model.BEiT3 import BEiT3
    except ImportError as error:
        raise ModelLoadError(
            "BEiT-3 requires torchscale from the optional 'models' dependency group"
        ) from error

    class BEiT3ForRetrieval(nn.Module):
        """Inference-only equivalent of Microsoft's BEiT3ForRetrieval."""

        def __init__(self) -> None:
            super().__init__()
            config = EncoderConfig(
                img_size=image_size,
                patch_size=16,
                vocab_size=64010,
                multiway=True,
                layernorm_embedding=False,
                normalize_output=True,
                no_output_layer=True,
                drop_path_rate=0,
                encoder_embed_dim=dimension,
                encoder_attention_heads=16,
                encoder_ffn_embed_dim=4096,
                encoder_layers=24,
                checkpoint_activations=None,
            )
            self.beit3 = BEiT3(config)
            self.language_head = nn.Linear(dimension, dimension, bias=False)
            self.vision_head = nn.Linear(dimension, dimension, bias=False)
            self.logit_scale = nn.Parameter(torch.ones([]) * np.log(1 / 0.07))

        def forward(
            self,
            *,
            image: Any | None = None,
            text_description: Any | None = None,
            padding_mask: Any | None = None,
            only_infer: bool = True,
        ) -> tuple[Any | None, Any | None]:
            if not only_infer:
                raise ValueError("FrameSeeker's BEiT-3 adapter supports inference only")
            vision_features = None
            if image is not None:
                output = self.beit3(
                    textual_tokens=None,
                    visual_tokens=image,
                    text_padding_position=None,
                )
                vision_features = nn.functional.normalize(
                    self.vision_head(output["encoder_out"][:, 0, :]), dim=-1
                )
            language_features = None
            if text_description is not None:
                output = self.beit3(
                    textual_tokens=text_description,
                    visual_tokens=None,
                    text_padding_position=padding_mask,
                )
                language_features = nn.functional.normalize(
                    self.language_head(output["encoder_out"][:, 0, :]), dim=-1
                )
            return vision_features, language_features

    return BEiT3ForRetrieval()


def _create_runtime(spec: ModelSpec) -> _BEiT3Runtime:
    if spec.dimension != 1024:
        raise ModelLoadError("BEiT-3 Large retrieval requires dimension 1024")
    if (
        spec.image_size is None
        or spec.pretrained is None
        or spec.tokenizer_url is None
        or spec.pretrained_sha256 is None
        or spec.tokenizer_sha256 is None
    ):
        raise ModelLoadError(
            "BEiT-3 requires image_size, checkpoint/tokenizer URLs and SHA-256 hashes"
        )
    try:
        import torch
        import sentencepiece as spm
        from torchvision import transforms
    except ImportError as error:
        raise ModelLoadError(
            "BEiT-3 requires the optional 'models' dependency group"
        ) from error

    device = spec.device or ("cuda" if torch.cuda.is_available() else "cpu")
    checkpoint_path = _cache_asset(
        torch,
        spec.pretrained,
        expected_sha256=spec.pretrained_sha256,
    )
    tokenizer_path = _cache_asset(
        torch,
        spec.tokenizer_url,
        expected_sha256=spec.tokenizer_sha256,
    )
    model = _build_retrieval_model(
        torch,
        image_size=spec.image_size,
        dimension=spec.dimension,
    )
    checkpoint = torch.load(
        checkpoint_path,
        map_location="cpu",
        weights_only=True,
    )
    if not isinstance(checkpoint, Mapping):
        raise ModelLoadError("BEiT-3 checkpoint must contain a state dictionary")
    state_dict = checkpoint.get("model", checkpoint)
    if not isinstance(state_dict, Mapping):
        raise ModelLoadError("BEiT-3 checkpoint model entry must be a state dictionary")
    model.load_state_dict(state_dict, strict=True)
    del state_dict
    del checkpoint
    gc.collect()
    model = model.to(device).eval()

    sentencepiece_processor = spm.SentencePieceProcessor(model_file=str(tokenizer_path))
    tokenizer = _BEiT3Tokenizer(torch, sentencepiece_processor)
    image_transform = transforms.Compose(
        [
            transforms.Resize(
                (spec.image_size, spec.image_size),
                interpolation=transforms.InterpolationMode.BICUBIC,
            ),
            transforms.ToTensor(),
            transforms.Normalize(mean=(0.5, 0.5, 0.5), std=(0.5, 0.5, 0.5)),
        ]
    )

    def preprocess(image: object) -> Any:
        convert = getattr(image, "convert", None)
        rgb_image = convert("RGB") if callable(convert) else image
        return image_transform(rgb_image)

    return _BEiT3Runtime(torch, model, tokenizer, preprocess, device)


class BEiT3EmbeddingModel(EmbeddingModel):
    """BEiT-3 Large COCO retrieval dual-encoder adapter."""

    def __init__(self, spec: ModelSpec) -> None:
        self.spec = spec
        try:
            self._runtime = _create_runtime(spec)
        except ModelLoadError:
            raise
        except Exception as error:
            raise ModelLoadError(f"cannot load BEiT-3 model {spec.model_id}: {error}") from error

    def encode_texts(self, texts: list[str]) -> FloatArray:
        if not texts:
            return np.empty((0, self.spec.dimension), dtype=np.float32)
        max_length = self.spec.text_max_length or 64
        encoded = self._runtime.tokenizer(
            texts,
            padding="max_length",
            truncation=True,
            max_length=max_length,
            return_tensors="pt",
        )
        token_ids = encoded["input_ids"].to(self._runtime.device)
        padding_mask = encoded["attention_mask"].eq(0).to(self._runtime.device)
        with self._runtime.torch.inference_mode():
            _, features = self._runtime.model(
                text_description=token_ids,
                padding_mask=padding_mask,
                only_infer=True,
            )
        if features is None:
            raise RuntimeError("BEiT-3 text encoder returned no features")
        return _normalize(features)

    def encode_images(self, images: list[object]) -> FloatArray:
        if not images:
            return np.empty((0, self.spec.dimension), dtype=np.float32)
        batch = self._runtime.torch.stack(
            [self._runtime.preprocess(image) for image in images]
        ).to(self._runtime.device)
        with self._runtime.torch.inference_mode():
            features, _ = self._runtime.model(image=batch, only_infer=True)
        if features is None:
            raise RuntimeError("BEiT-3 image encoder returned no features")
        return _normalize(features)
