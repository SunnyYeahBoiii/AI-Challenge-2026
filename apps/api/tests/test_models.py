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
