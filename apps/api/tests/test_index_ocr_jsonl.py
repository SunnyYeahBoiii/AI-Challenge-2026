"""Contract tests for the Gemini OCR JSONL importer."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from index_ocr_jsonl import (  # noqa: E402
    _doc_fields,
    extract_caption_ocr,
    extract_ocr,
    frame_identity,
    response_text,
)

KEYFRAME_URI = "gs://frameseeker-aic2026-assets/keyframes/S01/S01-V004/312838.webp"


def _doc(uri: str = KEYFRAME_URI, text: str = "OCR text: CHANG 4 HTV7") -> dict[str, Any]:
    return {
        "request": {"contents": [{"parts": [{"fileData": {"fileUri": uri}}], "role": "user"}]},
        "response": {"candidates": [{"content": {"parts": [{"text": text}]}}]},
    }


def test_frame_identity_reads_video_and_index_from_the_keyframe_uri() -> None:
    assert frame_identity(_doc()) == ("S01-V004", 312838)


def test_frame_identity_is_none_without_a_usable_uri() -> None:
    assert frame_identity({}) is None
    assert frame_identity({"request": {"contents": [{"parts": [{}]}]}}) is None


def test_response_text_joins_every_text_part() -> None:
    doc = _doc(text="first")
    doc["response"]["candidates"][0]["content"]["parts"].append({"text": " second"})
    assert response_text(doc) == "first second"


def test_extract_ocr_drops_the_prefix_and_normalises() -> None:
    assert extract_ocr("OCR text: CHANG 4   HTV7") == "chang 4 htv7"


def test_extract_ocr_cuts_the_camera_angle_section() -> None:
    raw = "OCR text: CHANG 4\nGóc quay ngang: không có gì"
    assert extract_ocr(raw) == "chang 4"


def test_extract_ocr_keeps_text_that_has_no_prefix() -> None:
    assert extract_ocr("HTV7 18:00 TRỰC TIẾP") == "htv7 18:00 trực tiếp"


def test_plain_update_touches_only_ocr_text() -> None:
    """A frame already in the index must not have its fields rewritten."""
    assert _doc_fields("L21_V001", 7, "abc", upsert=False) == {"ocr_text": "abc"}


def test_upsert_carries_the_fields_readers_filter_on() -> None:
    """Regression: an ocr_text-only doc is invisible to every reader.

    `fetch_frame_texts` and `score_frames_by_keywords` filter on the `video_id`
    and `frame_id` fields, not on `_id`, so a document created without them can
    never be found again.
    """
    doc = _doc_fields("S01-V004", 312838, "abc", upsert=True)
    assert doc["video_id"] == "S01-V004"
    assert doc["frame_id"] == 312838
    assert doc["frame_key"] == "S01-V004:312838"
    assert doc["ocr_text"] == "abc"


# --- vehicle-caption files -----------------------------------------------------
# These answers are not OCR: the prompt fixes the order as vehicle OCR →
# vehicle types → colour/movement → parked → human actions, so only the span
# before the first taxonomy token is readable text. Everything after is a
# controlled vocabulary shared by tens of thousands of frames, and indexing it
# would swamp keyword search — "xe nhỏ" alone matches a large share of them.


def test_extract_caption_ocr_keeps_only_the_leading_plates() -> None:
    raw = "51C-448.24 50H-417.00 xe nhỏ xe oto màu trắng xe oto đi thẳng"
    assert extract_caption_ocr(raw) == "51c-448.24 50h-417.00"


def test_extract_caption_ocr_drops_everything_from_the_taxonomy_on() -> None:
    assert extract_caption_ocr("xe nhỏ xe oto xe lớn") == ""
    assert extract_caption_ocr("màu bạc xe oto rẽ phải") == ""
    assert extract_caption_ocr("xe chuyên biệt đang đỗ") == ""


def test_extract_caption_ocr_keeps_a_sign_before_the_vehicle_section() -> None:
    raw = "Cong Truong Dan Chu 2 xe nhỏ xe oto màu xanh da trời xe oto đi thẳng"
    assert extract_caption_ocr(raw) == "cong truong dan chu 2"


def test_extract_caption_ocr_finds_the_earliest_marker() -> None:
    # "màu" is listed last but appears first; nothing after it may survive.
    assert extract_caption_ocr("màu xanh xe nhỏ 51C-448.24") == ""


def test_extract_caption_ocr_keeps_a_full_answer_that_is_all_text() -> None:
    assert extract_caption_ocr("MSB VCB ATM 24") == "msb vcb atm 24"
