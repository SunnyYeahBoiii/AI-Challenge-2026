"""Shared text normalization for Elasticsearch OCR/ASR indexing and search."""

from __future__ import annotations

import re
import unicodedata


def normalize_text(text: str) -> str:
    """Strip diacritics, lower-case, and keep only ascii letters/digits/spaces.

    Index and query must use the same transform so Vietnamese ASR/OCR fuzzy
    matches do not fail on accent differences.
    """
    if not text:
        return ""
    text = text.replace("Đ", "D").replace("đ", "d")
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text
