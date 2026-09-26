from typing import Any

from flask import Blueprint, jsonify, request

from app.config import Config
from app.errors import error_response
from app.models import AgentRunRequest
from app.services.agent.jobs import get_job, start_job

agent_bp = Blueprint("agent", __name__)


@agent_bp.route("/api/agent/trake/run", methods=["POST"])
def run_trake_agent() -> Any:
    """Start the agent for the shared board's Events; poll the returned job."""
    if not Config.ANTHROPIC_API_KEY:
        return error_response("AGENT_NOT_CONFIGURED", "ANTHROPIC_API_KEY is not set", 503)
    try:
        data = AgentRunRequest(**(request.get_json(silent=True) or {}))
    except Exception as error:
        return error_response("VALIDATION_ERROR", str(error), 400)
    job_id = start_job(data.instruction, data.event_ids or None)
    return jsonify({"job_id": job_id}), 202


@agent_bp.route("/api/agent/trake/<job_id>", methods=["GET"])
def get_trake_agent_job(job_id: str) -> Any:
    job = get_job(job_id)
    if job is None:
        return error_response("NOT_FOUND", "job not found", 404)
    return jsonify(job)
