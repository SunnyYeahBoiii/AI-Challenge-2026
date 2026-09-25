from typing import Literal, get_args

from pydantic import BaseModel, Field, model_validator

VideoPrefix = Literal[
    "L", "M", "N", "S",  # Existing broad filters remain valid for API clients.
    "L21_V", "L22_V", "L23_V", "L24_V", "L25_V", "L26_V", "L27_V", "L28_V", "L29_V", "L30_V",
    "S01_V",
]
ALLOWED_VIDEO_PREFIXES = set(get_args(VideoPrefix))


class SearchRequest(BaseModel):
    text: str = ""
    tags: list[str] = []
    tag_mode: Literal["and", "or"] = "and"
    ocr_keywords: list[str] = []
    asr_keywords: list[str] = []
    ocr_match_mode: Literal["and", "or"] | None = None
    asr_match_mode: Literal["and", "or"] | None = None
    # Legacy single-list API; expanded into ocr/asr when those are empty.
    keywords: list[str] = []
    keyword_mode: Literal["and", "or"] = "and"
    keyword_source: Literal["all", "ocr", "asr"] = "all"
    keyword_field_mode: Literal["asr", "ocr", "or", "and"] = "or"
    # Query-time strategy per field: `exact` is the ordered adjacent phrase,
    # `fuzzy` the unordered typo-tolerant bag of words. OCR defaults to exact
    # because burned-in captions are read verbatim; ASR likewise.
    ocr_search_mode: Literal["fuzzy", "exact"] = "exact"
    asr_search_mode: Literal["fuzzy", "exact"] = "exact"
    topk: int = Field(default=1500, ge=1, le=10000)
    enhance: bool = False
    video_prefixes: list[VideoPrefix] = []

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
        """Expand shared or legacy keywords into field-specific groups."""
        field_mode_explicit = "keyword_field_mode" in self.model_fields_set
        if self.ocr_keywords or self.asr_keywords:
            if not field_mode_explicit:
                self.keyword_field_mode = "and"
            return self
        if not self.keywords:
            return self
        if field_mode_explicit:
            field_mode = self.keyword_field_mode
        elif self.keyword_source == "ocr":
            field_mode = "ocr"
        elif self.keyword_source == "asr":
            field_mode = "asr"
        else:
            field_mode = "and"
        self.keyword_field_mode = field_mode
        if field_mode == "ocr":
            self.ocr_keywords = list(self.keywords)
        elif field_mode == "asr":
            self.asr_keywords = list(self.keywords)
        else:
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
    keywords: list[str] = []
    key_match_mode: Literal["and", "or"] = "and"
    keyword_source: Literal["all", "ocr", "asr"] = "all"
    keyword_field_mode: Literal["asr", "ocr", "or", "and"] = "or"
    # Query-time strategy per field: `exact` is the ordered adjacent phrase,
    # `fuzzy` the unordered typo-tolerant bag of words. OCR defaults to exact
    # because burned-in captions are read verbatim; ASR likewise.
    ocr_search_mode: Literal["fuzzy", "exact"] = "exact"
    asr_search_mode: Literal["fuzzy", "exact"] = "exact"
    enhance: bool | None = False
    topk: int = Field(default=1500, ge=1, le=10000)

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
        """Expand shared or legacy keywords into field-specific groups."""
        field_mode_explicit = "keyword_field_mode" in self.model_fields_set
        if self.ocr_keywords or self.asr_keywords:
            if not field_mode_explicit:
                self.keyword_field_mode = "and"
            return self
        if not self.keywords:
            return self
        if field_mode_explicit:
            field_mode = self.keyword_field_mode
        elif self.keyword_source == "ocr":
            field_mode = "ocr"
        elif self.keyword_source == "asr":
            field_mode = "asr"
        else:
            field_mode = "and"
        self.keyword_field_mode = field_mode
        if field_mode == "ocr":
            self.ocr_keywords = list(self.keywords)
        elif field_mode == "asr":
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
    video_prefixes: list[VideoPrefix] = []


class RepeatFrameRequest(BaseModel):
    """One displayed frame eligible for visual repeat detection."""

    video_id: str = Field(min_length=1)
    frame_index: int = Field(ge=0)
    timestamp: float = Field(allow_inf_nan=False)


class RepeatFramesRequest(BaseModel):
    """Bounded displayed-frame batch for exact local cosine comparisons."""

    frames: list[RepeatFrameRequest] = Field(min_length=1, max_length=1500)


class SimilarFramesRequest(BaseModel):
    video_id: str
    frame_index: int
    topk: int = Field(default=12, ge=1, le=10000)


class VideoIdRequest(BaseModel):
    video_id: str
    frame_index: int | None = None
    range: int = 5
