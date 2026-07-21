from __future__ import annotations

from typing import Any

from flask import Blueprint, jsonify, request
from pydantic import ValidationError

from app.models import DRESLoginRequest, DRESSubmissionRequest
from app.services.dres import DRESError, dres_client

dres_bp = Blueprint("dres", __name__)


def _error(code: str, message: str, status: int) -> tuple[Any, int]:
    return jsonify({"error": {"code": code, "message": message}}), status


@dres_bp.route("/api/dres/login", methods=["POST"])
def api_dres_login() -> tuple[Any, int] | Any:
    try:
        data = DRESLoginRequest.model_validate(request.get_json(silent=True) or {})
        result = dres_client.login(data.username, data.password)
    except ValidationError as error:
        return _error("INVALID_DRES_LOGIN", str(error), 400)
    except DRESError as error:
        return _error("DRES_LOGIN_FAILED", str(error), 502)
    return jsonify(result)


@dres_bp.route("/api/dres/submit/<submission_type>", methods=["POST"])
def api_dres_submit(submission_type: str) -> tuple[Any, int] | Any:
    try:
        data = DRESSubmissionRequest.model_validate(request.get_json(silent=True) or {})
        result = dres_client.submit(
            submission_type,
            video_id=data.video_path,
            timestamp=data.timestamp,
            answer=data.answer,
        )
    except (ValidationError, ValueError) as error:
        return _error("INVALID_DRES_SUBMISSION", str(error), 400)
    except DRESError as error:
        return _error("DRES_SUBMISSION_FAILED", str(error), 502)
    return jsonify(result)
