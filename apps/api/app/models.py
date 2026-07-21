from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

from app.config import Config


class EmbedTextRequest(BaseModel):
    text: str = Field(min_length=1)
    enhance: bool = True
    model_id: str | None = None


class EnsembleOptionsRequest(BaseModel):
    """HTTP representation of per-Query ensemble controls."""

    model_ids: list[str] | None = None
    model_weights: dict[str, float] = Field(default_factory=dict)
    candidate_topk: int = Field(default=Config.ENSEMBLE_CANDIDATE_TOP_K, ge=1, le=5_000)
    rrf_k: int = Field(default=Config.ENSEMBLE_RRF_K, ge=1, le=10_000)
    preserve_original_query: bool = True
    diversity_time_seconds: float = Field(default=0.0, ge=0.0, allow_inf_nan=False)
    max_per_video: int = Field(default=0, ge=0)
    allow_partial_models: bool = True


class SearchRequest(BaseModel):
    text: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    tag_mode: Literal["and", "or"] = "and"
    keywords: list[str] = Field(default_factory=list)
    keyword_mode: Literal["and", "or"] = "and"
    keyword_source: Literal["all", "ocr", "asr"] = "all"
    topk: int = Field(default=20, ge=1, le=1_000)
    enhance: bool = True
    ensemble: EnsembleOptionsRequest = Field(default_factory=EnsembleOptionsRequest)


class BoxQuery(BaseModel):
    text: str = ""
    image: str = ""
    tags: list[str] = Field(default_factory=list)
    tag_match_mode: Literal["and", "or"] = "and"
    keywords: list[str] = Field(default_factory=list)
    key_match_mode: Literal["and", "or"] = "and"
    enhance: bool | None = None
    topk: int = Field(default=20, ge=1, le=1_000)

    @model_validator(mode="after")
    def validate_query_source(self) -> Self:
        has_text = bool(self.text.strip())
        has_image = bool(self.image.strip())
        if has_text == has_image:
            raise ValueError("each BoxQuery requires exactly one of text or image")
        return self


class MultiBoxRequest(BaseModel):
    box_queries: list[BoxQuery] = Field(min_length=1)
    temporal_window_seconds: float = Field(
        default=120.0,
        gt=0.0,
        allow_inf_nan=False,
    )
    topk: int = Field(default=200, ge=1, le=1_000)
    enhance: bool = True


class SimilarFramesRequest(BaseModel):
    video_id: str = Field(min_length=1)
    frame_index: int = Field(ge=0)
    topk: int = Field(default=12, ge=1, le=200)


class VideoIdRequest(BaseModel):
    video_id: str = Field(min_length=1)
    frame_index: int | None = Field(default=None, ge=0)
    range: int = Field(default=5, ge=0, le=100)


class DRESLoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=256)
    password: str = Field(min_length=1, max_length=1_024)


class DRESSubmissionRequest(BaseModel):
    frame_id: int = Field(ge=0)
    video_path: str = Field(min_length=1, max_length=1_024)
    timestamp: float = Field(ge=0.0, allow_inf_nan=False)
    answer: str = Field(default="", max_length=10_000)


class FrameResult(BaseModel):
    id: str
    frame_uid: str = ""
    video_id: str
    frame_index: int
    frame_idx: int = 0
    shot_idx: int = 0
    start_time: float = 0.0
    end_time: float = 0.0
    pts_time: float = 0.0
    fps: float = 0.0
    score: float = 0.0
    fusion_score: float = 0.0
    model_ranks: dict[str, int] = Field(default_factory=dict)
    model_scores: dict[str, float] = Field(default_factory=dict)
    title: str = ""
    description: str = ""
    keywords: list[str] = Field(default_factory=list)
    thumbnail_url: str = ""
    watch_url: str = ""


class VideoResult(BaseModel):
    video_id: str
    title: str = ""
    description: str = ""
    keywords: list[str] = Field(default_factory=list)
    author: str = ""
    channel_id: str = ""
    length: int = 0
    publish_date: str = ""
    thumbnail_url: str = ""
    watch_url: str = ""
    level: str = ""
    frame_count: int = 0


class EmbedResponse(BaseModel):
    vector: list[float]
    dim: int
    model_id: str
    text: str = ""
    enhanced: bool = False
    filename: str = ""
