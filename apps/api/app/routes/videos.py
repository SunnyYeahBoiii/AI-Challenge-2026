from flask import Blueprint

videos_bp = Blueprint("videos", __name__)


@videos_bp.route("/api/videos")
def list_videos():
    return {"videos": []}
