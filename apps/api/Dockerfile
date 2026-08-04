FROM python:3.11-slim

WORKDIR /app

COPY apps/api/pyproject.toml .
RUN pip install --no-cache-dir -e .

COPY apps/api/app/ app/
COPY data/objects/object_detections.parquet /app/data/objects/object_detections.parquet

ENV OBJECT_DETECTIONS_PATH=/app/data/objects/object_detections.parquet

EXPOSE 5000

CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:5000", "app.main:app"]
