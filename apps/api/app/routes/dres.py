from flask import Blueprint, jsonify, request

from app.services.dres_client import DresError, dres_client

dres_bp = Blueprint("dres", __name__)


@dres_bp.route("/api/dres/session", methods=["POST"])
def login():
    try:
        result = dres_client.login()
    except DresError as e:
        return jsonify({"error": str(e)}), 502
    return jsonify({"sessionId": result.get("sessionId"),
                    "username": result.get("username"),
                    "role": result.get("role")})


@dres_bp.route("/api/dres/evaluations", methods=["GET"])
def evaluations():
    try:
        evals = dres_client.list_evaluations()
    except DresError as e:
        return jsonify({"error": str(e)}), 502
    active = [
        {"id": e["id"], "status": e.get("status")}
        for e in evals if e.get("status") == "ACTIVE"
    ]
    return jsonify({"evaluations": active, "total": len(active)})


@dres_bp.route("/api/dres/submit", methods=["POST"])
def submit():
    payload = request.get_json(silent=True) or {}
    evaluation_id = payload.get("evaluationId")
    video_id = payload.get("videoId")
    time_ms = payload.get("timeMs")
    if not evaluation_id or not video_id or time_ms is None:
        return jsonify({"error": "evaluationId, videoId, timeMs required"}), 400
    try:
        result = dres_client.submit(evaluation_id, video_id, int(time_ms))
    except DresError as e:
        return jsonify({"error": str(e)}), 502
    return jsonify(result)
