from __future__ import annotations

from typing import Any

from flask import Blueprint, jsonify

from app.services.es_client import es_client
from app.services.milvus_client import get_milvus_client
from app.services.model_registry import get_model_registry

health_bp = Blueprint("health", __name__)


@health_bp.route("/api/health")
def health() -> Any:
    collection_status: dict[str, str] = {}
    try:
        specs = get_model_registry().enabled_specs()
        for spec in specs:
            try:
                is_connected = get_milvus_client(spec).is_connected()
            except Exception:
                is_connected = False
            collection_status[spec.model_id] = "connected" if is_connected else "disconnected"
    except Exception:
        collection_status["configuration"] = "invalid"
    elasticsearch_ok = es_client.is_connected()
    milvus_ok = bool(collection_status) and all(
        status == "connected" for status in collection_status.values()
    )
    return jsonify(
        {
            "status": "healthy" if milvus_ok and elasticsearch_ok else "degraded",
            "milvus": "connected" if milvus_ok else "disconnected",
            "elasticsearch": "connected" if elasticsearch_ok else "disconnected",
            "models": collection_status,
        }
    )
