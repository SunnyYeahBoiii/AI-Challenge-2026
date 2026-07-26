# DRES Integration

How the API submits search results to the competition's DRES (Data Retrieval and Evaluation System) server.

## Overview

After a Frame is retrieved, the system submits it to DRES as a T-KIS or V-KIS answer. The integration is configured for the **USER participant** role only.

```
Frontend                  API (Flask)                       DRES Server
   │                         │                                  │
   │ POST /api/dres/submit   │                                  │
   │ {evaluationId,videoId,  │                                  │
   │  timeMs}                │                                  │
   │ ───────────────────────>│                                  │
   │                         │ (cached) login → sessionId      │
   │                         │ POST /api/v2/login               │
   │                         │ ────────────────────────────────>│
   │                         │ <── {sessionId} ────────────────│
   │                         │                                  │
   │                         │ POST /api/v2/submit/{evalId}     │
   │                         │   ?session={sessionId}          │
   │                         │   body: answerSets              │
   │                         │ ────────────────────────────────>│
   │                         │ <── {status, submission} ───────│
   │ <── {status, submission}│                                  │
```

## Configuration

All credentials live in `apps/api/.env` (never commit the real `.env`):

```bash
DRES_URL=
DRES_USERNAME=
DRES_PASSWORD=
```

`apps/api/app/config.py` exposes them as `Config.DRES_URL`, `Config.DRES_USERNAME`, `Config.DRES_PASSWORD` (blank defaults; raise at runtime if missing when used).

## DRES Workflow

The client (`app/services/dres_client.py`) follows the documented 3-step flow:

1. **Login** → `POST /api/v2/login` with `{username, password}` body. Returns `{sessionId, ...}`.
2. **List evaluations** → `GET /api/v2/client/evaluation/list?session={sessionId}`. Returns array of evaluations; we filter to `status == "ACTIVE"` and expose only `id` + `status` to callers.
3. **Submit answer** → `POST /api/v2/submit/{evaluationId}?session={sessionId}` with body:

```json
{
  "answerSets": [
    {
      "answers": [
        {
          "mediaItemName": "<VIDEO_ID>",
          "start": "<TIME(ms)>",
          "end": "<TIME(ms)>"
        }
      ]
    }
  ]
}
```

`start == end` is required (KIS tasks submit a single timestamp, not a range). The sessionId is cached in memory for the lifetime of the process; re-login happens lazily on expiry or first call.

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/dres/session` | Force login, return `{sessionId, username, role}` |
| `GET`  | `/api/dres/evaluations` | List active evaluations: `{evaluations: [{id, status}], total}` |
| `POST` | `/api/dres/submit/<task_type>` | Submit one answer; `task_type` ∈ `kis`/`qa`/`track` |

### Submit example

Frontend payload (`task_type` from URL, `timestamp` is `pts_time` in seconds):
```bash
curl -X POST http://localhost:5000/api/dres/submit/kis \
  -H "Content-Type: application/json" \
  -d '{"frame_id":"abc","video_path":"L21_V001","timestamp":45.23}'
```

If `evaluationId` is omitted in the body, the route auto-picks the first ACTIVE evaluation from DRES. You can also pass it explicitly:
```bash
curl -X POST http://localhost:5000/api/dres/submit/kis \
  -H "Content-Type: application/json" \
  -d '{"frame_id":"abc","video_path":"L21_V001","timestamp":45.23,"evaluationId":"abc123"}'
```

Response on success:
```json
{ "status": true, "submission": "CORRECT", "description": "Submission correct, well done!",
  "evaluationId": "abc123", "taskType": "kis", "frameId": "abc" }
```

Response on duplicate or invalid input: HTTP 502 with `{"error": "DRES 409: ..."}`.

## Timestamp Convention

Per `CONTEXT.md`, our internal `pts_time` is in **seconds** (float). DRES requires **milliseconds** (integer string). The route accepts `timestamp` in seconds (frontend) or `timeMs` in milliseconds (raw DRES format) and converts to ms before calling DRES. Pass either form; seconds is the preferred contract from the frontend.

## Error Handling

All DRES failures bubble up as `DresError` from the client and surface as HTTP 502 from routes. The original DRES status code and body are preserved in the message. Network errors (DNS, timeout, refused) surface as `DRES unreachable: <reason>`.

## Files

- `apps/api/app/services/dres_client.py` — HTTP client + session cache
- `apps/api/app/routes/dres.py` — Flask blueprint exposing 3 endpoints
- `apps/api/app/config.py` — env-driven config
- `apps/api/app/main.py` — registers `dres_bp`

## Dependencies

Uses stdlib `urllib.request` + `json`. No new packages added — `requests` / `httpx` only when async or connection pooling becomes a measured bottleneck.
