import logging
from collections.abc import Iterable, Sequence
from typing import Any

from elasticsearch import Elasticsearch

from app.config import Config
from app.services.es_schema import ES_ALIAS, frame_key

logger = logging.getLogger(__name__)

ES_URL = Config.ES_URL
ES_USER = Config.ES_USER
ES_PASS = Config.ES_PASS
ES_INDEX = ES_ALIAS
MAX_KEYWORD_HITS = Config.ES_MAX_KEYWORD_HITS

# ES rounds a bare percentage down, so "75%" of two clauses is one — every
# two-word keyword would silently degrade from AND to OR. The "2<" prefix keeps
# short keywords strict and only relaxes from the third word on.
OCR_MINIMUM_SHOULD_MATCH = "2<75%"
# AUTO fuzziness with a one-character prefix expands into thousands of terms on
# this vocabulary: "ajinomoto" measured 264ms against 4ms strict, for 1% more
# recall. Two characters plus a capped expansion puts it back under 30ms.
OCR_FUZZY_PREFIX_LENGTH = 2
OCR_FUZZY_MAX_EXPANSIONS = 20

FrameKey = tuple[Any, Any]


def _nonempty_keywords(keywords: Sequence[str]) -> list[str]:
    return [keyword for keyword in keywords if keyword.strip()]


def _field_group(clauses: list[dict[str, Any]], mode: str) -> dict[str, Any] | None:
    if not clauses:
        return None
    return {
        "bool": {
            "should": clauses,
            "minimum_should_match": 1 if mode == "or" else len(clauses),
        }
    }


def resolve_asr_phrase_slop(slop: int | None) -> int:
    """Fall back to the deployment default when the request leaves slop unset."""
    return Config.ES_ASR_PHRASE_SLOP if slop is None else max(0, slop)


def _phrase_clause(keyword: str, field: str, slop: int = 0) -> dict[str, Any]:
    """Phrase-match one keyword against `field`, allowing `slop` words of drift."""
    params: dict[str, Any] = {"query": keyword}
    if slop:
        params["slop"] = slop
    return {"match_phrase": {field: params}}


def _phrase_field_group(
    keywords: Sequence[str], field: str, mode: str, slop: int = 0
) -> dict[str, Any] | None:
    """Build an ordered, adjacent phrase group over `field` and its folded twin.

    ASR text is sequential, so phrase matching is the right fit — order and
    adjacency in the query reflect order and adjacency in the transcript. Each
    keyword tries the diacritic-preserving field first (boosted, so an exactly
    typed query wins) and falls back to the folded subfield, which is the only
    way a query typed without diacritics matches at all. Both clauses stay
    phrases: this loosens *spelling*, never word order.

    `slop` is how many positions the transcript may drift from the typed phrase
    — 0 demands strict adjacency, 2 tolerates a filler word between terms. It
    never reorders: a phrase query stays a phrase query.
    """
    original_keywords = _nonempty_keywords(keywords)
    clauses: list[dict[str, Any]] = []
    for keyword in original_keywords:
        exact = _phrase_clause(keyword, field, slop)
        exact["match_phrase"][field]["boost"] = 3
        clauses.append({
            "bool": {
                "should": [exact, _phrase_clause(keyword, f"{field}.folded", slop)],
                "minimum_should_match": 1,
            }
        })
    return _field_group(clauses, mode)


def _ocr_fuzzy_field_group(
    keywords: Sequence[str], field: str, mode: str
) -> dict[str, Any] | None:
    """Build an unordered, typo-tolerant match group for one field.

    OCR text on this dataset is a scrambled bag of words (no diacritics, no
    stable order), so `match_phrase` structurally cannot match a multi-word
    keyword. Each keyword becomes a `match` requiring every word up to two and
    75% beyond that, plus AUTO fuzziness for typo tolerance.

    Fuzziness is skipped for any keyword *containing* a digit. Plate numbers,
    timecodes and video ids ("51F", "L21_V001", "063127") have no meaningful
    edit-distance neighbours — "51F" measured 3 hits strict against 223 fuzzy.
    """
    original_keywords = _nonempty_keywords(keywords)
    clauses: list[dict[str, Any]] = []
    for keyword in original_keywords:
        match_params: dict[str, Any] = {
            "query": keyword,
            "minimum_should_match": OCR_MINIMUM_SHOULD_MATCH,
        }
        if not any(char.isdigit() for char in keyword):
            match_params["fuzziness"] = "AUTO"
            match_params["prefix_length"] = OCR_FUZZY_PREFIX_LENGTH
            match_params["max_expansions"] = OCR_FUZZY_MAX_EXPANSIONS
        clauses.append({"match": {field: match_params}})
    return _field_group(clauses, mode)


def _keyword_field_group(
    keywords: Sequence[str], field: str, mode: str, search_mode: str, slop: int = 0
) -> dict[str, Any] | None:
    """Build one field group using the requested query-time strategy.

    `fuzzy` is the unordered, typo-tolerant bag-of-words match; `exact` is the
    ordered, adjacent phrase. Either strategy applies to either field — OCR and
    ASR only differ in which one is the sensible default, not in what is legal.

    `slop` only reaches the phrase strategy; a fuzzy bag of words has no order
    to loosen.
    """
    if search_mode == "fuzzy":
        return _ocr_fuzzy_field_group(keywords, field, mode)
    if search_mode == "exact":
        return _phrase_field_group(keywords, field, mode, slop)
    raise ValueError(f"Unsupported keyword search mode: {search_mode}")


def _combine_field_groups(
    ocr_group: dict[str, Any] | None,
    asr_group: dict[str, Any] | None,
    keyword_field_mode: str,
) -> list[dict[str, Any]]:
    """Select and combine independently configured OCR and ASR field groups."""
    if keyword_field_mode == "ocr":
        return [ocr_group] if ocr_group is not None else []
    if keyword_field_mode == "asr":
        return [asr_group] if asr_group is not None else []

    groups = [group for group in (ocr_group, asr_group) if group is not None]
    if keyword_field_mode == "and" or len(groups) < 2:
        return groups
    if keyword_field_mode == "or":
        return [{"bool": {"should": groups, "minimum_should_match": 1}}]
    raise ValueError(f"Unsupported keyword field mode: {keyword_field_mode}")


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

    def score_frames_by_keywords(
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
        ocr_search_mode: str = "exact",
        asr_search_mode: str = "exact",
        keyword_field_mode: str = "and",
        asr_phrase_slop: int | None = None,
    ) -> dict[FrameKey, float]:
        """Map each matching (video_id, frame_index) to its BM25 relevance score.

        `ocr_search_mode`/`asr_search_mode` pick each field's strategy — fuzzy
        unordered terms or an ordered, adjacent phrase. `keyword_field_mode`
        decides whether the two field groups are AND-ed, OR-ed, or whether only
        one of them is consulted. Within each group, `ocr_mode`/`asr_mode`
        controls and/or, falling back to `mode` when unset.

        The score matters because a boolean verdict cannot separate a keyword
        that identifies a frame from one that matches half the corpus — the
        station watermark "htv online" is on 49% of frames. Only IDF demotes it.

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
            return dict.fromkeys(keys, 0.0)

        must = _combine_field_groups(
            _keyword_field_group(ocr, "ocr_text", ocr_mode or mode, ocr_search_mode),
            _keyword_field_group(
                asr,
                "asr_text",
                asr_mode or mode,
                asr_search_mode,
                resolve_asr_phrase_slop(asr_phrase_slop),
            ),
            keyword_field_mode,
        )
        if not must:
            return dict.fromkeys(keys, 0.0)

        bool_query: dict[str, Any] = {
            "must": must,
            # One keyed term list, not separate video_id/frame_id lists — those
            # would match the cross product of the two, far more docs than the
            # pairs actually asked about.
            "filter": [{"terms": {"frame_key": [frame_key(vid, idx) for vid, idx in keys]}}],
        }
        size = min(MAX_KEYWORD_HITS, max(len(keys), 100))
        body = {
            "query": {"bool": bool_query},
            "_source": ["video_id", "frame_id"],
            "size": size,
            "track_total_hits": False,
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
        scored = {
            (hit["_source"]["video_id"], hit["_source"]["frame_id"]): float(
                hit.get("_score") or 0.0
            )
            for hit in hits
        }
        return {key: scored[key] for key in keys if key in scored}

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
        ocr_search_mode: str = "exact",
        asr_search_mode: str = "exact",
        keyword_field_mode: str = "and",
        asr_phrase_slop: int | None = None,
    ) -> set[FrameKey]:
        """Return the subset of (video_id, frame_index) whose OCR/ASR text matches."""
        return set(
            self.score_frames_by_keywords(
                frame_keys,
                keywords=keywords,
                mode=mode,
                source=source,
                ocr_keywords=ocr_keywords,
                asr_keywords=asr_keywords,
                ocr_mode=ocr_mode,
                asr_mode=asr_mode,
                ocr_search_mode=ocr_search_mode,
                asr_search_mode=asr_search_mode,
                keyword_field_mode=keyword_field_mode,
                asr_phrase_slop=asr_phrase_slop,
            )
        )

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
        ocr_search_mode: str = "exact",
        asr_search_mode: str = "exact",
        keyword_field_mode: str = "and",
        asr_phrase_slop: int | None = None,
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

        must = _combine_field_groups(
            _keyword_field_group(ocr, "ocr_text", ocr_mode or mode, ocr_search_mode),
            _keyword_field_group(
                asr,
                "asr_text",
                asr_mode or mode,
                asr_search_mode,
                resolve_asr_phrase_slop(asr_phrase_slop),
            ),
            keyword_field_mode,
        )
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
                "track_total_hits": False,
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
