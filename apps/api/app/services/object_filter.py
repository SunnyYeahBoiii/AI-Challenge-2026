"""Post-filter Milvus frame candidates against RF-DETR object detections."""

from __future__ import annotations

import threading
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import polars as pl

from app.config import Config


Frame = dict[str, Any]
FrameKey = tuple[str, int]

REQUIRED_SCHEMA = pl.Schema(
    {
        "frame_id": pl.String,
        "class_id": pl.Int32,
        "class_name": pl.String,
        "count": pl.Int32,
    }
)


class ObjectFilterError(Exception):
    """Raised when the object-detection dataset cannot safely filter a search."""


_lazy_db: pl.LazyFrame | None = None
_lazy_db_path: Path | None = None
_lazy_db_lock = threading.Lock()


def _normalise_tags(tags: Sequence[str] | None) -> list[str]:
    """Return unique, case-insensitive COCO class names without changing separators."""
    return list(dict.fromkeys(tag.strip().casefold() for tag in tags or [] if tag.strip()))


def _frame_id(frame: Frame) -> str:
    """Build the Parquet key from a Milvus frame result."""
    return f"{frame['video_id']}/{int(frame['frame_index'])}"


def _validate_schema(schema: pl.Schema, path: Path) -> None:
    """Ensure the merged Parquet has the stable object-filter schema."""
    if schema != REQUIRED_SCHEMA:
        raise ObjectFilterError(
            f"Invalid object detections schema at {path}; expected {REQUIRED_SCHEMA}, got {schema}"
        )


def _get_lazy_db(path: Path | None = None) -> pl.LazyFrame:
    """Return the cached, schema-validated Parquet scan for object detections."""
    global _lazy_db, _lazy_db_path

    detections_path = path or Path(Config.OBJECT_DETECTIONS_PATH)
    if _lazy_db is not None and _lazy_db_path == detections_path:
        return _lazy_db

    with _lazy_db_lock:
        if _lazy_db is not None and _lazy_db_path == detections_path:
            return _lazy_db
        if not detections_path.is_file():
            raise ObjectFilterError(f"Object detections file not found: {detections_path}")
        try:
            lazy_db = pl.scan_parquet(detections_path)
            _validate_schema(lazy_db.collect_schema(), detections_path)
        except (OSError, pl.exceptions.PolarsError) as error:
            raise ObjectFilterError(f"Cannot read object detections at {detections_path}: {error}") from error
        _lazy_db = lazy_db
        _lazy_db_path = detections_path
        return lazy_db


def _matching_frame_ids(
    lazy_db: pl.LazyFrame, candidate_ids: list[str], tags: list[str], mode: str
) -> set[str]:
    """Return candidate frame IDs that satisfy the requested object classes."""
    candidates = pl.DataFrame({"frame_id": candidate_ids}, schema={"frame_id": pl.String}).lazy()
    matches = (
        lazy_db.join(candidates, on="frame_id", how="semi")
        .filter(pl.col("class_name").str.to_lowercase().is_in(tags))
        .select("frame_id", "class_name")
    )
    if mode == "or":
        result = matches.select("frame_id").unique().collect()
    else:
        result = (
            matches.group_by("frame_id")
            .agg(pl.col("class_name").str.to_lowercase().n_unique().alias("matched_tags"))
            .filter(pl.col("matched_tags") == len(tags))
            .select("frame_id")
            .collect()
        )
    return set(result.get_column("frame_id").to_list())


def filter_frames(
    frames: list[Frame], tags: Sequence[str] | None, mode: str = "and"
) -> list[Frame]:
    """Keep ranked Milvus frames whose detected COCO objects match ``tags``.

    The returned objects are the original Milvus result dictionaries, so their
    public response shape and vector ranking remain unchanged.
    """
    normalised_tags = _normalise_tags(tags)
    if not frames or not normalised_tags:
        return frames
    if mode not in {"and", "or"}:
        raise ObjectFilterError(f"Unsupported tag match mode: {mode}")

    candidate_ids = [_frame_id(frame) for frame in frames]
    matched_ids = _matching_frame_ids(_get_lazy_db(), candidate_ids, normalised_tags, mode)
    return [frame for frame in frames if _frame_id(frame) in matched_ids]


def _key_id(key: FrameKey) -> str:
    return f"{key[0]}/{int(key[1])}"


def filter_frame_keys(
    frame_keys: Sequence[FrameKey], tags: Sequence[str] | None, mode: str = "and"
) -> list[FrameKey]:
    """Filter keys while preserving their input (for example ES relevance) order."""
    normalised_tags = _normalise_tags(tags)
    if not frame_keys or not normalised_tags:
        return list(frame_keys)
    if mode not in {"and", "or"}:
        raise ObjectFilterError(f"Unsupported tag match mode: {mode}")
    candidate_ids = [_key_id(key) for key in frame_keys]
    matched = _matching_frame_ids(_get_lazy_db(), candidate_ids, normalised_tags, mode)
    return [key for key in frame_keys if _key_id(key) in matched]


def matching_frame_keys(
    tags: Sequence[str] | None,
    mode: str = "and",
    allowed_video_ids: set[str] | None = None,
    video_prefixes: Sequence[str] | None = None,
) -> list[FrameKey]:
    """Return every matching detection key in deterministic video/frame order."""
    normalised_tags = _normalise_tags(tags)
    if not normalised_tags:
        return []
    if mode not in {"and", "or"}:
        raise ObjectFilterError(f"Unsupported tag match mode: {mode}")
    lazy_db = _get_lazy_db()
    matches = (
        lazy_db.filter(pl.col("class_name").str.to_lowercase().is_in(normalised_tags))
        .select("frame_id", "class_name")
    )
    prefixes = sorted(set(video_prefixes or []))
    if prefixes:
        prefix_match = pl.col("frame_id").str.starts_with(prefixes[0])
        for prefix in prefixes[1:]:
            prefix_match = prefix_match | pl.col("frame_id").str.starts_with(prefix)
        matches = matches.filter(prefix_match)
    if mode == "or":
        rows = matches.select("frame_id").unique().collect()
    else:
        rows = (
            matches.group_by("frame_id")
            .agg(pl.col("class_name").str.to_lowercase().n_unique().alias("matched_tags"))
            .filter(pl.col("matched_tags") == len(normalised_tags))
            .select("frame_id")
            .collect()
        )
    keys: list[FrameKey] = []
    for frame_id in rows.get_column("frame_id").to_list():
        video_id, index = str(frame_id).rsplit("/", 1)
        if allowed_video_ids is None or video_id in allowed_video_ids:
            keys.append((video_id, int(index)))
    return sorted(set(keys), key=lambda key: (key[0], key[1]))
