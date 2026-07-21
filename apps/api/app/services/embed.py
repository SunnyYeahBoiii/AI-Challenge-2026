from __future__ import annotations

import io
import logging
import os
from typing import Any, cast

from PIL import Image, UnidentifiedImageError

from app.services.model_registry import FloatArray, get_model_registry

LOGGER = logging.getLogger(__name__)


def _selected_model_id(model_id: str | None) -> str:
    if model_id:
        return model_id
    enabled = get_model_registry().enabled_specs()
    if not enabled:
        raise RuntimeError("no embedding models are enabled")
    return enabled[0].model_id


def embed_text(texts: list[str], model_id: str | None = None) -> FloatArray:
    """Encode text with one configured model for debugging or legacy callers."""
    selected_model = _selected_model_id(model_id)
    return get_model_registry().get(selected_model).encode_texts(texts)


def decode_image(image_bytes: bytes) -> Image.Image:
    """Decode user-provided image bytes into an isolated RGB image."""
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            return image.convert("RGB").copy()
    except (OSError, UnidentifiedImageError) as error:
        raise ValueError("invalid image payload") from error


def embed_image(image_bytes: bytes, model_id: str | None = None) -> FloatArray:
    """Encode an image with one configured model for debugging or legacy callers."""
    selected_model = _selected_model_id(model_id)
    image = decode_image(image_bytes)
    return cast(FloatArray, get_model_registry().get(selected_model).encode_images([image])[0])


_client: Any | None = None


def _get_openai_client() -> Any | None:
    global _client
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        return None
    if _client is None:
        from openai import OpenAI

        _client = OpenAI(api_key=api_key)
    return _client


def enhance_query(raw_query: str) -> str:
    """Translate and expand a Query while explicitly preserving discriminative details."""
    client = _get_openai_client()
    if client is None:
        return raw_query
    prompt = (
        "Translate the retrieval query to English when needed and rewrite it as one concise "
        "visual scene description. Preserve every named entity, count, color, spatial relation, "
        "visible text, spoken phrase, action order, negation, and uncertainty. Do not invent new "
        f"details. Query: {raw_query}"
    )
    try:
        response = client.responses.create(model="gpt-4.1-nano", input=prompt)
        enhanced = str(response.output_text).strip()
        return enhanced or raw_query
    except Exception as error:
        LOGGER.warning("Query enhancement failed; using original Query: %s", error)
        return raw_query
