"""Load checksummed multi-model embedding artifacts into Milvus collections."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from app.services.embedding_artifacts import FrameRecord, iter_artifact_shards
from app.services.milvus_client import (
    FRAME_UID_MAX_LEN,
    TAG_ITEM_MAX_LEN,
    TAGS_MAX_COUNT,
    URL_MAX_LEN,
    VIDEO_ID_MAX_LEN,
    VIDEO_PATH_MAX_LEN,
    ensure_model_collection,
)
from app.services.model_registry import ModelSpec, load_model_specs

LOGGER = logging.getLogger("frameseeker.load_ensemble_embeddings")
FIELD_ORDER = [
    "frame_uid",
    "video_id",
    "video_path",
    "youtube_url",
    "frame_index",
    "frame_idx",
    "frame_path",
    "shot_idx",
    "start_time",
    "end_time",
    "pts_time",
    "fps",
    "timestamp",
    "tags",
    "embedding",
]


@dataclass(frozen=True)
class PreparedArtifact:
    """A fully validated artifact that is safe to compare before database writes."""

    manifest_path: Path
    spec: ModelSpec
    frame_count: int
    frame_uid_sha256: str


def _load_manifest(manifest_path: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("artifact manifest must be a JSON object")
    return manifest


def _manifest_model_id(manifest: Mapping[str, Any]) -> str:
    try:
        return str(manifest["model"]["id"])
    except (KeyError, TypeError) as error:
        raise ValueError("artifact manifest does not contain model.id") from error


def _columns(
    records: Sequence[Mapping[str, Any]],
    embeddings: np.ndarray,
) -> list[list[object]]:
    if len(records) != len(embeddings):
        raise ValueError("artifact record and embedding counts must match")
    if not np.isfinite(embeddings).all():
        raise ValueError("artifact embeddings must contain only finite values")
    columns: dict[str, list[object]] = {field: [] for field in FIELD_ORDER}
    seen: set[str] = set()
    for record, embedding in zip(records, embeddings):
        normalized = FrameRecord.from_mapping(record)
        frame_uid = normalized.frame_uid
        if frame_uid in seen:
            raise ValueError(f"duplicate frame_uid in artifact shard: {frame_uid}")
        seen.add(frame_uid)
        tags = [tag[:TAG_ITEM_MAX_LEN] for tag in normalized.tags]
        values: dict[str, object] = {
            "frame_uid": frame_uid,
            "video_id": normalized.video_id,
            "video_path": normalized.video_path,
            "youtube_url": normalized.youtube_url,
            "frame_index": normalized.frame_index,
            "frame_idx": normalized.original_frame_idx,
            "frame_path": normalized.frame_path,
            "shot_idx": normalized.shot_idx,
            "start_time": normalized.start_time,
            "end_time": normalized.end_time,
            "pts_time": normalized.pts_time,
            "fps": normalized.fps,
            "timestamp": normalized.pts_time,
            "tags": tags[:TAGS_MAX_COUNT],
            "embedding": np.asarray(embedding, dtype=np.float32).tolist(),
        }
        length_limits = {
            "frame_uid": FRAME_UID_MAX_LEN,
            "video_id": VIDEO_ID_MAX_LEN,
            "video_path": VIDEO_PATH_MAX_LEN,
            "youtube_url": URL_MAX_LEN,
            "frame_path": URL_MAX_LEN,
        }
        for field, max_length in length_limits.items():
            if len(str(values[field])) > max_length:
                raise ValueError(
                    f"artifact {field} exceeds Milvus maximum length {max_length}"
                )
        for field in FIELD_ORDER:
            columns[field].append(values[field])
    return [columns[field] for field in FIELD_ORDER]


def _select_spec(config_path: Path, model_id: str) -> ModelSpec:
    matches = [spec for spec in load_model_specs(config_path) if spec.model_id == model_id]
    if not matches:
        raise ValueError(f"model {model_id} is missing from {config_path}")
    return matches[0]


def _validate_manifest_model(manifest: Mapping[str, Any], spec: ModelSpec) -> None:
    if manifest.get("complete") is not True:
        raise ValueError("embedding artifact is incomplete; resume inference before loading")
    raw_model = manifest.get("model")
    if not isinstance(raw_model, Mapping):
        raise ValueError("artifact manifest model must be an object")
    expected: dict[str, object] = {
        "id": spec.model_id,
        "adapter": spec.adapter,
        "model_name": spec.model_name,
        "pretrained": spec.pretrained,
        "revision": spec.revision,
        "dtype": spec.dtype,
        "dimension": spec.dimension,
        "text_padding": spec.text_padding,
        "text_max_length": spec.text_max_length,
        "tokenizer_url": spec.tokenizer_url,
        "image_size": spec.image_size,
        "pretrained_sha256": spec.pretrained_sha256,
        "tokenizer_sha256": spec.tokenizer_sha256,
    }
    for field, expected_value in expected.items():
        actual_value = raw_model.get(field)
        if actual_value != expected_value:
            raise ValueError(
                f"artifact model {field} {actual_value!r} does not match "
                f"configured value {expected_value!r}"
            )


def _preflight_artifact(
    manifest_path: Path,
    *,
    insert_batch_size: int,
    verify_checksums: bool,
) -> tuple[int, str]:
    """Validate every shard before any collection can be dropped or modified."""
    seen_frame_uids: set[str] = set()
    validated = 0
    for embeddings, records in iter_artifact_shards(
        manifest_path,
        verify_checksums=verify_checksums,
    ):
        for start in range(0, len(records), insert_batch_size):
            end = start + insert_batch_size
            batch_records = records[start:end]
            for record in batch_records:
                frame_uid = str(record["frame_uid"])
                if frame_uid in seen_frame_uids:
                    raise ValueError(f"duplicate frame_uid in artifact: {frame_uid}")
                seen_frame_uids.add(frame_uid)
            _columns(batch_records, embeddings[start:end])
            validated += len(batch_records)
    if validated < 1:
        raise ValueError("embedding artifact contains no Frames")
    digest = hashlib.sha256()
    for frame_uid in sorted(seen_frame_uids):
        digest.update(frame_uid.encode("utf-8"))
        digest.update(b"\n")
    return validated, digest.hexdigest()


def _prepare_artifact(
    manifest_path: Path,
    *,
    config_path: Path,
    insert_batch_size: int,
    verify_checksums: bool,
) -> PreparedArtifact:
    manifest = _load_manifest(manifest_path)
    spec = _select_spec(config_path, _manifest_model_id(manifest))
    _validate_manifest_model(manifest, spec)
    frame_count, frame_uid_sha256 = _preflight_artifact(
        manifest_path,
        insert_batch_size=insert_batch_size,
        verify_checksums=verify_checksums,
    )
    return PreparedArtifact(
        manifest_path=manifest_path,
        spec=spec,
        frame_count=frame_count,
        frame_uid_sha256=frame_uid_sha256,
    )


def _artifact_frame_uids(manifest_path: Path) -> set[str]:
    frame_uids: set[str] = set()
    for _, records in iter_artifact_shards(manifest_path, verify_checksums=False):
        frame_uids.update(str(record["frame_uid"]) for record in records)
    return frame_uids


def _collection_frame_uids(collection: Any) -> set[str]:
    if int(collection.num_entities) < 1:
        return set()
    collection.load()
    iterator = collection.query_iterator(
        expr='frame_uid != ""',
        output_fields=["frame_uid"],
        batch_size=2_000,
        limit=-1,
    )
    frame_uids: set[str] = set()
    try:
        while batch := iterator.next():
            for record in batch:
                frame_uid = str(record.get("frame_uid") or "")
                if not frame_uid:
                    raise ValueError("Milvus collection contains an empty frame_uid")
                if frame_uid in frame_uids:
                    raise ValueError(f"Milvus collection contains duplicate frame_uid {frame_uid}")
                frame_uids.add(frame_uid)
    finally:
        iterator.close()
    return frame_uids


def _load_prepared_artifact(
    prepared: PreparedArtifact,
    *,
    insert_batch_size: int,
    recreate: bool,
) -> int:
    spec = prepared.spec
    collection = ensure_model_collection(
        spec,
        recreate=recreate,
        require_canonical_schema=True,
    )
    expected_frame_uids = _artifact_frame_uids(prepared.manifest_path)
    existing_frame_uids = _collection_frame_uids(collection)
    stale_frame_uids = existing_frame_uids - expected_frame_uids
    if stale_frame_uids:
        sample = ", ".join(sorted(stale_frame_uids)[:3])
        raise ValueError(
            f"collection {spec.collection} contains stale Frames not present in the "
            f"artifact ({sample}); rerun with --recreate after backing up the collection"
        )

    loaded = 0
    for embeddings, records in iter_artifact_shards(
        prepared.manifest_path,
        verify_checksums=False,
    ):
        for start in range(0, len(records), insert_batch_size):
            end = start + insert_batch_size
            batch_records = records[start:end]
            batch_embeddings = embeddings[start:end]
            columns = _columns(batch_records, batch_embeddings)
            collection.upsert(columns)
            loaded += len(batch_records)
            if loaded % 10_000 == 0:
                LOGGER.info("%s: loaded %d Frames", spec.model_id, loaded)
    collection.flush()
    collection.load()
    actual_frame_uids = _collection_frame_uids(collection)
    if actual_frame_uids != expected_frame_uids:
        missing = expected_frame_uids - actual_frame_uids
        extra = actual_frame_uids - expected_frame_uids
        raise ValueError(
            f"collection {spec.collection} failed gallery verification after loading: "
            f"{len(missing)} missing and {len(extra)} extra Frames"
        )
    LOGGER.info("%s: completed and verified %d Frames", spec.model_id, loaded)
    return loaded


def load_artifact(
    *,
    manifest_path: Path,
    config_path: Path,
    insert_batch_size: int,
    verify_checksums: bool,
    recreate: bool,
    dry_run: bool,
) -> int:
    """Validate and upsert one model artifact into its configured collection."""
    loaded = load_artifacts(
        manifest_paths=[manifest_path],
        config_path=config_path,
        insert_batch_size=insert_batch_size,
        verify_checksums=verify_checksums,
        recreate=recreate,
        dry_run=dry_run,
    )
    return next(iter(loaded.values()))


def load_artifacts(
    *,
    manifest_paths: Sequence[Path],
    config_path: Path,
    insert_batch_size: int,
    verify_checksums: bool,
    recreate: bool,
    dry_run: bool,
) -> dict[str, int]:
    """Preflight matching model galleries, then load and verify every collection."""
    if insert_batch_size < 1:
        raise ValueError("insert_batch_size must be positive")
    if not manifest_paths:
        raise ValueError("at least one embedding artifact manifest is required")
    prepared = [
        _prepare_artifact(
            manifest_path,
            config_path=config_path,
            insert_batch_size=insert_batch_size,
            verify_checksums=verify_checksums,
        )
        for manifest_path in manifest_paths
    ]
    model_ids = [artifact.spec.model_id for artifact in prepared]
    if len(set(model_ids)) != len(model_ids):
        raise ValueError("each model artifact may only be loaded once")
    reference = prepared[0]
    for artifact in prepared[1:]:
        if (
            artifact.frame_count != reference.frame_count
            or artifact.frame_uid_sha256 != reference.frame_uid_sha256
        ):
            raise ValueError(
                f"{artifact.spec.model_id} gallery Frame set differs from "
                f"{reference.spec.model_id}; encode every model from the same manifest "
                "without model-specific skipped Frames"
            )
    if dry_run:
        for artifact in prepared:
            LOGGER.info(
                "%s: validated %d Frames",
                artifact.spec.model_id,
                artifact.frame_count,
            )
        return {
            artifact.spec.model_id: artifact.frame_count for artifact in prepared
        }
    return {
        artifact.spec.model_id: _load_prepared_artifact(
            artifact,
            insert_batch_size=insert_batch_size,
            recreate=recreate,
        )
        for artifact in prepared
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifests", nargs="+", type=Path)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "config" / "ensemble.json",
    )
    parser.add_argument("--insert-batch-size", type=int, default=2_000)
    parser.add_argument("--skip-checksums", action="store_true")
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Drop and recreate the exact configured collection before loading",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_artifacts(
        manifest_paths=args.manifests,
        config_path=args.config,
        insert_batch_size=args.insert_batch_size,
        verify_checksums=not args.skip_checksums,
        recreate=args.recreate,
        dry_run=args.dry_run,
    )
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    raise SystemExit(main())
