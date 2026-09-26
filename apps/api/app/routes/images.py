"""Image input routes."""

import base64
from typing import Any

from flask import Blueprint, Response, jsonify, request

from app.errors import error_response
from app.services.image_sources import ImageSourceError, fetch_public_image

images_bp = Blueprint("images", __name__)


@images_bp.route("/api/images/fetch", methods=["POST"])
def api_fetch_image() -> Response | tuple[Any, int]:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not isinstance(payload.get("url"), str):
        return error_response("VALIDATION_ERROR", "url is required", 400)

    url = payload["url"].strip()
    if not url:
        return error_response("VALIDATION_ERROR", "url is required", 400)

    try:
        image = fetch_public_image(url)
    except ImageSourceError as exc:
        return error_response(exc.code, str(exc), exc.status_code)

    encoded = base64.b64encode(image.data).decode("ascii")
    return jsonify(
        {
            "data": {
                "data_url": f"data:{image.media_type};base64,{encoded}",
                "media_type": image.media_type,
                "size": len(image.data),
            }
        }
    )
