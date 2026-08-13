from typing import Any

from flask import Blueprint, jsonify, request

from app.services.es_client import es_client

videos_bp = Blueprint("videos", __name__)


@videos_bp.route("/api/videos")
def list_videos() -> Any:
    q = request.args.get("q", "")
    tags = (
        request.args.getlist("tags")
        or request.args.get("tags", "").split(",")
        if request.args.get("tags")
        else []
    )
    size = int(request.args.get("size", 50))
    results = es_client.search_videos(query=q, tags=tags, size=size)
    return jsonify({
        "videos": [r["_source"] for r in results],
        "total": len(results),
    })


@videos_bp.route("/api/videos/<video_id>")
def get_video(video_id: str) -> Any:
    video = es_client.get_video(video_id)
    if video is None:
        return jsonify({"error": "Video not found"}), 404
    return jsonify(video)
