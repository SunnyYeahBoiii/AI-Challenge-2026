"""Shared Elasticsearch schema for frame-level OCR and ASR text."""

from typing import Any

FOLDED_TEXT_ANALYZER = "vietnamese_folded"

ES_MAPPING: dict[str, Any] = {
    "settings": {
        "analysis": {
            "filter": {
                "vietnamese_ascii_folding": {
                    "type": "asciifolding",
                    "preserve_original": False,
                }
            },
            "analyzer": {
                FOLDED_TEXT_ANALYZER: {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": ["lowercase", "vietnamese_ascii_folding"],
                }
            },
        }
    },
    "mappings": {
        "properties": {
            "video_id": {"type": "keyword"},
            "video_path": {"type": "keyword"},
            "frame_id": {"type": "integer"},
            "frame_idx": {"type": "integer"},
            "frame_path": {"type": "keyword"},
            "ocr_text": {
                "type": "text",
                "analyzer": FOLDED_TEXT_ANALYZER,
                "search_analyzer": FOLDED_TEXT_ANALYZER,
            },
            # ASR text keeps full diacritics — folding would collapse Vietnamese
            # minimal pairs (co/cỏ/cọ) and the source text is clean, not noisy.
            "asr_text": {"type": "text"},
            "timestamp": {"type": "float"},
        }
    },
}
