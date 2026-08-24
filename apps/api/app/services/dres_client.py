import json
import urllib.error
import urllib.request
from urllib.parse import urlparse

from app.config import Config


class DresError(Exception):
    def __init__(self, status_code: int, body: dict | str, message: str = ""):
        self.status_code = status_code
        self.body = body
        super().__init__(message or f"DRES {status_code}: {body}")


def _parse_body(raw: bytes) -> dict | str:
    text = raw.decode("utf-8", errors="ignore").strip()
    if not text:
        return ""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


class DresClient:
    """Stateless wrapper around the DRES REST API.

    Runs behind gunicorn with multiple workers, so nothing about a session
    can live in process memory — the caller (frontend) holds the sessionId
    returned by login() and passes it back on every subsequent call.
    """

    def __init__(self):
        self.base_url = Config.DRES_URL.rstrip("/")

    def _resolve_base_url(self, base_url: str | None) -> str:
        if base_url is not None and not isinstance(base_url, str):
            raise DresError(400, "DRES URL must be a string")
        candidate = (base_url or self.base_url).strip().rstrip("/")
        parsed = urlparse(candidate)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise DresError(400, "DRES URL must be an absolute http(s) URL")
        return candidate

    def _request(self, method: str, path: str, body: dict | None = None,
                 query: dict | None = None, base_url: str | None = None) -> dict:
        url = f"{self._resolve_base_url(base_url)}{path}"
        if query:
            from urllib.parse import urlencode
            url = f"{url}?{urlencode(query)}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(
            url, data=data, method=method,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                payload = resp.read().decode("utf-8")
                return json.loads(payload) if payload else {}
        except urllib.error.HTTPError as e:
            parsed = _parse_body(e.read())
            raise DresError(e.code, parsed) from e
        except urllib.error.URLError as e:
            raise DresError(0, str(e.reason), message=f"DRES unreachable: {e.reason}") from e

    def login(self, username: str, password: str, base_url: str | None = None) -> dict:
        result = self._request(
            "POST",
            "/api/v2/login",
            body={"username": username, "password": password},
            base_url=base_url,
        )
        if not result.get("sessionId"):
            raise DresError(502, result, message=f"DRES login returned no sessionId: {result}")
        return result

    def logout(self, session_id: str, base_url: str | None = None) -> None:
        self._request(
            "GET", "/api/v2/logout", query={"session": session_id}, base_url=base_url
        )

    def list_evaluations(self, session_id: str, base_url: str | None = None) -> list[dict]:
        return self._request(
            "GET",
            "/api/v2/client/evaluation/list",
            query={"session": session_id},
            base_url=base_url,
        )

    def list_media_items(self, session_id: str, base_url: str | None = None) -> list:
        return self._request(
            "GET",
            "/api/v2/client/mediaItem/list",
            query={"session": session_id, "collection": ""},
            base_url=base_url,
        )

    def submit(self, evaluation_id: str, video_id: str, time_ms: int, session_id: str,
               base_url: str | None = None) -> dict:
        body = {
            "answerSets": [
                {
                    "answers": [
                        {
                            "mediaItemName": video_id,
                            "start": str(time_ms),
                            "end": str(time_ms),
                        }
                    ]
                }
            ]
        }
        return self._request(
            "POST",
            f"/api/v2/submit/{evaluation_id}",
            body=body,
            query={"session": session_id},
            base_url=base_url,
        )

    def submit_qa(
        self,
        evaluation_id: str,
        answer: str,
        video_id: str,
        time_ms: int,
        session_id: str,
        base_url: str | None = None,
    ) -> dict:
        """Submit one QA answer as text: QA-<ANSWER>-<VIDEO_ID>-<TIME(ms)>."""
        body = {
            "answerSets": [
                {
                    "answers": [
                        {"text": f"{answer}"}
                    ]
                }
            ]
        }
        return self._request(
            "POST",
            f"/api/v2/submit/{evaluation_id}",
            body=body,
            query={"session": session_id},
            base_url=base_url,
        )

    def submit_trake(
        self,
        evaluation_id: str,
        video_id: str,
        frame_ids: list[int],
        session_id: str,
        base_url: str | None = None,
    ) -> dict:
        """Submit TRAKE as text: TR-<VIDEO_ID>-<FRAME_ID1>,<FRAME_ID2>,..."""
        ids = ",".join(str(int(fid)) for fid in frame_ids)
        body = {
            "answerSets": [
                {
                    "answers": [
                        {"text": f"TR-{video_id}-{ids}"}
                    ]
                }
            ]
        }
        return self._request(
            "POST",
            f"/api/v2/submit/{evaluation_id}",
            body=body,
            query={"session": session_id},
            base_url=base_url,
        )


dres_client = DresClient()
