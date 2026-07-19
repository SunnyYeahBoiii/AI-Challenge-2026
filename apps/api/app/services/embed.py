import io
import os

import numpy as np
import open_clip
import torch
from PIL import Image

EMBEDDING_DIM = 1024
_device = "cuda" if torch.cuda.is_available() else "cpu"
_model = None
_tokenizer = None
_preprocess = None


def _load_model():
    global _model, _tokenizer, _preprocess
    if _model is None:
        _model, _, _preprocess = open_clip.create_model_and_transforms(
            "ViT-H-14", pretrained="dfn5b"
        )
        _tokenizer = open_clip.get_tokenizer("ViT-H-14")
        _model = _model.to(_device).eval()
    return _model, _tokenizer, _preprocess


def embed_text(texts: list[str]) -> np.ndarray:
    model, tokenizer, _ = _load_model()
    tokens = tokenizer(texts).to(_device)
    with torch.no_grad():
        features = model.encode_text(tokens)
        features = features / features.norm(dim=-1, keepdim=True)
    return features.cpu().numpy().astype(np.float32)


def embed_image(image_bytes: bytes) -> np.ndarray:
    model, _, preprocess = _load_model()
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    batch = preprocess(img).unsqueeze(0).to(_device)
    with torch.no_grad():
        features = model.encode_image(batch)
        features = features / features.norm(dim=-1, keepdim=True)
    return features.cpu().numpy().astype(np.float32)[0]


_client = None


def _get_openai_client():
    global _client
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        return None
    if _client is None:
        from openai import OpenAI

        _client = OpenAI(api_key=api_key)
    return _client


def enhance_query(raw_query: str) -> str:
    client = _get_openai_client()
    if client is None:
        return raw_query
    resp = client.responses.create(
        model="gpt-4.1-nano",
        input=f"Translate to English if needed, then rephrase as a descriptive scene sentence: {raw_query}",
    )
    return resp.output_text
