from __future__ import annotations

import json
import math
import os
import re
from binascii import Error as Base64Error
from pathlib import Path
from typing import Any

from flask import Blueprint, jsonify, request, send_file
from pydantic import ValidationError

from app.config import Config
from app.models import (
    EnsembleOptionsRequest,
    MultiBoxRequest,
    SearchRequest,
    SimilarFramesRequest,
    VideoIdRequest,
)
from app.services.ensemble_search import EnsembleSearchError, EnsembleSearchOptions
from app.services.ensemble_profiles import RetrievalMode, get_ensemble_profile
from app.services.hybrid_search import (
    multi_box_search,
    search_composed_with_meta,
    search_image_with_meta,
    search_similar_frames,
    search_text_with_meta,
    search_video_frames,
)
from app.services.model_registry import ModelConfigurationError, ModelLoadError

API_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = API_ROOT.parents[1] if API_ROOT.parent.name == "apps" else API_ROOT
KEYFRAMES_DIR = Path(
    os.getenv(
        "KEYFRAMES_DIR",
        str(REPOSITORY_ROOT / "data" / "keyframes" / "keyframes"),
    )
)

search_bp = Blueprint("search", __name__)
VIDEO_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}")
MAX_SEARCH_TOP_K = 1_000


def _error(code: str, message: str, status: int) -> tuple[Any, int]:
    return jsonify({"error": {"code": code, "message": message}}), status


def _options(
    data: EnsembleOptionsRequest,
    *,
    result_top_k: int,
    enhance: bool = True,
    mode: RetrievalMode = "text",
) -> EnsembleSearchOptions:
    profile = get_ensemble_profile(data.profile) if data.profile else None
    return EnsembleSearchOptions(
        profile=profile.profile_id if profile else None,
        model_ids=(
            profile.model_ids_for(mode)
            if profile
            else tuple(data.model_ids) if data.model_ids else None
        ),
        model_weights=data.model_weights,
        candidate_top_k=max(data.candidate_topk, result_top_k),
        result_top_k=result_top_k,
        rrf_k=data.rrf_k or (profile.rrf_k if profile else Config.ENSEMBLE_RRF_K),
        use_enhanced_query=enhance,
        preserve_original_query=data.preserve_original_query,
        min_time_gap_seconds=data.diversity_time_seconds,
        max_per_video=data.max_per_video,
        allow_partial_models=data.allow_partial_models,
    )


def _ensemble_form() -> EnsembleOptionsRequest:
    raw_options = request.form.get("ensemble", "{}")
    parsed = json.loads(raw_options)
    if not isinstance(parsed, dict):
        raise ValueError("ensemble form field must be a JSON object")
    return EnsembleOptionsRequest.model_validate(parsed)


def _form_top_k() -> int:
    top_k = int(request.form.get("topk", 20))
    if not 1 <= top_k <= MAX_SEARCH_TOP_K:
        raise ValueError(f"topk must be between 1 and {MAX_SEARCH_TOP_K}")
    return top_k


def _form_match_mode(field: str) -> str:
    mode = request.form.get(field, "and")
    if mode not in {"and", "or"}:
        raise ValueError(f"{field} must be 'and' or 'or'")
    return mode


@search_bp.route("/api/search", methods=["POST"])
def api_search() -> tuple[Any, int] | Any:
    try:
        data = SearchRequest.model_validate(request.get_json(silent=True) or {})
        response = search_text_with_meta(
            data.text,
            options=_options(data.ensemble, result_top_k=data.topk, enhance=data.enhance),
            tags=data.tags,
            tag_mode=data.tag_mode,
            keywords=data.keywords,
            keyword_mode=data.keyword_mode,
            keyword_source=data.keyword_source,
        )
    except (EnsembleSearchError, ModelConfigurationError, ModelLoadError) as error:
        return _error("SEARCH_FAILED", str(error), 422)
    except (ValidationError, ValueError, json.JSONDecodeError) as error:
        return _error("INVALID_SEARCH_REQUEST", str(error), 400)
    return jsonify(
        {
            "query": data.text,
            "enhanced": any(
                variant != data.text.strip() for variant in response.query_variants
            ),
            "results": response.results,
            "total": len(response.results),
            "meta": response.meta(),
        }
    )


@search_bp.route("/api/search/image", methods=["POST"])
def api_search_image() -> tuple[Any, int] | Any:
    if "image" not in request.files:
        return _error("INVALID_IMAGE_REQUEST", "image file is required", 400)
    try:
        top_k = _form_top_k()
        ensemble = _ensemble_form()
        response = search_image_with_meta(
            request.files["image"].read(),
            options=_options(
                ensemble,
                result_top_k=top_k,
                enhance=False,
                mode="image",
            ),
            tags=request.form.getlist("tags"),
            tag_mode=_form_match_mode("tag_mode"),
            keywords=request.form.getlist("keywords"),
            keyword_mode=_form_match_mode("keyword_mode"),
            keyword_source=request.form.get("keyword_source", "all"),
        )
    except (EnsembleSearchError, ModelConfigurationError, ModelLoadError) as error:
        return _error("IMAGE_SEARCH_FAILED", str(error), 422)
    except (ValidationError, ValueError, json.JSONDecodeError) as error:
        return _error("INVALID_IMAGE_REQUEST", str(error), 400)
    return jsonify(
        {
            "filename": request.files["image"].filename,
            "results": response.results,
            "total": len(response.results),
            "meta": response.meta(),
        }
    )


@search_bp.route("/api/search/composed", methods=["POST"])
def api_search_composed() -> tuple[Any, int] | Any:
    if "image" not in request.files:
        return _error("INVALID_COMPOSED_REQUEST", "image file is required", 400)
    try:
        uses_structured_feedback = (
            "original_text" in request.form or "feedback_text" in request.form
        )
        if uses_structured_feedback:
            original_query = request.form.get("original_text", "").strip()
            feedback_text = request.form.get("feedback_text", "").strip()
            if not original_query:
                raise ValueError("original_text is required for structured feedback")
            if not feedback_text:
                raise ValueError("feedback_text is required for structured feedback")
        else:
            original_query = ""
            feedback_text = request.form.get("text", "").strip()
            if not feedback_text:
                raise ValueError("text is required")
        text_weight = float(request.form.get("text_weight", 0.75))
        if not math.isfinite(text_weight) or not 0.0 <= text_weight <= 1.0:
            raise ValueError("text_weight must be between 0 and 1")
        top_k = _form_top_k()
        ensemble = _ensemble_form()
        response = search_composed_with_meta(
            feedback_text,
            request.files["image"].read(),
            original_query=original_query or None,
            text_weight=text_weight,
            options=_options(
                ensemble,
                result_top_k=top_k,
                enhance=False,
                mode="composed",
            ),
        )
    except (EnsembleSearchError, ModelConfigurationError, ModelLoadError) as error:
        return _error("COMPOSED_SEARCH_FAILED", str(error), 422)
    except (ValidationError, ValueError, json.JSONDecodeError) as error:
        return _error("INVALID_COMPOSED_REQUEST", str(error), 400)
    return jsonify(
        {
            "query": response.query,
            "originalQuery": original_query,
            "feedbackText": feedback_text,
            "textWeight": text_weight,
            "results": response.results,
            "total": len(response.results),
            "meta": response.meta(),
        }
    )


@search_bp.route("/api/search/video", methods=["POST"])
def api_search_video() -> tuple[Any, int] | Any:
    try:
        data = VideoIdRequest.model_validate(request.get_json(silent=True) or {})
    except ValidationError as error:
        return _error("INVALID_VIDEO_REQUEST", str(error), 400)
    results = search_video_frames(data.video_id, data.frame_index, data.range)
    return jsonify({"video_id": data.video_id, "results": results, "total": len(results)})


@search_bp.route("/api/search/similar", methods=["POST"])
def api_search_similar() -> tuple[Any, int] | Any:
    try:
        data = SimilarFramesRequest.model_validate(request.get_json(silent=True) or {})
    except ValidationError as error:
        return _error("INVALID_SIMILAR_REQUEST", str(error), 400)
    results = search_similar_frames(data.video_id, data.frame_index, data.topk)
    return jsonify({"results": results, "total": len(results)})


@search_bp.route("/api/frames", methods=["POST"])
def api_frames() -> tuple[Any, int] | Any:
    try:
        data = MultiBoxRequest.model_validate(request.get_json(silent=True) or {})
        results = multi_box_search(
            box_queries=[box.model_dump() for box in data.box_queries],
            temporal_window=data.temporal_window_seconds,
            topk=data.topk,
            enhance=data.enhance,
        )
    except (EnsembleSearchError, ModelConfigurationError, ModelLoadError) as error:
        return _error("BOX_SEARCH_FAILED", str(error), 422)
    except ValidationError as error:
        return _error("INVALID_BOX_QUERY", str(error), 400)
    except (ValueError, Base64Error) as error:
        return _error("INVALID_BOX_QUERY", str(error), 400)
    return jsonify({"results": results, "total": len(results)})


@search_bp.route("/api/keyframes/<video_id>/<int:frame_index>")
def serve_keyframe(video_id: str, frame_index: int) -> tuple[Any, int] | Any:
    if VIDEO_ID_PATTERN.fullmatch(video_id) is None:
        return _error("INVALID_VIDEO_ID", "Invalid video id", 400)
    level = video_id[:3]
    root = KEYFRAMES_DIR.resolve()
    path = (root / level / video_id / f"{frame_index:04d}.webp").resolve()
    if not path.is_relative_to(root):
        return _error("INVALID_VIDEO_ID", "Invalid video id", 400)
    if path.is_file():
        return send_file(path, mimetype="image/webp")
    return _error("FRAME_NOT_FOUND", "Frame not found", 404)
