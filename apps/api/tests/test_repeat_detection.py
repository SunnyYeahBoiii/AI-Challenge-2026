"""Tests for exact repeat detection over displayed Milvus frame embeddings."""

from __future__ import annotations

import numpy as np
import pytest
from flask import Flask

from app.routes import search as search_routes
from app.services import repeat_detection


@pytest.fixture(autouse=True)
def clear_cache() -> None:
    repeat_detection.clear_repeat_cache()


def test_marks_every_member_of_a_near_duplicate_pair(monkeypatch: pytest.MonkeyPatch) -> None:
    frames = [("V1", 1, 0.0), ("V1", 2, 6.0), ("V2", 3, 0.0)]
    vectors = {
        ("V1", 1): [1.0, 0.0, 0.0],
        ("V1", 2): [0.99, float(np.sqrt(1 - 0.99**2)), 0.0],
        ("V2", 3): [0.0, 0.0, 1.0],
    }
    monkeypatch.setattr(repeat_detection.manager, "active_collection_name", lambda: "data_frames")
    monkeypatch.setattr(
        repeat_detection,
        "get_milvus_client",
        lambda _collection: type("Milvus", (), {"query_frame_embeddings": lambda _self, _keys: vectors})(),
    )

    assert repeat_detection.find_repeat_frame_keys(frames) == {("V1", 1), ("V1", 2)}


def test_repeat_thresholds_match_the_current_group_policy() -> None:
    assert repeat_detection.REPEAT_SIMILARITY_THRESHOLD == 0.92
    assert repeat_detection.L25_REPEAT_SIMILARITY_THRESHOLD == 0.97


def test_threshold_is_inclusive_and_self_comparisons_do_not_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    threshold = repeat_detection.REPEAT_SIMILARITY_THRESHOLD
    frames = [("V1", 1, 0.0), ("V1", 2, 6.0), ("V1", 3, 12.0)]
    vectors = {
        ("V1", 1): [1.0, 0.0],
        ("V1", 2): [threshold, float(np.sqrt(1 - threshold**2))],
        ("V1", 3): [0.0, 1.0],
    }
    monkeypatch.setattr(repeat_detection.manager, "active_collection_name", lambda: "data_frames")
    monkeypatch.setattr(
        repeat_detection,
        "get_milvus_client",
        lambda _collection: type("Milvus", (), {"query_frame_embeddings": lambda _self, _keys: vectors})(),
    )

    assert repeat_detection.find_repeat_frame_keys(frames) == {("V1", 1), ("V1", 2)}


def test_missing_or_invalid_vectors_are_ignored_without_failing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frames = [("V1", 1, 0.0), ("V1", 2, 6.0), ("V1", 3, 12.0)]
    vectors = {
        ("V1", 1): [1.0, 0.0],
        ("V1", 2): [1.0, 0.0],
        ("V1", 3): [float("nan"), 0.0],
    }
    monkeypatch.setattr(repeat_detection.manager, "active_collection_name", lambda: "data_frames")
    monkeypatch.setattr(
        repeat_detection,
        "get_milvus_client",
        lambda _collection: type("Milvus", (), {"query_frame_embeddings": lambda _self, _keys: vectors})(),
    )

    assert repeat_detection.find_repeat_frame_keys(frames) == {("V1", 1), ("V1", 2)}


def test_deduplicates_input_and_reuses_collection_aware_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    class Milvus:
        def query_frame_embeddings(self, _keys: list[tuple[str, int]]) -> dict[tuple[str, int], list[float]]:
            nonlocal calls
            calls += 1
            return {("V1", 1): [1.0, 0.0], ("V1", 2): [1.0, 0.0]}

    monkeypatch.setattr(repeat_detection.manager, "active_collection_name", lambda: "data_frames")
    monkeypatch.setattr(repeat_detection, "get_milvus_client", lambda _collection: Milvus())
    frames = [("V1", 2, 6.0), ("V1", 1, 0.0), ("V1", 2, 6.0)]

    assert repeat_detection.find_repeat_frame_keys(frames) == {("V1", 1), ("V1", 2)}
    assert repeat_detection.find_repeat_frame_keys(list(reversed(frames))) == {("V1", 1), ("V1", 2)}
    assert calls == 1


def test_selects_highest_furthest_and_out_video_repeat_witnesses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frames = [("V1", 100, 0.0), ("V1", 110, 6.0), ("V1", 500, 12.0), ("V2", 7, 0.0)]
    vectors = {
        ("V1", 100): [1.0, 0.0, 0.0],
        ("V1", 110): [0.99, float(np.sqrt(1 - 0.99**2)), 0.0],
        ("V1", 500): [0.95, 0.0, float(np.sqrt(1 - 0.95**2))],
        ("V2", 7): [0.98, float(np.sqrt(1 - 0.98**2)), 0.0],
    }
    monkeypatch.setattr(repeat_detection.manager, "active_collection_name", lambda: "data_frames")
    monkeypatch.setattr(
        repeat_detection,
        "get_milvus_client",
        lambda _collection: type("Milvus", (), {"query_frame_embeddings": lambda _self, _keys: vectors})(),
    )

    details = repeat_detection.find_repeat_frame_details(frames)

    assert details[("V1", 100)] == {
        "in_video_highest_duplicate": {"video_id": "V1", "frame_index": 110},
        "in_video_furthest_duplicate": {"video_id": "V1", "frame_index": 500},
        "out_video_highest_duplicate": {"video_id": "V2", "frame_index": 7},
    }


def test_repeat_details_keep_one_same_video_reference_for_highest_and_furthest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frames = [("V1", 1, 0.0), ("V1", 20, 6.0)]
    vectors = {("V1", 1): [1.0, 0.0], ("V1", 20): [1.0, 0.0]}
    monkeypatch.setattr(repeat_detection.manager, "active_collection_name", lambda: "data_frames")
    monkeypatch.setattr(
        repeat_detection,
        "get_milvus_client",
        lambda _collection: type("Milvus", (), {"query_frame_embeddings": lambda _self, _keys: vectors})(),
    )

    details = repeat_detection.find_repeat_frame_details(frames)

    assert details[("V1", 1)] == {
        "in_video_highest_duplicate": {"video_id": "V1", "frame_index": 20},
        "in_video_furthest_duplicate": {"video_id": "V1", "frame_index": 20},
    }


def test_same_video_frames_under_six_seconds_apart_are_not_repeats(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frames = [("V1", 1, 10.0), ("V1", 2, 15.999), ("V2", 3, 10.0)]
    vectors = {
        ("V1", 1): [1.0, 0.0],
        ("V1", 2): [1.0, 0.0],
        ("V2", 3): [0.0, 1.0],
    }
    monkeypatch.setattr(repeat_detection.manager, "active_collection_name", lambda: "data_frames")
    monkeypatch.setattr(
        repeat_detection,
        "get_milvus_client",
        lambda _collection: type("Milvus", (), {"query_frame_embeddings": lambda _self, _keys: vectors})(),
    )

    assert repeat_detection.find_repeat_frame_keys(frames) == set()


def test_different_video_or_six_second_same_video_pairs_are_eligible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frames = [("V1", 1, 10.0), ("V1", 2, 16.0), ("V2", 3, 10.0)]
    vectors = {
        ("V1", 1): [1.0, 0.0],
        ("V1", 2): [1.0, 0.0],
        ("V2", 3): [1.0, 0.0],
    }
    monkeypatch.setattr(repeat_detection.manager, "active_collection_name", lambda: "data_frames")
    monkeypatch.setattr(
        repeat_detection,
        "get_milvus_client",
        lambda _collection: type("Milvus", (), {"query_frame_embeddings": lambda _self, _keys: vectors})(),
    )

    assert repeat_detection.find_repeat_frame_keys(frames) == {("V1", 1), ("V1", 2), ("V2", 3)}


def test_l25_frames_are_compared_only_within_l25_and_use_stricter_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frames = [("L25_V001", 1, 0.0), ("L25_V002", 2, 0.0), ("L21_V001", 3, 0.0)]
    vectors = {
        ("L25_V001", 1): [1.0, 0.0],
        ("L25_V002", 2): [0.945, float(np.sqrt(1 - 0.945**2))],
        ("L21_V001", 3): [1.0, 0.0],
    }
    monkeypatch.setattr(repeat_detection.manager, "active_collection_name", lambda: "data_frames")
    monkeypatch.setattr(
        repeat_detection,
        "get_milvus_client",
        lambda _collection: type("Milvus", (), {"query_frame_embeddings": lambda _self, _keys: vectors})(),
    )

    assert repeat_detection.find_repeat_frame_keys(frames) == set()


def test_l25_same_video_requires_fifteen_seconds_and_threshold_is_inclusive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    threshold = repeat_detection.L25_REPEAT_SIMILARITY_THRESHOLD
    frames = [("L25_V001", 1, 0.0), ("L25_V001", 2, 14.999), ("L25_V001", 3, 15.0)]
    vectors = {
        ("L25_V001", 1): [1.0, 0.0],
        ("L25_V001", 2): [threshold, float(np.sqrt(1 - threshold**2))],
        ("L25_V001", 3): [threshold, float(np.sqrt(1 - threshold**2))],
    }
    monkeypatch.setattr(repeat_detection.manager, "active_collection_name", lambda: "data_frames")
    monkeypatch.setattr(
        repeat_detection,
        "get_milvus_client",
        lambda _collection: type("Milvus", (), {"query_frame_embeddings": lambda _self, _keys: vectors})(),
    )

    assert repeat_detection.find_repeat_frame_keys(frames) == {("L25_V001", 1), ("L25_V001", 3)}


def test_repeat_route_returns_repeated_frame_keys_with_duplicate_references(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = Flask(__name__)
    app.register_blueprint(search_routes.search_bp)
    monkeypatch.setattr(
        search_routes,
        "find_repeat_frame_details",
        lambda _frames: {
            ("V1", 2): {
                "in_video_highest_duplicate": {"video_id": "V1", "frame_index": 8},
                "in_video_furthest_duplicate": {"video_id": "V1", "frame_index": 20},
            },
            ("V2", 4): {"out_video_highest_duplicate": {"video_id": "V1", "frame_index": 2}},
        },
    )

    response = app.test_client().post(
        "/api/frames/repeats",
        json={
            "frames": [
                {"video_id": "V1", "frame_index": 2, "timestamp": 1.0},
                {"video_id": "V2", "frame_index": 4, "timestamp": 2.0},
            ]
        },
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "repeat_frames": [
            {
                "video_id": "V1",
                "frame_index": 2,
                "in_video_highest_duplicate": {"video_id": "V1", "frame_index": 8},
                "in_video_furthest_duplicate": {"video_id": "V1", "frame_index": 20},
            },
            {
                "video_id": "V2",
                "frame_index": 4,
                "out_video_highest_duplicate": {"video_id": "V1", "frame_index": 2},
            },
        ]
    }


def test_repeat_route_rejects_more_than_display_budget() -> None:
    app = Flask(__name__)
    app.register_blueprint(search_routes.search_bp)
    response = app.test_client().post(
        "/api/frames/repeats",
        json={
            "frames": [
                {"video_id": "V1", "frame_index": index, "timestamp": float(index)}
                for index in range(1501)
            ]
        },
    )

    assert response.status_code == 400
