import io
from pathlib import Path
from typing import Any

import numpy as np
import torch
from PIL import Image
from torchvision import transforms
from transformers import XLMRobertaTokenizer

from app.config import WEIGHTS_DIR
from app.services.encoders._beit3_vendor import BEiT3ForRetrieval, beit3_large_patch16_384_retrieval
from app.services.encoders.base import Embeddings, Encoder, to_numpy

_CHECKPOINT = WEIGHTS_DIR / "beit3_large_patch16_384_coco_retrieval.pth"
_SPM_MODEL = WEIGHTS_DIR / "beit3.spm"
_CHECKPOINT_URL = (
    "https://github.com/addf400/files/releases/download/beit3/"
    "beit3_large_patch16_384_coco_retrieval.pth"
)
_SPM_MODEL_URL = "https://github.com/addf400/files/releases/download/beit3/beit3.spm"

_MAX_TEXT_LEN = 64

# IMAGENET_INCEPTION_MEAN/STD, per unilm/beit3's eval transform for non-imagenet tasks.
_MEAN = (0.5, 0.5, 0.5)
_STD = (0.5, 0.5, 0.5)


def _ensure_weight(path: Path, url: str) -> None:
    if path.is_file():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        torch.hub.download_url_to_file(url, str(path), progress=True)
    except Exception as exc:
        raise RuntimeError(f"Failed to download BEiT-3 weight from {url} to {path}") from exc


class Beit3Encoder(Encoder):
    model_id = "beit3"
    collection_name = "data_frames_beit3"
    embedding_dim = 1024

    def __init__(self) -> None:
        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        self._model: BEiT3ForRetrieval | None = None
        self._tokenizer: Any = None
        self._transform: Any = None

    def load(self) -> None:
        _ensure_weight(_CHECKPOINT, _CHECKPOINT_URL)
        _ensure_weight(_SPM_MODEL, _SPM_MODEL_URL)
        model = beit3_large_patch16_384_retrieval()
        checkpoint = torch.load(_CHECKPOINT, map_location="cpu", weights_only=False)
        model.load_state_dict(checkpoint["model"], strict=False)
        self._model = model.to(self._device).eval()
        self._tokenizer = XLMRobertaTokenizer(str(_SPM_MODEL))
        self._transform = transforms.Compose(
            [
                transforms.Resize((384, 384), interpolation=transforms.InterpolationMode.BICUBIC),
                transforms.ToTensor(),
                transforms.Normalize(mean=_MEAN, std=_STD),
            ]
        )

    def unload(self) -> None:
        self._model = None
        self._tokenizer = None
        self._transform = None
        if self._device == "cuda":
            torch.cuda.empty_cache()

    def _tokenize(self, texts: list[str]) -> tuple[torch.Tensor, torch.Tensor]:
        tokenizer = self._tokenizer
        token_ids = []
        for text in texts:
            ids = tokenizer.convert_tokens_to_ids(tokenizer.tokenize(text))
            ids = [tokenizer.bos_token_id, *ids[: _MAX_TEXT_LEN - 2], tokenizer.eos_token_id]
            token_ids.append(ids)
        max_len = max(len(ids) for ids in token_ids)
        padded = torch.full((len(token_ids), max_len), tokenizer.pad_token_id, dtype=torch.long)
        padding_mask = torch.ones((len(token_ids), max_len), dtype=torch.long)
        for i, ids in enumerate(token_ids):
            padded[i, : len(ids)] = torch.tensor(ids, dtype=torch.long)
            padding_mask[i, : len(ids)] = 0
        return padded.to(self._device), padding_mask.to(self._device)

    def embed_text(self, texts: list[str]) -> Embeddings:
        if not texts:
            return np.zeros((0, self.embedding_dim), dtype=np.float32)
        token_ids, padding_mask = self._tokenize(texts)
        with torch.no_grad():
            assert self._model is not None
            _, language_cls = self._model(text_description=token_ids, padding_mask=padding_mask)
        return to_numpy(language_cls)

    def embed_image(self, image_bytes: bytes) -> Embeddings:
        embedding: Embeddings = self.embed_images([image_bytes])[0]
        return embedding

    def embed_images(self, images: list[bytes]) -> Embeddings:
        if not images:
            return np.zeros((0, self.embedding_dim), dtype=np.float32)
        tensors = [self._transform(Image.open(io.BytesIO(b)).convert("RGB")) for b in images]
        batch = torch.stack(tensors).to(self._device)
        with torch.no_grad():
            assert self._model is not None
            vision_cls, _ = self._model(image=batch)
        return to_numpy(vision_cls)
