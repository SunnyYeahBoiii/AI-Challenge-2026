from flask import Blueprint, jsonify, request

from app.services.dres_client import DresError, dres_client

dres_bp = Blueprint("dres", __name__)


def _err(e: DresError):
    payload = e.body if isinstance(e.body, dict) else {"description": str(e.body)}
    return jsonify({"error": payload, "statusCode": e.status_code}), e.status_code or 502


@dres_bp.route("/api/dres/session", methods=["POST"])
def login():
    payload = request.get_json(silent=True) or {}
    username = payload.get("username")
    password = payload.get("password")
    if not username or not password:
        return jsonify({"error": {"description": "username and password required"}}), 400
    try:
        result = dres_client.login(username, password)
    except DresError as e:
        return _err(e)
    return jsonify({"sessionId": result.get("sessionId"),
                    "username": result.get("username"),
                    "role": result.get("role")})


@dres_bp.route("/api/dres/logout", methods=["POST"])
def logout():
    payload = request.get_json(silent=True) or {}
    session_id = payload.get("sessionId")
    if not session_id:
        return jsonify({"error": {"description": "sessionId required"}}), 400
    try:
        dres_client.logout(session_id)
    except DresError:
        pass
    return jsonify({"loggedOut": True})


@dres_bp.route("/api/dres/evaluations", methods=["GET"])
def evaluations():
    session_id = request.args.get("session")
    if not session_id:
        return jsonify({"error": {"description": "session query param required"}}), 400
    try:
        evals = dres_client.list_evaluations(session_id)
    except DresError as e:
        return _err(e)
    active = [
        {"id": e["id"], "status": e.get("status")}
        for e in evals if e.get("status") == "ACTIVE"
    ]
    return jsonify({"evaluations": active, "total": len(active)})


@dres_bp.route("/api/dres/media-items", methods=["GET"])
def media_items():
    session_id = request.args.get("session")
    if not session_id:
        return jsonify({"error": {"description": "session query param required"}}), 400
    try:
        items = dres_client.list_media_items(session_id)
    except DresError as e:
        return _err(e)
    sample = items[:50] if isinstance(items, list) else items
    return jsonify({"items": sample, "total": len(items) if isinstance(items, list) else 0})


@dres_bp.route("/api/dres/submit/<task_type>", methods=["POST"])
def submit(task_type):
    payload = request.get_json(silent=True) or {}
    video_path = payload.get("video_path") or payload.get("videoId")
    timestamp = payload.get("timestamp", payload.get("timeMs"))
    frame_id = payload.get("frame_id")
    session_id = payload.get("sessionId")
    if not session_id:
        return jsonify({"error": {"description": "sessionId required — log in first"}}), 400
    if not video_path or timestamp is None:
        return jsonify({"error": {"description": "video_path and timestamp required"}}), 400
    evaluation_id = payload.get("evaluationId")
    if not evaluation_id:
        try:
            evals = dres_client.list_evaluations(session_id)
        except DresError as e:
            return _err(e)
        active = [e for e in evals if e.get("status") == "ACTIVE"]
        if not active:
            return jsonify({"error": {"description": "no active evaluation"}}), 404
        evaluation_id = active[0]["id"]
    time_ms = int(float(timestamp) * 1000) if isinstance(timestamp, (int, float)) else int(timestamp)
    try:
        result = dres_client.submit(evaluation_id, video_path, time_ms, session_id)
    except DresError as e:
        return _err(e)
    result["evaluationId"] = evaluation_id
    result["taskType"] = task_type
    if frame_id is not None:
        result["frameId"] = frame_id
    return jsonify(result)
