"""Request-model validation tests."""

import pytest
from pydantic import ValidationError

from app.models import BoxQuery, SearchRequest


def test_search_request_rejects_tags_without_text() -> None:
    with pytest.raises(ValidationError, match="tags require a text query"):
        SearchRequest(tags=["person"])


def test_box_query_rejects_tags_without_text_or_image() -> None:
    with pytest.raises(ValidationError, match="tags require text or image content"):
        BoxQuery(tags=["traffic light"])


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
