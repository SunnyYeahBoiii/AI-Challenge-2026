from flask import Blueprint, jsonify
from app.config import Config
from app.services.milvus_client import ping as milvus_ping

health_bp = Blueprint("health", __name__)

@health_bp.route("/api/health")
def health():
    try:
        milvus_ok = milvus_ping()
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


@health_bp.route("/api/media/sources")
def media_sources():
    """Expose only public playback-origin availability to the web client."""
    return jsonify({
        "cloudfront": bool(Config.MEDIA_BASE_URL),
        "minio": bool(Config.MINIO_ENDPOINT and Config.MINIO_BUCKET_VIDEOS),
    })
