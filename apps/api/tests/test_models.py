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
    assert req.keyword_field_mode == "and"


@pytest.mark.parametrize(
    ("field_mode", "ocr_keywords", "asr_keywords"),
    [
        ("ocr", ["x"], []),
        ("asr", [], ["x"]),
        ("or", ["x"], ["x"]),
        ("and", ["x"], ["x"]),
    ],
)
def test_unified_keywords_expand_by_field_mode(
    field_mode: str, ocr_keywords: list[str], asr_keywords: list[str]
) -> None:
    req = BoxQuery(text="q", keywords=["x"], keyword_field_mode=field_mode)
    assert req.ocr_keywords == ocr_keywords
    assert req.asr_keywords == asr_keywords
    assert req.keyword_field_mode == field_mode


def test_explicit_field_mode_defaults_to_or_for_new_clients() -> None:
    assert BoxQuery(text="q", keyword_field_mode="or").keyword_field_mode == "or"


def test_dedicated_legacy_keywords_keep_field_and_semantics() -> None:
    req = SearchRequest(text="q", ocr_keywords=["ocr"], asr_keywords=["asr"])
    assert req.keyword_field_mode == "and"


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


def test_box_query_topk_defaults_to_1500() -> None:
    assert BoxQuery(text="q").topk == 1500


def test_legacy_search_topk_defaults_to_1500() -> None:
    assert SearchRequest(text="q").topk == 1500


def test_topk_accepts_10000() -> None:
    assert BoxQuery(text="q", topk=10000).topk == 10000
    assert SearchRequest(text="q", topk=10000).topk == 10000


def test_keyword_search_modes_use_ocr_unordered_and_asr_exact_defaults() -> None:
    assert SearchRequest(text="q").ocr_search_mode == "unordered"
    assert SearchRequest(text="q").asr_search_mode == "exact"
    assert BoxQuery(text="q").ocr_search_mode == "unordered"
    assert BoxQuery(text="q").asr_search_mode == "exact"


def test_ocr_accepts_unordered_search_mode() -> None:
    assert BoxQuery(text="q", ocr_search_mode="unordered").ocr_search_mode == "unordered"


@pytest.mark.parametrize("field", ["ocr_search_mode", "asr_search_mode"])
def test_box_query_rejects_invalid_keyword_search_mode(field: str) -> None:
    with pytest.raises(ValidationError):
        BoxQuery(text="q", **{field: "substring"})


def test_box_query_rejects_invalid_keyword_field_mode() -> None:
    with pytest.raises(ValidationError):
        BoxQuery(text="q", keywords=["x"], keyword_field_mode="either")


@pytest.mark.parametrize("topk", [0, 10001])
def test_box_query_rejects_topk_outside_supported_range(topk: int) -> None:
    with pytest.raises(ValidationError):
        BoxQuery(text="q", topk=topk)


@pytest.mark.parametrize("topk", [0, 10001])
def test_legacy_search_rejects_topk_outside_supported_range(topk: int) -> None:
    with pytest.raises(ValidationError):
        SearchRequest(text="q", topk=topk)


def test_multi_box_temporal_window_defaults_to_90_seconds() -> None:
    request = MultiBoxRequest(box_queries=[BoxQuery(text="q")])
    assert request.temporal_window_seconds == 90.0


def test_multi_box_accepts_video_prefixes() -> None:
    request = MultiBoxRequest(box_queries=[BoxQuery(text="q")], video_prefixes=["L", "N"])
    assert request.video_prefixes == ["L", "N"]


def test_multi_box_accepts_specific_video_categories() -> None:
    request = MultiBoxRequest(
        box_queries=[BoxQuery(text="q")],
        video_prefixes=["L21_V", "L22_V", "M", "S01-", "S01_V"],
    )
    assert request.video_prefixes == ["L21_V", "L22_V", "M", "S01-", "S01_V"]


def test_multi_box_rejects_unknown_video_prefix() -> None:
    with pytest.raises(ValidationError):
        MultiBoxRequest(box_queries=[BoxQuery(text="q")], video_prefixes=["X"])


def test_multi_box_rejects_non_positive_temporal_window() -> None:
    with pytest.raises(ValidationError):
        MultiBoxRequest(box_queries=[BoxQuery(text="q")], temporal_window_seconds=0)


def test_multi_box_rejects_no_boxes() -> None:
    with pytest.raises(ValidationError):
        MultiBoxRequest(box_queries=[])
