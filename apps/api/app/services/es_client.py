import logging
from collections.abc import Iterable, Sequence
from time import perf_counter
from typing import Any

from elasticsearch import ApiError, ConnectionError, ConnectionTimeout, Elasticsearch

from app.config import Config

from app.services.text_normalize import normalize_text

logger = logging.getLogger(__name__)

ES_URL = Config.ES_URL
ES_USER = Config.ES_USER
ES_PASS = Config.ES_PASS
ES_REQUEST_TIMEOUT = Config.ES_REQUEST_TIMEOUT
ES_MAX_RETRIES = Config.ES_MAX_RETRIES
ES_INDEX = "video_texts"
MAX_KEYWORD_HITS = Config.ES_MAX_KEYWORD_HITS

FrameKey = tuple[Any, Any]


class ElasticsearchSearchError(RuntimeError):
    """Raised when Elasticsearch cannot serve a search request."""

    def __init__(self, operation: str) -> None:
        super().__init__(f"Elasticsearch {operation} failed")
        self.operation = operation


def _normalized_keywords(keywords: Sequence[str]) -> list[str]:
    return [keyword for keyword in (normalize_text(keyword) for keyword in keywords) if keyword]


DEFAULT_SEARCH_CONFIG: dict[str, Any] = {
    "query_type": "match",
    "fuzzy": False,
    "operator": "and",
    "minimum_should_match": "100%",
    "prefix_length": 2,
    "max_expansions": 20,
    "slop": 0,
}


def _resolve_search_config(config: dict[str, Any] | None) -> dict[str, Any]:
    return {**DEFAULT_SEARCH_CONFIG, **(config or {})}


def _keyword_clause(keyword: str, field: str, config: dict[str, Any]) -> dict[str, Any]:
    if config["query_type"] == "match_phrase":
        return {"match_phrase": {field: {"query": keyword, "slop": config["slop"]}}}

    options: dict[str, Any] = {"query": keyword, "operator": config["operator"]}
    if config["operator"] == "or":
        options["minimum_should_match"] = config["minimum_should_match"]
    if config["fuzzy"]:
        options.update({
            "fuzziness": "AUTO",
            "prefix_length": config["prefix_length"],
            "max_expansions": config["max_expansions"],
        })
    return {"match": {field: options}}


def _keyword_field_group(
    keywords: Sequence[str], field: str, relation: str, config: dict[str, Any] | None
) -> dict[str, Any] | None:
    """Build one source group; relation is between separate TagInput keywords."""
    normalized_keywords = _normalized_keywords(keywords)
    if not normalized_keywords:
        return None
    resolved_config = _resolve_search_config(config)
    clauses = [_keyword_clause(keyword, field, resolved_config) for keyword in normalized_keywords]
    return {
        "bool": {
            "should": clauses,
            "minimum_should_match": 1 if relation == "or" else len(clauses),
        }
    }


class ESClient:
    def __init__(self) -> None:
        if ES_USER and ES_PASS:
            self.es = Elasticsearch(
                ES_URL,
                basic_auth=(ES_USER, ES_PASS),
                request_timeout=ES_REQUEST_TIMEOUT,
                max_retries=ES_MAX_RETRIES,
                retry_on_timeout=True,
            )
        else:
            self.es = Elasticsearch(
                ES_URL,
                request_timeout=ES_REQUEST_TIMEOUT,
                max_retries=ES_MAX_RETRIES,
                retry_on_timeout=True,
            )

    def _search(
        self,
        body: dict[str, Any],
        *,
        operation: str,
        context: dict[str, Any],
    ) -> Any:
        """Execute a search with structured timing and availability errors."""
        started_at = perf_counter()
        try:
            response = self.es.search(index=ES_INDEX, body=body)
        except (ApiError, ConnectionError, ConnectionTimeout) as error:
            duration_ms = (perf_counter() - started_at) * 1000
            logger.exception(
                "Elasticsearch request failed operation=%s index=%s duration_ms=%.1f context=%s",
                operation,
                ES_INDEX,
                duration_ms,
                context,
            )
            raise ElasticsearchSearchError(operation) from error

        logger.info(
            "Elasticsearch request completed operation=%s index=%s duration_ms=%.1f context=%s",
            operation,
            ES_INDEX,
            (perf_counter() - started_at) * 1000,
            context,
        )
        return response

    def _msearch(
        self,
        searches: list[dict[str, Any]],
        *,
        operation: str,
        context: dict[str, Any],
    ) -> Any:
        """Execute a multi-search with structured timing and availability errors."""
        started_at = perf_counter()
        try:
            response = self.es.msearch(index=ES_INDEX, searches=searches)
        except (ApiError, ConnectionError, ConnectionTimeout) as error:
            duration_ms = (perf_counter() - started_at) * 1000
            logger.exception(
                "Elasticsearch multi-search failed operation=%s index=%s duration_ms=%.1f context=%s",
                operation,
                ES_INDEX,
                duration_ms,
                context,
            )
            raise ElasticsearchSearchError(operation) from error

        logger.info(
            "Elasticsearch multi-search completed operation=%s index=%s duration_ms=%.1f context=%s",
            operation,
            ES_INDEX,
            (perf_counter() - started_at) * 1000,
            context,
        )
        return response

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
        resp = self._search(
            body,
            operation="search_videos",
            context={"query": query, "size": size},
        )
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
        body = {"query": {"term": {"video_id": video_id}}, "size": 1}
        resp = self._search(
            body,
            operation="get_video",
            context={"video_id": video_id},
        )
        hits = resp["hits"]["hits"]
        source: dict[str, Any] | None = hits[0]["_source"] if hits else None
        return source

    def context_frame_keys(
        self,
        windows: Sequence[tuple[str, int, int]],
        count: int = 10,
    ) -> list[tuple[list[FrameKey], list[FrameKey]]]:
        """Return stored keyframe identities immediately around each interval.

        This deliberately queries Elasticsearch's frame catalogue rather than
        running another vector search. Results are aligned to ``windows`` and
        ordered chronologically within each before/after side.
        """
        if not windows:
            return []

        size = max(1, int(count))
        searches: list[dict[str, Any]] = []
        for video_id, start_frame_index, end_frame_index in windows:
            common_filter = [{"term": {"video_id": video_id}}]
            searches.extend([
                {},
                {
                    "query": {
                        "bool": {
                            "filter": common_filter + [
                                {"range": {"frame_id": {"lt": start_frame_index}}}
                            ]
                        }
                    },
                    "_source": ["video_id", "frame_id"],
                    "size": size,
                    "sort": [{"frame_id": {"order": "desc"}}],
                },
                {},
                {
                    "query": {
                        "bool": {
                            "filter": common_filter + [
                                {"range": {"frame_id": {"gt": end_frame_index}}}
                            ]
                        }
                    },
                    "_source": ["video_id", "frame_id"],
                    "size": size,
                    "sort": [{"frame_id": {"order": "asc"}}],
                },
            ])

        response = self._msearch(
            searches,
            operation="context_frame_keys",
            context={"window_count": len(windows), "count": size},
        )
        responses = response.get("responses", [])
        if len(responses) != len(windows) * 2:
            raise RuntimeError("Elasticsearch returned an incomplete context lookup response")

        contexts: list[tuple[list[FrameKey], list[FrameKey]]] = []
        for offset in range(0, len(responses), 2):
            before_response, after_response = responses[offset:offset + 2]
            if "error" in before_response or "error" in after_response:
                raise RuntimeError("Elasticsearch could not look up neighbouring keyframes")
            before = [
                (hit["_source"]["video_id"], hit["_source"]["frame_id"])
                for hit in before_response.get("hits", {}).get("hits", [])
            ]
            after = [
                (hit["_source"]["video_id"], hit["_source"]["frame_id"])
                for hit in after_response.get("hits", {}).get("hits", [])
            ]
            contexts.append((list(reversed(before)), after))
        return contexts

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
        ocr_search_config: dict[str, Any] | None = None,
        asr_search_config: dict[str, Any] | None = None,
    ) -> set[FrameKey]:
        """Return the subset of (video_id, frame_index) whose OCR/ASR text matches.

        OCR keywords match `ocr_text` only; ASR keywords match `asr_text` only.
        When both groups are non-empty they are AND-ed. `ocr_mode`/`asr_mode`
        control the relationship between separate keywords; each source's
        search config controls the DSL query for each individual keyword.

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
        ocr_group = _keyword_field_group(ocr, "ocr_text", ocr_mode or mode, ocr_search_config)
        asr_group = _keyword_field_group(asr, "asr_text", asr_mode or mode, asr_search_config)
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
        resp = self._search(
            body,
            operation="match_frames_by_keywords",
            context={
                "frame_key_count": len(keys),
                "ocr_keywords": ocr,
                "asr_keywords": asr,
                "ocr_mode": ocr_mode or mode,
                "asr_mode": asr_mode or mode,
            },
        )
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
        ocr_search_config: dict[str, Any] | None = None,
        asr_search_config: dict[str, Any] | None = None,
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
                _keyword_field_group(ocr, "ocr_text", ocr_mode or mode, ocr_search_config),
                _keyword_field_group(asr, "asr_text", asr_mode or mode, asr_search_config),
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
        page = 0
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
            hits = self._search(
                body,
                operation="keyword_frame_hits",
                context={
                    "page": page,
                    "page_size": size,
                    "keywords": list(keywords or []),
                    "ocr_keywords": ocr,
                    "asr_keywords": asr,
                    "ocr_mode": ocr_mode or mode,
                    "asr_mode": asr_mode or mode,
                    "ocr_search_config": ocr_search_config,
                    "asr_search_config": asr_search_config,
                    "allowed_video_count": len(allowed_video_ids or []),
                },
            )["hits"]["hits"]
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
            page += 1

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
        hits = self._search(
            body,
            operation="fetch_frame_texts",
            context={"frame_key_count": len(keys)},
        )["hits"]["hits"]
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
