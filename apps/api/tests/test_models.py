"""Request-model validation tests."""

import pytest
from pydantic import ValidationError

from app.models import BoxQuery, MultiBoxRequest, SearchRequest


@pytest.mark.parametrize(
    "payload",
    [
        {"tags": ["person"]},
        {"ocr_keywords": ["Long về đích số 3"]},
        {"asr_keywords": ["hồ Long Ẩn"]},
    ],
)
def test_search_request_accepts_filter_only_content(payload: dict[str, object]) -> None:
    SearchRequest(**payload)


@pytest.mark.parametrize(
    "payload",
    [
        {"tags": ["traffic light"]},
        {"ocr_keywords": ["Long về đích số 3"]},
        {"asr_keywords": ["hồ Long Ẩn"]},
    ],
)
def test_box_query_accepts_filter_only_content(payload: dict[str, object]) -> None:
    BoxQuery(**payload)


def test_search_request_rejects_completely_empty_search() -> None:
    with pytest.raises(ValidationError, match="at least one search input"):
        SearchRequest()


def test_box_query_rejects_completely_empty_box() -> None:
    with pytest.raises(ValidationError, match="at least one search input"):
        BoxQuery()


def test_box_query_accepts_spaced_coco_class_name_with_text() -> None:
    query = BoxQuery(text="street", tags=["traffic light"])
    assert query.tags == ["traffic light"]


def test_search_request_expands_legacy_keywords_to_ocr() -> None:
    req = SearchRequest(text="q", keywords=["hd"], keyword_source="ocr")
    assert req.ocr_keywords == ["hd"]
    assert req.asr_keywords == []


def test_search_request_expands_legacy_keywords_to_asr() -> None:
    req = SearchRequest(text="q", keywords=["chao"], keyword_source="asr")
    assert req.ocr_keywords == []
    assert req.asr_keywords == ["chao"]


def test_search_request_expands_legacy_all_to_both_lists() -> None:
    req = SearchRequest(text="q", keywords=["x"], keyword_source="all")
    assert req.ocr_keywords == ["x"]
    assert req.asr_keywords == ["x"]


def test_explicit_ocr_asr_keywords_skip_legacy_expand() -> None:
    req = SearchRequest(
        text="q",
        ocr_keywords=["ocr"],
        asr_keywords=["asr"],
        keywords=["legacy"],
        keyword_source="all",
    )
    assert req.ocr_keywords == ["ocr"]
    assert req.asr_keywords == ["asr"]


def test_box_query_expands_legacy_keywords() -> None:
    box = BoxQuery(text="q", keywords=["k"], keyword_source="asr")
    assert box.asr_keywords == ["k"]
    assert box.ocr_keywords == []


def test_box_query_topk_defaults_to_500() -> None:
    assert BoxQuery(text="q").topk == 500


@pytest.mark.parametrize("topk", [0, 5001])
def test_box_query_rejects_topk_outside_supported_range(topk: int) -> None:
    with pytest.raises(ValidationError):
        BoxQuery(text="q", topk=topk)


def test_multi_box_temporal_window_defaults_to_90_seconds() -> None:
    request = MultiBoxRequest(box_queries=[BoxQuery(text="q")])
    assert request.temporal_window_seconds == 90.0


def test_multi_box_rejects_non_positive_temporal_window() -> None:
    with pytest.raises(ValidationError):
        MultiBoxRequest(box_queries=[BoxQuery(text="q")], temporal_window_seconds=0)


def test_multi_box_rejects_no_boxes() -> None:
    with pytest.raises(ValidationError):
        MultiBoxRequest(box_queries=[])
