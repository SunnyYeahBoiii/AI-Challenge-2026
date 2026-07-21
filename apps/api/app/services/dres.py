from __future__ import annotations

import json
import math
from collections.abc import Mapping
from threading import RLock
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, urlopen

from app.config import Config


class DRESError(RuntimeError):
    """Raised when DRES authentication or submission cannot be completed."""


class DRESClient:
    """Small DRES v2 client that keeps the team session token on the server."""

    def __init__(
        self,
        base_url: str,
        evaluation_id: str,
        *,
        timeout_seconds: float = 10.0,
        session_token: str = "",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.evaluation_id = evaluation_id.strip()
        self.timeout_seconds = timeout_seconds
        self._session_token = session_token.strip()
        self._lock = RLock()

    def _require_configuration(self, *, require_evaluation: bool = False) -> None:
        if not self.base_url:
            raise DRESError("DRES_BASE_URL is not configured")
        parsed_url = urlsplit(self.base_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise DRESError("DRES_BASE_URL must be an absolute HTTP(S) URL")
        if self.timeout_seconds <= 0 or not math.isfinite(self.timeout_seconds):
            raise DRESError("DRES_TIMEOUT_SECONDS must be a positive finite number")
        if require_evaluation and not self.evaluation_id:
            raise DRESError("DRES_EVALUATION_ID is not configured")

    def _request(
        self,
        path: str,
        payload: Mapping[str, object],
    ) -> dict[str, Any]:
        request = Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310
                raw_body = response.read()
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise DRESError(f"DRES rejected the request ({error.code}): {detail}") from error
        except (URLError, TimeoutError, OSError) as error:
            raise DRESError(f"cannot reach DRES: {error}") from error
        try:
            parsed = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise DRESError("DRES returned an invalid JSON response") from error
        if not isinstance(parsed, dict):
            raise DRESError("DRES returned a non-object JSON response")
        return parsed

    def login(self, username: str, password: str) -> dict[str, Any]:
        """Authenticate with DRES without exposing its session token to the browser."""
        self._require_configuration()
        response = self._request(
            "/api/v2/login",
            {"username": username, "password": password},
        )
        session_token = str(response.get("sessionId", "")).strip()
        if not session_token:
            raise DRESError("DRES login response did not contain sessionId")
        with self._lock:
            self._session_token = session_token
        return {key: value for key, value in response.items() if key != "sessionId"}

    def submit(
        self,
        submission_type: str,
        *,
        video_id: str,
        timestamp: float,
        answer: str = "",
    ) -> dict[str, Any]:
        """Submit an official DRES v2 media answer using millisecond timestamps."""
        self._require_configuration(require_evaluation=True)
        if submission_type not in {"kis", "qa", "track"}:
            raise ValueError("submission type must be kis, qa or track")
        if not math.isfinite(timestamp) or timestamp < 0:
            raise ValueError("timestamp must be a non-negative finite number")
        normalized_answer = answer.strip()
        if submission_type == "qa" and not normalized_answer:
            raise ValueError("answer is required for QA submissions")
        with self._lock:
            session_token = self._session_token
        if not session_token:
            raise DRESError("not logged in to DRES")

        timestamp_ms = round(timestamp * 1_000)
        dres_answer: dict[str, object] = {
            "mediaItemName": video_id,
            "start": timestamp_ms,
            "end": timestamp_ms,
        }
        if normalized_answer:
            dres_answer["text"] = normalized_answer
        payload = {"answerSets": [{"answers": [dres_answer]}]}
        evaluation_id = quote(self.evaluation_id, safe="")
        query = urlencode({"session": session_token})
        return self._request(f"/api/v2/submit/{evaluation_id}?{query}", payload)


dres_client = DRESClient(
    Config.DRES_BASE_URL,
    Config.DRES_EVALUATION_ID,
    timeout_seconds=Config.DRES_TIMEOUT_SECONDS,
    session_token=Config.DRES_SESSION_TOKEN,
)
