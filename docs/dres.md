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

**KIS / track** (`task_type` ∈ `kis`/`track`):

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

**QA** (`task_type` = `qa`) — frontend sends `answer` as one full string (multi-line allowed). Backend builds a single text answer:

```json
{
  "answerSets": [
    {
      "answers": [
        {
          "text": "QA-<ANSWER>-<VIDEO_ID>-<TIME(ms)>"
        }
      ]
    }
  ]
}
```

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/dres/session` | Login with `{username, password}` body, return `{sessionId, username, role}` |
| `POST` | `/api/dres/logout` | Logout with `{sessionId}` body, best-effort (always returns `{loggedOut: true}` even if DRES errors) |
| `GET`  | `/api/dres/evaluations?session=<sessionId>` | List active evaluations: `{evaluations: [{id, status}], total}` |
| `GET`  | `/api/dres/media-items?session=<sessionId>` | List up to 50 media items. **Currently broken upstream** — DRES no longer routes `GET /api/v2/client/mediaItem/list`, so this returns the Javalin 404 described below. Kept as a probe: if the endpoint ever returns, it is the only way to read the `mediaItemName` format DRES expects. |
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

### Verdict codes

`error.code` is the field to branch on — never the prose. `verdict_code()` in `routes/dres.py` maps a DRES body to one of:

| Code | Meaning |
|------|---------|
| `DRES_CORRECT` | `submission: "CORRECT"` |
| `DRES_WRONG` | `submission: "WRONG"` — counted, but wrong |
| `DRES_REJECTED` | DRES evaluated the answer, then a server-side filter refused to record it |
| `DRES_DUPLICATE` | `status: false` for a reason other than a filter |
| `DRES_ERROR` | Transport failure, or a body with no recognisable verdict |

The same code is attached to **successful** responses (top-level `code`), so the frontend classifies both paths through one function.

### A filter rejection looks like a 404

DRES answers a submission that trips a server-side filter with **HTTP 404** and `status: false` — byte-for-byte the same shape it uses for a plain duplicate. A real example, submitting one answer past the team's quota:

```json
{
  "description": "Submission 9910a5d6-… was rejected by filter: Maximum number of correct submissions (1) exceeded for the team.",
  "status": false
}
```

Nothing is broken: the answer was evaluated and the request was well-formed. DRES simply declined to store a result past the cap. The two cases are only separable by DRES's own wording, so that matching happens once in `verdict_code()` and leaves the frontend comparing a code.

Note the `description` prose is DRES's, not ours — do not match on it outside `verdict_code()`.

### Two DRES response shapes

DRES is a Javalin server and speaks two dialects:

- **Application verdicts** — `description` carries the explanation.
- **Framework failures** — RFC 7807 problem details, where the text is in `title`:

  ```json
  { "type": "https://javalin.io/documentation#endpointnotfound",
    "title": "Endpoint GET /api/v2/client/mediaItem/list not found",
    "status": 404, "details": {} }
  ```

  `title` is 404, an `int`. `_reason()` reads `description`, then `title`, then `detail` so neither dialect degrades to a bare generic string.

DRES content-negotiates on `Accept`: requesting a vanished endpoint with `Accept: application/json` gets the JSON problem above, while a browser-style request falls through to the DRES Angular SPA and returns HTML with HTTP 200. `DresClient` always sends `Accept: application/json`, so it never sees the HTML.

## Files

- `apps/api/app/services/dres_client.py` — stateless HTTP client (no session caching)
- `apps/api/app/routes/dres.py` — Flask blueprint exposing the endpoints, plus `verdict_code()` / `_reason()`
- `apps/api/app/config.py` — env-driven config (`DRES_URL` only)
- `apps/api/app/main.py` — registers `dres_bp`
- `apps/web/src/lib/submit-verdict.ts` — the shared `SubmitStatus` union, badge style, and tooltip text used by every submit surface
- `apps/web/src/lib/api.ts` — `classifyDresSubmit()` maps a response onto `SubmitStatus`
- `apps/web/src/hooks/use-dres-submit.ts` — `readFailure()` prefers `error.details` over the generic `error.message`
- `apps/web/src/components/dres-settings-dialog.tsx` — login UI, hands `sessionId` up to `page.tsx`
- `apps/web/src/components/submission-confirmation-dialog.tsx` — submit UI, sends `sessionId` with every submission

## Dependencies

Uses stdlib `urllib.request` + `json`. No new packages added — `requests` / `httpx` only when async or connection pooling becomes a measured bottleneck.
