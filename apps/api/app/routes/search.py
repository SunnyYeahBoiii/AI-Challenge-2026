import logging

from flask import Blueprint, request, jsonify
from pymilvus.exceptions import MilvusException

from app.errors import error_response
from app.models import (
    ALLOWED_VIDEO_PREFIXES,
    MultiBoxRequest,
    RepeatFramesRequest,
    SearchRequest,
    SimilarFramesRequest,
    VideoIdRequest,
)
from app.services.encoders.manager import NoActiveModelError
from app.services.hybrid_search import (
    search_text,
    search_image,
    search_video_frames,
    multi_box_search,
    search_similar_frames,
)
from app.services.object_filter import ObjectFilterError
from app.services.repeat_detection import find_repeat_frame_details

logger = logging.getLogger(__name__)

search_bp = Blueprint("search", __name__)


def _milvus_error_response(error: MilvusException):
    """Surface Milvus client failures as JSON instead of Werkzeug HTML."""
    return error_response("MILVUS_ERROR", str(error), 502)


@search_bp.route("/api/search", methods=["POST"])
def api_search():
    try:
        data = SearchRequest(**request.get_json())
    except Exception as e:
        return error_response("VALIDATION_ERROR", str(e), 400)
    try:
        results = search_text(
            query=data.text,
            tags=data.tags,
            keywords=data.keywords,
            topk=data.topk,
            enhance=data.enhance,
            tag_mode=data.tag_mode,
            keyword_mode=data.keyword_mode,
            keyword_source=data.keyword_source,
            ocr_keywords=data.ocr_keywords,
            asr_keywords=data.asr_keywords,
            ocr_mode=data.ocr_match_mode,
            asr_mode=data.asr_match_mode,
            ocr_search_mode=data.ocr_search_mode,
            asr_search_mode=data.asr_search_mode,
            keyword_field_mode=data.keyword_field_mode,
            video_prefixes=data.video_prefixes,
        )
    except NoActiveModelError as error:
        return error_response("NO_ACTIVE_MODEL", str(error), 409)
    except ObjectFilterError as error:
        return error_response("OBJECT_FILTER_FAILED", str(error), 500)
    except MilvusException as error:
        return _milvus_error_response(error)
    return jsonify({
        "query": data.text,
        "enhanced": data.enhance,
        "results": results,
        "total": len(results),
    })


@search_bp.route("/api/search/image", methods=["POST"])
def api_search_image():
    if "image" not in request.files:
        return error_response("VALIDATION_ERROR", "image file required", 400)
    file = request.files["image"]
    try:
        topk = int(request.form.get("topk", 20))
    except ValueError:
        return error_response("VALIDATION_ERROR", "topk must be an integer", 400)
    topk = max(1, min(topk, 5000))
    tags = request.form.getlist("tags") if request.form.get("tags") else []
    keywords = request.form.getlist("keywords") if request.form.get("keywords") else []
    ocr_keywords = (
        request.form.getlist("ocr_keywords") if request.form.get("ocr_keywords") else []
    )
    asr_keywords = (
        request.form.getlist("asr_keywords") if request.form.get("asr_keywords") else []
    )
    ocr_search_mode = request.form.get("ocr_search_mode", "exact")
    asr_search_mode = request.form.get("asr_search_mode", "exact")
    keyword_field_mode = request.form.get("keyword_field_mode", "and")
    video_prefixes = request.form.getlist("video_prefixes")
    if ocr_search_mode not in {"fuzzy", "exact"}:
        return error_response("VALIDATION_ERROR", "ocr_search_mode must be fuzzy or exact", 400)
    if asr_search_mode not in {"fuzzy", "exact"}:
        return error_response("VALIDATION_ERROR", "asr_search_mode must be fuzzy or exact", 400)
    if keyword_field_mode not in {"asr", "ocr", "or", "and"}:
        return error_response(
            "VALIDATION_ERROR", "keyword_field_mode must be one of: asr, ocr, or, and", 400
        )
    if any(prefix not in ALLOWED_VIDEO_PREFIXES for prefix in video_prefixes):
        return error_response("VALIDATION_ERROR", "video_prefixes contains an unsupported video prefix", 400)
    image_bytes = file.read()
    try:
        results = search_image(
            image_bytes=image_bytes,
            tags=tags,
            keywords=keywords,
            topk=topk,
            tag_mode=request.form.get("tag_mode", "and"),
            keyword_mode=request.form.get("keyword_mode", "and"),
            keyword_source=request.form.get("keyword_source", "all"),
            ocr_keywords=ocr_keywords,
            asr_keywords=asr_keywords,
            ocr_mode=request.form.get("ocr_match_mode") or None,
            asr_mode=request.form.get("asr_match_mode") or None,
            ocr_search_mode=ocr_search_mode,
            asr_search_mode=asr_search_mode,
            keyword_field_mode=keyword_field_mode,
            video_prefixes=video_prefixes,
        )
    except NoActiveModelError as error:
        return error_response("NO_ACTIVE_MODEL", str(error), 409)
    except ObjectFilterError as error:
        return error_response("OBJECT_FILTER_FAILED", str(error), 500)
    except MilvusException as error:
        return _milvus_error_response(error)
    return jsonify({
        "filename": file.filename,
        "results": results,
        "total": len(results),
    })


@search_bp.route("/api/search/video", methods=["POST"])
def api_search_video():
    try:
        data = VideoIdRequest(**request.get_json())
    except Exception as e:
        return error_response("VALIDATION_ERROR", str(e), 400)
    try:
        results = search_video_frames(data.video_id, data.frame_index, data.range)
    except NoActiveModelError as error:
        return error_response("NO_ACTIVE_MODEL", str(error), 409)
    except MilvusException as error:
        return _milvus_error_response(error)
    return jsonify({
        "video_id": data.video_id,
        "results": results,
        "total": len(results),
    })


@search_bp.route("/api/search/similar", methods=["POST"])
def api_search_similar():
    try:
        data = SimilarFramesRequest(**request.get_json())
    except Exception as e:
        return error_response("VALIDATION_ERROR", str(e), 400)
    try:
        results = search_similar_frames(data.video_id, data.frame_index, data.topk)
    except NoActiveModelError as error:
        return error_response("NO_ACTIVE_MODEL", str(error), 409)
    except MilvusException as error:
        return _milvus_error_response(error)
    return jsonify({
        "results": results,
        "total": len(results),
    })


@search_bp.route("/api/frames", methods=["POST"])
def api_frames():
    try:
        data = MultiBoxRequest(**request.get_json())
    except Exception as e:
        return error_response("VALIDATION_ERROR", str(e), 400)
    box_list = [b.model_dump() for b in data.box_queries]
    try:
        results = multi_box_search(
            box_queries=box_list,
            temporal_window=data.temporal_window_seconds,
            enhance=data.enhance,
            mode=data.mode,
            video_prefixes=data.video_prefixes,
        )
    except NoActiveModelError as error:
        return error_response("NO_ACTIVE_MODEL", str(error), 409)
    except ObjectFilterError as error:
        return error_response("OBJECT_FILTER_FAILED", str(error), 500)
    except MilvusException as error:
        return _milvus_error_response(error)
    return jsonify(results)


@search_bp.route("/api/frames/repeats", methods=["POST"])
def api_repeat_frames():
    """Mark visually repeated frames in one bounded displayed-result batch."""
    try:
        data = RepeatFramesRequest(**request.get_json())
    except Exception as error:
        return error_response("VALIDATION_ERROR", str(error), 400)
    try:
        repeat_details = find_repeat_frame_details(
            [(frame.video_id, frame.frame_index, frame.timestamp) for frame in data.frames]
        )
    except NoActiveModelError as error:
        return error_response("NO_ACTIVE_MODEL", str(error), 409)
    except MilvusException as error:
        return _milvus_error_response(error)
    except ValueError as error:
        return error_response("VALIDATION_ERROR", str(error), 400)
    except Exception as error:
        logger.exception("Could not detect repeated frames")
        return error_response("REPEAT_DETECTION_FAILED", str(error), 502)
    return jsonify({
        "repeat_frames": [
            {"video_id": video_id, "frame_index": frame_index, **details}
            for (video_id, frame_index), details in sorted(repeat_details.items())
        ]
    })
