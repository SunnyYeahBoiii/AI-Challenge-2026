# Architecture Rules

## Monorepo Structure

```
AI-Challenge-2026/
├── apps/
│   ├── web/          # Next.js 16 frontend (port 3000)
│   ├── api/          # Flask backend (port 5001)
│   └── cloud-api/    # NestJS TRAKE collab + submissions, Prisma/SQLite (port 5002)
├── docs/
│   ├── CONTEXT.md    # Domain glossary
│   ├── adr/          # Architecture Decision Records
│   └── rules/        # This directory
├── docker-compose.yml
├── turbo.json
└── pnpm-workspace.yaml
```

## API Response Format

JSON:API-inspired envelope:

```json
{
  "data": [...],
  "meta": {
    "total": 100,
    "page": 1,
    "pageSize": 20
  }
}
```

Single resource:
```json
{
  "data": { "id": "1", "type": "frame", "attributes": {...} }
}
```

## Error Response Format

Consistent error envelope (apps/api — implemented in `app/errors.py`):

```json
{
  "error": {
    "code": "SEARCH_FAILED",
    "message": "Milvus connection timeout",
    "details": {
      "field": "query",
      "reason": "Connection refused"
    }
  }
}
```

Exception: apps/cloud-api returns NestJS-default errors and bare resource
shapes (`{boards: [...]}`) over both HTTP and Socket.IO — the web client and
board consumers depend on those shapes. Changing them is a coordinated
client+server migration, not a drive-by.

## Separation of Concerns

| System | Purpose | Use For |
|--------|---------|---------|
| Milvus | Vector similarity search | Embedding-based frame search |
| Elasticsearch | Full-text search + metadata | OCR text, ASR text, keyword filtering |

- Do not cross-use: Milvus for vectors only, Elasticsearch for text/metadata only
- Query builder pattern: service layer constructs queries, no raw strings in routes

## Service Layer Architecture

```
Route (HTTP) → Service (Business Logic) → Database (Data Access)
```

- Routes: parse request, call service, format response
- Services: business logic, raise exceptions on errors
- Database clients: thin wrappers around Milvus/Elasticsearch SDKs

## Docker

- Multi-stage builds required (already in place for both apps)
- `.dockerignore` must exclude: `.env`, `node_modules`, `__pycache__`, `.next`, `venv`
- Never hardcode secrets in Dockerfiles — use env vars or Docker secrets

## Security (Minimal)

- No hardcoded secrets — use `.env` files and environment variables
- Input validation on all external API inputs (DRES, search queries)
- Rate limiting on search endpoints (when implemented)

## Testing

- Python: pytest, coverage ≥ 90%
- TypeScript: Vitest/Jest, coverage ≥ 80%
- Integration tests required for: Milvus, Elasticsearch, DRES submission

## Documentation

- Domain glossary: `docs/CONTEXT.md`
- Architecture decisions: `docs/adr/NNNN-<title>.md`
- Rules: `docs/rules/`
- Inline docstrings: Google style for Python (critical paths), JSDoc for TypeScript (public functions)
