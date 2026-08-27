"""Upload Qwen3-VL and SigLIP2 embedding artifacts into Milvus only.

Usage:
    cd apps/api
    uv run python scripts/upload_embedding_artifacts.py --artifact all
    uv run python scripts/upload_embedding_artifacts.py --artifact qwen --dry-run
    uv run python scripts/upload_embedding_artifacts.py --artifact siglip2 --drop

The script reads records-*.jsonl and embeddings-*.npy pairs directly from the
artifact directories. It never connects to Elasticsearch.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import numpy as np
from dotenv import load_dotenv
from pymilvus import Collection, CollectionSchema, DataType, FieldSchema, connections, utility

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

MILVUS_URI = os.getenv("MILVUS_URI", "http://localhost:19530")
MILVUS_TOKEN = os.getenv("MILVUS_TOKEN", "")
DATA_ROOT = Path(__file__).resolve().parents[3] / "data" / "Data"
CHECKPOINT_DIR = Path(__file__).resolve().parent / ".milvus_upload_checkpoints"
MILVUS_BATCH = 8000
TAG_ITEM_MAX_LEN = 32
TAGS_MAX_COUNT = 100


@dataclass(frozen=True)
class ArtifactConfig:
    """One embedding artifact and its separate Milvus collection."""

    name: str
    root: Path
    collection_name: str
    expected_dim: int


ARTIFACTS = {
    "qwen": ArtifactConfig(
        name="qwen",
        root=DATA_ROOT / "qwen3-vl-embedding-2b-batch1",
        collection_name="data_frames_qwen3",
        expected_dim=2048,
    ),
    "siglip2": ArtifactConfig(
        name="siglip2",
        root=DATA_ROOT / "siglip2-so400m-batch1",
        collection_name="data_frames_siglip2",
        expected_dim=1152,
    ),
}


def embedding_path(root: Path, record_path: Path) -> Path:
    """Return the NPY path aligned with one records JSONL shard."""
    return root / "embeddings" / record_path.name.replace("records-", "embeddings-").replace(
        ".jsonl", ".npy"
    )


def status_path(root: Path, record_path: Path) -> Path:
    """Return the status JSON path aligned with one records JSONL shard."""
    return root / "status" / record_path.name.replace("records-", "status-").replace(
        ".jsonl", ".json"
    )


def record_files(config: ArtifactConfig) -> list[Path]:
    """List every records shard in deterministic order."""
    files = sorted((config.root / "records").glob("records-*.jsonl"))
    if not files:
        raise FileNotFoundError(f"No records shards found under {config.root}")
    return files


def read_manifest(config: ArtifactConfig) -> dict[str, Any]:
    """Read and validate the artifact manifest before inserting anything."""
    manifest_path = config.root / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(manifest_path)
    manifest = cast(dict[str, Any], json.loads(manifest_path.read_text(encoding="utf-8")))
    dim = int(manifest.get("embedding_dim", 0))
    if dim != config.expected_dim:
        raise ValueError(
            f"{config.name}: manifest dimension {dim} does not match expected {config.expected_dim}"
        )
    if not bool(manifest.get("normalized")):
        raise ValueError(f"{config.name}: artifact is not marked as L2-normalized")
    return manifest


def load_validated_shard(config: ArtifactConfig, record_path: Path) -> tuple[list[dict[str, Any]], np.ndarray]:
    """Load one aligned JSONL/NPY pair after validating its status and shape."""
    npy_path = embedding_path(config.root, record_path)
    shard_status_path = status_path(config.root, record_path)
    if not npy_path.is_file() or not shard_status_path.is_file():
        raise FileNotFoundError(f"Missing pair or status for {record_path.name}")
    status = json.loads(shard_status_path.read_text(encoding="utf-8"))
    if not bool(status.get("normalized")):
        raise ValueError(f"{record_path.name}: shard is not marked as normalized")
    status_dim = int(status.get("embedding_dim", 0))
    if status_dim != config.expected_dim:
        raise ValueError(f"{record_path.name}: status dimension {status_dim} is invalid")
    with record_path.open(encoding="utf-8") as handle:
        records = [json.loads(line) for line in handle]
    embeddings = np.load(npy_path, allow_pickle=False)
    if embeddings.ndim != 2 or embeddings.shape != (len(records), config.expected_dim):
        raise ValueError(
            f"{record_path.name}: expected {(len(records), config.expected_dim)}, got {embeddings.shape}"
        )
    if embeddings.dtype not in (np.dtype("float16"), np.dtype("float32")):
        raise ValueError(f"{record_path.name}: unsupported dtype {embeddings.dtype}")
    expected_rows = int(status.get("record_count", status.get("rows", -1)))
    if expected_rows != len(records):
        raise ValueError(f"{record_path.name}: status has {expected_rows} rows, records has {len(records)}")
    return records, embeddings


def connect_milvus() -> None:
    """Connect to Milvus using the existing API environment variables."""
    print(f"Connecting to Milvus at {MILVUS_URI}...")
    connections.connect(alias="default", uri=MILVUS_URI, token=MILVUS_TOKEN)
    print("Milvus connected.")


def collection_schema(dim: int) -> CollectionSchema:
    """Return the same frame metadata schema used by the existing Milvus loader."""
    fields = [
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
        FieldSchema(
            name="tags",
            dtype=DataType.ARRAY,
            element_type=DataType.VARCHAR,
            max_length=TAG_ITEM_MAX_LEN,
            max_capacity=TAGS_MAX_COUNT,
        ),
        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=dim),
    ]
    return CollectionSchema(fields, description=f"Frame embeddings ({dim} dimensions)")


def ensure_collection(config: ArtifactConfig, drop: bool) -> Collection:
    """Open or create the model-specific IP collection."""
    if utility.has_collection(config.collection_name):
        if drop:
            print(f"Dropping existing collection '{config.collection_name}'...")
            utility.drop_collection(config.collection_name)
        else:
            collection = Collection(config.collection_name)
            embedding_field = next(field for field in collection.schema.fields if field.name == "embedding")
            dimension = int(embedding_field.params["dim"])
            if dimension != config.expected_dim:
                raise ValueError(
                    f"Collection '{config.collection_name}' has dim={dimension}, "
                    f"expected {config.expected_dim}"
                )
            return collection
    collection = Collection(config.collection_name, collection_schema(config.expected_dim))
    collection.create_index(
        field_name="embedding",
        index_params={"metric_type": "IP", "index_type": "AUTOINDEX", "params": {}},
    )
    print(f"Created collection '{config.collection_name}' (dim={config.expected_dim}, metric=IP).")
    return collection


def checkpoint_path(config: ArtifactConfig, collection_name: str) -> Path:
    """Store resumable upload state outside the downloaded embedding artifacts."""
    safe_collection = collection_name.replace("/", "_").replace("\\", "_")
    return CHECKPOINT_DIR / f"{config.name}-{safe_collection}.json"


def load_checkpoint(config: ArtifactConfig, collection_name: str) -> set[str]:
    """Load completed shard names and reject a checkpoint for another collection."""
    path = checkpoint_path(config, collection_name)
    if not path.is_file():
        return set()
    checkpoint = json.loads(path.read_text(encoding="utf-8"))
    if checkpoint.get("collection_name") != collection_name:
        raise ValueError(f"Checkpoint belongs to another collection: {path}")
    if int(checkpoint.get("embedding_dim", 0)) != config.expected_dim:
        raise ValueError(f"Checkpoint dimension mismatch: {path}")
    return set(checkpoint.get("processed_shards", []))


def save_checkpoint(config: ArtifactConfig, collection_name: str, processed: set[str]) -> None:
    """Atomically persist upload progress after each successful shard."""
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    path = checkpoint_path(config, collection_name)
    temporary = path.with_suffix(".tmp")
    payload = {
        "artifact": config.name,
        "collection_name": collection_name,
        "embedding_dim": config.expected_dim,
        "processed_shards": sorted(processed),
    }
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def record_value(record: dict[str, Any], key: str, default: Any = "") -> Any:
    """Read a field from records produced by either embedding notebook."""
    return record.get(key, default)


def milvus_rows(records: list[dict[str, Any]], embeddings: np.ndarray) -> list[list[object]]:
    """Convert one insert batch into the column-oriented pymilvus format."""
    rows: list[list[object]] = [[] for _ in range(14)]
    float_embeddings = embeddings.astype(np.float32, copy=False)
    for record, embedding in zip(records, float_embeddings, strict=True):
        frame_index = int(record_value(record, "frame_idx", record_value(record, "frame_index", 0)) or 0)
        timestamp = float(record_value(record, "timestamp", record_value(record, "pts_time", 0.0)) or 0.0)
        tags = [str(tag)[:TAG_ITEM_MAX_LEN] for tag in list(record_value(record, "tags", []) or [])]
        rows[0].append(str(record_value(record, "video_id", "")))
        rows[1].append(str(record_value(record, "video_path", "")).rstrip("/"))
        rows[2].append(str(record_value(record, "youtube_url", "")))
        rows[3].append(frame_index)
        rows[4].append(frame_index)
        rows[5].append(str(record_value(record, "frame_path", "")))
        rows[6].append(int(record_value(record, "shot_idx", 0) or 0))
        rows[7].append(float(record_value(record, "start_time", 0.0) or 0.0))
        rows[8].append(float(record_value(record, "end_time", 0.0) or 0.0))
        rows[9].append(float(record_value(record, "pts_time", timestamp) or timestamp))
        rows[10].append(float(record_value(record, "fps", 0.0) or 0.0))
        rows[11].append(timestamp)
        rows[12].append(tags[:TAGS_MAX_COUNT])
        rows[13].append(embedding.tolist())
    return rows


def append_rows(target: list[list[object]], source: list[list[object]]) -> None:
    """Append a complete shard's column-oriented rows to an insert buffer."""
    if len(target) != len(source):
        raise ValueError("Milvus column count mismatch")
    for target_column, source_column in zip(target, source, strict=True):
        target_column.extend(source_column)


def flush_insert_buffer(
    collection: Collection,
    buffer: list[list[object]],
    buffered_shards: list[str],
    config: ArtifactConfig,
    collection_name: str,
    processed: set[str],
) -> int:
    """Insert one full cross-shard batch and checkpoint it for a later resume."""
    if not buffer[0]:
        return 0
    collection.insert(buffer)
    row_count = len(buffer[0])
    processed.update(buffered_shards)
    save_checkpoint(config, collection_name, processed)
    return row_count


def upload_artifact(config: ArtifactConfig, collection_name: str, drop: bool, dry_run: bool) -> int:
    """Validate and upload one complete model artifact, without Elasticsearch."""
    manifest = read_manifest(config)
    files = record_files(config)
    print(
        f"\n{config.name}: {manifest.get('total_frames', 'unknown')} frames, "
        f"{len(files)} shards, dim={config.expected_dim}"
    )
    for record_path in files:
        load_validated_shard(config, record_path)
    print(f"{config.name}: artifact validation passed.")
    if dry_run:
        return sum(len(load_validated_shard(config, path)[0]) for path in files)

    collection = ensure_collection(config, drop)
    processed = set() if drop else load_checkpoint(config, collection_name)
    if collection.num_entities and not processed:
        raise RuntimeError(
            f"Collection '{collection_name}' already has {collection.num_entities} entities but no upload "
            "checkpoint. Use --drop to replace it, or restore the matching checkpoint before resuming."
        )
    inserted = 0
    started = time.monotonic()
    buffer: list[list[object]] = [[] for _ in range(14)]
    buffered_shards: list[str] = []
    for shard_index, record_path in enumerate(files, 1):
        if record_path.name in processed:
            continue
        records, embeddings = load_validated_shard(config, record_path)
        shard_rows = milvus_rows(records, embeddings)
        if buffer[0] and len(buffer[0]) + len(shard_rows[0]) > MILVUS_BATCH:
            inserted += flush_insert_buffer(
                collection,
                buffer,
                buffered_shards,
                config,
                collection_name,
                processed,
            )
            elapsed = time.monotonic() - started
            rate = inserted / elapsed if elapsed else 0.0
            print(f"  [{shard_index - 1}/{len(files)}] {inserted} inserted, {rate:.0f} rows/s")
            buffer = [[] for _ in range(14)]
            buffered_shards = []
        append_rows(buffer, shard_rows)
        buffered_shards.append(record_path.name)
    inserted += flush_insert_buffer(
        collection,
        buffer,
        buffered_shards,
        config,
        collection_name,
        processed,
    )
    collection.flush()
    print(f"{config.name}: collection '{collection_name}' has {collection.num_entities} entities.")
    return inserted


def parse_args() -> argparse.Namespace:
    """Parse command-line options."""
    parser = argparse.ArgumentParser(description="Upload Qwen/SigLIP2 artifacts to Milvus only")
    parser.add_argument("--artifact", choices=[*ARTIFACTS, "all"], default="all")
    parser.add_argument("--collection", help="Override collection name; valid only for one artifact")
    parser.add_argument("--drop", action="store_true", help="Drop selected collection before uploading")
    parser.add_argument("--dry-run", action="store_true", help="Validate artifacts without database writes")
    return parser.parse_args()


def main() -> None:
    """Run the selected Milvus-only uploads."""
    args = parse_args()
    selected = list(ARTIFACTS) if args.artifact == "all" else [args.artifact]
    if args.collection and len(selected) != 1:
        raise SystemExit("--collection can only be used with --artifact qwen or --artifact siglip2")
    if not args.dry_run:
        connect_milvus()
    total = 0
    for name in selected:
        config = ARTIFACTS[name]
        collection_name = args.collection or config.collection_name
        total += upload_artifact(config, collection_name, args.drop, args.dry_run)
    print(f"\nDone: {total} rows {'validated' if args.dry_run else 'uploaded'}.")


if __name__ == "__main__":
    main()
