import re
from pathlib import Path
from typing import Any

from flask import Blueprint, abort, jsonify, request, send_from_directory

from app.config import Config
from app.errors import error_response
from app.services.es_client import es_client

videos_bp = Blueprint("videos", __name__)
_SAFE_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]+$")
_SAFE_HLS_ASSET = re.compile(r"^(?:index\.m3u8|init\.mp4|seg\d{5}\.m4s)$")
_SOURCE_CONTENT_TYPES = {"mp4": "video/mp4", "mov": "video/quicktime"}
_HLS_CONTENT_TYPES = {
    "m3u8": "application/vnd.apple.mpegurl",
    "mp4": "video/mp4",
    "m4s": "video/iso.segment",
}


@videos_bp.route("/api/media/videos/<video_id>.<extension>")
def get_local_video(video_id: str, extension: str) -> Any:
    if not _SAFE_VIDEO_ID.fullmatch(video_id) or extension not in _SOURCE_CONTENT_TYPES:
        abort(404)
    return send_from_directory(
        Config.VIDEOS_DIR,
        f"{video_id}.{extension}",
        conditional=True,
        mimetype=_SOURCE_CONTENT_TYPES[extension],
    )


@videos_bp.route("/api/media/videos/<video_id>/<asset>")
def get_local_hls_asset(video_id: str, asset: str) -> Any:
    if not _SAFE_VIDEO_ID.fullmatch(video_id) or not _SAFE_HLS_ASSET.fullmatch(asset):
        abort(404)
    extension = asset.rsplit(".", 1)[-1]
    return send_from_directory(
        Path(Config.VIDEOS_DIR) / video_id,
        asset,
        conditional=True,
        mimetype=_HLS_CONTENT_TYPES[extension],
    )


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
