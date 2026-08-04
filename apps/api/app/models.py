from typing import Literal
from pydantic import BaseModel, model_validator


class EmbedTextRequest(BaseModel):
    text: str
    enhance: bool = True


class SearchRequest(BaseModel):
    text: str = ""
    tags: list[str] = []
    tag_mode: Literal["and", "or"] = "and"
    keywords: list[str] = []
    keyword_mode: Literal["and", "or"] = "and"
    keyword_source: Literal["all", "ocr", "asr"] = "all"
    topk: int = 20
    enhance: bool = True

    @model_validator(mode="after")
    def validate_tags_need_text(self) -> "SearchRequest":
        """Require a vector-producing text query when tags are present."""
        if self.tags and not self.text.strip():
            raise ValueError("tags require a text query")
        return self


class BoxQuery(BaseModel):
    text: str = ""
    image: str = ""  # base64 encoded
    tags: list[str] = []
    tag_match_mode: Literal["and", "or"] = "and"
    keywords: list[str] = []
    key_match_mode: Literal["and", "or"] = "and"
    keyword_source: Literal["all", "ocr", "asr"] = "all"
    enhance: bool | None = None
    topk: int = 20

    @model_validator(mode="after")
    def validate_tags_need_query_content(self) -> "BoxQuery":
        """Require text or image content because tags only refine vector results."""
        if self.tags and not (self.text.strip() or self.image.strip()):
            raise ValueError("tags require text or image content")
        return self


class MultiBoxRequest(BaseModel):
    box_queries: list[BoxQuery]
    temporal_window_seconds: float = 120.0
    topk: int = 200
    enhance: bool = True
    mode: Literal["parallel", "sequential"] = "parallel"


class SimilarFramesRequest(BaseModel):
    video_id: str
    frame_index: int
    topk: int = 12


class VideoIdRequest(BaseModel):
    video_id: str
    frame_index: int | None = None
    range: int = 5


class FrameResult(BaseModel):
    id: str
    video_id: str
    frame_index: int
    shot_idx: int = 0
    start_time: float = 0.0
    end_time: float = 0.0
    pts_time: float = 0.0
    fps: float = 0.0
    score: float = 0.0
    title: str = ""
    description: str = ""
    keywords: list[str] = []
    author: str = ""
    publish_date: str = ""
    thumbnail_url: str = ""
    watch_url: str = ""
    sequence_idx: int | None = None
    sequence_id: str = ""


class VideoResult(BaseModel):
    video_id: str
    title: str = ""
    description: str = ""
    keywords: list[str] = []
    author: str = ""
    channel_id: str = ""
    length: int = 0
    publish_date: str = ""
    thumbnail_url: str = ""
    watch_url: str = ""
    level: str = ""
    frame_count: int = 0


class SearchResponse(BaseModel):
    query: str = ""
    enhanced: bool = False
    results: list[FrameResult] = []
    total: int = 0


class VideoSearchResponse(BaseModel):
    videos: list[VideoResult] = []
    total: int = 0


class EmbedResponse(BaseModel):
    vector: list[float]
    dim: int
    text: str = ""
    enhanced: bool = False
    filename: str = ""
