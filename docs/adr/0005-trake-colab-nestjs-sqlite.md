# 0005: TRAKE collab in NestJS + SQLite; DRES submit stays on Flask

> **Amended 2026-08:** `apps/trake-colab` was renamed/migrated to
> `apps/cloud-api`. Teammates point `NEXT_PUBLIC_CLOUD_API_URL` at the host
> running it — the value is baked into the browser bundle, so it must be a
> browser-reachable address (LAN/Tailscale IP), never a docker-internal
> hostname. Everything below still applies to the renamed service.
>
> **Amended 2026-09:** the submissions/queries endpoints it grew (shared
> submission tracking, task list, CSV + zip export) are removed, along with
> their Prisma models and the web Cloud submit mode. Submitting is DRES-live
> only: one click on a frame goes straight to Flask and the verdict comes back
> as a badge on the button, with no confirmation dialog in between. CSV export
> is gone with them. cloud-api is back to TrakeBoard state only.

## Context

TRAKE requires an ordered set of Selections across Events, refined by the whole team under a tight ±0.5s tolerance. FrameSeeker already searches and submits KIS/QA through Flask. We needed realtime shared Candidate lists without putting DRES credentials in a new service or rewriting the search stack.

## Decision

- Add `apps/cloud-api` (NestJS + Socket.IO + Prisma/SQLite; originally `apps/trake-colab`) as the single-host collab service for TrakeBoard state.
- Keep DRES login/submit on Flask (`submit_trake` → `TR-<VIDEO_ID>-<ids>`). The web client builds frame ids and POSTs `/api/dres/submit/track`.
- TRACK mode in `apps/web` drives add-to-Event / right panel / DnD; Nest never calls DRES.

## Consequences

- One machine must run cloud-api; teammates set `NEXT_PUBLIC_CLOUD_API_URL` to that host.
- SQLite via Prisma is enough for a single process; restart preserves boards on disk. Schema lives in `apps/cloud-api/prisma/schema.prisma`.
- Splitting collab from DRES keeps ADR-0002 (credentials server-side on Flask) intact.
