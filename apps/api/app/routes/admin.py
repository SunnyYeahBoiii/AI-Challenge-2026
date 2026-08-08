from flask import Blueprint, jsonify, request
from flask.typing import ResponseReturnValue

from app.services.encoders import manager

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/api/admin/model", methods=["GET"])
def get_model() -> ResponseReturnValue:
    return jsonify({"status": manager.get_status(), "available_models": manager.list_models()})


@admin_bp.route("/api/admin/model", methods=["POST"])
def set_model() -> ResponseReturnValue:
    body = request.get_json(silent=True) or {}
    model_id = body.get("model_id")
    collection_name = body.get("collection_name")

    if model_id is None:
        status = manager.unload()
        return jsonify({"status": status})

    try:
        status = manager.swap(model_id, collection_name)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc), "status": manager.get_status()}), 500

    return jsonify({"status": status})
