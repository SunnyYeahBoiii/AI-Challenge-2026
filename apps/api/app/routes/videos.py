from typing import Any

from flask import Blueprint, jsonify, request

from app.services.es_client import es_client

videos_bp = Blueprint("videos", __name__)


@videos_bp.route("/api/videos")
def list_videos() -> Any:
    q = request.args.get("q", "")
    tags = [
        tag.strip()
        for raw_tag in request.args.getlist("tags")
        for tag in raw_tag.split(",")
        if tag.strip()
    ]
    try:
        size = int(request.args.get("size", 50))
    except ValueError:
        return jsonify({"error": "size must be an integer between 1 and 1000"}), 400
    if not 1 <= size <= 1_000:
        return jsonify({"error": "size must be an integer between 1 and 1000"}), 400
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
