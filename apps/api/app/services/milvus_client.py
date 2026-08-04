import os
import threading
from collections.abc import Sequence
from typing import Any

from pymilvus import Collection, connections

MILVUS_URI = os.getenv("MILVUS_URI", "http://localhost:19530")
MILVUS_TOKEN = os.getenv("MILVUS_TOKEN", "")
COLLECTION_NAME = "data_frames"
SEARCH_EF = int(os.getenv("MILVUS_SEARCH_EF", "128"))
QUERY_LIMIT = 16384

Frame = dict[str, Any]

OUTPUT_FIELDS = [
    "video_id", "video_path", "youtube_url",
    "frame_index", "frame_idx", "frame_path",
    "shot_idx", "start_time", "end_time",
    "pts_time", "fps", "timestamp", "tags",
]


def _hit_to_frame(hit: Any, score_key: str = "vector_score") -> Frame:
    entity = hit.entity
    frame: Frame = {"id": str(hit.id)}
    for field in OUTPUT_FIELDS:
        frame[field] = entity.get(field)
    frame["tags"] = list(entity.get("tags") or [])
    frame[score_key] = float(hit.score)
    return frame


def _row_to_frame(row: dict[str, Any]) -> Frame:
    frame: Frame = {"id": str(row.get("id", ""))}
    for field in OUTPUT_FIELDS:
        frame[field] = row.get(field)
    frame["tags"] = list(row.get("tags") or [])
    return frame


class MilvusClient:
    def __init__(self) -> None:
        connections.connect(alias="default", uri=MILVUS_URI, token=MILVUS_TOKEN)
        self.col = Collection(COLLECTION_NAME)
        self.col.load()

    def search_batch(
        self,
        embeddings: Sequence[Sequence[float]],
        topk: int = 20,
        expr: str | None = None,
    ) -> list[list[Frame]]:
        """One RPC for many query vectors. Returns one frame list per vector,
        in the same order as `embeddings`."""
        if not embeddings:
            return []
        params = {"metric_type": "IP", "params": {"ef": max(SEARCH_EF, topk)}}
        results = self.col.search(
            data=list(embeddings),
            anns_field="embedding",
            param=params,
            limit=topk,
            expr=expr,
            output_fields=OUTPUT_FIELDS,
        )
        return [[_hit_to_frame(hit) for hit in per_query] for per_query in results]

    def search(
        self, embedding: Sequence[float], topk: int = 20, expr: str | None = None
    ) -> list[Frame]:
        batched = self.search_batch([embedding], topk=topk, expr=expr)
        return batched[0] if batched else []

    def query_frames(self, expr: str, limit: int = QUERY_LIMIT) -> list[Frame]:
        """Scalar fetch — no ANN involved. Used to list a video's frames, which
        a similarity search with a zero vector would do far more expensively."""
        rows = self.col.query(expr=expr, output_fields=OUTPUT_FIELDS, limit=limit)
        return [_row_to_frame(row) for row in rows]

    def get_frame_embedding(self, video_id: str, frame_index: int) -> list[float] | None:
        expr = f'video_id == "{video_id}" and frame_index == {frame_index}'
        results = self.col.query(expr=expr, output_fields=["embedding"], limit=1)
        if not results:
            return None
        embedding: list[float] = results[0]["embedding"]
        return embedding

    def is_connected(self) -> bool:
        try:
            from pymilvus import utility

            return bool(utility.has_collection(COLLECTION_NAME))
        except Exception:
            return False


_milvus_client: MilvusClient | None = None
_client_lock = threading.Lock()


def get_milvus_client() -> MilvusClient:
    global _milvus_client
    if _milvus_client is None:
        with _client_lock:
            if _milvus_client is None:
                _milvus_client = MilvusClient()
    return _milvus_client


def warmup() -> None:
    get_milvus_client()
