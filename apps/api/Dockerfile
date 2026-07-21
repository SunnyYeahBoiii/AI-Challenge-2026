FROM python:3.12-slim

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_HTTP_RETRIES=10 \
    UV_HTTP_TIMEOUT=300 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

COPY pyproject.toml .
COPY uv.lock .
RUN --mount=type=cache,target=/root/.cache/uv \
    pip install --no-cache-dir uv==0.8.24 \
    && uv sync --frozen --no-dev --extra models --no-install-project

COPY app/ app/
COPY scripts/ scripts/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --extra models

COPY config/ config/
COPY gunicorn.conf.py .

EXPOSE 5000

CMD ["gunicorn", "-c", "gunicorn.conf.py", "app.main:app"]
