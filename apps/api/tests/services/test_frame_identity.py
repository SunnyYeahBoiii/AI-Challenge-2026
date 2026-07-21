from __future__ import annotations

import pytest

from app.services.frame_identity import build_frame_uid, frame_uid


def test_build_frame_uid_is_stable_and_validates_inputs() -> None:
    assert build_frame_uid("V1", 7) == "V1:00000007"
    with pytest.raises(ValueError, match="video_id"):
        build_frame_uid("", 1)
    with pytest.raises(ValueError, match="non-negative"):
        build_frame_uid("V1", -1)


def test_frame_uid_prefers_explicit_id_and_falls_back_to_path() -> None:
    assert frame_uid({"frame_uid": "canonical"}) == "canonical"
    assert frame_uid({"video_id": "V2", "frame_index": 3}) == "V2:00000003"
    assert frame_uid({"frame_path": "frames\\V3\\0004.webp"}) == "frames/V3/0004.webp"
    with pytest.raises(ValueError, match="video_id"):
        frame_uid({"title": "missing"})
