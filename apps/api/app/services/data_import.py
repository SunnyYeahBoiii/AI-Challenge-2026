"""Validated streaming readers for metadata and chunked embeddings."""

from __future__ import annotations

import io
import json
import re
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from itertools import zip_longest
from pathlib import Path, PurePosixPath
from typing import Any

import ijson
import numpy as np
import numpy.typing as npt

Embedding = npt.NDArray[np.float32]
_CHUNK_PATTERN = re.compile(r"(?:^|/)embeddings-(\d{5})\.npy$")
_MISSING = object()


class ImportDataError(Exception):
    """Raised when import inputs are incomplete or inconsistent."""


@dataclass(frozen=True)
class FrameImportRecord:
    """One aligned metadata and embedding row ready for both databases."""

    id: str
    video_id: str
    video_path: str
    youtube_url: str
    frame_index: int
    frame_idx: int
    frame_path: str
    shot_idx: int
    start_time: float
    end_time: float
    pts_time: float
    fps: float
    ocr_text: str
    asr_text: str
    embedding: Embedding

    def elasticsearch_values(self) -> dict[str, object]:
        """Return the fields stored in the Elasticsearch frame index."""
        return {
            "video_id": self.video_id,
            "video_path": self.video_path,
            "frame_id": self.frame_index,
            "frame_idx": self.frame_idx,
            "frame_path": self.frame_path,
            "ocr_text": self.ocr_text,
            "asr_text": self.asr_text,
            "timestamp": self.pts_time,
        }


def _embedding_members(archive: zipfile.ZipFile) -> list[str]:
    indexed: list[tuple[int, str]] = []
    for name in archive.namelist():
        match = _CHUNK_PATTERN.search(name)
        if match:
            indexed.append((int(match.group(1)), name))

    indexed.sort()
    if not indexed:
        raise ImportDataError("Embedding archive contains no embeddings-*.npy chunks")

    indices = [index for index, _ in indexed]
    if indices != list(range(len(indices))):
        raise ImportDataError("Embedding chunk numbers must be contiguous from 00000")
    return [name for _, name in indexed]


def iter_embeddings(archive_path: Path, embedding_dim: int) -> Iterator[Embedding]:
    """Yield validated float32 vectors from ordered ZIP chunks."""
    if not archive_path.is_file():
        raise ImportDataError(f"Embedding archive not found: {archive_path}")

    with zipfile.ZipFile(archive_path) as archive:
        for name in _embedding_members(archive):
            array = np.load(io.BytesIO(archive.read(name)), allow_pickle=False)
            if array.dtype != np.float32:
                raise ImportDataError(f"{name} must contain float32 vectors, got {array.dtype}")
            if array.ndim != 2 or array.shape[1] != embedding_dim:
                raise ImportDataError(
                    f"{name} must have shape (rows, {embedding_dim}), got {array.shape}"
                )

            norms = np.linalg.norm(array, axis=1)
            if not np.all(np.isfinite(array)) or not np.allclose(norms, 1.0, atol=1e-3):
                raise ImportDataError(f"{name} contains invalid or non-normalized vectors")
            yield from array


def iter_metadata(metadata_path: Path) -> Iterator[dict[str, Any]]:
    """Stream records from the top-level metadata JSON array."""
    if not metadata_path.is_file():
        raise ImportDataError(f"Metadata file not found: {metadata_path}")

    with metadata_path.open("rb") as metadata_file:
        yield from ijson.items(metadata_file, "item")


def _load_media_urls(media_info_dir: Path) -> dict[str, str]:
    if not media_info_dir.is_dir():
        raise ImportDataError(f"Media-info directory not found: {media_info_dir}")

    urls: dict[str, str] = {}
    for path in media_info_dir.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ImportDataError(f"Cannot read media info {path}: {error}") from error
        urls[path.stem] = str(payload.get("watch_url", ""))
    return urls


def _optional_int(value: Any, default: int, field: str, position: int) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as error:
        raise ImportDataError(f"Invalid {field} at row {position}: {value!r}") from error


def _optional_float(value: Any, default: float, field: str, position: int) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError) as error:
        raise ImportDataError(f"Invalid {field} at row {position}: {value!r}") from error


def _parse_record(
    raw: dict[str, Any],
    embedding: Embedding,
    position: int,
    keyframes_dir: Path,
    media_urls: dict[str, str],
) -> FrameImportRecord:
    file_path = PurePosixPath(str(raw.get("file_path", "")))
    if not file_path.parts or file_path.parts[0] != "keyframes" or len(file_path.parts) < 4:
        raise ImportDataError(f"Invalid keyframe path at row {position}: {file_path}")

    try:
        frame_index = int(file_path.stem)
    except ValueError as error:
        raise ImportDataError(f"Invalid frame filename at row {position}: {file_path.name}") from error

    video_id = file_path.parent.name
    expected_index = (raw.get("clip_embeddings") or {}).get("index")
    if _optional_int(expected_index, -1, "clip_embeddings.index", position) != position:
        raise ImportDataError(
            f"Metadata embedding index mismatch at row {position}: {expected_index}"
        )

    keyframe_path = keyframes_dir.joinpath(*file_path.parts[1:])
    if not keyframe_path.is_file():
        raise ImportDataError(f"Keyframe not found at row {position}: {keyframe_path}")
    if video_id not in media_urls:
        raise ImportDataError(f"Media info not found for {video_id}")

    keyframe_info = raw.get("keyframe_info") or {}
    if "timestamp" not in keyframe_info:
        raise ImportDataError(f"timestamp missing from keyframe_info at row {position}")

    return FrameImportRecord(
        id=f"{video_id}/{frame_index}",
        video_id=video_id,
        video_path=str(file_path.parent),
        youtube_url=media_urls[video_id],
        frame_index=frame_index,
        frame_idx=_optional_int(
            keyframe_info.get("frame_idx"), frame_index, "frame_idx", position
        ),
        frame_path=str(file_path),
        shot_idx=_optional_int(keyframe_info.get("shot_idx"), 0, "shot_idx", position),
        start_time=_optional_float(
            keyframe_info.get("start_time"), 0.0, "start_time", position
        ),
        end_time=_optional_float(keyframe_info.get("end_time"), 0.0, "end_time", position),
        pts_time=_optional_float(keyframe_info["timestamp"], 0.0, "timestamp", position),
        fps=_optional_float(keyframe_info.get("fps"), 0.0, "fps", position),
        # Both text fields are already normalized in this metadata export.
        ocr_text=str(raw.get("ocr_text", "") or ""),
        asr_text=str(raw.get("normalized_audio_text", "") or ""),
        embedding=embedding,
    )


def iter_import_records(
    metadata_path: Path,
    embeddings_path: Path,
    keyframes_dir: Path,
    media_info_dir: Path,
    embedding_dim: int,
) -> Iterator[FrameImportRecord]:
    """Yield strictly aligned metadata, media and embedding records."""
    media_urls = _load_media_urls(media_info_dir)
    pairs = zip_longest(
        iter_metadata(metadata_path),
        iter_embeddings(embeddings_path, embedding_dim),
        fillvalue=_MISSING,
    )

    for position, (raw, embedding) in enumerate(pairs):
        if raw is _MISSING or embedding is _MISSING:
            raise ImportDataError("Metadata and embeddings have different row counts")
        assert isinstance(raw, dict)
        assert isinstance(embedding, np.ndarray)
        yield _parse_record(raw, embedding, position, keyframes_dir, media_urls)
