from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeAlias

import numpy as np
from numpy.typing import NDArray

from app.services.frame_identity import build_frame_uid
from app.services.model_registry import ModelSpec

ARTIFACT_VERSION = 1
FloatArray: TypeAlias = NDArray[np.float32]


@dataclass(frozen=True)
class FrameRecord:
    """Canonical metadata shared by every model-specific embedding artifact."""

    frame_uid: str
    video_id: str
    video_path: str
    frame_index: int
    original_frame_idx: int
    frame_path: str
    youtube_url: str = ""
    shot_idx: int = 0
    start_time: float = 0.0
    end_time: float = 0.0
    pts_time: float = 0.0
    fps: float = 0.0
    tags: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> FrameRecord:
        """Normalize current AIC metadata and future JSONL manifests."""
        frame_path = str(raw.get("frame_path") or raw.get("file_path") or "").replace(
            "\\", "/"
        )
        if not frame_path:
            raise ValueError("frame_path or file_path is required")
        video_path = str(raw.get("video_path") or Path(frame_path).parent).replace("\\", "/")
        video_id = str(
            raw.get("video_id") or video_path.rstrip("/").split("/")[-1]
        ).strip()
        if not video_id:
            raise ValueError("video_id is required")
        try:
            filename_frame_index = int(Path(frame_path).stem)
        except ValueError as error:
            raise ValueError(f"frame filename must be numeric: {frame_path}") from error
        frame_index = int(raw.get("frame_index", filename_frame_index))

        keyframe_info = raw.get("keyframe_info") or {}
        if not isinstance(keyframe_info, Mapping):
            raise ValueError("keyframe_info must be an object")
        original_frame_idx = int(
            raw.get(
                "original_frame_idx",
                raw.get("frame_idx", keyframe_info.get("frame_idx", frame_index)),
            )
        )
        shot_idx = int(raw.get("shot_idx", keyframe_info.get("shot_idx", 0)))
        start_time = float(raw.get("start_time", keyframe_info.get("start_time", 0.0)))
        end_time = float(raw.get("end_time", keyframe_info.get("end_time", 0.0)))
        pts_time = float(
            raw.get(
                "pts_time",
                raw.get("timestamp", keyframe_info.get("pts_time", 0.0)),
            )
        )
        fps = float(raw.get("fps", keyframe_info.get("fps", 0.0)))
        if original_frame_idx < 0 or shot_idx < 0:
            raise ValueError("frame_idx and shot_idx must be non-negative")
        numeric_metadata = {
            "start_time": start_time,
            "end_time": end_time,
            "pts_time": pts_time,
            "fps": fps,
        }
        if any(not math.isfinite(value) or value < 0 for value in numeric_metadata.values()):
            raise ValueError("Frame timing metadata must be finite and non-negative")
        raw_tags: list[object] = []
        for field in ("tags", "OD_tags", "RAM_tags"):
            field_tags = raw.get(field, [])
            if isinstance(field_tags, (str, bytes)) or not isinstance(
                field_tags, Sequence
            ):
                raise ValueError(f"{field} must be an array")
            raw_tags.extend(field_tags)
        tags = tuple(
            dict.fromkeys(str(tag).strip() for tag in raw_tags if str(tag).strip())
        )
        canonical_frame_uid = build_frame_uid(video_id, frame_index)
        supplied_frame_uid = str(raw.get("frame_uid") or "").strip()
        if supplied_frame_uid and supplied_frame_uid != canonical_frame_uid:
            raise ValueError(
                f"frame_uid must equal canonical identity {canonical_frame_uid}"
            )
        return cls(
            frame_uid=canonical_frame_uid,
            video_id=video_id,
            video_path=video_path,
            frame_index=frame_index,
            original_frame_idx=original_frame_idx,
            frame_path=frame_path,
            youtube_url=str(raw.get("youtube_url") or raw.get("watch_url") or "").strip(),
            shot_idx=shot_idx,
            start_time=start_time,
            end_time=end_time,
            pts_time=pts_time,
            fps=fps,
            tags=tags,
        )

    def as_metadata(self) -> dict[str, object]:
        data = asdict(self)
        data["frame_idx"] = data.pop("original_frame_idx")
        data["timestamp"] = data["pts_time"]
        data["tags"] = list(self.tags)
        return data


def iter_input_records(path: Path) -> Iterator[dict[str, Any]]:
    """Read canonical records from JSONL or a JSON array."""
    if path.suffix.lower() == ".jsonl":
        with path.open(encoding="utf-8") as input_file:
            for line_number, line in enumerate(input_file, start=1):
                if not line.strip():
                    continue
                record = json.loads(line)
                if not isinstance(record, dict):
                    raise ValueError(f"JSONL line {line_number} is not an object")
                yield record
        return

    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("JSON input must be an array; use JSONL for streaming input")
    for record in raw:
        if not isinstance(record, dict):
            raise ValueError("JSON array items must be objects")
        yield record


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as artifact:
        for chunk in iter(lambda: artifact.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class EmbeddingArtifactWriter:
    """Write deterministic, checksummed embedding shards with resumable metadata."""

    def __init__(
        self,
        output_root: Path,
        spec: ModelSpec,
        *,
        shard_size: int = 10_000,
        resume: bool = False,
    ) -> None:
        if shard_size < 1:
            raise ValueError("shard_size must be positive")
        self.spec = spec
        self.output_dir = output_root / spec.model_id
        self.manifest_path = self.output_dir / "manifest.json"
        self.shard_size = shard_size
        self._pending_records: list[FrameRecord] = []
        self._pending_embeddings: FloatArray = np.empty(
            (0, spec.dimension), dtype=np.float32
        )
        self._shards: list[dict[str, object]] = []
        self._next_shard = 0
        self._created_at = datetime.now(UTC).isoformat()
        self.processed_frame_uids: set[str] = set()

        self.output_dir.mkdir(parents=True, exist_ok=True)
        existing_files = list(self.output_dir.iterdir())
        if existing_files and not resume:
            raise FileExistsError(
                f"artifact directory is not empty: {self.output_dir}; use --resume"
            )
        if existing_files and resume and not self.manifest_path.exists():
            raise FileNotFoundError(
                f"cannot resume artifact without manifest: {self.manifest_path}"
            )
        if resume and self.manifest_path.exists():
            self._load_existing_manifest()

    def _load_existing_manifest(self) -> None:
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        raw_model = manifest.get("model", {})
        if not isinstance(raw_model, Mapping):
            raise ValueError("resume manifest model must be an object")
        if raw_model.get("id") != self.spec.model_id:
            raise ValueError("resume manifest belongs to a different model")
        if raw_model.get("dimension") != self.spec.dimension:
            raise ValueError("resume manifest has a different embedding dimension")
        expected_identity: dict[str, object] = {
            "adapter": self.spec.adapter,
            "model_name": self.spec.model_name,
            "pretrained": self.spec.pretrained,
            "revision": self.spec.revision,
            "text_padding": self.spec.text_padding,
            "text_max_length": self.spec.text_max_length,
        }
        for field, expected_value in expected_identity.items():
            if raw_model.get(field) != expected_value:
                raise ValueError(
                    f"resume manifest model {field} differs from the configured model"
                )
        self._shards = list(manifest.get("shards", []))
        self._created_at = str(manifest.get("created_at", self._created_at))
        self._next_shard = len(self._shards)
        for _, records in iter_artifact_shards(
            self.manifest_path,
            verify_checksums=True,
        ):
            for record in records:
                frame_uid = str(record["frame_uid"])
                if frame_uid in self.processed_frame_uids:
                    raise ValueError(f"duplicate frame_uid in resume artifact: {frame_uid}")
                self.processed_frame_uids.add(frame_uid)

    def append(self, records: Sequence[FrameRecord], embeddings: np.ndarray) -> None:
        """Append one inference batch and flush complete shards."""
        array = np.asarray(embeddings, dtype=np.float32)
        expected_shape = (len(records), self.spec.dimension)
        if array.shape != expected_shape:
            raise ValueError(f"embedding shape {array.shape} does not match {expected_shape}")
        if not np.isfinite(array).all():
            raise ValueError("embeddings must contain only finite values")
        existing = self.processed_frame_uids | {
            record.frame_uid for record in self._pending_records
        }
        new_ids: set[str] = set()
        for record in records:
            if record.frame_uid in existing or record.frame_uid in new_ids:
                raise ValueError(f"duplicate frame_uid: {record.frame_uid}")
            new_ids.add(record.frame_uid)
        self._pending_records.extend(records)
        self._pending_embeddings = np.concatenate([self._pending_embeddings, array], axis=0)
        while len(self._pending_records) >= self.shard_size:
            self._flush(self.shard_size)

    def _flush(self, count: int) -> None:
        records = self._pending_records[:count]
        embeddings = self._pending_embeddings[:count]
        stem = f"{self._next_shard:05d}"
        embeddings_path = self.output_dir / f"embeddings-{stem}.npy"
        records_path = self.output_dir / f"records-{stem}.jsonl"
        np.save(embeddings_path, embeddings, allow_pickle=False)
        with records_path.open("w", encoding="utf-8") as records_file:
            for record in records:
                records_file.write(json.dumps(record.as_metadata(), ensure_ascii=False) + "\n")

        self._shards.append(
            {
                "index": self._next_shard,
                "count": count,
                "embeddings_file": embeddings_path.name,
                "records_file": records_path.name,
                "embeddings_sha256": _sha256(embeddings_path),
                "records_sha256": _sha256(records_path),
            }
        )
        self.processed_frame_uids.update(record.frame_uid for record in records)
        self._pending_records = self._pending_records[count:]
        self._pending_embeddings = self._pending_embeddings[count:]
        self._next_shard += 1
        self._write_manifest(is_complete=False)

    def _write_manifest(self, *, is_complete: bool) -> None:
        total_frames = sum(int(str(shard["count"])) for shard in self._shards)
        manifest = {
            "artifact_version": ARTIFACT_VERSION,
            "created_at": self._created_at,
            "updated_at": datetime.now(UTC).isoformat(),
            "complete": is_complete,
            "model": {
                "id": self.spec.model_id,
                "adapter": self.spec.adapter,
                "model_name": self.spec.model_name,
                "pretrained": self.spec.pretrained,
                "revision": self.spec.revision,
                "dimension": self.spec.dimension,
                "collection": self.spec.collection,
                "text_padding": self.spec.text_padding,
                "text_max_length": self.spec.text_max_length,
            },
            "total_frames": total_frames,
            "shards": self._shards,
        }
        temporary_path = self.manifest_path.with_suffix(".json.tmp")
        temporary_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary_path.replace(self.manifest_path)

    def finalize(self) -> Path:
        """Flush remaining data and atomically publish the artifact manifest."""
        if self._pending_records:
            self._flush(len(self._pending_records))
        self._write_manifest(is_complete=True)
        return self.manifest_path


def iter_artifact_shards(
    manifest_path: Path,
    *,
    verify_checksums: bool = True,
) -> Iterator[tuple[np.ndarray, list[dict[str, Any]]]]:
    """Load embedding shards after validating artifact version, shape and checksums."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if int(manifest.get("artifact_version", 0)) != ARTIFACT_VERSION:
        raise ValueError("unsupported embedding artifact version")
    dimension = int(manifest.get("model", {}).get("dimension", 0))
    if dimension < 1:
        raise ValueError("artifact manifest has an invalid model dimension")
    artifact_dir = manifest_path.parent
    shards = manifest.get("shards", [])
    if not isinstance(shards, list):
        raise ValueError("artifact manifest shards must be a list")
    declared_total = int(manifest.get("total_frames", 0))
    shard_total = sum(int(shard["count"]) for shard in shards)
    if declared_total != shard_total:
        raise ValueError(
            f"artifact total_frames {declared_total} does not match shard total {shard_total}"
        )
    for expected_index, shard in enumerate(shards):
        if int(shard.get("index", -1)) != expected_index:
            raise ValueError("artifact shard indices must be contiguous and ordered")
        embeddings_path = artifact_dir / str(shard["embeddings_file"])
        records_path = artifact_dir / str(shard["records_file"])
        if verify_checksums:
            if _sha256(embeddings_path) != shard["embeddings_sha256"]:
                raise ValueError(f"embedding checksum mismatch: {embeddings_path}")
            if _sha256(records_path) != shard["records_sha256"]:
                raise ValueError(f"record checksum mismatch: {records_path}")
        embeddings = np.load(embeddings_path, allow_pickle=False)
        records = list(iter_input_records(records_path))
        expected_shape = (int(shard["count"]), dimension)
        if embeddings.shape != expected_shape or len(records) != expected_shape[0]:
            raise ValueError(f"artifact shard shape mismatch: {embeddings_path}")
        if not np.isfinite(embeddings).all():
            raise ValueError(f"artifact shard contains non-finite embeddings: {embeddings_path}")
        yield np.asarray(embeddings, dtype=np.float32), records
