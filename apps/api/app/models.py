import re
from typing import Literal

from pydantic import BaseModel, Field, model_validator


_MINIMUM_SHOULD_MATCH = re.compile(
    r"^(?:-?\d+|-?\d+%|\d+<-?(?:\d+|\d+%)(?:\s+\d+<-?(?:\d+|\d+%))*)$"
)


class KeywordSearchConfig(BaseModel):
    """Elasticsearch DSL options for one OCR or ASR keyword source."""

    query_type: Literal["match", "match_phrase"] = "match"
    fuzzy: bool = False
    operator: Literal["and", "or"] = "and"
    minimum_should_match: str = "100%"
    prefix_length: int = Field(default=2, ge=0, le=10)
    max_expansions: int = Field(default=20, ge=1, le=100)
    slop: int = Field(default=0, ge=0, le=10)

    @model_validator(mode="after")
    def validate_dsl_options(self) -> "KeywordSearchConfig":
        if not _MINIMUM_SHOULD_MATCH.fullmatch(self.minimum_should_match.strip()):
            raise ValueError("minimum_should_match is not a valid Elasticsearch expression")
        if self.query_type == "match_phrase" and self.fuzzy:
            raise ValueError("fuzzy is not supported with match_phrase")
        if self.query_type == "match" and self.operator == "and":
            if self.minimum_should_match != "100%":
                raise ValueError("minimum_should_match must be 100% when operator is and")
        return self


class SearchRequest(BaseModel):
    text: str = ""
    tags: list[str] = []
    tag_mode: Literal["and", "or"] = "and"
    ocr_keywords: list[str] = []
    asr_keywords: list[str] = []
    ocr_match_mode: Literal["and", "or"] | None = None
    asr_match_mode: Literal["and", "or"] | None = None
    ocr_search_config: KeywordSearchConfig | None = None
    asr_search_config: KeywordSearchConfig | None = None
    # Legacy single-list API; expanded into ocr/asr when those are empty.
    keywords: list[str] = []
    keyword_mode: Literal["and", "or"] = "and"
    keyword_source: Literal["all", "ocr", "asr"] = "all"
    topk: int = Field(default=20, ge=1, le=5000)
    enhance: bool = True

    @model_validator(mode="after")
    def validate_search_content(self) -> "SearchRequest":
        """Accept vector or filter-only searches, but reject an empty request."""
        if not any((
            self.text.strip(),
            self.tags,
            self.ocr_keywords,
            self.asr_keywords,
            self.keywords,
        )):
            raise ValueError("at least one search input is required")
        return self

    @model_validator(mode="after")
    def expand_legacy_keywords(self) -> "SearchRequest":
        """Map legacy keywords+keyword_source into ocr/asr lists when unset."""
        if self.ocr_keywords or self.asr_keywords or not self.keywords:
            return self
        if self.keyword_source == "ocr":
            self.ocr_keywords = list(self.keywords)
        elif self.keyword_source == "asr":
            self.asr_keywords = list(self.keywords)
        else:
            # source=all: same keywords on both fields (AND across sources).
            self.ocr_keywords = list(self.keywords)
            self.asr_keywords = list(self.keywords)
        return self


class BoxQuery(BaseModel):
    text: str = ""
    image: str = ""  # base64 encoded
    tags: list[str] = []
    tag_match_mode: Literal["and", "or"] = "and"
    ocr_keywords: list[str] = []
    asr_keywords: list[str] = []
    ocr_match_mode: Literal["and", "or"] | None = None
    asr_match_mode: Literal["and", "or"] | None = None
    ocr_search_config: KeywordSearchConfig | None = None
    asr_search_config: KeywordSearchConfig | None = None
    keywords: list[str] = []
    key_match_mode: Literal["and", "or"] = "and"
    keyword_source: Literal["all", "ocr", "asr"] = "all"
    enhance: bool | None = None
    topk: int = Field(default=500, ge=1, le=5000)

    @model_validator(mode="after")
    def validate_search_content(self) -> "BoxQuery":
        """Accept vector or filter-only boxes, but reject a completely empty box."""
        if not any((
            self.text.strip(),
            self.image.strip(),
            self.tags,
            self.ocr_keywords,
            self.asr_keywords,
            self.keywords,
        )):
            raise ValueError("at least one search input is required")
        return self

    @model_validator(mode="after")
    def expand_legacy_keywords(self) -> "BoxQuery":
        """Map legacy keywords+keyword_source into ocr/asr lists when unset."""
        if self.ocr_keywords or self.asr_keywords or not self.keywords:
            return self
        if self.keyword_source == "ocr":
            self.ocr_keywords = list(self.keywords)
        elif self.keyword_source == "asr":
            self.asr_keywords = list(self.keywords)
        else:
            self.ocr_keywords = list(self.keywords)
            self.asr_keywords = list(self.keywords)
        return self


class MultiBoxRequest(BaseModel):
    box_queries: list[BoxQuery] = Field(min_length=1)
    temporal_window_seconds: float = Field(default=90.0, gt=0)
    enhance: bool = True
    mode: Literal["parallel", "sequential"] = "parallel"


class SimilarFramesRequest(BaseModel):
    video_id: str
    frame_index: int
    topk: int = Field(default=12, ge=1, le=5000)


class VideoIdRequest(BaseModel):
    video_id: str
    frame_index: int | None = None
    range: int = 5
