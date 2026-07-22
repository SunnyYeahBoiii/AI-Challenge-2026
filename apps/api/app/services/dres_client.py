import json
import urllib.error
import urllib.request

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
    def __init__(self):
        self.base_url = Config.DRES_URL.rstrip("/")
        self.username = Config.DRES_USERNAME
        self.password = Config.DRES_PASSWORD
        self._session_id: str | None = None

    def _request(self, method: str, path: str, body: dict | None = None,
                 query: dict | None = None) -> dict:
        url = f"{self.base_url}{path}"
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

    def login(self) -> dict:
        result = self._request("POST", "/api/v2/login",
                               body={"username": self.username, "password": self.password})
        self._session_id = result.get("sessionId")
        if not self._session_id:
            raise DresError(f"DRES login returned no sessionId: {result}")
        return result

    def _ensure_session(self) -> str:
        if not self._session_id:
            self.login()
        assert self._session_id is not None
        return self._session_id

    def list_evaluations(self) -> list[dict]:
        session_id = self._ensure_session()
        return self._request("GET", "/api/v2/client/evaluation/list",
                             query={"session": session_id})

    def submit(self, evaluation_id: str, video_id: str, time_ms: int) -> dict:
        session_id = self._ensure_session()
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
        )


dres_client = DresClient()
