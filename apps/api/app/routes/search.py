from pathlib import Path

from flask import Blueprint, request, jsonify, send_file
from app.models import SearchRequest, MultiBoxRequest, VideoIdRequest, SimilarFramesRequest
from app.services.hybrid_search import (
    search_text,
    search_image,
    search_video_frames,
    multi_box_search,
    search_similar_frames,
)

KEYFRAMES_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "data" / "keyframes" / "keyframes"

search_bp = Blueprint("search", __name__)


@search_bp.route("/api/search", methods=["POST"])
def api_search():
    try:
        data = SearchRequest(**request.get_json())
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    results = search_text(
        query=data.text,
        tags=data.tags,
        keywords=data.keywords,
        topk=data.topk,
        enhance=data.enhance,
    )
    return jsonify({
        "query": data.text,
        "enhanced": data.enhance,
        "results": results,
        "total": len(results),
    })


@search_bp.route("/api/search/image", methods=["POST"])
def api_search_image():
    if "image" not in request.files:
        return jsonify({"error": "image file required"}), 400
    file = request.files["image"]
    topk = int(request.form.get("topk", 20))
    tags = request.form.getlist("tags") if request.form.get("tags") else []
    keywords = request.form.getlist("keywords") if request.form.get("keywords") else []
    image_bytes = file.read()
    results = search_image(
        image_bytes=image_bytes,
        tags=tags,
        keywords=keywords,
        topk=topk,
    )
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
        return jsonify({"error": str(e)}), 400
    results = search_video_frames(data.video_id, data.frame_index, data.range)
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
        return jsonify({"error": str(e)}), 400
    results = search_similar_frames(data.video_id, data.frame_index, data.topk)
    return jsonify({
        "results": results,
        "total": len(results),
    })


@search_bp.route("/api/frames", methods=["POST"])
def api_frames():
    try:
        data = MultiBoxRequest(**request.get_json())
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    box_list = [b.model_dump() for b in data.box_queries]
    results = multi_box_search(
        box_queries=box_list,
        temporal_window=data.temporal_window_seconds,
        topk=data.topk,
        enhance=data.enhance,
        mode=data.mode,
    )
    return jsonify({
        "results": results,
        "total": len(results),
    })


@search_bp.route("/api/keyframes/<video_id>/<int:frame_index>")
def serve_keyframe(video_id, frame_index):
    level = video_id[:3]
    path = KEYFRAMES_DIR / level / video_id / f"{frame_index:04d}.webp"
    if path.exists():
        return send_file(path, mimetype="image/webp")
    return jsonify({"error": "frame not found"}), 404
