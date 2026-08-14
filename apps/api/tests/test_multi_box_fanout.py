"""Tests for temporal-search embedding and Milvus fan-out.

Milvus, post-filters, and the encoder are stubbed. These tests pin the RPC
shape and ensure every box's own raw-candidate Top-K remains authoritative.
"""

from threading import Lock

import numpy as np
import pytest

from app.services import hybrid_search as hs
from app.services.encoders import manager


def _hit(video_id: str, frame_index: int, timestamp: float, score: float) -> hs.Frame:
    return {
        "video_id": video_id,
        "frame_index": frame_index,
        "frame_idx": frame_index,
        "timestamp": timestamp,
        "vector_score": score,
        "youtube_url": "",
    }


class FakeMilvus:
    """Record batched and scalar ANN calls in a thread-safe list."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self._lock = Lock()

    def search_batch(self, embeddings, topk=20, expr=None):
        with self._lock:
            self.calls.append({"kind": "batch", "nq": len(embeddings), "topk": topk, "expr": expr})
        return [
            [_hit(f"V{query_index}", i, float(i), 1.0 - i / max(topk, 1)) for i in range(topk)]
            for query_index, _ in enumerate(embeddings)
        ]

    def search(self, embedding, topk=20, expr=None):
        with self._lock:
            call_index = len(self.calls)
            self.calls.append({"kind": "scalar", "nq": 1, "topk": topk, "expr": expr})
        return [_hit("V1", call_index + 1, float(call_index + 1), 0.9) for _ in range(topk)]

    def query_frame_keys(self, frame_keys, chunk_size=500):
        return [_hit(video_id, frame_index, float(frame_index), 0.0) for video_id, frame_index in frame_keys]


@pytest.fixture
def stub(monkeypatch):
    fake = FakeMilvus()
    embed_calls = {"text": 0, "image": 0}

    def fake_embed_text(texts):
        embed_calls["text"] += 1
        return np.array([[float(i)] * 4 for i, _ in enumerate(texts)], dtype=np.float32)

    def fake_embed_images(images):
        embed_calls["image"] += 1
        return np.array([[9.0] * 4 for _ in images], dtype=np.float32)

    monkeypatch.setattr(manager, "embed_text", fake_embed_text)
    monkeypatch.setattr(manager, "embed_images", fake_embed_images)
    monkeypatch.setattr(manager, "active_collection_name", lambda: "fake_collection")
    monkeypatch.setattr(hs, "enhance_queries", lambda queries: [query.upper() for query in queries])
    monkeypatch.setattr(hs, "get_milvus_client", lambda collection_name: fake)
    monkeypatch.setattr(hs, "filter_frames", lambda frames, *args, **kwargs: frames)
    monkeypatch.setattr(hs, "_filter_by_keywords", lambda frames, *args, **kwargs: frames)
    monkeypatch.setattr(hs, "matching_frame_keys", lambda *args, **kwargs: [("V1", 2), ("V2", 4)])
    monkeypatch.setattr(hs, "filter_frame_keys", lambda keys, *args, **kwargs: list(keys))
    return fake, embed_calls


# ── Embedding batching ──────────────────────────────────────────────────────
def test_all_text_boxes_share_one_forward_pass(stub):
    _, embed_calls = stub
    boxes = [{"text": "a"}, {"text": "b"}, {"text": "c"}]
    hs._box_vectors(boxes, enhance_default=False)
    assert embed_calls["text"] == 1


def test_enhance_respects_per_box_override(monkeypatch, stub):
    seen = {}

    def fake_enhance(queries):
        seen["queries"] = list(queries)
        return [query.upper() for query in queries]

    monkeypatch.setattr(hs, "enhance_queries", fake_enhance)
    boxes = [{"text": "a", "enhance": True}, {"text": "b", "enhance": False}, {"text": "c"}]
    hs._box_vectors(boxes, enhance_default=True)
    assert seen["queries"] == ["a", "c"]


def test_box_without_query_yields_no_vector(stub):
    vectors = hs._box_vectors([{"text": "a"}, {"text": "", "image": ""}], enhance_default=False)
    assert vectors[0] is not None
    assert vectors[1] is None


# ── Per-box Top-K bucket batching ───────────────────────────────────────────
def test_parallel_batches_four_box_topks_into_two_range_calls(stub):
    fake, _ = stub
    boxes = [
        {"text": "a", "topk": 150},
        {"text": "b", "topk": 300},
        {"text": "c", "topk": 700},
        {"text": "d", "topk": 900},
    ]
    vectors = [[float(i)] * 4 for i in range(4)]

    per_box = hs._parallel_retrieve(boxes, vectors)

    calls = sorted(fake.calls, key=lambda call: int(call["topk"]))
    assert calls == [
        {"kind": "batch", "nq": 2, "topk": 300, "expr": None},
        {"kind": "batch", "nq": 2, "topk": 900, "expr": None},
    ]
    assert [len(results) for results in per_box] == [150, 300, 700, 900]


def test_parallel_uses_at_most_three_bucket_calls(stub):
    fake, _ = stub
    boxes = [
        {"text": "a", "topk": 500},
        {"text": "b", "topk": 501},
        {"text": "c", "topk": 1501},
        {"text": "d", "topk": 5000},
    ]
    hs._parallel_retrieve(boxes, [[1.0] * 4 for _ in boxes])
    assert sorted(int(call["topk"]) for call in fake.calls) == [500, 501, 5000]
    assert len(fake.calls) == 3


def test_parallel_tags_do_not_split_milvus_batch(stub):
    fake, _ = stub
    boxes = [
        {"text": "a", "topk": 100, "tags": ["car"]},
        {"text": "b", "topk": 200, "tags": ["person"]},
    ]
    hs._parallel_retrieve(boxes, [[1.0] * 4, [2.0] * 4])
    assert len(fake.calls) == 1
    assert fake.calls[0]["expr"] is None


def test_filter_only_box_uses_scalar_metadata_query_not_ann(stub):
    fake, _ = stub
    results = hs._parallel_retrieve([{"tags": ["car"], "topk": 500}], [None])
    assert [(frame["video_id"], frame["frame_index"]) for frame in results[0]] == [
        ("V1", 2),
        ("V2", 4),
    ]
    assert all(frame["filter_only"] for frame in results[0])
    assert fake.calls == []


def test_keyword_only_preserves_es_order_and_exact_topk(monkeypatch, stub):
    fake, _ = stub
    monkeypatch.setattr(
        hs.es_client,
        "iter_keyword_frame_hits",
        lambda **kwargs: iter([("V2", 9, 5.0), ("V1", 3, 4.0), ("V1", 4, 3.0)]),
    )
    results = hs._parallel_retrieve(
        [{"ocr_keywords": ["Long về đích số 3"], "topk": 2}], [None]
    )[0]
    assert [(frame["video_id"], frame["frame_index"]) for frame in results] == [
        ("V2", 9),
        ("V1", 3),
    ]
    assert [frame["retrieval_rank"] for frame in results] == [0, 1]
    assert fake.calls == []


def test_filter_only_continues_after_missing_milvus_keys(monkeypatch, stub):
    _, _ = stub

    class MissingFirstMilvus(FakeMilvus):
        def query_frame_keys(self, frame_keys, chunk_size=500):
            return [
                _hit(video_id, frame_index, float(frame_index), 0.0)
                for video_id, frame_index in frame_keys
                if frame_index != 1
            ]

    fake = MissingFirstMilvus()
    monkeypatch.setattr(hs, "get_milvus_client", lambda _name: fake)
    monkeypatch.setattr(
        hs.es_client,
        "iter_keyword_frame_hits",
        lambda **kwargs: iter([("V1", 1, 5.0), ("V1", 2, 4.0), ("V1", 3, 3.0)]),
    )
    results = hs._filter_only_candidates({"asr_keywords": ["phrase"], "topk": 2})
    assert [frame["frame_index"] for frame in results] == [2, 3]


def test_combined_filter_keeps_es_order_after_polars_intersection(monkeypatch, stub):
    _, _ = stub
    monkeypatch.setattr(
        hs.es_client,
        "iter_keyword_frame_hits",
        lambda **kwargs: iter([("V1", 1, 5.0), ("V1", 2, 4.0), ("V1", 3, 3.0)]),
    )
    monkeypatch.setattr(
        hs,
        "filter_frame_keys",
        lambda keys, *args, **kwargs: [key for key in keys if key[1] != 2],
    )
    results = hs._filter_only_candidates({
        "ocr_keywords": ["phrase"],
        "tags": ["person"],
        "topk": 2,
    })
    assert [frame["frame_index"] for frame in results] == [1, 3]


def test_sequential_filter_only_restricts_before_topk(monkeypatch, stub):
    _, _ = stub
    seen: list[set[str] | None] = []

    def fake_filter_only(box, allowed_video_ids=None):
        seen.append(allowed_video_ids)
        return [_hit("V1", 3, 3.0, 0.0)]

    monkeypatch.setattr(hs, "_filter_only_candidates", fake_filter_only)
    boxes = [{"text": "first", "topk": 1}, {"tags": ["person"], "topk": 1}]
    hs._sequential_retrieve(boxes, [[1.0] * 4, None], window=90.0)
    assert seen == [{"V1"}]


def test_parallel_truncates_before_post_filters(monkeypatch, stub):
    _, _ = stub
    lengths_seen: list[int] = []

    def record_filter(frames, *args, **kwargs):
        lengths_seen.append(len(frames))
        return frames

    monkeypatch.setattr(hs, "filter_frames", record_filter)
    boxes = [{"text": "a", "topk": 10}, {"text": "b", "topk": 20}]
    hs._parallel_retrieve(boxes, [[1.0] * 4, [2.0] * 4])
    assert lengths_seen == [10, 20]


# ── Sequential retrieval ────────────────────────────────────────────────────
def test_sequential_uses_one_exact_topk_search_per_stage(stub):
    fake, _ = stub
    boxes = [
        {"text": "a", "topk": 150},
        {"text": "b", "topk": 300},
        {"text": "c", "topk": 700},
    ]

    hs._sequential_retrieve(boxes, [[1.0] * 4 for _ in boxes], window=90.0)

    assert [call["kind"] for call in fake.calls] == ["scalar", "scalar", "scalar"]
    assert [call["topk"] for call in fake.calls] == [150, 300, 700]
    assert fake.calls[0]["expr"] is None
    assert all('video_id in ["V1"]' == call["expr"] for call in fake.calls[1:])


def test_single_box_is_identical_in_parallel_and_sequential(stub):
    box = [{"text": "a", "topk": 3}]
    parallel = hs.multi_box_search(box, temporal_window=90.0, enhance=False, mode="parallel")
    sequential = hs.multi_box_search(box, temporal_window=90.0, enhance=False, mode="sequential")
    assert parallel["videos"] == sequential["videos"]
    assert parallel["total_valid_frames"] == sequential["total_valid_frames"]
