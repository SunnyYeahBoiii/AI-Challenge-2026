import os
from pymilvus import Collection, connections

MILVUS_URI = os.getenv("MILVUS_URI", "http://localhost:19530")
COLLECTION_NAME = "keyframes"

class MilvusClient:
    def __init__(self):
        connections.connect(alias="default", uri=MILVUS_URI)
        self.col = Collection(COLLECTION_NAME)
        self.col.load()

    def search(self, embedding, topk=20, expr=None):
        params = {"metric_type": "IP", "params": {"ef": 128}}
        results = self.col.search(
            data=[embedding],
            anns_field="embedding",
            param=params,
            limit=topk,
            expr=expr,
            output_fields=["video_id", "frame_index", "shot_idx", "start_time", "end_time", "pts_time", "fps"],
        )
        frames = []
        for hit in results[0]:
            frames.append({
                "id": str(hit.id),
                "video_id": hit.entity.get("video_id"),
                "frame_index": hit.entity.get("frame_index"),
                "shot_idx": hit.entity.get("shot_idx"),
                "start_time": hit.entity.get("start_time"),
                "end_time": hit.entity.get("end_time"),
                "pts_time": hit.entity.get("pts_time"),
                "fps": hit.entity.get("fps"),
                "vector_score": float(hit.score),
            })
        return frames

    def is_connected(self):
        try:
            from pymilvus import utility
            return utility.has_collection(COLLECTION_NAME)
        except Exception:
            return False

_milvus_client = None

def get_milvus_client():
    global _milvus_client
    if _milvus_client is None:
        _milvus_client = MilvusClient()
    return _milvus_client
