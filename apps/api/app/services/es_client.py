import logging
import os
from collections.abc import Iterable, Sequence
from typing import Any

from elasticsearch import Elasticsearch

from app.services.text_normalize import normalize_text

logger = logging.getLogger(__name__)

ES_URL = os.getenv("ES_URL", "http://localhost:9200")
ES_USER = os.getenv("ES_USER", "")
ES_PASS = os.getenv("ES_PASS", "")
ES_INDEX = "video_texts"
MAX_KEYWORD_HITS = int(os.getenv("ES_MAX_KEYWORD_HITS", "10000"))

FrameKey = tuple[Any, Any]


def _normalized_keywords(keywords: Sequence[str]) -> list[str]:
    return [kw for kw in (normalize_text(k) for k in keywords) if kw]


def _fuzzy_field_group(
    keywords: Sequence[str], field: str, mode: str
) -> dict[str, Any] | None:
    """Build a bool should-group of fuzzy matches against one text field."""
    normalized = _normalized_keywords(keywords)
    if not normalized:
        return None
    clauses = [
        {"multi_match": {"query": kw, "fields": [field], "fuzziness": "AUTO"}}
        for kw in normalized
    ]
    return {
        "bool": {
            "should": clauses,
            "minimum_should_match": 1 if mode == "or" else len(clauses),
        }
    }


class ESClient:
    def __init__(self) -> None:
        if ES_USER and ES_PASS:
            self.es = Elasticsearch(ES_URL, basic_auth=(ES_USER, ES_PASS))
        else:
            self.es = Elasticsearch(ES_URL)

    def search_videos(
        self,
        query: str | None = None,
        tags: Sequence[str] | None = None,
        size: int = 50,
    ) -> list[dict[str, Any]]:
        must: list[dict[str, Any]] = []
        if query:
            normalized = normalize_text(query)
            if normalized:
                must.append({
                    "multi_match": {
                        "query": normalized,
                        "fields": ["ocr_text^3", "asr_text^2"],
                        "fuzziness": "AUTO",
                    }
                })
        body: dict[str, Any] = {"size": size}
        if must:
            body["query"] = {"bool": {"must": must}}
        else:
            body["query"] = {"match_all": {}}
        resp = self.es.search(index=ES_INDEX, body=body)
        return [
            {"_source": hit["_source"], "score": hit["_score"]}
            for hit in resp["hits"]["hits"]
        ]

    def get_video(self, video_id: str) -> dict[str, Any] | None:
        resp = self.es.search(
            index=ES_INDEX,
            body={"query": {"term": {"video_id": video_id}}, "size": 1},
        )
        hits = resp["hits"]["hits"]
        source: dict[str, Any] | None = hits[0]["_source"] if hits else None
        return source

    def match_frames_by_keywords(
        self,
        frame_keys: Iterable[FrameKey],
        keywords: Sequence[str] | None = None,
        mode: str = "and",
        source: str = "all",
        *,
        ocr_keywords: Sequence[str] | None = None,
        asr_keywords: Sequence[str] | None = None,
        ocr_mode: str | None = None,
        asr_mode: str | None = None,
    ) -> set[FrameKey]:
        """Return the subset of (video_id, frame_index) whose OCR/ASR text matches.

        OCR keywords fuzzy-match `ocr_text` only; ASR keywords match `asr_text`
        only. When both groups are non-empty they are AND-ed. Within each group,
        `ocr_mode`/`asr_mode` controls and/or, falling back to `mode` when unset.

        Legacy `keywords` + `source` still work when the dedicated lists are empty:
        ocr/asr map to one field; all duplicates keywords into both groups.
        """
        keys = list(frame_keys)
        ocr = list(ocr_keywords or [])
        asr = list(asr_keywords or [])
        if not ocr and not asr and keywords:
            if source == "ocr":
                ocr = list(keywords)
            elif source == "asr":
                asr = list(keywords)
            else:
                ocr = list(keywords)
                asr = list(keywords)

        if (not ocr and not asr) or not keys:
            return set(keys)

        video_ids = sorted({vid for vid, _ in keys})
        frame_ids = sorted({idx for _, idx in keys})
        must: list[dict[str, Any]] = []
        ocr_group = _fuzzy_field_group(ocr, "ocr_text", ocr_mode or mode)
        asr_group = _fuzzy_field_group(asr, "asr_text", asr_mode or mode)
        if ocr_group:
            must.append(ocr_group)
        if asr_group:
            must.append(asr_group)
        if not must:
            return set(keys)

        bool_query: dict[str, Any] = {
            "must": must,
            "filter": [
                {"terms": {"video_id": video_ids}},
                {"terms": {"frame_id": frame_ids}},
            ],
        }
        size = min(MAX_KEYWORD_HITS, max(len(keys), 100))
        body = {
            "query": {"bool": bool_query},
            "_source": ["video_id", "frame_id"],
            "size": size,
        }
        resp = self.es.search(index=ES_INDEX, body=body)
        hits = resp["hits"]["hits"]
        if len(hits) >= size:
            # Truncation drops matching frames silently, which looks identical to
            # "the keyword matched nothing". Say so instead.
            logger.warning(
                "keyword match hit the %d-doc page size; some matches were dropped "
                "(raise ES_MAX_KEYWORD_HITS)",
                size,
            )
        matched = {
            (hit["_source"]["video_id"], hit["_source"]["frame_id"])
            for hit in hits
        }
        return {key for key in keys if key in matched}

    def is_connected(self) -> bool:
        try:
            return bool(self.es.ping())
        except Exception:
            return False


es_client = ESClient()
