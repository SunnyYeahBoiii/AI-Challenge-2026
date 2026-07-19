from flask import Blueprint, jsonify
from app.services.milvus_client import get_milvus_client

health_bp = Blueprint("health", __name__)

@health_bp.route("/api/health")
def health():
    try:
        milvus_ok = get_milvus_client().is_connected()
    except Exception:
        milvus_ok = False
    try:
        from app.services.es_client import es_client
        es_ok = es_client.is_connected()
    except Exception:
        es_ok = False
    return jsonify({
        "status": "healthy" if milvus_ok and es_ok else "degraded",
        "milvus": "connected" if milvus_ok else "disconnected",
        "elasticsearch": "connected" if es_ok else "disconnected",
    })
