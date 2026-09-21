"""Fast REPEAT witness lookups backed by a precomputed SigLIP2 graph."""

from __future__ import annotations

import logging
import threading
from collections.abc import Sequence
from pathlib import Path

from app.config import Config, PROJECT_DIR
from app.services.repeat_graph import FrameKey, RepeatFrameDetails, RepeatGraph, RepeatGraphError, load_repeat_graph, repeat_graph_manifest_path

logger = logging.getLogger(__name__)
RepeatCandidate = tuple[str, int, float]
_graph_lock = threading.Lock()
_loaded_graph: RepeatGraph | None = None
_loaded_signature: tuple[int, int, int, int] | None = None
_graph_error_signature: tuple[int, int, int, int] | None = None


def _signature(graph_path: Path, manifest_path: Path) -> tuple[int, int, int, int] | None:
    try:
        graph, manifest = graph_path.stat(), manifest_path.stat()
    except OSError:
        return None
    return graph.st_mtime_ns, graph.st_size, manifest.st_mtime_ns, manifest.st_size


def clear_repeat_cache() -> None:
    global _loaded_graph, _loaded_signature, _graph_error_signature
    with _graph_lock:
        _loaded_graph = None
        _loaded_signature = None
        _graph_error_signature = None


def _repeat_graph() -> RepeatGraph | None:
    graph_path = Config.SIGLIP2_REPEAT_GRAPH
    manifest_path = repeat_graph_manifest_path(graph_path)
    signature = _signature(graph_path, manifest_path)
    if signature is None:
        return None
    global _loaded_graph, _loaded_signature, _graph_error_signature
    with _graph_lock:
        if _loaded_graph is not None and _loaded_signature == signature:
            return _loaded_graph
        if _graph_error_signature == signature:
            return None
        try:
            graph = load_repeat_graph(
                graph_path,
                manifest_path,
                metadata_path=PROJECT_DIR / "data" / "metadata" / "concatenate-data-b1.json",
            )
        except RepeatGraphError as error:
            logger.warning("REPEAT graph unavailable: %s", error)
            _loaded_graph = None
            _loaded_signature = None
            _graph_error_signature = signature
            return None
        _loaded_graph, _loaded_signature, _graph_error_signature = graph, signature, None
        return graph


def find_repeat_frame_details(
    frames: Sequence[RepeatCandidate],
    exclude_frame: FrameKey | None = None,
) -> dict[FrameKey, RepeatFrameDetails]:
    graph = _repeat_graph()
    if graph is None:
        return {}
    candidates = tuple(dict.fromkeys((str(video_id), int(frame_index)) for video_id, frame_index, _ in frames))
    return graph.details_for(candidates, exclude_frame=exclude_frame)


def find_repeat_frame_keys(frames: Sequence[RepeatCandidate]) -> set[FrameKey]:
    return set(find_repeat_frame_details(frames))
