from __future__ import annotations

import base64
import logging
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any

from app.config import Config
from app.services.embed import decode_image, enhance_query
from app.services.embedding_cache import TextEmbeddingCache
from app.services.ensemble_search import (
    EnsembleSearchError,
    EnsembleSearchOptions,
    EnsembleSearchResponse,
    EnsembleSearchService,
)
from app.services.es_client import es_client
from app.services.fusion import RankedSource, diversify_frames, reciprocal_rank_fusion
from app.services.milvus_client import get_milvus_client, get_vector_backend
from app.services.model_registry import get_model_registry

FrameData = dict[str, Any]
LOGGER = logging.getLogger(__name__)


def _retrieval_score(frame: Mapping[str, Any]) -> float:
    return float(frame.get("score") or frame.get("fusion_score") or 0.0)


def _enrich_frames(frames: Sequence[Mapping[str, Any]]) -> list[FrameData]:
    """Add display metadata from Elasticsearch while preserving fused ranking order."""
    video_ids = list(dict.fromkeys(str(frame.get("video_id", "")) for frame in frames))
    try:
        video_cache = es_client.get_videos(video_ids)
    except Exception as error:
        LOGGER.warning("Video metadata enrichment failed: %s", error)
        video_cache = {}
    enriched: list[FrameData] = []
    seen: set[str] = set()
    for raw_frame in frames:
        frame = dict(raw_frame)
        uid = str(frame.get("frame_uid", ""))
        if uid in seen:
            continue
        seen.add(uid)
        video_id = str(frame.get("video_id", ""))
        metadata = video_cache.get(video_id, {})
        frame["title"] = metadata.get("title", "")
        frame["description"] = metadata.get("description", "")
        frame["keywords"] = metadata.get("keywords", [])
        frame["watch_url"] = frame.get("youtube_url") or metadata.get("watch_url", "")
        frame["thumbnail_url"] = (
            f"/api/keyframes/{video_id}/{int(frame.get('frame_index', 0))}"
        )
        enriched.append(frame)
    return enriched


def _filter_tags(
    frames: Sequence[FrameData],
    tags: Sequence[str] | None,
    mode: str,
) -> list[FrameData]:
    if not tags:
        return list(frames)
    wanted = {tag.casefold() for tag in tags}
    filtered: list[FrameData] = []
    for frame in frames:
        available = {str(tag).casefold() for tag in frame.get("tags", [])}
        matches = wanted.issubset(available) if mode == "and" else bool(wanted & available)
        if matches:
            filtered.append(frame)
    return filtered


def _filter_keywords(
    frames: Sequence[FrameData],
    keywords: Sequence[str] | None,
    mode: str,
    source: str,
) -> list[FrameData]:
    if not keywords or not frames:
        return list(frames)
    video_ids = list(dict.fromkeys(str(frame["video_id"]) for frame in frames))
    matched_ids = set(
        es_client.filter_videos_by_keywords(video_ids, list(keywords), mode=mode, source=source)
    )
    return [frame for frame in frames if str(frame["video_id"]) in matched_ids]


_ensemble_service: EnsembleSearchService | None = None


def get_ensemble_search_service() -> EnsembleSearchService:
    global _ensemble_service
    if _ensemble_service is None:
        _ensemble_service = EnsembleSearchService(
            registry=get_model_registry(),
            vector_backend=get_vector_backend(),
            query_enhancer=enhance_query,
            embedding_cache=TextEmbeddingCache(Config.TEXT_EMBEDDING_CACHE_SIZE),
        )
    return _ensemble_service


def reset_ensemble_search_service() -> None:
    global _ensemble_service
    _ensemble_service = None


def _candidate_options(
    options: EnsembleSearchOptions,
    *,
    has_filters: bool,
) -> EnsembleSearchOptions:
    expanded_limit = max(
        options.result_top_k,
        min(options.candidate_top_k, options.result_top_k * 4) if has_filters else 0,
    )
    return replace(
        options,
        result_top_k=expanded_limit,
        min_time_gap_seconds=0.0,
        max_per_video=0,
    )


def _postprocess_response(
    response: EnsembleSearchResponse,
    options: EnsembleSearchOptions,
    *,
    tags: Sequence[str] | None,
    tag_mode: str,
    keywords: Sequence[str] | None,
    keyword_mode: str,
    keyword_source: str,
) -> EnsembleSearchResponse:
    frames = [dict(frame) for frame in response.results]
    frames = _filter_tags(frames, tags, tag_mode)
    frames = _filter_keywords(frames, keywords, keyword_mode, keyword_source)
    frames = diversify_frames(
        frames,
        min_time_gap_seconds=options.min_time_gap_seconds,
        max_per_video=options.max_per_video,
        limit=options.result_top_k,
    )
    return replace(response, results=_enrich_frames(frames))


def search_text_with_meta(
    query: str,
    *,
    options: EnsembleSearchOptions,
    tags: Sequence[str] | None = None,
    tag_mode: str = "and",
    keywords: Sequence[str] | None = None,
    keyword_mode: str = "and",
    keyword_source: str = "all",
) -> EnsembleSearchResponse:
    """Run multi-model text retrieval followed by structured metadata filtering."""
    has_filters = bool(tags or keywords)
    candidate_options = _candidate_options(options, has_filters=has_filters)
    response = get_ensemble_search_service().search_text(query, candidate_options)
    return _postprocess_response(
        response,
        options,
        tags=tags,
        tag_mode=tag_mode,
        keywords=keywords,
        keyword_mode=keyword_mode,
        keyword_source=keyword_source,
    )


def search_image_with_meta(
    image_bytes: bytes,
    *,
    options: EnsembleSearchOptions,
    tags: Sequence[str] | None = None,
    tag_mode: str = "and",
    keywords: Sequence[str] | None = None,
    keyword_mode: str = "and",
    keyword_source: str = "all",
) -> EnsembleSearchResponse:
    """Run multi-model image retrieval followed by metadata filtering."""
    has_filters = bool(tags or keywords)
    candidate_options = _candidate_options(options, has_filters=has_filters)
    response = get_ensemble_search_service().search_image(
        decode_image(image_bytes),
        candidate_options,
    )
    return _postprocess_response(
        response,
        options,
        tags=tags,
        tag_mode=tag_mode,
        keywords=keywords,
        keyword_mode=keyword_mode,
        keyword_source=keyword_source,
    )


def search_composed_with_meta(
    feedback_text: str,
    image_bytes: bytes,
    *,
    original_query: str | None = None,
    text_weight: float,
    options: EnsembleSearchOptions,
) -> EnsembleSearchResponse:
    """Run paper-inspired composed text+image feedback retrieval."""
    response = get_ensemble_search_service().search_composed(
        feedback_text,
        decode_image(image_bytes),
        original_query=original_query,
        text_weight=text_weight,
        options=options,
    )
    return replace(response, results=_enrich_frames(response.results))


def search_text(
    query: str = "",
    tags: Sequence[str] | None = None,
    tag_mode: str = "and",
    keywords: Sequence[str] | None = None,
    keyword_mode: str = "and",
    keyword_source: str = "all",
    topk: int = 20,
    enhance: bool = True,
) -> list[FrameData]:
    """Compatibility wrapper used by current callers."""
    options = EnsembleSearchOptions(
        candidate_top_k=max(200, topk * 4),
        result_top_k=topk,
        use_enhanced_query=enhance,
    )
    return search_text_with_meta(
        query,
        options=options,
        tags=tags,
        tag_mode=tag_mode,
        keywords=keywords,
        keyword_mode=keyword_mode,
        keyword_source=keyword_source,
    ).results


def search_image(
    image_bytes: bytes,
    tags: Sequence[str] | None = None,
    tag_mode: str = "and",
    keywords: Sequence[str] | None = None,
    keyword_mode: str = "and",
    keyword_source: str = "all",
    topk: int = 20,
) -> list[FrameData]:
    """Compatibility wrapper used by current callers."""
    options = EnsembleSearchOptions(candidate_top_k=max(200, topk * 4), result_top_k=topk)
    return search_image_with_meta(
        image_bytes,
        options=options,
        tags=tags,
        tag_mode=tag_mode,
        keywords=keywords,
        keyword_mode=keyword_mode,
        keyword_source=keyword_source,
    ).results


def search_video_frames(
    video_id: str,
    frame_index: int | None = None,
    range: int = 5,
) -> list[FrameData]:
    """Get ordered Frames from the primary model collection without dummy vectors."""
    frames = get_milvus_client().list_video_frames(
        video_id,
        frame_index=frame_index,
        frame_range=range,
    )
    frames = _enrich_frames(sorted(frames, key=lambda frame: int(frame.get("frame_index", 0))))
    if frame_index is None:
        return frames
    position = next(
        (
            index
            for index, frame in enumerate(frames)
            if int(frame.get("frame_index", -1)) == frame_index
        ),
        None,
    )
    if position is None:
        return frames
    return frames[max(0, position - range) : position + range + 1]


def search_similar_frames(video_id: str, frame_index: int, topk: int = 12) -> list[FrameData]:
    """Find visually similar Frames in every model space and fuse the rankings."""
    registry = get_model_registry()
    backend = get_vector_backend()
    sources: list[RankedSource] = []
    for spec in registry.enabled_specs():
        if spec.weight <= 0.0:
            continue
        try:
            embedding = get_milvus_client(spec).get_frame_embedding(video_id, frame_index)
            if embedding is None:
                continue
            ranking = backend.search(spec, embedding, topk + 1)
            sources.append(RankedSource(f"{spec.model_id}:similar", ranking, spec.weight))
        except Exception as error:
            LOGGER.warning("Similar-frame search failed for %s: %s", spec.model_id, error)
    if not sources:
        raise EnsembleSearchError("no embedding model could search for similar Frames")
    fused = reciprocal_rank_fusion(sources)
    fused = [
        frame
        for frame in fused
        if not (
            str(frame.get("video_id")) == video_id
            and int(frame.get("frame_index", -1)) == frame_index
        )
    ]
    return _enrich_frames(fused[:topk])


def _decode_box_image(payload: str) -> bytes:
    encoded = payload.split(",", maxsplit=1)[1] if payload.startswith("data:") else payload
    return base64.b64decode(encoded, validate=True)


def _best_temporal_sequence(
    groups: Sequence[Sequence[FrameData]],
    window_seconds: float,
) -> list[FrameData]:
    """Find the highest-scoring ordered event sequence with dynamic programming."""
    if not groups or any(not group for group in groups):
        return []
    states: list[tuple[float, list[FrameData]]] = [
        (_retrieval_score(frame), [frame]) for frame in groups[0]
    ]
    for group in groups[1:]:
        next_states: list[tuple[float, list[FrameData]]] = []
        for current in group:
            current_time = float(current.get("pts_time") or 0.0)
            valid = [
                state
                for state in states
                if 0.0
                <= current_time - float(state[1][-1].get("pts_time") or 0.0)
                <= window_seconds
                and current_time - float(state[1][0].get("pts_time") or 0.0)
                <= window_seconds
            ]
            if not valid:
                continue
            best_score, best_path = max(valid, key=lambda state: state[0])
            next_states.append(
                (
                    best_score
                    + _retrieval_score(current),
                    [*best_path, current],
                )
            )
        states = next_states
        if not states:
            return []
    return max(states, key=lambda state: state[0])[1]


def _merge_temporal_sequences(
    per_box: Sequence[Sequence[FrameData]],
    window: float,
) -> list[FrameData]:
    common_videos = set.intersection(
        *[{str(frame["video_id"]) for frame in box} for box in per_box]
    ) if per_box else set()
    sequences: list[tuple[float, str, list[FrameData]]] = []
    for video_id in sorted(common_videos):
        groups = [
            sorted(
                [frame for frame in box if str(frame["video_id"]) == video_id],
                key=lambda frame: float(frame.get("pts_time", 0.0)),
            )
            for box in per_box
        ]
        sequence = _best_temporal_sequence(groups, window)
        if not sequence:
            continue
        sequence_score = sum(_retrieval_score(frame) for frame in sequence) / len(sequence)
        for index, frame in enumerate(sequence):
            frame["sequence_idx"] = index
            frame["score"] = sequence_score
        sequences.append((sequence_score, video_id, sequence))
    sequences.sort(key=lambda item: (-item[0], item[1]))
    return [frame for _, _, sequence in sequences for frame in sequence]


def multi_box_search(
    box_queries: Sequence[Mapping[str, Any]],
    temporal_window: float = 120.0,
    topk: int = 200,
    enhance: bool = True,
) -> list[FrameData]:
    """Run ensemble retrieval per BoxQuery and align ordered events by timestamp."""
    per_box: list[list[FrameData]] = []
    for box in box_queries:
        text = str(box.get("text", ""))
        image = str(box.get("image", ""))
        box_topk = int(box.get("topk", topk))
        if text:
            box_enhance = box.get("enhance")
            per_box.append(
                search_text(
                    query=text,
                    tags=box.get("tags"),
                    tag_mode=str(box.get("tag_match_mode", "and")),
                    keywords=box.get("keywords"),
                    keyword_mode=str(box.get("key_match_mode", "and")),
                    topk=box_topk,
                    enhance=enhance if box_enhance is None else bool(box_enhance),
                )
            )
        elif image:
            per_box.append(
                search_image(
                    image_bytes=_decode_box_image(image),
                    tags=box.get("tags"),
                    tag_mode=str(box.get("tag_match_mode", "and")),
                    keywords=box.get("keywords"),
                    keyword_mode=str(box.get("key_match_mode", "and")),
                    topk=box_topk,
                )
            )
    if len(per_box) <= 1:
        return per_box[0] if per_box else []
    return _merge_temporal_sequences(per_box, temporal_window)[:topk]
