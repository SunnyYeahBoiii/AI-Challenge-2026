from flask import Blueprint, request, jsonify
from pymilvus.exceptions import MilvusException

from app.errors import error_response
from app.models import (
    FrameContextRequest,
    MultiBoxRequest,
    SearchRequest,
    SimilarFramesRequest,
    VideoIdRequest,
)
from app.services.encoders.manager import NoActiveModelError
from app.services.es_client import ElasticsearchSearchError
from app.services.frame_context import get_frame_contexts
from app.services.hybrid_search import (
    search_text,
    search_image,
    search_video_frames,
    multi_box_search,
    search_similar_frames,
)
from app.services.object_filter import ObjectFilterError

search_bp = Blueprint("search", __name__)


def _milvus_error_response(error: MilvusException):
    """Surface Milvus client failures as JSON instead of Werkzeug HTML."""
    return error_response("MILVUS_ERROR", str(error), 502)


def _elasticsearch_error_response(error: ElasticsearchSearchError):
    """Return a retryable response for an Elasticsearch availability failure."""
    return error_response(
        "ELASTICSEARCH_UNAVAILABLE",
        "Elasticsearch is temporarily unavailable. Please retry.",
        502,
        {"operation": error.operation},
    )


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
            ocr_search_config=(data.ocr_search_config.model_dump() if data.ocr_search_config else None),
            asr_search_config=(data.asr_search_config.model_dump() if data.asr_search_config else None),
        )
    except NoActiveModelError as error:
        return error_response("NO_ACTIVE_MODEL", str(error), 409)
    except ObjectFilterError as error:
        return error_response("OBJECT_FILTER_FAILED", str(error), 500)
    except ElasticsearchSearchError as error:
        return _elasticsearch_error_response(error)
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
        )
    except NoActiveModelError as error:
        return error_response("NO_ACTIVE_MODEL", str(error), 409)
    except ObjectFilterError as error:
        return error_response("OBJECT_FILTER_FAILED", str(error), 500)
    except ElasticsearchSearchError as error:
        return _elasticsearch_error_response(error)
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
        )
    except NoActiveModelError as error:
        return error_response("NO_ACTIVE_MODEL", str(error), 409)
    except ObjectFilterError as error:
        return error_response("OBJECT_FILTER_FAILED", str(error), 500)
    except ElasticsearchSearchError as error:
        return _elasticsearch_error_response(error)
    except MilvusException as error:
        return _milvus_error_response(error)
    return jsonify(results)


@search_bp.route("/api/frames/context", methods=["POST"])
def api_frame_context():
    try:
        data = FrameContextRequest(**request.get_json())
    except Exception as error:
        return error_response("VALIDATION_ERROR", str(error), 400)
    try:
        collection_name, contexts = get_frame_contexts([
            (window.video_id, window.start_frame_index, window.end_frame_index)
            for window in data.windows
        ])
    except NoActiveModelError as error:
        return error_response("NO_ACTIVE_MODEL", str(error), 409)
    except MilvusException as error:
        return _milvus_error_response(error)
    except ElasticsearchSearchError as error:
        return _elasticsearch_error_response(error)
    except RuntimeError as error:
        return error_response("CONTEXT_LOOKUP_FAILED", str(error), 502)
    return jsonify({"collection_name": collection_name, "contexts": contexts})
