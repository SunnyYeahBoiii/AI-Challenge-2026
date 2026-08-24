from flask import Blueprint, jsonify, request

from app.errors import error_response
from app.services.dres_client import DresError, dres_client

dres_bp = Blueprint("dres", __name__)


def _err(e: DresError):
    details = e.body if isinstance(e.body, dict) else {"description": str(e.body)}
    return error_response("DRES_ERROR", "DRES request failed", e.status_code or 502, details)


@dres_bp.route("/api/dres/session", methods=["POST"])
def login():
    payload = request.get_json(silent=True) or {}
    username = payload.get("username")
    password = payload.get("password")
    dres_url = payload.get("dresUrl")
    if not username or not password:
        return error_response("VALIDATION_ERROR", "username and password required", 400)
    try:
        result = dres_client.login(username, password, dres_url)
    except DresError as e:
        return _err(e)
    return jsonify({"sessionId": result.get("sessionId"),
                    "username": result.get("username"),
                    "role": result.get("role")})


@dres_bp.route("/api/dres/logout", methods=["POST"])
def logout():
    payload = request.get_json(silent=True) or {}
    session_id = payload.get("sessionId")
    dres_url = payload.get("dresUrl")
    if not session_id:
        return error_response("VALIDATION_ERROR", "sessionId required", 400)
    try:
        dres_client.logout(session_id, dres_url)
    except DresError:
        pass
    return jsonify({"loggedOut": True})


@dres_bp.route("/api/dres/evaluations", methods=["GET"])
def evaluations():
    session_id = request.args.get("session")
    dres_url = request.args.get("dresUrl")
    if not session_id:
        return error_response("VALIDATION_ERROR", "session query param required", 400)
    try:
        evals = dres_client.list_evaluations(session_id, dres_url)
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
    dres_url = request.args.get("dresUrl")
    if not session_id:
        return error_response("VALIDATION_ERROR", "session query param required", 400)
    try:
        items = dres_client.list_media_items(session_id, dres_url)
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
    dres_url = payload.get("dresUrl")
    if not session_id:
        return error_response("VALIDATION_ERROR", "sessionId required — log in first", 400)

    is_trake = task_type in ("track", "trake")
    frame_ids = payload.get("frame_ids") or payload.get("frameIds")

    if is_trake:
        if not video_path:
            return error_response("VALIDATION_ERROR", "video_path required for TRAKE", 400)
        if not isinstance(frame_ids, list) or len(frame_ids) == 0:
            return error_response("VALIDATION_ERROR", "frame_ids required for TRAKE", 400)
        try:
            frame_ids = [int(fid) for fid in frame_ids]
        except (TypeError, ValueError):
            return error_response("VALIDATION_ERROR", "frame_ids must be integers", 400)
    elif not video_path or timestamp is None:
        return error_response("VALIDATION_ERROR", "video_path and timestamp required", 400)

    qa_answer = ""
    if task_type == "qa":
        raw_answer = payload.get("answer") or payload.get("text") or ""
        if isinstance(raw_answer, list):
            qa_answer = "\n".join(str(a) for a in raw_answer).strip()
        else:
            qa_answer = str(raw_answer).strip()
        if not qa_answer:
            return error_response("VALIDATION_ERROR", "answer required for QA", 400)

    evaluation_id = payload.get("evaluationId")
    if not evaluation_id:
        try:
            evals = dres_client.list_evaluations(session_id, dres_url)
        except DresError as e:
            return _err(e)
        active = [e for e in evals if e.get("status") == "ACTIVE"]
        if not active:
            return error_response("NOT_FOUND", "no active evaluation", 404)
        evaluation_id = active[0]["id"]

    try:
        if is_trake:
            result = dres_client.submit_trake(
                evaluation_id, video_path, frame_ids, session_id, dres_url
            )
            result["frameIds"] = frame_ids
            result["trakeText"] = f"TR-{video_path}-{','.join(str(f) for f in frame_ids)}"
        elif task_type == "qa":
            time_ms = int(float(timestamp) * 1000)
            result = dres_client.submit_qa(
                evaluation_id, qa_answer, video_path, time_ms, session_id, dres_url
            )
        else:
            time_ms = int(float(timestamp) * 1000)
            result = dres_client.submit(evaluation_id, video_path, time_ms, session_id, dres_url)
    except DresError as e:
        return _err(e)
    result["evaluationId"] = evaluation_id
    result["taskType"] = task_type
    if frame_id is not None:
        result["frameId"] = frame_id
    return jsonify(result)
