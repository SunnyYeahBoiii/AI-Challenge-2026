# AGENTS.md — AI-Challenge-2026

FrameSeeker: AI-powered video and image search for AI Challenge 2026 competition.

## Quick Start

```bash
# Start everything
pnpm dev

# Or Docker
docker compose up --build
```

- Frontend: http://localhost:3000
- Backend API: http://localhost:5001
- cloud-api (TRAKE collab + submissions, host machine): http://localhost:5002

Teammates point `NEXT_PUBLIC_CLOUD_API_URL` at the host running `apps/cloud-api`.

## Rules

| Rule | Location |
|------|----------|
| Python | [docs/rules/python.md](docs/rules/python.md) |
| TypeScript | [docs/rules/typescript.md](docs/rules/typescript.md) |
| Architecture | [docs/rules/architecture.md](docs/rules/architecture.md) |
| Workflow | [docs/rules/workflow.md](docs/rules/workflow.md) |
| Clean Code | [docs/rules/clean-code.md](docs/rules/clean-code.md) |

## Domain Glossary

See [docs/CONTEXT.md](docs/CONTEXT.md) for terms: Frame, Video, Query, BoxQuery, DRES, TrakeBoard, Event, Candidate, Selection, Embedding, Milvus, Elasticsearch.

## Architecture Decisions

See [docs/adr/](docs/adr/) for ADRs.

## Verify Before Submit

```bash
# Python
cd apps/api && uv run ruff check . && uv run mypy app && uv run pytest

# TypeScript (web)
cd apps/web && pnpm build   # includes type-check; `pnpm lint` (next lint) was removed in Next 15+

# TypeScript (cloud-api)
cd apps/cloud-api && pnpm lint && pnpm build

# Docker
docker compose config       # validate compose file after changes
```
