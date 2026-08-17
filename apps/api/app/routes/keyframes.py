import re
from typing import Any

from flask import Blueprint, abort, send_from_directory

from app.config import Config

keyframes_bp = Blueprint("keyframes", __name__)

_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9_-]+$")
_SAFE_FILENAME = re.compile(r"^\d+\.webp$")


@keyframes_bp.route("/api/keyframes/<level>/<video_id>/<filename>")
def get_keyframe(level: str, video_id: str, filename: str) -> Any:
    if not (_SAFE_SEGMENT.match(level) and _SAFE_SEGMENT.match(video_id) and _SAFE_FILENAME.match(filename)):
        abort(404)
    return send_from_directory(f"{Config.KEYFRAMES_DIR}/{level}/{video_id}", filename)
