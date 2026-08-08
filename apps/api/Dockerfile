FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

# Install from the lockfile (not `pip install -e .`): torchscale's PyPI metadata
# pins fairscale==0.4.0, which conflicts with open-clip-torch's fairscale range.
# uv.lock already resolved this via [tool.uv].override-dependencies in
# pyproject.toml; plain pip has no equivalent and fails to resolve.
COPY apps/api/pyproject.toml apps/api/uv.lock ./
RUN uv sync --frozen --no-install-project

COPY apps/api/app/ app/
COPY data/objects/object_detections.parquet /app/data/objects/object_detections.parquet

ENV OBJECT_DETECTIONS_PATH=/app/data/objects/object_detections.parquet
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 5000

CMD ["gunicorn", "-w", "1", "-k", "gthread", "--threads", "4", "--timeout", "180", "--graceful-timeout", "30", "-b", "0.0.0.0:5000", "app.main:app"]
