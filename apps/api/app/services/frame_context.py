"""Lookup service for non-ranked keyframes surrounding official search hits."""

from collections.abc import Sequence
from typing import Any

from app.services.encoders import manager
from app.services.es_client import es_client
from app.services.hybrid_search.common import Frame, FrameKey, _enrich_frames
from app.services.milvus_client import get_milvus_client

CONTEXT_FRAME_COUNT = 10
ContextWindow = tuple[str, int, int]


class FrameContextLookupError(RuntimeError):
    """Elasticsearch could not identify neighbouring stored keyframes."""


def _frame_key(frame: Frame) -> FrameKey:
    return (str(frame.get("video_id") or ""), int(frame.get("frame_index") or 0))


def get_frame_contexts(windows: Sequence[ContextWindow]) -> tuple[str, list[dict[str, Any]]]:
    """Fetch metadata for each interval's neighbours without vector search.

    The returned list has one element for every requested window, even when a
    keyframe is absent from Milvus. That lets the UI retain an empty side rather
    than treating a partially indexed video as a failed result.
    """
    normalized_windows = [
        (str(video_id), int(start_frame_index), int(end_frame_index))
        for video_id, start_frame_index, end_frame_index in windows
    ]
    collection_name = manager.active_collection_name()
    try:
        key_groups = es_client.context_frame_keys(normalized_windows, CONTEXT_FRAME_COUNT)
    except Exception as error:
        raise FrameContextLookupError("Could not look up neighbouring keyframes") from error
    requested_keys = [key for before, after in key_groups for key in (*before, *after)]
    frames_by_key = {
        _frame_key(frame): frame
        for frame in _enrich_frames(
            get_milvus_client(collection_name).query_frame_keys(requested_keys) if requested_keys else []
        )
    }

    contexts: list[dict[str, Any]] = []
    for (video_id, start_frame_index, end_frame_index), (before, after) in zip(
        normalized_windows, key_groups, strict=True
    ):
        contexts.append({
            "video_id": video_id,
            "start_frame_index": start_frame_index,
            "end_frame_index": end_frame_index,
            "before": [frames_by_key[key] for key in before if key in frames_by_key],
            "after": [frames_by_key[key] for key in after if key in frames_by_key],
        })
    return collection_name, contexts
