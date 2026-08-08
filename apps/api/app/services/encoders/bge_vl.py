import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import torch
from transformers import AutoModel

from app.services.encoders.base import Embeddings, Encoder, to_numpy

_HF_ID = "BAAI/BGE-VL-large"

# The underlying CLIP text tower has a fixed 77-token position embedding table.
# The vendor's own `encode(text=...)` re-tokenizes without truncation, so long
# queries crash with a position-embedding shape mismatch. Longer queries are
# split into <=75-token chunks (leaving room for BOS/EOS), embedded separately,
# then mean-pooled back into one vector — no content is discarded.
_MAX_TEXT_TOKENS = 77
_CHUNK_BUDGET = _MAX_TEXT_TOKENS - 2


class BgeVlEncoder(Encoder):
    model_id = "bge_vl_large"
    collection_name = "data_frames_bge_vl_large"
    embedding_dim = 768

    def __init__(self) -> None:
        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        self._model: Any = None

    def load(self) -> None:
        model = AutoModel.from_pretrained(_HF_ID, trust_remote_code=True, dtype=torch.bfloat16)
        model.set_processor(_HF_ID)
        self._model = model.to(self._device).eval()

    def unload(self) -> None:
        self._model = None
        if self._device == "cuda":
            torch.cuda.empty_cache()

    def embed_text(self, texts: list[str]) -> Embeddings:
        if not texts:
            return np.zeros((0, self.embedding_dim), dtype=np.float32)

        chunk_lists = [self._split_into_chunks(t) for t in texts]
        flat_chunks = [chunk for chunks in chunk_lists for chunk in chunks]

        with torch.no_grad():
            features = self._model.encode(text=flat_chunks)
            features = features / features.norm(dim=-1, keepdim=True)

            rows = []
            offset = 0
            for chunks in chunk_lists:
                group = features[offset : offset + len(chunks)]
                offset += len(chunks)
                pooled = group.mean(dim=0)
                pooled = pooled / pooled.norm()
                rows.append(pooled)
            pooled_features = torch.stack(rows)

        return to_numpy(pooled_features)

    def _split_into_chunks(self, text: str) -> list[str]:
        """Split into <=`_CHUNK_BUDGET`-token pieces so none exceeds the 77-token
        position embedding table. A short text is returned as a single chunk."""
        tokenizer = self._model.processor.tokenizer
        token_ids = tokenizer(text, add_special_tokens=False)["input_ids"]
        if len(token_ids) <= _CHUNK_BUDGET:
            return [text]
        pieces = [token_ids[i : i + _CHUNK_BUDGET] for i in range(0, len(token_ids), _CHUNK_BUDGET)]
        return [str(tokenizer.decode(piece, skip_special_tokens=True)) for piece in pieces]

    def embed_image(self, image_bytes: bytes) -> Embeddings:
        embedding: Embeddings = self.embed_images([image_bytes])[0]
        return embedding

    def embed_images(self, images: list[bytes]) -> Embeddings:
        if not images:
            return np.zeros((0, self.embedding_dim), dtype=np.float32)
        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = []
            for i, image_bytes in enumerate(images):
                path = Path(tmp_dir) / f"{i}.jpg"
                path.write_bytes(image_bytes)
                paths.append(str(path))
            with torch.no_grad():
                features = self._model.encode(images=paths)
                features = features / features.norm(dim=-1, keepdim=True)
        return to_numpy(features)
