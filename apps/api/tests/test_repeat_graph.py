"""Tests for the precomputed SigLIP2 repeat graph."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from app.services.repeat_graph import RepeatGraph


def _write_graph(tmp_path: Path, *, neighbor_override: int | None = None) -> tuple[Path, Path]:
    graph_path = tmp_path / "repeat.npz"
    manifest_path = tmp_path / "repeat.manifest.json"
    neighbors = np.asarray([1, 2, 3, 0, 0, 0], dtype=np.uint32)
    if neighbor_override is not None:
        neighbors[0] = neighbor_override
    np.savez_compressed(
        graph_path,
        format_version=np.asarray([1], dtype=np.uint16),
        video_ids=np.asarray(["V1", "V1", "V1", "V2"]),
        frame_indices=np.asarray([10, 20, 100, 7], dtype=np.int64),
        indptr=np.asarray([0, 3, 4, 5, 6], dtype=np.uint64),
        neighbors=neighbors,
        cosines=np.asarray([0.99, 0.95, 0.98, 0.99, 0.95, 0.98], dtype=np.float32),
    )
    manifest_path.write_text(
        json.dumps(
            {
                "format_version": 1,
                "model_id": "siglip2",
                "embedding_dim": 1152,
                "node_count": 4,
                "directed_edge_count": 6,
                "undirected_edge_count": 3,
            }
        ),
        encoding="utf-8",
    )
    return graph_path, manifest_path


def test_graph_returns_global_highest_furthest_and_out_video_witnesses(
    tmp_path: Path,
) -> None:
    graph_path, manifest_path = _write_graph(tmp_path)
    graph = RepeatGraph.load(graph_path, manifest_path)

    assert graph.find_repeat_frame_details([("V1", 10)]) == {
        ("V1", 10): {
            "in_video_highest_duplicate": {"video_id": "V1", "frame_index": 20},
            "in_video_furthest_duplicate": {"video_id": "V1", "frame_index": 100},
            "out_video_highest_duplicate": {"video_id": "V2", "frame_index": 7},
        }
    }


def test_graph_rejects_neighbor_outside_node_range(tmp_path: Path) -> None:
    graph_path, manifest_path = _write_graph(tmp_path, neighbor_override=4)

    with pytest.raises(ValueError, match="neighbor index"):
        RepeatGraph.load(graph_path, manifest_path)
