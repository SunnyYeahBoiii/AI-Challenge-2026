import logging
import os
from collections.abc import Iterable, Sequence
from typing import Any

from elasticsearch import Elasticsearch

logger = logging.getLogger(__name__)

ES_URL = os.getenv("ES_URL", "http://localhost:9200")
ES_USER = os.getenv("ES_USER", "")
ES_PASS = os.getenv("ES_PASS", "")
ES_INDEX = "video_texts"
MAX_KEYWORD_HITS = int(os.getenv("ES_MAX_KEYWORD_HITS", "10000"))

FrameKey = tuple[Any, Any]

# Documents in `video_texts` are frame-level and only carry ocr_text / asr_text.
_SOURCE_FIELDS = {
    "all": ["ocr_text^3", "asr_text^2"],
    "ocr": ["ocr_text"],
    "asr": ["asr_text"],
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
            must.append({
                "multi_match": {
                    "query": query,
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
        keywords: Sequence[str],
        mode: str = "and",
        source: str = "all",
    ) -> set[FrameKey]:
        """Return the subset of (video_id, frame_index) whose OCR/ASR text matches.

        `frame_keys` is an iterable of (video_id, frame_index) tuples. Both sides
        of the join are frame-level: matching on video_id alone would let one
        matching frame drag in every other frame of the same video.
        """
        keys = list(frame_keys)
        if not keywords or not keys:
            return set(keys)

        video_ids = sorted({vid for vid, _ in keys})
        frame_ids = sorted({idx for _, idx in keys})
        fields = _SOURCE_FIELDS.get(source, _SOURCE_FIELDS["all"])
        clauses = [
            {"multi_match": {"query": kw, "fields": fields, "fuzziness": "AUTO"}}
            for kw in keywords
        ]
        bool_query: dict[str, Any] = {
            "should": clauses,
            "minimum_should_match": 1 if mode == "or" else len(clauses),
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
                "(raise ES_MAX_KEYWORD_HITS)", size
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
