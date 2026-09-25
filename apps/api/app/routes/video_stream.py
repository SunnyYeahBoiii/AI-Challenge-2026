from typing import Any

import re

from flask import Blueprint, abort, send_from_directory
from flask import send_file

from app.errors import error_response
from app.services.local_videos import resolve_hls_dir, resolve_video_path

video_stream_bp = Blueprint("video_stream", __name__)


@video_stream_bp.route("/api/videos/<video_id>/stream", methods=["GET", "HEAD"])
def stream_video(video_id: str) -> Any:
    """Serve a local mp4/mov with HTTP Range (206) so the browser can seek in GB-size files.

    `conditional=True` makes Werkzeug honour Range/If-Range/ETag and stream the slice
    straight from the file object — no full-file read into memory.
    """
    path = resolve_video_path(video_id)
    if path is None:
        return error_response("NOT_FOUND", "Video file not found", 404)
    # .mov from these sources is h264/aac; labelling it video/mp4 lets Chrome/Firefox play it.
    resp = send_file(path, mimetype="video/mp4", conditional=True, max_age=3600)
    resp.headers["Accept-Ranges"] = "bytes"
    return resp


_HLS_FILE = re.compile(r"^(index\.m3u8|init\.mp4|seg\d+\.m4s)$")
_HLS_MIME = {".m3u8": "application/vnd.apple.mpegurl", ".mp4": "video/mp4", ".m4s": "video/iso.segment"}


@video_stream_bp.route("/api/videos/<video_id>/hls/<filename>", methods=["GET", "HEAD"])
def stream_hls(video_id: str, filename: str) -> Any:
    """Serve a locally packaged HLS playlist/segment. Segments never change, so cache hard."""
    root = resolve_hls_dir(video_id)
    if root is None or not _HLS_FILE.match(filename):
        abort(404)
    is_playlist = filename.endswith(".m3u8")
    resp = send_from_directory(
        root, filename, mimetype=_HLS_MIME["." + filename.rsplit(".", 1)[1]],
        conditional=True, max_age=60 if is_playlist else 31536000,
    )
    if not is_playlist:
        resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return resp
