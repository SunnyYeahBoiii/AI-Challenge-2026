from typing import Any

from flask import Blueprint, jsonify, request

from app.errors import error_response
from app.services.es_client import es_client

videos_bp = Blueprint("videos", __name__)


@videos_bp.route("/api/videos")
def list_videos() -> Any:
    q = request.args.get("q", "")
    try:
        size = int(request.args.get("size", 50))
    except ValueError:
        return error_response("VALIDATION_ERROR", "size must be an integer", 400)
    results = es_client.search_videos(query=q, size=size)
    return jsonify({
        "videos": [r["_source"] for r in results],
        "total": len(results),
    })


@videos_bp.route("/api/videos/<video_id>")
def get_video(video_id: str) -> Any:
    video = es_client.get_video(video_id)
    if video is None:
        return error_response("NOT_FOUND", "Video not found", 404)
    return jsonify(video)
