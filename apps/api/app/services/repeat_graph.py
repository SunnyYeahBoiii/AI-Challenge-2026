"""Runtime loader for the shareable precomputed SigLIP2 REPEAT graph."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypedDict, cast

import numpy as np
import numpy.typing as npt

FrameKey = tuple[str, int]
REPEAT_GRAPH_FORMAT_VERSION = 1
SIGLIP2_REPEAT_MODEL_ID = "siglip2"


class RepeatGraphError(RuntimeError):
    """Raised when a graph artifact is missing, corrupted, or mismatched."""


class RepeatFrameReference(TypedDict):
    video_id: str
    frame_index: int
    cosine: float


class RepeatFrameDetails(TypedDict, total=False):
    in_video_highest_duplicate: RepeatFrameReference
    in_video_furthest_duplicate: RepeatFrameReference
    out_video_highest_duplicate: RepeatFrameReference


def repeat_graph_manifest_path(graph_path: Path) -> Path:
    return graph_path.with_suffix(".manifest.json")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class RepeatGraph:
    video_ids: npt.NDArray[np.str_]
    frame_indices: npt.NDArray[np.int64]
    indptr: npt.NDArray[np.uint64]
    neighbors: npt.NDArray[np.uint32]
    cosines: npt.NDArray[np.float32]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "_node_by_frame",
            {
                (str(video_id), int(frame_index)): index
                for index, (video_id, frame_index) in enumerate(
                    zip(self.video_ids, self.frame_indices, strict=True)
                )
            },
        )

    def details_for(
        self,
        frames: Sequence[FrameKey],
        *,
        exclude_frame: FrameKey | None = None,
    ) -> dict[FrameKey, RepeatFrameDetails]:
        node_by_frame = cast(dict[FrameKey, int], getattr(self, "_node_by_frame"))
        excluded = (str(exclude_frame[0]), int(exclude_frame[1])) if exclude_frame else None
        details_by_frame: dict[FrameKey, RepeatFrameDetails] = {}
        for video_id, frame_index in dict.fromkeys((str(v), int(i)) for v, i in frames):
            node = node_by_frame.get((video_id, frame_index))
            if node is None:
                continue
            start, end = int(self.indptr[node]), int(self.indptr[node + 1])
            if start == end:
                continue
            neighbor_nodes, scores = self.neighbors[start:end], self.cosines[start:end]
            eligible = [
                offset for offset, neighbor in enumerate(neighbor_nodes)
                if (str(self.video_ids[int(neighbor)]), int(self.frame_indices[int(neighbor)])) != excluded
            ]
            same_video = [
                offset for offset in eligible if str(self.video_ids[int(neighbor_nodes[offset])]) == video_id
            ]
            outside_video = [
                offset for offset in eligible if str(self.video_ids[int(neighbor_nodes[offset])]) != video_id
            ]
            witnesses: RepeatFrameDetails = {}
            if same_video:
                highest = max(same_video, key=lambda offset: (
                    float(scores[offset]),
                    abs(int(self.frame_indices[int(neighbor_nodes[offset])]) - frame_index),
                    int(self.frame_indices[int(neighbor_nodes[offset])]),
                ))
                furthest = max(same_video, key=lambda offset: (
                    abs(int(self.frame_indices[int(neighbor_nodes[offset])]) - frame_index),
                    float(scores[offset]),
                    int(self.frame_indices[int(neighbor_nodes[offset])]),
                ))
                witnesses["in_video_highest_duplicate"] = _reference(self, int(neighbor_nodes[highest]), float(scores[highest]))
                witnesses["in_video_furthest_duplicate"] = _reference(self, int(neighbor_nodes[furthest]), float(scores[furthest]))
            if outside_video:
                highest_outside = min(outside_video, key=lambda offset: (
                    -float(scores[offset]),
                    str(self.video_ids[int(neighbor_nodes[offset])]),
                    int(self.frame_indices[int(neighbor_nodes[offset])]),
                ))
                witnesses["out_video_highest_duplicate"] = _reference(
                    self, int(neighbor_nodes[highest_outside]), float(scores[highest_outside])
                )
            if witnesses:
                details_by_frame[(video_id, frame_index)] = witnesses
        return details_by_frame


def _reference(graph: RepeatGraph, node: int, cosine: float) -> RepeatFrameReference:
    return {"video_id": str(graph.video_ids[node]), "frame_index": int(graph.frame_indices[node]), "cosine": cosine}


def load_repeat_graph(graph_path: Path, manifest_path: Path, *, metadata_path: Path) -> RepeatGraph:
    if not graph_path.is_file() or not manifest_path.is_file():
        raise RepeatGraphError("Repeat-graph artifact or manifest is missing")
    try:
        manifest: Any = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RepeatGraphError(f"Could not read repeat-graph manifest: {error}") from error
    if not isinstance(manifest, dict):
        raise RepeatGraphError("Repeat-graph manifest must be an object")
    expected = {
        "format_version": REPEAT_GRAPH_FORMAT_VERSION,
        "model_id": SIGLIP2_REPEAT_MODEL_ID,
        "embedding_dim": 1152,
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise RepeatGraphError(f"Repeat-graph manifest {key} does not match")
    try:
        if _sha256(metadata_path) != manifest.get("metadata_sha256"):
            raise RepeatGraphError("Repeat-graph metadata checksum does not match its manifest")
        with np.load(graph_path, allow_pickle=False) as source:
            required = {"format_version", "video_ids", "frame_indices", "indptr", "neighbors", "cosines"}
            if not required.issubset(source.files):
                raise RepeatGraphError("Repeat-graph archive is missing required arrays")
            format_version = source["format_version"].copy()
            video_ids = source["video_ids"].copy()
            frame_indices = source["frame_indices"].astype(np.int64, copy=True)
            indptr = source["indptr"].astype(np.uint64, copy=True)
            neighbors = source["neighbors"].astype(np.uint32, copy=True)
            cosines = source["cosines"].astype(np.float32, copy=True)
    except (OSError, ValueError) as error:
        raise RepeatGraphError(f"Could not load repeat graph: {error}") from error
    node_count = int(video_ids.shape[0])
    if (
        format_version.shape != (1,)
        or int(format_version[0]) != REPEAT_GRAPH_FORMAT_VERSION
        or video_ids.ndim != 1
        or frame_indices.shape != (node_count,)
        or indptr.shape != (node_count + 1,)
        or neighbors.ndim != 1
        or cosines.shape != neighbors.shape
        or int(indptr[0]) != 0
        or int(indptr[-1]) != neighbors.size
        or np.any(indptr[1:] < indptr[:-1])
        or (neighbors.size and int(neighbors.max()) >= node_count)
        or not np.isfinite(cosines).all()
        or manifest.get("node_count") != node_count
        or manifest.get("directed_edge_count") != int(neighbors.size)
    ):
        raise RepeatGraphError("Repeat-graph structure is invalid")
    return RepeatGraph(video_ids, frame_indices, indptr, neighbors, cosines)
