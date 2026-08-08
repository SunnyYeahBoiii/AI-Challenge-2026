import os
import threading
from collections.abc import Sequence
from typing import Any

from pymilvus import Collection, connections, utility

MILVUS_URI = os.getenv("MILVUS_URI", "http://localhost:19530")
MILVUS_TOKEN = os.getenv("MILVUS_TOKEN", "")
SEARCH_EF = int(os.getenv("MILVUS_SEARCH_EF", "128"))
# Hard ceiling enforced by Milvus ANN search (limit / HNSW ef).
MILVUS_MAX_TOPK = 16384
QUERY_LIMIT = MILVUS_MAX_TOPK


def clamp_milvus_topk(topk: int) -> int:
    """Clamp a requested ANN topk into Milvus's valid [1, MILVUS_MAX_TOPK] range."""
    return max(1, min(int(topk), MILVUS_MAX_TOPK))

Frame = dict[str, Any]

OUTPUT_FIELDS = [
    "video_id", "video_path", "youtube_url",
    "frame_index", "frame_idx", "frame_path",
    "shot_idx", "start_time", "end_time",
    "pts_time", "fps", "timestamp", "tags",
]


def _to_native(v: Any) -> Any:
    return v.item() if hasattr(v, "item") else v


def _hit_to_frame(hit: Any, score_key: str = "vector_score") -> Frame:
    entity = hit.entity
    frame: Frame = {"id": str(hit.id)}
    for field in OUTPUT_FIELDS:
        frame[field] = _to_native(entity.get(field))
    frame["tags"] = list(entity.get("tags") or [])
    frame[score_key] = float(hit.score)
    return frame


def _row_to_frame(row: dict[str, Any]) -> Frame:
    frame: Frame = {"id": str(row.get("id", ""))}
    for field in OUTPUT_FIELDS:
        frame[field] = _to_native(row.get(field))
    frame["tags"] = list(row.get("tags") or [])
    return frame


_connected = False
_connect_lock = threading.Lock()


def _ensure_connected() -> None:
    global _connected
    if not _connected:
        with _connect_lock:
            if not _connected:
                connections.connect(alias="default", uri=MILVUS_URI, token=MILVUS_TOKEN)
                _connected = True


def ping() -> bool:
    """Check Milvus server reachability, independent of any specific collection
    (e.g. no encoder model may be active yet)."""
    try:
        _ensure_connected()
        utility.list_collections()
        return True
    except Exception:
        return False


class MilvusClient:
    def __init__(self, collection_name: str) -> None:
        _ensure_connected()
        self.collection_name = collection_name
        self.col = Collection(collection_name)
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
        limit = clamp_milvus_topk(topk)
        params = {"metric_type": "IP", "params": {"ef": max(SEARCH_EF, limit)}}
        results = self.col.search(
            data=list(embeddings),
            anns_field="embedding",
            param=params,
            limit=limit,
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
            return bool(utility.has_collection(self.collection_name))
        except Exception:
            return False


_clients: dict[str, MilvusClient] = {}
_clients_lock = threading.Lock()


def get_milvus_client(collection_name: str) -> MilvusClient:
    client = _clients.get(collection_name)
    if client is None:
        with _clients_lock:
            client = _clients.get(collection_name)
            if client is None:
                client = MilvusClient(collection_name)
                _clients[collection_name] = client
    return client
