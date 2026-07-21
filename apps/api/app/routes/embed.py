from __future__ import annotations

from typing import Any

from flask import Blueprint, jsonify, request
from pydantic import ValidationError

from app.models import EmbedTextRequest
from app.services.embed import embed_image, embed_text, enhance_query
from app.services.model_registry import (
    ModelConfigurationError,
    ModelLoadError,
    get_model_registry,
)

embed_bp = Blueprint("embed", __name__)


def _error(code: str, message: str, status: int) -> tuple[Any, int]:
    return jsonify({"error": {"code": code, "message": message}}), status


@embed_bp.route("/api/embed/text", methods=["POST"])
def api_embed_text() -> tuple[Any, int] | Any:
    try:
        data = EmbedTextRequest.model_validate(request.get_json(silent=True) or {})
        text = enhance_query(data.text) if data.enhance else data.text
        vector = embed_text([text], data.model_id)[0].tolist()
        selected_model = data.model_id or get_model_registry().enabled_specs()[0].model_id
    except ValidationError as error:
        return _error("INVALID_EMBED_REQUEST", str(error), 400)
    except (ModelConfigurationError, ModelLoadError, RuntimeError) as error:
        return _error("EMBEDDING_FAILED", str(error), 422)
    return jsonify(
        {
            "vector": vector,
            "dim": len(vector),
            "model_id": selected_model,
            "text": text,
            "enhanced": text != data.text,
        }
    )

@embed_bp.route("/api/embed/image", methods=["POST"])
def api_embed_image() -> tuple[Any, int] | Any:
    if "image" not in request.files:
        return _error("INVALID_EMBED_REQUEST", "image file is required", 400)
    try:
        model_id = request.form.get("model_id") or None
        vector = embed_image(request.files["image"].read(), model_id).tolist()
        selected_model = model_id or get_model_registry().enabled_specs()[0].model_id
    except ValueError as error:
        return _error("INVALID_EMBED_REQUEST", str(error), 400)
    except (ModelConfigurationError, ModelLoadError, RuntimeError) as error:
        return _error("EMBEDDING_FAILED", str(error), 422)
    return jsonify(
        {
            "vector": vector,
            "dim": len(vector),
            "model_id": selected_model,
            "filename": request.files["image"].filename,
        }
    )


@embed_bp.route("/api/models", methods=["GET"])
def api_models() -> Any:
    specs = get_model_registry().enabled_specs()
    return jsonify(
        {
            "data": [
                {
                    "id": spec.model_id,
                    "adapter": spec.adapter,
                    "modelName": spec.model_name,
                    "pretrained": spec.pretrained,
                    "dimension": spec.dimension,
                    "collection": spec.collection,
                    "weight": spec.weight,
                }
                for spec in specs
            ],
            "meta": {"total": len(specs)},
        }
    )
