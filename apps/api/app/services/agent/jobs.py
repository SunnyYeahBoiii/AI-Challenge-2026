"""File-backed job store: gunicorn runs several workers, so job state cannot
live in process memory (same constraint as DresClient)."""
from __future__ import annotations

import json
import logging
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Any

from app.services.agent.runner import run_agent

logger = logging.getLogger(__name__)

JOBS_DIR = Path(tempfile.gettempdir()) / "frameseeker_agent_jobs"


def _path(job_id: str) -> Path:
    return JOBS_DIR / f"{job_id}.json"


def _write(job_id: str, job: dict[str, Any]) -> None:
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _path(job_id).with_suffix(".tmp")
    tmp.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
    tmp.replace(_path(job_id))


def get_job(job_id: str) -> dict[str, Any] | None:
    if not job_id.isalnum():
        return None
    try:
        job: dict[str, Any] = json.loads(_path(job_id).read_text(encoding="utf-8"))
        return job
    except (OSError, json.JSONDecodeError):
        return None


def start_job(instruction: str, event_ids: list[str] | None) -> str:
    job_id = uuid.uuid4().hex
    job: dict[str, Any] = {"status": "running", "steps": [], "summary": "", "error": ""}
    _write(job_id, job)

    def on_step(step: dict[str, Any]) -> None:
        job["steps"].append(step)
        _write(job_id, job)

    def work() -> None:
        try:
            job["summary"] = run_agent(instruction, event_ids, on_step)
            job["status"] = "done"
        except Exception as error:
            logger.exception("agent job %s failed", job_id)
            job["status"] = "error"
            job["error"] = f"{type(error).__name__}: {error}"
        _write(job_id, job)

    threading.Thread(target=work, daemon=True).start()
    return job_id
