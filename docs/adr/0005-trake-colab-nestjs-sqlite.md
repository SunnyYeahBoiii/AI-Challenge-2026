# 0005: TRAKE collab in NestJS + SQLite; DRES submit stays on Flask

## Context

TRAKE requires an ordered set of Selections across Events, refined by the whole team under a tight ±0.5s tolerance. FrameSeeker already searches and submits KIS/QA through Flask. We needed realtime shared Candidate lists without putting DRES credentials in a new service or rewriting the search stack.

## Decision

- Add `apps/trake-colab` (NestJS + Socket.IO + Prisma/SQLite) as the single-host collab service for TrakeBoard state.
- Keep DRES login/submit on Flask (`submit_trake` → `TR-<VIDEO_ID>-<ids>`). The web client builds frame ids and POSTs `/api/dres/submit/track`.
- TRACK mode in `apps/web` drives add-to-Event / right panel / DnD; Nest never calls DRES.

## Consequences

- One machine must run trake-colab; teammates set `NEXT_PUBLIC_TRAKE_COLAB_URL` to that host.
- SQLite via Prisma is enough for a single process; restart preserves boards on disk. Schema lives in `apps/trake-colab/prisma/schema.prisma`.
- Splitting collab from DRES keeps ADR-0002 (credentials server-side on Flask) intact.
