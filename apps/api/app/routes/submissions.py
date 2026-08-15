from typing import Any

from flask import Blueprint, jsonify, request
from pymilvus.exceptions import MilvusException

from app.services.encoders.manager import NoActiveModelError
from app.services.hybrid_search import search_video_frames
from app.services.storage import keyframe_url, video_url

submissions_bp = Blueprint("submissions", __name__)


@submissions_bp.route("/api/submissions/keyframe", methods=["POST"])
def get_submission_keyframe() -> tuple[Any, int]:
    """Get nearest keyframe for a submission."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body required"}), 400

    video_id = data.get("video_id")
    frame_index = data.get("frame_index")
    search_range = data.get("range", 100)

    if not video_id or frame_index is None:
        return jsonify({"error": "video_id and frame_index required"}), 400

    try:
        results = search_video_frames(video_id, frame_index, search_range)
    except NoActiveModelError as error:
        return jsonify({"error": str(error)}), 409
    except MilvusException as error:
        return jsonify({"error": str(error)}), 400

    if not results:
        return jsonify({"error": "No keyframe found"}), 404

    nearest = min(results, key=lambda f: abs(f["frame_index"] - frame_index))

    return jsonify({
        "frame_index": nearest["frame_index"],
        "timestamp": nearest["timestamp"],
        "thumbnail_url": keyframe_url(video_id, nearest["frame_index"]),
        "video_url": video_url(video_id),
        "is_exact": nearest["frame_index"] == frame_index,
    }), 200


@submissions_bp.route("/api/submissions/keyframes", methods=["POST"])
def get_submission_keyframes() -> tuple[Any, int]:
    """Batch get nearest keyframes for multiple submissions."""
    data = request.get_json()
    if not data or "items" not in data:
        return jsonify({"error": "items array required"}), 400

    items = data["items"]
    results: dict[str, dict[str, Any] | None] = {}

    for item in items:
        video_id = item.get("video_id")
        frame_index = item.get("frame_index")
        key = item.get("key", f"{video_id}-{frame_index}")
        search_range = item.get("range", 100)

        if not video_id or frame_index is None:
            results[key] = None
            continue

        try:
            frames = search_video_frames(video_id, frame_index, search_range)
            if not frames:
                results[key] = None
                continue

            nearest = min(frames, key=lambda f: abs(f["frame_index"] - frame_index))
            results[key] = {
                "frame_index": nearest["frame_index"],
                "timestamp": nearest["timestamp"],
                "thumbnail_url": keyframe_url(video_id, nearest["frame_index"]),
                "video_url": video_url(video_id),
                "is_exact": nearest["frame_index"] == frame_index,
            }
        except Exception:
            results[key] = None

    return jsonify({"keyframes": results}), 200
