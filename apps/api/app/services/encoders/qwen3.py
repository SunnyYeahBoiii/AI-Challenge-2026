"""Qwen3-VL-Embedding encoder for the shared text/image retrieval space."""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any, cast

import numpy as np
import torch
import torch.nn.functional as functional
from PIL import Image
from transformers.models.qwen3_vl.configuration_qwen3_vl import Qwen3VLConfig
from transformers.models.qwen3_vl.modeling_qwen3_vl import (
    Qwen3VLModel,
    Qwen3VLPreTrainedModel,
)
from transformers.models.qwen3_vl.processing_qwen3_vl import Qwen3VLProcessor
from transformers.utils.generic import ModelOutput

from app.services.encoders.base import Embeddings, Encoder, to_numpy

_MODEL_ID = "Qwen/Qwen3-VL-Embedding-2B"
_MAX_LENGTH = 8192
_MIN_PIXELS = 4 * 32 * 32
# Keep this equal to the max_pixels used to create the Batch-1 artifact.
_MAX_PIXELS = 921600
_DEFAULT_INSTRUCTION = "Represent the user's input."
_IMAGE_PATCH_SIZE = 16


@dataclass
class _QwenEmbeddingOutput(ModelOutput):
    last_hidden_state: torch.Tensor | None = None
    attention_mask: torch.Tensor | None = None


class _Qwen3VLForEmbedding(Qwen3VLPreTrainedModel):
    """Embedding-compatible Qwen backbone matching the official Qwen wrapper."""

    _checkpoint_conversion_mapping: dict[str, str] = {}
    accepts_loss_kwargs = False
    config_class = Qwen3VLConfig  # type: ignore[assignment]
    config: Qwen3VLConfig

    def __init__(self, config: Qwen3VLConfig) -> None:
        super().__init__(config)
        self.model = Qwen3VLModel(config)  # type: ignore[no-untyped-call]
        self.post_init()  # type: ignore[no-untyped-call]

    def forward(self, **kwargs: Any) -> _QwenEmbeddingOutput:
        outputs = self.model(**kwargs)
        return _QwenEmbeddingOutput(
            last_hidden_state=outputs.last_hidden_state,
            attention_mask=kwargs.get("attention_mask"),
        )


def _process_vision_info(conversations: list[list[dict[str, Any]]]) -> tuple[Any, Any, dict[str, Any]]:
    """Load Qwen's vision preprocessing lazily so text-only unit tests stay lightweight."""
    from qwen_vl_utils import process_vision_info  # type: ignore[import-untyped]

    return cast(
        tuple[Any, Any, dict[str, Any]],
        process_vision_info(
            conversations,
            image_patch_size=_IMAGE_PATCH_SIZE,
            return_video_metadata=True,
            return_video_kwargs=True,
        ),
    )


class Qwen3Encoder(Encoder):
    """Qwen3-VL-Embedding-2B encoder aligned with the Batch-1 artifacts."""

    model_id = "qwen3"
    collection_name = "data_frames_qwen3"
    embedding_dim = 2048

    def __init__(self) -> None:
        device_name = "cuda" if torch.cuda.is_available() else "cpu"
        self._device = torch.device(device_name)
        self._dtype = torch.float16 if device_name == "cuda" else torch.float32
        self._model: Any = None
        self._processor: Any = None

    def load(self) -> None:
        self._model = (
            _Qwen3VLForEmbedding.from_pretrained(
                _MODEL_ID,
                dtype=self._dtype,
                attn_implementation="sdpa",
            )
            .to(self._device)
            .eval()
        )
        self._processor = Qwen3VLProcessor.from_pretrained(
            _MODEL_ID,
            padding_side="right",
        )

    def unload(self) -> None:
        self._model = None
        self._processor = None
        if self._device.type == "cuda":
            torch.cuda.empty_cache()

    def embed_text(self, texts: list[str]) -> Embeddings:
        if not texts:
            return np.zeros((0, self.embedding_dim), dtype=np.float32)
        conversations = [self._format_model_input(text=text) for text in texts]
        return self._embed_conversations(conversations)

    def embed_image(self, image_bytes: bytes) -> Embeddings:
        embedding: Embeddings = self.embed_images([image_bytes])[0]
        return embedding

    def embed_images(self, images: list[bytes]) -> Embeddings:
        if not images:
            return np.zeros((0, self.embedding_dim), dtype=np.float32)
        pil_images = [self._decode_image(image_bytes) for image_bytes in images]
        conversations = [self._format_model_input(image=image) for image in pil_images]
        return self._embed_conversations(conversations)

    def _embed_conversations(self, conversations: list[list[dict[str, Any]]]) -> Embeddings:
        model, processor = self._loaded_components()
        text = processor.apply_chat_template(
            conversations,
            add_generation_prompt=True,
            tokenize=False,
        )
        images, video_inputs, video_kwargs = _process_vision_info(conversations)
        videos: list[Any] | None
        video_metadata: list[Any] | None
        if video_inputs is not None:
            video_pairs = list(video_inputs)
            videos = [pair[0] for pair in video_pairs]
            video_metadata = [pair[1] for pair in video_pairs]
        else:
            videos = None
            video_metadata = None

        inputs = processor(
            text=text,
            images=images,
            videos=videos,
            video_metadata=video_metadata,
            truncation=True,
            max_length=_MAX_LENGTH,
            padding=True,
            do_resize=False,
            return_tensors="pt",
            **video_kwargs,
        )
        model_inputs = self._to_device(inputs)
        with torch.inference_mode():
            outputs = model(**model_inputs)
        if outputs.last_hidden_state is None:
            raise ValueError("Qwen3 did not return last_hidden_state")
        attention_mask = model_inputs.get("attention_mask")
        if not isinstance(attention_mask, torch.Tensor):
            raise ValueError("Qwen3 did not return attention_mask")
        embeddings = self._pool_last(outputs.last_hidden_state, attention_mask)
        return to_numpy(functional.normalize(embeddings.float(), p=2, dim=-1))

    @staticmethod
    def _format_model_input(
        text: str | None = None,
        image: Image.Image | None = None,
    ) -> list[dict[str, Any]]:
        content: list[dict[str, Any]] = []
        if image is not None:
            content.append(
                {
                    "type": "image",
                    "image": image,
                    "min_pixels": _MIN_PIXELS,
                    "max_pixels": _MAX_PIXELS,
                }
            )
        if text is not None:
            content.append({"type": "text", "text": text})
        if not content:
            content.append({"type": "text", "text": "NULL"})
        return [
            {
                "role": "system",
                "content": [{"type": "text", "text": _DEFAULT_INSTRUCTION}],
            },
            {"role": "user", "content": content},
        ]

    def _loaded_components(self) -> tuple[Any, Any]:
        if self._model is None or self._processor is None:
            raise RuntimeError("Qwen3 encoder is not loaded")
        return self._model, self._processor

    def _to_device(self, inputs: dict[str, Any]) -> dict[str, Any]:
        return {
            name: value.to(self._device, non_blocking=True) if hasattr(value, "to") else value
            for name, value in inputs.items()
        }

    @staticmethod
    def _pool_last(hidden_state: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:
        flipped_mask = attention_mask.flip(dims=[1])
        last_one_positions = flipped_mask.argmax(dim=1)
        columns = attention_mask.shape[1] - last_one_positions - 1
        rows = torch.arange(hidden_state.shape[0], device=hidden_state.device)
        return hidden_state[rows, columns]

    @staticmethod
    def _decode_image(image_bytes: bytes) -> Image.Image:
        with Image.open(io.BytesIO(image_bytes)) as image:
            return image.convert("RGB")
