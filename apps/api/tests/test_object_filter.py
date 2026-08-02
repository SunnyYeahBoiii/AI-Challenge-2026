"""Tests for Polars post-filtering of ranked Milvus frame candidates."""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from app.config import Config
from app.services import object_filter


def _frame(frame_index: int, score: float) -> dict[str, object]:
    return {"video_id": "K01_V001", "frame_index": frame_index, "score": score}


@pytest.fixture
def detections_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the service at a small, strict-schema object-detection dataset."""
    path = tmp_path / "object_detections.parquet"
    pl.DataFrame(
        {
            "frame_id": ["K01_V001/1", "K01_V001/1", "K01_V001/2", "K01_V001/3"],
            "class_id": [1, 3, 1, 9],
            "class_name": ["person", "car", "person", "boat"],
            "count": [2, 1, 1, 1],
        },
        schema=object_filter.REQUIRED_SCHEMA,
    ).write_parquet(path)
    monkeypatch.setattr(Config, "OBJECT_DETECTIONS_PATH", str(path))
    monkeypatch.setattr(object_filter, "_lazy_db", None)
    monkeypatch.setattr(object_filter, "_lazy_db_path", None)
    return path


def test_returns_original_frames_without_tags(detections_path: Path) -> None:
    frames = [_frame(1, 0.9)]
    assert object_filter.filter_frames(frames, []) is frames


def test_or_mode_keeps_frames_with_any_requested_object(detections_path: Path) -> None:
    frames = [_frame(3, 0.9), _frame(2, 0.8), _frame(1, 0.7)]
    results = object_filter.filter_frames(frames, ["person", "car"], "or")
    assert [frame["frame_index"] for frame in results] == [2, 1]
    assert [frame["score"] for frame in results] == [0.8, 0.7]


def test_and_mode_requires_every_requested_object(detections_path: Path) -> None:
    frames = [_frame(2, 0.9), _frame(1, 0.8), _frame(3, 0.7)]
    results = object_filter.filter_frames(frames, ["PERSON", "car", "person"], "and")
    assert [frame["frame_index"] for frame in results] == [1]


def test_preserves_coco_class_names_with_spaces(detections_path: Path) -> None:
    path = detections_path
    pl.DataFrame(
        {
            "frame_id": ["K01_V001/4"],
            "class_id": [10],
            "class_name": ["traffic light"],
            "count": [1],
        },
        schema=object_filter.REQUIRED_SCHEMA,
    ).write_parquet(path)
    object_filter._lazy_db = None
    object_filter._lazy_db_path = None

    frame = [_frame(4, 0.9)]
    assert object_filter.filter_frames(frame, ["traffic light"], "and") == frame
    assert object_filter.filter_frames(frame, ["traffic_light"], "and") == []


def test_missing_detection_dataset_raises_an_actionable_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing_path = tmp_path / "missing.parquet"
    monkeypatch.setattr(Config, "OBJECT_DETECTIONS_PATH", str(missing_path))
    monkeypatch.setattr(object_filter, "_lazy_db", None)
    monkeypatch.setattr(object_filter, "_lazy_db_path", None)

    with pytest.raises(object_filter.ObjectFilterError, match="Object detections file not found"):
        object_filter.filter_frames([_frame(1, 0.9)], ["person"])
