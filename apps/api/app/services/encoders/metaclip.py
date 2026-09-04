import io
from typing import Any

import numpy as np
import open_clip
import torch
from PIL import Image

from app.services.encoders.base import Embeddings, Encoder, to_numpy

# open_clip architecture name + pretrained tag for MetaCLIP-2 worldwide huge/quickgelu.
# Verified via `open_clip.list_pretrained_tags_by_model(_ARCH)` -> ["metaclip2_worldwide"],
# which resolves to the HF hub checkpoint "timm/vit_huge_patch14_clip_224.metaclip2_worldwide".
_ARCH = "ViT-H-14-worldwide-quickgelu"
_PRETRAINED = "metaclip2_worldwide"


class MetaClipEncoder(Encoder):
    model_id = "metaclip"
    collection_name = "data_frames_metaclip"
    embedding_dim = 1024

    def __init__(self) -> None:
        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        self._precision = "fp16" if self._device == "cuda" else "bf16"
        self._dtype = torch.float16 if self._device == "cuda" else torch.bfloat16
        self._model: Any = None
        self._tokenizer: Any = None
        self._preprocess: Any = None

    def load(self) -> None:
        model, _, preprocess = open_clip.create_model_and_transforms(
            _ARCH,
            pretrained=_PRETRAINED,
            precision=self._precision,
            device=self._device,
        )
        self._tokenizer = open_clip.get_tokenizer(_ARCH)
        self._preprocess = preprocess
        self._model = model.eval()

    def unload(self) -> None:
        self._model = None
        self._tokenizer = None
        self._preprocess = None
        if self._device == "cuda":
            torch.cuda.empty_cache()

    def embed_text(self, texts: list[str]) -> Embeddings:
        if not texts:
            return np.zeros((0, self.embedding_dim), dtype=np.float32)
        tokens = self._tokenizer(texts).to(self._device)
        with torch.no_grad():
            features = self._model.encode_text(tokens)
            features = features / features.norm(dim=-1, keepdim=True)
        return to_numpy(features)

    def embed_image(self, image_bytes: bytes) -> Embeddings:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        batch = self._preprocess(img).unsqueeze(0).to(self._device, dtype=self._dtype)
        with torch.no_grad():
            features = self._model.encode_image(batch)
            features = features / features.norm(dim=-1, keepdim=True)
        vector: Embeddings = to_numpy(features)[0]
        return vector

    def embed_images(self, images: list[bytes]) -> Embeddings:
        if not images:
            return np.zeros((0, self.embedding_dim), dtype=np.float32)
        tensors = [self._preprocess(Image.open(io.BytesIO(b)).convert("RGB")) for b in images]
        batch = torch.stack(tensors).to(self._device, dtype=self._dtype)
        with torch.no_grad():
            features = self._model.encode_image(batch)
            features = features / features.norm(dim=-1, keepdim=True)
        return to_numpy(features)
