from __future__ import annotations

import os
from collections.abc import Sequence
from typing import Any

from dotenv import load_dotenv
from pymilvus import (
    Collection,
    CollectionSchema,
    DataType,
    FieldSchema,
    connections,
    utility,
)

from app.services.frame_identity import build_frame_uid
from app.services.model_registry import ModelSpec, get_model_registry

load_dotenv()
MILVUS_URI = os.getenv("MILVUS_URI", "http://localhost:19530")
MILVUS_TOKEN = os.getenv("MILVUS_TOKEN", "")
TAG_ITEM_MAX_LEN = 64
TAGS_MAX_COUNT = 100
FRAME_UID_MAX_LEN = 256
VIDEO_ID_MAX_LEN = 128
VIDEO_PATH_MAX_LEN = 500
URL_MAX_LEN = 1000

FRAME_OUTPUT_FIELDS = [
    "id",
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
]
CANONICAL_COLLECTION_FIELDS = {
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
}


def _connect() -> None:
    kwargs: dict[str, object] = {"alias": "default", "uri": MILVUS_URI}
    if MILVUS_TOKEN:
        kwargs["token"] = MILVUS_TOKEN
    connections.connect(**kwargs)


def _escape_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _normalize_frame_metadata(frame: dict[str, Any]) -> dict[str, Any]:
    frame_index = int(frame.get("frame_index") or 0)
    video_id = str(frame.get("video_id") or "")
    frame["frame_index"] = frame_index
    frame["frame_idx"] = int(
        frame["frame_idx"] if frame.get("frame_idx") is not None else frame_index
    )
    frame["frame_uid"] = frame.get("frame_uid") or build_frame_uid(
        video_id, frame_index
    )
    frame["id"] = str(frame.get("id") or frame["frame_uid"])
    frame["tags"] = list(frame.get("tags") or [])
    for field in ("shot_idx",):
        frame[field] = int(frame.get(field) or 0)
    for field in ("start_time", "end_time", "pts_time", "fps", "timestamp"):
        frame[field] = float(frame.get(field) or 0.0)
    return frame


class MilvusCollectionClient:
    """Thin data-access wrapper for one model-specific Milvus collection."""

    def __init__(self, spec: ModelSpec) -> None:
        _connect()
        self.spec = spec
        self.collection = Collection(spec.collection)
        self.collection.load()
        self._field_names = {field.name for field in self.collection.schema.fields}
        self._output_fields = [
            field for field in FRAME_OUTPUT_FIELDS if field in self._field_names
        ]

    def search(
        self,
        embedding: Sequence[float],
        *,
        top_k: int = 20,
        expression: str | None = None,
    ) -> list[dict[str, Any]]:
        if len(embedding) != self.spec.dimension:
            raise ValueError(
                f"{self.spec.model_id} expects {self.spec.dimension} dimensions, "
                f"received {len(embedding)}"
            )
        results = self.collection.search(
            data=[list(embedding)],
            anns_field="embedding",
            param={"metric_type": "IP", "params": {"ef": 128}},
            limit=top_k,
            expr=expression,
            output_fields=self._output_fields,
        )
        frames: list[dict[str, Any]] = []
        for hit in results[0]:
            frame = {field: hit.entity.get(field) for field in self._output_fields}
            frame = _normalize_frame_metadata(frame)
            frame["id"] = str(hit.id)
            frame["vector_score"] = float(hit.score)
            frame["model_id"] = self.spec.model_id
            frames.append(frame)
        return frames

    def get_frame_embedding(self, video_id: str, frame_index: int) -> list[float] | None:
        escaped_video_id = _escape_string(video_id)
        expression = (
            f'video_id == "{escaped_video_id}" and frame_index == {int(frame_index)}'
        )
        results = self.collection.query(expr=expression, output_fields=["embedding"], limit=1)
        if not results:
            return None
        return list(results[0]["embedding"])

    def list_video_frames(
        self,
        video_id: str,
        *,
        limit: int | None = None,
        frame_index: int | None = None,
        frame_range: int = 5,
    ) -> list[dict[str, Any]]:
        if limit is not None and limit < 1:
            raise ValueError("limit must be positive")
        if frame_range < 0:
            raise ValueError("frame_range cannot be negative")
        escaped_video_id = _escape_string(video_id)
        expression = f'video_id == "{escaped_video_id}"'
        if frame_index is not None:
            lower_bound = max(0, int(frame_index) - frame_range)
            upper_bound = int(frame_index) + frame_range
            expression += (
                f" and frame_index >= {lower_bound} and frame_index <= {upper_bound}"
            )
        if frame_index is not None:
            window_limit = (frame_range * 2) + 1
            results = self.collection.query(
                expr=expression,
                output_fields=self._output_fields,
                limit=min(limit, window_limit) if limit is not None else window_limit,
            )
        else:
            iterator = self.collection.query_iterator(
                expr=expression,
                output_fields=self._output_fields,
                batch_size=1_000,
                limit=limit if limit is not None else -1,
            )
            results = []
            try:
                while batch := iterator.next():
                    results.extend(batch)
            finally:
                iterator.close()
        frames: list[dict[str, Any]] = []
        for raw_frame in results:
            frames.append(_normalize_frame_metadata(dict(raw_frame)))
        return frames

    def is_connected(self) -> bool:
        return bool(utility.has_collection(self.spec.collection))


class MilvusVectorBackend:
    """Resolve the correct Milvus collection for each ensemble model."""

    def search(
        self,
        spec: ModelSpec,
        embedding: Sequence[float],
        top_k: int,
        expression: str | None = None,
    ) -> list[dict[str, Any]]:
        return get_milvus_client(spec).search(
            embedding,
            top_k=top_k,
            expression=expression,
        )


def ensure_model_collection(
    spec: ModelSpec,
    *,
    recreate: bool = False,
    require_canonical_schema: bool = False,
) -> Collection:
    """Create or validate a model-specific collection with canonical Frame identity."""
    _connect()
    if utility.has_collection(spec.collection):
        if recreate:
            utility.drop_collection(spec.collection)
        else:
            collection = Collection(spec.collection)
            fields_by_name = {
                field.name: field for field in collection.schema.fields
            }
            embedding_field = fields_by_name.get("embedding")
            if embedding_field is None:
                raise ValueError(
                    f"collection {spec.collection} has no embedding field"
                )
            existing_dimension = int(embedding_field.params["dim"])
            if existing_dimension != spec.dimension:
                raise ValueError(
                    f"collection {spec.collection} dimension {existing_dimension} does not "
                    f"match model {spec.dimension}"
                )
            if require_canonical_schema:
                missing_fields = CANONICAL_COLLECTION_FIELDS - fields_by_name.keys()
                frame_uid_field = fields_by_name.get("frame_uid")
                if missing_fields or not bool(
                    getattr(frame_uid_field, "is_primary", False)
                ):
                    missing = ", ".join(sorted(missing_fields))
                    details = f"missing fields: {missing}" if missing else (
                        "frame_uid is not the primary key"
                    )
                    raise ValueError(
                        f"collection {spec.collection} does not use the canonical "
                        f"Frame schema ({details}); load into a new collection or rerun "
                        "with --recreate after backing up data"
                    )
            return collection

    fields = [
        FieldSchema(
            name="frame_uid",
            dtype=DataType.VARCHAR,
            max_length=FRAME_UID_MAX_LEN,
            is_primary=True,
        ),
        FieldSchema(name="video_id", dtype=DataType.VARCHAR, max_length=VIDEO_ID_MAX_LEN),
        FieldSchema(name="video_path", dtype=DataType.VARCHAR, max_length=VIDEO_PATH_MAX_LEN),
        FieldSchema(name="youtube_url", dtype=DataType.VARCHAR, max_length=URL_MAX_LEN),
        FieldSchema(name="frame_index", dtype=DataType.INT64),
        FieldSchema(name="frame_idx", dtype=DataType.INT64),
        FieldSchema(name="frame_path", dtype=DataType.VARCHAR, max_length=URL_MAX_LEN),
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
        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=spec.dimension),
    ]
    schema = CollectionSchema(
        fields,
        description=f"Frame embeddings for {spec.model_id}",
        enable_dynamic_field=False,
    )
    collection = Collection(spec.collection, schema)
    collection.create_index(
        field_name="embedding",
        index_params={"metric_type": "IP", "index_type": "AUTOINDEX", "params": {}},
    )
    return collection


_clients: dict[str, MilvusCollectionClient] = {}
_vector_backend: MilvusVectorBackend | None = None


def get_milvus_client(spec: ModelSpec | None = None) -> MilvusCollectionClient:
    if spec is None:
        enabled = get_model_registry().enabled_specs()
        if not enabled:
            raise RuntimeError("no embedding models are enabled")
        spec = enabled[0]
    if spec.model_id not in _clients:
        _clients[spec.model_id] = MilvusCollectionClient(spec)
    return _clients[spec.model_id]


def get_vector_backend() -> MilvusVectorBackend:
    global _vector_backend
    if _vector_backend is None:
        _vector_backend = MilvusVectorBackend()
    return _vector_backend


def reset_milvus_clients() -> None:
    """Clear cached collection wrappers after configuration changes."""
    global _vector_backend
    _clients.clear()
    _vector_backend = None
