# 0002: DRES Participant Integration

We integrate directly against the DRES REST API from the Flask backend using the **USER participant** credentials stored in `.env`. The client owns the session lifecycle (login → cached sessionId → submit), exposed through three small Flask routes for the frontend to drive.

**Considered alternatives:**

- **DRES Python client library** (the official `dres-client` on PyPI) — adds a dependency and pulls in asyncio, but our flow is three POST/GET calls. Stdlib `urllib` covers it.
- **Frontend → DRES direct** — exposes participant credentials in the browser. Rejected: credentials must stay server-side, and the backend already has the search context (videoId, timestamp).
- **Admin credentials with backend proxying submissions for all users** — out of scope; we are a single participant team, USER role is correct per competition rules.

**Consequences:**

- `timeMs` (ms) is the wire format; `pts_time` (s, float) is our internal format. Conversion happens at the call site, not in the client — keeps the client dumb and matches `CONTEXT.md`.
- `sessionId` is process-local and cached; multi-worker deployments (gunicorn) each hold their own session, re-logging in independently. Acceptable: login is cheap, and per-worker sessions avoid cross-process cache invalidation.
- No retry/backoff on DRES errors yet. DRES returns structured `status: false` for duplicate submissions, which we propagate as 502 — caller decides. Add retry only if DRES flakiness is observed in production.
