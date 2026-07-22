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


@dres_bp.route("/api/dres/submit/<task_type>", methods=["POST"])
def submit(task_type):
    payload = request.get_json(silent=True) or {}
    video_path = payload.get("video_path") or payload.get("videoId")
    timestamp = payload.get("timestamp", payload.get("timeMs"))
    frame_id = payload.get("frame_id")
    if not video_path or timestamp is None:
        return jsonify({"error": "video_path and timestamp required"}), 400
    evaluation_id = payload.get("evaluationId")
    if not evaluation_id:
        try:
            evals = dres_client.list_evaluations()
        except DresError as e:
            return jsonify({"error": str(e)}), 502
        active = [e for e in evals if e.get("status") == "ACTIVE"]
        if not active:
            return jsonify({"error": "no active evaluation"}), 404
        evaluation_id = active[0]["id"]
    time_ms = int(float(timestamp) * 1000) if isinstance(timestamp, (int, float)) else int(timestamp)
    try:
        result = dres_client.submit(evaluation_id, video_path, time_ms)
    except DresError as e:
        return jsonify({"error": str(e)}), 502
    result["evaluationId"] = evaluation_id
    result["taskType"] = task_type
    if frame_id is not None:
        result["frameId"] = frame_id
    return jsonify(result)
