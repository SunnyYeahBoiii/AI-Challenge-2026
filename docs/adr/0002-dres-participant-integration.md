# 0002: DRES Participant Integration

We integrate directly against the DRES REST API from the Flask backend using the **USER participant** credentials stored in `.env`. Exposed through small Flask routes for the frontend to drive.

> **Amended 2026-08:** the client is stateless now — the browser owns the
> session lifecycle (login → stores `sessionId` in sessionStorage → passes it
> on every submit), and the API runs single-worker gunicorn. The "client owns
> the session" paragraph below no longer applies.

**Considered alternatives:**

- **DRES Python client library** (the official `dres-client` on PyPI) — adds a dependency and pulls in asyncio, but our flow is three POST/GET calls. Stdlib `urllib` covers it.
- **Frontend → DRES direct** — exposes participant credentials in the browser. Rejected: credentials must stay server-side, and the backend already has the search context (videoId, timestamp).
- **Admin credentials with backend proxying submissions for all users** — out of scope; we are a single participant team, USER role is correct per competition rules.

**Consequences:**

- `timeMs` (ms) is the wire format; `pts_time` (s, float) is our internal format. Conversion happens at the call site, not in the client — keeps the client dumb and matches `CONTEXT.md`.
- `sessionId` is process-local and cached; multi-worker deployments (gunicorn) each hold their own session, re-logging in independently. *(Superseded — see amendment above: the browser holds the sessionId.)*
- No retry/backoff on DRES errors yet. DRES returns structured `status: false` for duplicate submissions, which we propagate as 502 — caller decides. Add retry only if DRES flakiness is observed in production.
