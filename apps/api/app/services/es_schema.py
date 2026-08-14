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
            "asr_text": {
                "type": "text",
                "analyzer": FOLDED_TEXT_ANALYZER,
                "search_analyzer": FOLDED_TEXT_ANALYZER,
            },
            "timestamp": {"type": "float"},
        }
    },
}


def mismatched_mapping_fields(properties: dict[str, Any]) -> list[str]:
    """Compare mappings while accepting ES's implicit search-analyzer default."""
    expected = ES_MAPPING["mappings"]["properties"]
    mismatched: list[str] = []
    for field, definition in expected.items():
        actual = properties.get(field, {})
        for key in ("type", "analyzer", "search_analyzer"):
            expected_value = definition.get(key)
            if expected_value is None:
                continue
            actual_value = actual.get(key)
            if key == "search_analyzer" and actual_value is None:
                actual_value = actual.get("analyzer")
            if actual_value != expected_value:
                mismatched.append(field)
                break
    return mismatched
