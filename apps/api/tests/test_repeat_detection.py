"""Regression coverage for precomputed SigLIP2 REPEAT graph lookups."""

from __future__ import annotations

import hashlib
import json

import numpy as np
import pytest
from flask import Flask

from app.routes import search as search_routes
from app.services import repeat_detection


def _sha256(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(autouse=True)
def clear_cache() -> None:
    repeat_detection.clear_repeat_cache()


def _configure_graph(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    metadata = tmp_path / "data" / "metadata" / "concatenate-data-b1.json"
    metadata.parent.mkdir(parents=True)
    metadata.write_text("[]", encoding="utf-8")
    graph = tmp_path / "data" / "repeat_graphs" / "siglip2-repeat-graph.npz"
    graph.parent.mkdir(parents=True)
    np.savez_compressed(
        graph,
        format_version=np.asarray([1], dtype=np.uint16),
        video_ids=np.asarray(["L21_V001", "L21_V001", "L22_V001", "L23_V001"]),
        frame_indices=np.asarray([10, 500, 7, 9], dtype=np.int64),
        indptr=np.asarray([0, 3, 4, 5, 6], dtype=np.uint64),
        neighbors=np.asarray([1, 2, 3, 0, 0, 0], dtype=np.uint32),
        cosines=np.asarray([0.95, 0.93, 0.94, 0.95, 0.93, 0.94], dtype=np.float32),
    )
    graph.with_suffix(".manifest.json").write_text(
        json.dumps({
            "format_version": 1,
            "model_id": "siglip2",
            "embedding_dim": 1152,
            "metadata_sha256": _sha256(metadata),
            "node_count": 4,
            "directed_edge_count": 6,
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(repeat_detection.Config, "SIGLIP2_REPEAT_GRAPH", graph)
    monkeypatch.setattr(repeat_detection, "PROJECT_DIR", tmp_path)


def test_graph_lookup_is_model_independent_and_selects_witnesses(monkeypatch, tmp_path) -> None:
    _configure_graph(monkeypatch, tmp_path)
    details = repeat_detection.find_repeat_frame_details([("L21_V001", 10, 0.0)])
    assert details[("L21_V001", 10)] == {
        "in_video_highest_duplicate": {"video_id": "L21_V001", "frame_index": 500, "cosine": pytest.approx(0.95)},
        "in_video_furthest_duplicate": {"video_id": "L21_V001", "frame_index": 500, "cosine": pytest.approx(0.95)},
        "out_video_highest_duplicate": {"video_id": "L23_V001", "frame_index": 9, "cosine": pytest.approx(0.94)},
    }


def test_nested_lookup_excludes_the_source_before_witness_selection(monkeypatch, tmp_path) -> None:
    _configure_graph(monkeypatch, tmp_path)
    details = repeat_detection.find_repeat_frame_details(
        [("L21_V001", 500, 0.0)], exclude_frame=("L21_V001", 10)
    )
    assert details == {}


def test_missing_graph_keeps_search_usable(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(repeat_detection.Config, "SIGLIP2_REPEAT_GRAPH", tmp_path / "missing.npz")
    assert repeat_detection.find_repeat_frame_details([("L21_V001", 10, 0.0)]) == {}


def test_repeat_route_forwards_nested_exclusion(monkeypatch) -> None:
    app = Flask(__name__)
    app.register_blueprint(search_routes.search_bp)
    received = {}

    def fake_details(_frames, exclude_frame=None):
        received["exclude"] = exclude_frame
        return {("V1", 2): {"out_video_highest_duplicate": {"video_id": "V2", "frame_index": 8, "cosine": 0.99}}}

    monkeypatch.setattr(search_routes, "find_repeat_frame_details", fake_details)
    response = app.test_client().post(
        "/api/frames/repeats",
        json={
            "frames": [{"video_id": "V1", "frame_index": 2, "timestamp": 1.0}],
            "exclude_frame": {"video_id": "V2", "frame_index": 8},
        },
    )
    assert response.status_code == 200
    assert received["exclude"] == ("V2", 8)
