# DRES Integration

How the API submits search results to the competition's DRES (Data Retrieval and Evaluation System) server.

## Overview

After a Frame is retrieved, the system submits it to DRES as a T-KIS or V-KIS answer. The integration is configured for the **USER participant** role only.

The backend runs under gunicorn with multiple workers (`Dockerfile`: `-w 2`), so nothing about a DRES session can live in a single worker's process memory — a login handled by worker A would be invisible to a submit request routed to worker B. Instead, the **frontend** holds the `sessionId` (in `sessionStorage`) after login and sends it explicitly on every subsequent call. The backend (`DresClient`) is fully stateless: every method takes `session_id` as an argument and never caches it.

```
Frontend                       API (Flask)                       DRES Server
   │                              │                                  │
   │ (once) POST /api/dres/session│                                  │
   │ {username,password}          │                                  │
   │ ─────────────────────────────>│                                  │
   │                              │ POST /api/v2/login                │
   │                              │ ────────────────────────────────>│
   │                              │ <── {sessionId} ─────────────────│
   │ <── {sessionId} ─────────────│                                  │
   │ (store in sessionStorage)   │                                  │
   │                              │                                  │
   │ POST /api/dres/submit/kis    │                                  │
   │ {evaluationId?,videoId,      │                                  │
   │  timestamp,sessionId}        │                                  │
   │ ─────────────────────────────>│                                  │
   │                              │ POST /api/v2/submit/{evalId}      │
   │                              │   ?session={sessionId}           │
   │                              │   body: answerSets                │
   │                              │ ────────────────────────────────>│
   │                              │ <── {status, submission} ────────│
   │ <── {status, submission} ────│                                  │
```

## Configuration

Only the server URL lives in `apps/api/.env`:

```bash
DRES_URL=
```

`apps/api/app/config.py` exposes it as `Config.DRES_URL` (blank default; raise at runtime if missing when used).

Username/password are **never** stored on the backend — the user enters them once through the DRES Settings dialog (`dres-settings-dialog.tsx`), which posts to `/api/dres/session` and receives `{sessionId, username, role}` back. `sessionId` and `username` are kept in the browser's `sessionStorage` (`page.tsx`) and `sessionId` is threaded into every later submit call. Once logged in, the header shows the team name (`username`) with a Logout button in place of the "DRES Settings" button; Logout clears `sessionStorage` immediately (client-side state always wins) and fires a best-effort `POST /api/dres/logout` to invalidate the session server-side. If the DRES session expires server-side, the next submit fails with a `DresError` (surfaced as 502/4xx) and the user re-opens DRES Settings to log in again.

## DRES Workflow

The client (`app/services/dres_client.py`) follows the documented 3-step flow:

1. **Login** → `POST /api/v2/login` with `{username, password}` body (credentials supplied by the caller, never stored). Returns `{sessionId, ...}`.
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

`start == end` is required (KIS tasks submit a single timestamp, not a range).

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/dres/session` | Login with `{username, password}` body, return `{sessionId, username, role}` |
| `POST` | `/api/dres/logout` | Logout with `{sessionId}` body, best-effort (always returns `{loggedOut: true}` even if DRES errors) |
| `GET`  | `/api/dres/evaluations?session=<sessionId>` | List active evaluations: `{evaluations: [{id, status}], total}` |
| `GET`  | `/api/dres/media-items?session=<sessionId>` | List up to 50 media items: `{items, total}` (debugging only; unused by the frontend) |
| `POST` | `/api/dres/submit/<task_type>` | Submit one answer; `task_type` ∈ `kis`/`qa`/`track`; body must include `sessionId` |

### Submit example

Frontend payload (`task_type` from URL, `timestamp` is `pts_time` in seconds, `sessionId` from the prior login):
```bash
curl -X POST http://localhost:5000/api/dres/submit/kis \
  -H "Content-Type: application/json" \
  -d '{"frame_id":"abc","video_path":"L21_V001","timestamp":45.23,"sessionId":"<sessionId>"}'
```

If `evaluationId` is omitted in the body, the route auto-picks the first ACTIVE evaluation from DRES (using the same `sessionId`). You can also pass it explicitly:
```bash
curl -X POST http://localhost:5000/api/dres/submit/kis \
  -H "Content-Type: application/json" \
  -d '{"frame_id":"abc","video_path":"L21_V001","timestamp":45.23,"sessionId":"<sessionId>","evaluationId":"abc123"}'
```

Response on success — the `submission` field is the source of truth, not the HTTP status; DRES returns HTTP 200 for both a correct and a *wrong* answer:
```json
{ "status": true, "submission": "CORRECT", "description": "Submission correct, well done!",
  "evaluationId": "abc123", "taskType": "kis", "frameId": "abc" }
```
```json
{ "status": true, "submission": "WRONG", "description": "Submission wrong, try again!" }
```

Response on duplicate submission: `{"status": false, "description": "..."}`. The frontend (`submission-confirmation-dialog.tsx`) reads `submission`/`status` to distinguish CORRECT / WRONG / duplicate, not just `res.ok`.

## Timestamp Convention

Per `CONTEXT.md`, our internal `pts_time` is in **seconds** (float). DRES requires **milliseconds** (integer string). The route accepts `timestamp` in seconds (frontend) or `timeMs` in milliseconds (raw DRES format) and converts to ms before calling DRES. Pass either form; seconds is the preferred contract from the frontend.

## Error Handling

All DRES failures bubble up as `DresError` from the client and surface as HTTP 502 (or the original DRES status code) from routes. Missing `sessionId` on `/api/dres/evaluations`, `/api/dres/media-items`, or `/api/dres/submit/<task_type>` is rejected with 400 before any DRES call is made. Network errors (DNS, timeout, refused) surface as `DRES unreachable: <reason>`.

## Files

- `apps/api/app/services/dres_client.py` — stateless HTTP client (no session caching)
- `apps/api/app/routes/dres.py` — Flask blueprint exposing 3 endpoints
- `apps/api/app/config.py` — env-driven config (`DRES_URL` only)
- `apps/api/app/main.py` — registers `dres_bp`
- `apps/web/src/components/dres-settings-dialog.tsx` — login UI, hands `sessionId` up to `page.tsx`
- `apps/web/src/components/submission-confirmation-dialog.tsx` — submit UI, sends `sessionId` with every submission

## Dependencies

Uses stdlib `urllib.request` + `json`. No new packages added — `requests` / `httpx` only when async or connection pooling becomes a measured bottleneck.
