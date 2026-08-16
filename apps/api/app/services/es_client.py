import logging
from collections.abc import Iterable, Sequence
from typing import Any

from elasticsearch import Elasticsearch

from app.config import Config

logger = logging.getLogger(__name__)

ES_URL = Config.ES_URL
ES_USER = Config.ES_USER
ES_PASS = Config.ES_PASS
ES_INDEX = "video_texts"
MAX_KEYWORD_HITS = Config.ES_MAX_KEYWORD_HITS

FrameKey = tuple[Any, Any]


def _nonempty_keywords(keywords: Sequence[str]) -> list[str]:
    return [keyword for keyword in keywords if keyword.strip()]


def _exact_phrase_field_group(
    keywords: Sequence[str], field: str, mode: str
) -> dict[str, Any] | None:
    """Build an analyzed, ordered and adjacent phrase group for one field."""
    original_keywords = _nonempty_keywords(keywords)
    if not original_keywords:
        return None
    clauses = [{"match_phrase": {field: keyword}} for keyword in original_keywords]
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
        size: int = 50,
    ) -> list[dict[str, Any]]:
        must: list[dict[str, Any]] = []
        if query:
            must.append({
                "bool": {
                    "should": [
                        {"prefix": {"video_id": query}},
                        {"prefix": {"video_id": query.upper()}},
                    ],
                }
            })
        body: dict[str, Any] = {"size": size * 4}
        if must:
            body["query"] = {"bool": {"must": must}}
        else:
            body["query"] = {"match_all": {}}
        resp = self.es.search(index=ES_INDEX, body=body)
        seen: set[str] = set()
        results: list[dict[str, Any]] = []
        for hit in resp["hits"]["hits"]:
            vid = hit["_source"].get("video_id")
            if vid and vid not in seen:
                seen.add(vid)
                results.append({"_source": hit["_source"], "score": hit["_score"]})
                if len(results) >= size:
                    break
        return results

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

        OCR keywords phrase-match `ocr_text` only; ASR keywords phrase-match
        `asr_text` only. When both groups are non-empty they are AND-ed. Within each group,
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
        ocr_group = _exact_phrase_field_group(ocr, "ocr_text", ocr_mode or mode)
        asr_group = _exact_phrase_field_group(asr, "asr_text", asr_mode or mode)
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

    def iter_keyword_frame_hits(
        self,
        keywords: Sequence[str] | None = None,
        mode: str = "and",
        source: str = "all",
        *,
        ocr_keywords: Sequence[str] | None = None,
        asr_keywords: Sequence[str] | None = None,
        ocr_mode: str | None = None,
        asr_mode: str | None = None,
        allowed_video_ids: Sequence[str] | None = None,
        page_size: int = 500,
    ) -> Iterable[tuple[str, int, float]]:
        """Yield global keyword matches in stable Elasticsearch relevance order."""
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

        must = [
            group
            for group in (
                _exact_phrase_field_group(ocr, "ocr_text", ocr_mode or mode),
                _exact_phrase_field_group(asr, "asr_text", asr_mode or mode),
            )
            if group is not None
        ]
        if not must:
            return

        filters: list[dict[str, Any]] = []
        if allowed_video_ids is not None:
            video_ids = sorted(set(allowed_video_ids))
            if not video_ids:
                return
            filters.append({"terms": {"video_id": video_ids}})

        search_after: list[Any] | None = None
        size = max(1, min(int(page_size), MAX_KEYWORD_HITS))
        while True:
            bool_query: dict[str, Any] = {"must": must}
            if filters:
                bool_query["filter"] = filters
            body: dict[str, Any] = {
                "query": {"bool": bool_query},
                "_source": ["video_id", "frame_id"],
                "size": size,
                "sort": [
                    {"_score": "desc"},
                    {"video_id": "asc"},
                    {"frame_id": "asc"},
                ],
            }
            if search_after is not None:
                body["search_after"] = search_after
            hits = self.es.search(index=ES_INDEX, body=body)["hits"]["hits"]
            if not hits:
                return
            for hit in hits:
                source_doc = hit["_source"]
                yield (
                    str(source_doc["video_id"]),
                    int(source_doc["frame_id"]),
                    float(hit.get("_score") or 0.0),
                )
            if len(hits) < size or "sort" not in hits[-1]:
                return
            search_after = list(hits[-1]["sort"])

    def fetch_frame_texts(
        self, frame_keys: Iterable[FrameKey]
    ) -> dict[FrameKey, dict[str, str]]:
        """Fetch original OCR/ASR text for a small navigator frame window."""
        keys = list(frame_keys)
        if not keys:
            return {}
        video_ids = sorted({video_id for video_id, _ in keys if video_id})
        frame_ids = sorted({frame_id for _, frame_id in keys if frame_id is not None})
        if not video_ids or not frame_ids:
            return {}
        body = {
            "query": {
                "bool": {
                    "filter": [
                        {"terms": {"video_id": video_ids}},
                        {"terms": {"frame_id": frame_ids}},
                    ]
                }
            },
            "_source": ["video_id", "frame_id", "ocr_text", "asr_text"],
            "size": min(MAX_KEYWORD_HITS, max(len(keys) * 2, 100)),
        }
        hits = self.es.search(index=ES_INDEX, body=body)["hits"]["hits"]
        return {
            (hit["_source"]["video_id"], hit["_source"]["frame_id"]): {
                "ocr_text": hit["_source"].get("ocr_text", "") or "",
                "asr_text": hit["_source"].get("asr_text", "") or "",
            }
            for hit in hits
        }

    def is_connected(self) -> bool:
        try:
            return bool(self.es.ping())
        except Exception:
            return False


es_client = ESClient()
