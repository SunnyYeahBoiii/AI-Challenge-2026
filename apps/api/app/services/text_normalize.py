"""Shared text normalization for Elasticsearch OCR/ASR indexing and search."""

from __future__ import annotations

import re


def normalize_text(text: str) -> str:
    """Lowercase and collapse whitespace — preserves Vietnamese diacritics."""
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r"\s+", " ", text).strip()
    return text
