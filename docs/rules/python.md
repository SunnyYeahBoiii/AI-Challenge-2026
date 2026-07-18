# Python Rules

## Tooling

- **Linter/Formatter:** Ruff (line-length 100, target py311)
- **Type Checker:** mypy strict mode
- **Package Manager:** uv
- **Test Framework:** pytest

## Code Style

- Follow PEP 8 via Ruff enforcement
- Maximum line length: 100 characters
- Use type hints on all function signatures
- Prefer `pathlib` over `os.path`
- Use f-strings for string formatting
- Import ordering: stdlib → third-party → local (enforced by Ruff)

## Blueprint Pattern

Each domain gets its own Flask blueprint:

```
app/routes/
├── search.py      # search_bp
├── videos.py      # videos_bp
├── embed.py       # embed_bp
├── dres.py        # dres_bp
└── __init__.py    # register all blueprints
```

- Blueprints self-register in `app/routes/__init__.py`
- Route handlers handle HTTP only — no business logic
- Use `@search_bp.route(...)` decorators

## Service Layer

Routes → Services → Database. Never call database directly from routes.

```
app/
├── routes/        # HTTP layer (request parsing, response formatting)
├── services/      # Business logic (search, embed, DRES submission)
└── database/      # Data access (Milvus client, Elasticsearch client)
```

- Services are plain Python classes or modules
- Services raise custom exceptions for business logic errors
- Routes catch exceptions and format HTTP responses

## Error Handling

Use exceptions (Flask convention):

```python
# Define custom exceptions in services/
class SearchError(Exception): ...
class EmbeddingError(Exception): ...
class DRESSubmissionError(Exception): ...

# Routes catch and format
@search_bp.route("/api/search", methods=["POST"])
def search():
    try:
        results = search_service.search(query)
        return jsonify({"data": results}), 200
    except SearchError as e:
        return jsonify({"error": {"code": "SEARCH_FAILED", "message": str(e)}}), 422
```

### HTTP Status Codes

| Scenario | Status |
|----------|--------|
| Success (created) | 201 |
| Success (default) | 200 |
| Validation error (bad input) | 400 |
| Business logic error | 422 |
| External service failure | 502 |
| Internal error | 500 |

## Configuration

Keep current pattern — `Config` class with `python-dotenv`:

- `app/config.py` reads env vars
- `.env` for local development
- Environment variables for production
- `.env.example` must always be updated when adding new vars

## Testing (TDD — Strict)

- Write tests before implementation
- Coverage ≥ 90%
- Integration tests required for: Milvus, Elasticsearch, DRES submission
- Test file naming: `test_<module>.py`
- Test location: `tests/` directory mirroring `app/` structure

```bash
# Run tests
uv run pytest

# Check coverage
uv run pytest --cov=app --cov-report=term-missing
```

## Docstrings

Critical paths only (services, routes, complex utilities):

```python
def search_frames(query: str, top_k: int = 20) -> list[Frame]:
    """Search for frames matching text query using vector similarity.

    Args:
        query: Text query to search for.
        top_k: Maximum number of results to return.

    Returns:
        List of Frame objects sorted by cosine similarity.

    Raises:
        SearchError: If Milvus query fails.
    """
```

Simple helpers/utilities: short docstring `"""Do something."""` is sufficient.
