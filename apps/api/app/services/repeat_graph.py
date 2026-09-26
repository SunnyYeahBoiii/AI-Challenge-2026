"""Load and query the precomputed SigLIP2 visual-repeat graph."""

from __future__ import annotations

from collections.abc import Sequence
import json
import logging
from pathlib import Path
import threading
from typing import TypedDict
from zipfile import BadZipFile

import numpy as np

from app.config import Config


logger = logging.getLogger(__name__)

FrameKey = tuple[str, int]


class RepeatFrameReference(TypedDict):
    """A duplicate frame identity safe to return to the browser."""

    video_id: str
    frame_index: int


class RepeatFrameDetails(TypedDict, total=False):
    """The selected repeat witnesses for one frame."""

    in_video_highest_duplicate: RepeatFrameReference
    in_video_furthest_duplicate: RepeatFrameReference
    out_video_highest_duplicate: RepeatFrameReference


class RepeatGraph:
    """Immutable CSR adjacency graph keyed by video and frame index."""

    def __init__(
        self,
        *,
        source_path: Path,
        video_ids: np.ndarray,
        frame_indices: np.ndarray,
        indptr: np.ndarray,
        neighbors: np.ndarray,
        cosines: np.ndarray,
    ) -> None:
        self.video_ids = video_ids
        self.frame_indices = frame_indices
        self.indptr = indptr
        self.neighbors = neighbors
        self.cosines = cosines
        self.cache_key = f"siglip2:{source_path}:{source_path.stat().st_mtime_ns}"
        unique_videos, starts, counts = np.unique(
            video_ids, return_index=True, return_counts=True
        )
        self._video_ranges = {
            str(video_id): (int(start), int(start + count))
            for video_id, start, count in zip(unique_videos, starts, counts, strict=True)
        }

    @classmethod
    def load(cls, graph_path: Path, manifest_path: Path) -> RepeatGraph:
        """Load a graph after validating its manifest and CSR structure."""
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("format_version") != 1:
            raise ValueError("unsupported repeat graph format version")
        if manifest.get("model_id") != "siglip2" or manifest.get("embedding_dim") != 1152:
            raise ValueError("repeat graph was not built with the expected SigLIP2 model")

        with np.load(graph_path, allow_pickle=False) as archive:
            required = {
                "format_version",
                "video_ids",
                "frame_indices",
                "indptr",
                "neighbors",
                "cosines",
            }
            missing = required.difference(archive.files)
            if missing:
                raise ValueError(f"repeat graph is missing arrays: {sorted(missing)}")
            format_version = np.asarray(archive["format_version"])
            video_ids = np.asarray(archive["video_ids"])
            frame_indices = np.asarray(archive["frame_indices"])
            indptr = np.asarray(archive["indptr"])
            neighbors = np.asarray(archive["neighbors"])
            cosines = np.asarray(archive["cosines"])

        if format_version.shape != (1,) or int(format_version[0]) != 1:
            raise ValueError("repeat graph archive has an unsupported format version")
        node_count = int(manifest.get("node_count", -1))
        edge_count = int(manifest.get("directed_edge_count", -1))
        if video_ids.shape != (node_count,) or frame_indices.shape != (node_count,):
            raise ValueError("repeat graph node arrays do not match the manifest")
        if indptr.shape != (node_count + 1,):
            raise ValueError("repeat graph indptr does not match the node count")
        if neighbors.shape != (edge_count,) or cosines.shape != (edge_count,):
            raise ValueError("repeat graph edge arrays do not match the manifest")
        if int(indptr[0]) != 0 or int(indptr[-1]) != edge_count:
            raise ValueError("repeat graph indptr bounds are invalid")
        if np.any(indptr[1:] < indptr[:-1]):
            raise ValueError("repeat graph indptr must be monotonic")
        if edge_count and int(np.max(neighbors)) >= node_count:
            raise ValueError("repeat graph contains a neighbor index outside the node range")
        if not np.isfinite(cosines).all():
            raise ValueError("repeat graph contains a non-finite cosine score")
        if node_count > 1:
            previous_videos = video_ids[:-1]
            current_videos = video_ids[1:]
            if np.any(current_videos < previous_videos):
                raise ValueError("repeat graph nodes must be sorted by video and frame")
            same_video = current_videos == previous_videos
            if np.any(frame_indices[1:][same_video] <= frame_indices[:-1][same_video]):
                raise ValueError("repeat graph frame keys must be unique and sorted")

        return cls(
            source_path=graph_path,
            video_ids=video_ids,
            frame_indices=frame_indices,
            indptr=indptr,
            neighbors=neighbors,
            cosines=cosines,
        )

    def _node_index(self, key: FrameKey) -> int | None:
        bounds = self._video_ranges.get(key[0])
        if bounds is None:
            return None
        start, end = bounds
        relative = int(np.searchsorted(self.frame_indices[start:end], key[1]))
        index = start + relative
        if index >= end or int(self.frame_indices[index]) != key[1]:
            return None
        return index

    def _reference(self, node_index: int) -> RepeatFrameReference:
        return {
            "video_id": str(self.video_ids[node_index]),
            "frame_index": int(self.frame_indices[node_index]),
        }

    def find_repeat_frame_details(
        self, keys: Sequence[FrameKey]
    ) -> dict[FrameKey, RepeatFrameDetails]:
        """Return the best global graph witnesses for each requested frame."""
        result: dict[FrameKey, RepeatFrameDetails] = {}
        for key in keys:
            node_index = self._node_index(key)
            if node_index is None:
                continue
            start = int(self.indptr[node_index])
            end = int(self.indptr[node_index + 1])
            if start == end:
                continue
            neighbor_nodes = self.neighbors[start:end]
            scores = self.cosines[start:end]
            source_video_id, source_frame_index = key
            same_video_positions = [
                position
                for position, neighbor in enumerate(neighbor_nodes)
                if str(self.video_ids[int(neighbor)]) == source_video_id
            ]
            outside_positions = [
                position
                for position, neighbor in enumerate(neighbor_nodes)
                if str(self.video_ids[int(neighbor)]) != source_video_id
            ]
            details: RepeatFrameDetails = {}
            if same_video_positions:
                highest = max(
                    same_video_positions,
                    key=lambda position: (
                        float(scores[position]),
                        abs(
                            int(self.frame_indices[int(neighbor_nodes[position])])
                            - source_frame_index
                        ),
                        int(self.frame_indices[int(neighbor_nodes[position])]),
                    ),
                )
                furthest = max(
                    same_video_positions,
                    key=lambda position: (
                        abs(
                            int(self.frame_indices[int(neighbor_nodes[position])])
                            - source_frame_index
                        ),
                        float(scores[position]),
                        int(self.frame_indices[int(neighbor_nodes[position])]),
                    ),
                )
                details["in_video_highest_duplicate"] = self._reference(
                    int(neighbor_nodes[highest])
                )
                details["in_video_furthest_duplicate"] = self._reference(
                    int(neighbor_nodes[furthest])
                )
            if outside_positions:
                highest_outside = min(
                    outside_positions,
                    key=lambda position: (
                        -float(scores[position]),
                        str(self.video_ids[int(neighbor_nodes[position])]),
                        int(self.frame_indices[int(neighbor_nodes[position])]),
                    ),
                )
                details["out_video_highest_duplicate"] = self._reference(
                    int(neighbor_nodes[highest_outside])
                )
            if details:
                result[key] = details
        return result


_graph: RepeatGraph | None = None
_load_attempted = False
_graph_lock = threading.Lock()


def get_repeat_graph() -> RepeatGraph | None:
    """Load the configured graph once, returning None so Milvus can be used as fallback."""
    global _graph, _load_attempted
    with _graph_lock:
        if _load_attempted:
            return _graph
        _load_attempted = True
        graph_path = Path(Config.REPEAT_GRAPH_PATH)
        manifest_path = Path(Config.REPEAT_GRAPH_MANIFEST_PATH)
        if not graph_path.is_file() or not manifest_path.is_file():
            logger.warning("Repeat graph files are missing; falling back to Milvus")
            return None
        try:
            _graph = RepeatGraph.load(graph_path, manifest_path)
        except (BadZipFile, KeyError, OSError, ValueError) as error:
            logger.warning("Could not load repeat graph; falling back to Milvus: %s", error)
        return _graph
