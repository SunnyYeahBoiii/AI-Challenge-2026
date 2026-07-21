from __future__ import annotations

import pytest

from app.services.fusion import RankedSource, diversify_frames, reciprocal_rank_fusion


def _frame(frame_uid: str, video_id: str = "V1", pts_time: float = 0.0) -> dict[str, object]:
    return {
        "frame_uid": frame_uid,
        "video_id": video_id,
        "frame_index": int(frame_uid.removeprefix("f")),
        "pts_time": pts_time,
    }


def test_weighted_rrf_combines_rankings_without_score_calibration() -> None:
    sources = [
        RankedSource("model-a:original", [_frame("f1"), _frame("f2")], weight=1.0),
        RankedSource("model-b:original", [_frame("f2"), _frame("f3")], weight=2.0),
    ]

    results = reciprocal_rank_fusion(sources, rrf_k=60)

    assert [result["frame_uid"] for result in results] == ["f2", "f3", "f1"]
    assert results[0]["fusion_score"] == pytest.approx((1 / 62) + (2 / 61))
    assert results[0]["source_ranks"] == {
        "model-a:original": 2,
        "model-b:original": 1,
    }


def test_rrf_counts_duplicate_frame_only_once_per_source() -> None:
    duplicate = _frame("f1")
    source = RankedSource("model-a", [duplicate, duplicate, _frame("f2")])

    results = reciprocal_rank_fusion([source], rrf_k=10)

    assert [result["frame_uid"] for result in results] == ["f1", "f2"]
    assert results[1]["source_ranks"]["model-a"] == 2


def test_diversity_suppresses_nearby_frames_and_caps_each_video() -> None:
    frames = [
        _frame("f1", "V1", 10.0),
        _frame("f2", "V1", 10.5),
        _frame("f3", "V1", 20.0),
        _frame("f4", "V1", 30.0),
        _frame("f5", "V2", 10.2),
    ]

    results = diversify_frames(
        frames,
        min_time_gap_seconds=2.0,
        max_per_video=2,
        limit=10,
    )

    assert [result["frame_uid"] for result in results] == ["f1", "f3", "f5"]


def test_fusion_and_diversity_validate_inputs_and_tie_break_stably() -> None:
    with pytest.raises(ValueError, match="source_id"):
        RankedSource("", [])
    with pytest.raises(ValueError, match="weight"):
        RankedSource("a", [], -1.0)
    with pytest.raises(ValueError, match="weight"):
        RankedSource("a", [], float("nan"))
    with pytest.raises(ValueError, match="weight"):
        RankedSource("a", [], 0.0)
    with pytest.raises(ValueError, match="rrf_k"):
        reciprocal_rank_fusion([], rrf_k=0)
    with pytest.raises(ValueError, match="time"):
        diversify_frames([], min_time_gap_seconds=-1.0)
    with pytest.raises(ValueError, match="max_per_video"):
        diversify_frames([], max_per_video=-1)

    tied = reciprocal_rank_fusion(
        [
            RankedSource("a", [_frame("f2")]),
            RankedSource("b", [_frame("f1")]),
        ],
        rrf_k=1,
    )
    assert [frame["frame_uid"] for frame in tied] == ["f1", "f2"]
    limited = diversify_frames([_frame("f1"), _frame("f2")], limit=1)
    assert limited[0]["frame_uid"] == "f1"
