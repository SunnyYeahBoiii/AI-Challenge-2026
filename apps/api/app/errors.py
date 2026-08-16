"""Consistent error envelope per docs/rules/architecture.md.

Every error response is `{"error": {"code", "message", "details"?}}` so
clients can branch on `code` instead of parsing prose.
"""
from typing import Any

from flask import jsonify
from werkzeug.exceptions import HTTPException


def error_response(
    code: str, message: str, status: int, details: dict[str, Any] | None = None
) -> tuple[Any, int]:
    body: dict[str, Any] = {"error": {"code": code, "message": message}}
    if details is not None:
        body["error"]["details"] = details
    return jsonify(body), status


def register_error_handlers(app: Any) -> None:
    """Envelope unhandled exceptions and HTTP errors (404, 405, ...)."""

    @app.errorhandler(HTTPException)  # type: ignore[untyped-decorator]
    def _http_error(exc: HTTPException) -> tuple[Any, int]:
        code = exc.name.upper().replace(" ", "_")
        return error_response(code, exc.description or exc.name, exc.code or 500)

    @app.errorhandler(Exception)  # type: ignore[untyped-decorator]
    def _unhandled(exc: Exception) -> tuple[Any, int]:
        return error_response("INTERNAL_ERROR", str(exc), 500)
