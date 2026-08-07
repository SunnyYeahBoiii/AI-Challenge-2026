"""
Load pre-computed embeddings + metadata into Milvus and Elasticsearch.

Usage:
    cd apps/api
    uv run python scripts/load_data.py
    uv run python scripts/load_data.py --limit 10 --dry-run
    uv run python scripts/load_data.py --validate-only
    uv run python scripts/load_data.py --recreate

Expects .env in apps/api/ with MILVUS_URI, ES_URL, EMBEDDING_DIM, etc.
Data files:
    - data/embeddings/metaclip2-worldwide-huge.zip
    - data/metadata/concatenate-data.json
    - data/keyframes/<level>/<video_id>/<frame>.webp
    - data/media-info/<video_id>.json
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections.abc import Iterable
from itertools import islice
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from elasticsearch import Elasticsearch
from pymilvus import Collection, CollectionSchema, DataType, FieldSchema, connections, utility

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.data_import import FrameImportRecord, ImportDataError, iter_import_records

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _default_data_root() -> Path:
    """Locate the repository data directory, falling back to the Docker mount."""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "data"
        required = (candidate / "metadata", candidate / "embeddings", candidate / "keyframes")
        if all(path.is_dir() for path in required):
            return candidate
    return Path("/data")


DATA_ROOT = Path(os.getenv("DATA_ROOT", str(_default_data_root())))
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1024"))
MILVUS_BATCH_SIZE = int(os.getenv("MILVUS_BATCH_SIZE", "8000"))

DEFAULT_METADATA = DATA_ROOT / "metadata" / "concatenate-data.json"
DEFAULT_EMBEDDINGS = DATA_ROOT / "embeddings" / "metaclip2-worldwide-huge.zip"
DEFAULT_KEYFRAMES = DATA_ROOT / "keyframes"
DEFAULT_MEDIA_INFO = DATA_ROOT / "media-info"

COLLECTION_NAME = "data_frames"
ES_INDEX = "video_texts"

ES_MAPPING: dict[str, Any] = {
    "mappings": {
        "properties": {
            "video_id": {"type": "keyword"},
            "video_path": {"type": "keyword"},
            "frame_id": {"type": "integer"},
            "frame_idx": {"type": "integer"},
            "frame_path": {"type": "keyword"},
            "ocr_text": {"type": "text"},
            "asr_text": {"type": "text"},
            "timestamp": {"type": "float"},
        }
    }
}


def _milvus_fields(embedding_dim: int) -> list[FieldSchema]:
    """Return main's schema, excluding only the legacy tags field."""
    return [
        FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
        FieldSchema(name="video_id", dtype=DataType.VARCHAR, max_length=64),
        FieldSchema(name="video_path", dtype=DataType.VARCHAR, max_length=500),
        FieldSchema(name="youtube_url", dtype=DataType.VARCHAR, max_length=500),
        FieldSchema(name="frame_index", dtype=DataType.INT64),
        FieldSchema(name="frame_idx", dtype=DataType.INT64),
        FieldSchema(name="frame_path", dtype=DataType.VARCHAR, max_length=500),
        FieldSchema(name="shot_idx", dtype=DataType.INT64),
        FieldSchema(name="start_time", dtype=DataType.FLOAT),
        FieldSchema(name="end_time", dtype=DataType.FLOAT),
        FieldSchema(name="pts_time", dtype=DataType.FLOAT),
        FieldSchema(name="fps", dtype=DataType.FLOAT),
        FieldSchema(name="timestamp", dtype=DataType.FLOAT),
        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=embedding_dim),
    ]


def _connect_milvus() -> None:
    uri = os.getenv("MILVUS_URI", "http://localhost:19530")
    token = os.getenv("MILVUS_TOKEN", "")
    kwargs: dict[str, str] = {"alias": "default", "uri": uri}
    if token:
        kwargs["token"] = token
    connections.connect(**kwargs)


def _ensure_milvus_collection(embedding_dim: int, recreate: bool) -> Collection:
    _connect_milvus()
    exists = bool(utility.has_collection(COLLECTION_NAME))
    if exists and recreate:
        utility.drop_collection(COLLECTION_NAME)
        exists = False

    if exists:
        collection = Collection(COLLECTION_NAME)
        expected = [(field.name, field.dtype) for field in _milvus_fields(embedding_dim)]
        actual = [(field.name, field.dtype) for field in collection.schema.fields]
        vector_field = next(
            (field for field in collection.schema.fields if field.name == "embedding"),
            None,
        )
        actual_dim = int(vector_field.params.get("dim", 0)) if vector_field else 0
        if actual != expected or actual_dim != embedding_dim:
            raise ImportDataError(
                "Existing Milvus schema does not match the current schema; "
                "rerun with --recreate"
            )
        return collection

    collection = Collection(
        COLLECTION_NAME,
        CollectionSchema(
            _milvus_fields(embedding_dim),
            description="Video frames with metadata and MetaCLIP2 embeddings",
        ),
    )
    collection.create_index(
        field_name="embedding",
        index_params={"metric_type": "IP", "index_type": "AUTOINDEX", "params": {}},
    )
    return collection


def _connect_elasticsearch() -> Elasticsearch:
    url = os.getenv("ES_URL", "http://localhost:9200")
    user = os.getenv("ES_USER", "")
    password = os.getenv("ES_PASS", "")
    client = Elasticsearch(url, basic_auth=(user, password)) if user and password else Elasticsearch(url)
    if not client.ping():
        raise ConnectionError(f"Cannot connect to Elasticsearch at {url}")
    return client


def _ensure_es_index(client: Elasticsearch, recreate: bool) -> None:
    exists = bool(client.indices.exists(index=ES_INDEX))
    if exists and recreate:
        client.indices.delete(index=ES_INDEX)
        exists = False
    if not exists:
        client.indices.create(index=ES_INDEX, mappings=ES_MAPPING["mappings"])
        return

    mapping = client.indices.get_mapping(index=ES_INDEX)
    properties = mapping[ES_INDEX]["mappings"].get("properties", {})
    expected = ES_MAPPING["mappings"]["properties"]
    mismatched = [
        field
        for field, definition in expected.items()
        if properties.get(field, {}).get("type") != definition["type"]
    ]
    if mismatched:
        raise ImportDataError(
            f"Existing Elasticsearch mapping differs for {', '.join(mismatched)}; "
            "rerun with --recreate"
        )


def _milvus_values(records: list[FrameImportRecord]) -> list[list[object]]:
    """Build insert columns for the auto-ID Milvus schema."""
    columns: list[list[object]] = [[] for _ in range(13)]
    for record in records:
        values = [
            record.video_id,
            record.video_path,
            record.youtube_url,
            record.frame_index,
            record.frame_idx,
            record.frame_path,
            record.shot_idx,
            record.start_time,
            record.end_time,
            record.pts_time,
            record.fps,
            record.pts_time,
            record.embedding.tolist(),
        ]
        for column, value in zip(columns, values, strict=True):
            column.append(value)
    return columns


def _write_es_batch(client: Elasticsearch, records: list[FrameImportRecord]) -> None:
    operations: list[dict[str, object]] = []
    for record in records:
        operations.append({"index": {"_index": ES_INDEX, "_id": record.id}})
        operations.append(record.elasticsearch_values())

    response = client.bulk(operations=operations, refresh=False)
    if response.get("errors"):
        failures = [
            item["index"].get("error")
            for item in response["items"]
            if item["index"].get("error")
        ]
        raise ImportDataError(f"Elasticsearch bulk import failed: {failures[0]}")


def _batches(
    records: Iterable[FrameImportRecord], size: int
) -> Iterable[list[FrameImportRecord]]:
    iterator = iter(records)
    while batch := list(islice(iterator, size)):
        yield batch


def import_records(
    records: Iterable[FrameImportRecord],
    collection: Collection,
    elasticsearch: Elasticsearch,
    batch_size: int,
) -> int:
    """Insert frame rows into Milvus and upsert their text documents in ES."""
    count = 0
    started = time.monotonic()
    for batch in _batches(records, batch_size):
        collection.insert(_milvus_values(batch))
        _write_es_batch(elasticsearch, batch)
        count += len(batch)
        elapsed = max(time.monotonic() - started, 0.001)
        print(f"Imported {count:,} frames ({count / elapsed:,.0f} frames/s)", flush=True)

    collection.flush()
    elasticsearch.indices.refresh(index=ES_INDEX)
    return count


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, default=DEFAULT_METADATA)
    parser.add_argument("--embeddings", type=Path, default=DEFAULT_EMBEDDINGS)
    parser.add_argument("--keyframes", type=Path, default=DEFAULT_KEYFRAMES)
    parser.add_argument("--media-info", type=Path, default=DEFAULT_MEDIA_INFO)
    parser.add_argument("--embedding-dim", type=int, default=EMBEDDING_DIM)
    parser.add_argument("--batch-size", type=int, default=MILVUS_BATCH_SIZE)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="delete and recreate both database targets before importing",
    )
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.embedding_dim <= 0:
        raise SystemExit("--embedding-dim must be positive")
    if args.batch_size <= 0:
        raise SystemExit("--batch-size must be positive")
    if args.limit is not None and args.limit <= 0:
        raise SystemExit("--limit must be positive")

    records: Iterable[FrameImportRecord] = iter_import_records(
        args.metadata,
        args.embeddings,
        args.keyframes,
        args.media_info,
        args.embedding_dim,
    )
    if args.limit is not None:
        records = islice(records, args.limit)

    if args.validate_only or args.dry_run:
        count = sum(1 for _ in records)
        suffix = " (dry run)" if args.dry_run else ""
        print(f"Validated {count:,} aligned metadata, media, and embedding rows{suffix}.")
        return

    collection = _ensure_milvus_collection(args.embedding_dim, args.recreate)
    elasticsearch = _connect_elasticsearch()
    _ensure_es_index(elasticsearch, args.recreate)
    count = import_records(records, collection, elasticsearch, args.batch_size)
    print(f"Import complete: {count:,} rows in Milvus and Elasticsearch.")


if __name__ == "__main__":
    try:
        main()
    except ImportDataError as error:
        raise SystemExit(f"Import validation failed: {error}") from error
