"""Shared Elasticsearch schema for frame-level OCR and ASR text."""

from typing import Any

FOLDED_TEXT_ANALYZER = "vietnamese_folded"

# The alias every reader and writer talks to. Reindexing builds a fresh
# concrete index and re-points the alias, so the name never has downtime
# after the first migration.
ES_ALIAS = "video_texts"
ES_INDEX_PREFIX = f"{ES_ALIAS}_v"


def frame_key(video_id: str, frame_id: int) -> str:
    """Single-field identity for a frame — also used as the document `_id`.

    Filtering by `video_id` and `frame_id` as two independent `terms` clauses
    matches their cross product, not the pairs actually asked for; one keyed
    field avoids that entirely.
    """
    return f"{video_id}:{frame_id}"


ES_MAPPING: dict[str, Any] = {
    "settings": {
        # Single node: an unassignable replica leaves the cluster yellow forever.
        "number_of_shards": 1,
        "number_of_replicas": 0,
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
            "frame_key": {"type": "keyword"},
            "video_id": {"type": "keyword"},
            "video_path": {"type": "keyword"},
            "frame_id": {"type": "integer"},
            "frame_idx": {"type": "integer"},
            "shot_idx": {"type": "integer"},
            "frame_path": {"type": "keyword"},
            # Source OCR arrives already stripped of diacritics, so folding here
            # is what lets a properly typed Vietnamese query reach it at all.
            "ocr_text": {
                "type": "text",
                "analyzer": FOLDED_TEXT_ANALYZER,
                "search_analyzer": FOLDED_TEXT_ANALYZER,
            },
            # ASR keeps full diacritics on the main field so exact phrases can
            # outrank folded ones — folding alone would collapse Vietnamese
            # minimal pairs (co/cỏ/cọ). The subfield exists so a query typed
            # without diacritics still finds the frame, just scored lower.
            "asr_text": {
                "type": "text",
                "fields": {
                    "folded": {
                        "type": "text",
                        "analyzer": FOLDED_TEXT_ANALYZER,
                        "search_analyzer": FOLDED_TEXT_ANALYZER,
                    }
                },
            },
            "timestamp": {"type": "float"},
        }
    },
}
