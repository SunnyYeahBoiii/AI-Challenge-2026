"""Tests for the multi-box fan-out: batching, RPC count and two-stage recall.

Milvus, ES and CLIP are all stubbed; what is under test is how many calls the
pipeline makes and what it passes to them.
"""

import numpy as np
import pytest

from app.services import hybrid_search as hs


class FakeMilvus:
    """Records every search so tests can assert on RPC count and batch size."""

    def __init__(self, response_by_call=None, query_rows=None):
        self.calls = []
        self.queries = []
        self.response_by_call = response_by_call or []
        self.query_rows = query_rows or []

    def search_batch(self, embeddings, topk=20, expr=None):
        self.calls.append({"nq": len(embeddings), "topk": topk, "expr": expr})
        if self.response_by_call:
            index = min(len(self.calls) - 1, len(self.response_by_call) - 1)
            return self.response_by_call[index](embeddings, expr)
        return [[] for _ in embeddings]

    def query_frames(self, expr, limit=100):
        self.queries.append({"expr": expr, "limit": limit})
        return [dict(row) for row in self.query_rows]


@pytest.fixture
def stub(monkeypatch):
    """Replace CLIP and Milvus; return the fake so tests can inspect it."""
    fake = FakeMilvus()
    embed_calls = {"text": 0, "image": 0}

    def fake_embed_text(texts):
        embed_calls["text"] += 1
        return np.array([[float(i)] * 4 for i, _ in enumerate(texts)], dtype=np.float32)

    def fake_embed_images(images):
        embed_calls["image"] += 1
        return np.array([[9.0] * 4 for _ in images], dtype=np.float32)

    monkeypatch.setattr(hs, "embed_text", fake_embed_text)
    monkeypatch.setattr(hs, "embed_images", fake_embed_images)
    monkeypatch.setattr(hs, "enhance_queries", lambda qs: [q.upper() for q in qs])
    monkeypatch.setattr(hs, "get_milvus_client", lambda: fake)
    monkeypatch.setattr(hs, "filter_frames", lambda frames, *args, **kwargs: frames)
    monkeypatch.setattr(hs, "_filter_by_keywords", lambda frames, *a, **k: frames)
    return fake, embed_calls


def _vec(values):
    return [list(v) for v in values]


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
        return [q.upper() for q in queries]

    monkeypatch.setattr(hs, "enhance_queries", fake_enhance)
    boxes = [{"text": "a", "enhance": True}, {"text": "b", "enhance": False}, {"text": "c"}]
    hs._box_vectors(boxes, enhance_default=True)
    assert seen["queries"] == ["a", "c"]


def test_box_without_query_yields_no_vector(stub):
    vectors = hs._box_vectors([{"text": "a"}, {"text": "", "image": ""}], enhance_default=False)
    assert vectors[0] is not None
    assert vectors[1] is None


# ── Milvus RPC batching ─────────────────────────────────────────────────────
def test_boxes_without_tags_share_one_rpc(stub):
    fake, _ = stub
    boxes = [{"text": "a"}, {"text": "b"}, {"text": "c"}]
    vectors = _vec([[1] * 4, [2] * 4, [3] * 4])
    hs._grouped_search(boxes, vectors, topk=50)

    assert len(fake.calls) == 1
    assert fake.calls[0]["nq"] == 3
    assert fake.calls[0]["expr"] is None


def test_boxes_with_identical_tags_share_one_rpc(stub):
    fake, _ = stub
    boxes = [{"text": "a", "tags": ["car"]}, {"text": "b", "tags": ["car"]}]
    hs._grouped_search(boxes, _vec([[1] * 4, [2] * 4]), topk=50)

    assert len(fake.calls) == 1
    assert fake.calls[0]["expr"] is None


def test_boxes_with_different_tags_still_share_one_rpc(stub):
    """Tags are post-filtered locally and never split a Milvus batch."""
    fake, _ = stub
    boxes = [{"text": "a", "tags": ["car"]}, {"text": "b", "tags": ["dog"]}]
    hs._grouped_search(boxes, _vec([[1] * 4, [2] * 4]), topk=50)

    assert len(fake.calls) == 1
    assert fake.calls[0]["nq"] == 2
    assert fake.calls[0]["expr"] is None


def test_extra_expr_is_sent_without_tags(stub):
    fake, _ = stub
    boxes = [{"text": "a", "tags": ["car"]}]
    hs._grouped_search(boxes, _vec([[1] * 4]), topk=50, extra_expr='video_id in ["V1"]')

    expr = fake.calls[0]["expr"]
    assert expr == 'video_id in ["V1"]'


# ── Filter-only boxes ───────────────────────────────────────────────────────
def test_tags_only_box_does_not_query_milvus(stub):
    """A box with tags but no text is a pure filter — no ANN, no wasted vector."""
    fake, _ = stub
    per_box = hs._grouped_search([{"tags": ["car"]}], [None], topk=50)

    assert fake.calls == []
    assert fake.queries == []
    assert per_box == [[]]


def test_box_with_neither_query_nor_filter_hits_nothing(stub):
    fake, _ = stub
    per_box = hs._grouped_search([{}], [None], topk=50)

    assert fake.calls == []
    assert fake.queries == []
    assert per_box == [[]]


def test_vector_and_tags_only_boxes_do_not_trigger_scalar_queries(stub):
    fake, _ = stub
    boxes = [{"text": "a"}, {"tags": ["car"]}]
    per_box = hs._grouped_search(boxes, [[1.0] * 4, None], topk=50)

    assert len(fake.calls) == 1 and fake.calls[0]["nq"] == 1
    assert fake.queries == []
    assert per_box[1] == []


# ── Two-stage recall ────────────────────────────────────────────────────────
def _hit(video_id, frame_index, pts_time, score):
    return {
        "video_id": video_id,
        "frame_index": frame_index,
        "pts_time": pts_time,
        "vector_score": score,
        "youtube_url": "",
    }


def test_two_stage_narrows_to_shared_videos(monkeypatch):
    """Stage 2 must re-search inside the videos both boxes touched."""
    stage1 = [
        [_hit("V1", 1, 10.0, 0.9), _hit("V2", 1, 10.0, 0.5)],
        [_hit("V1", 5, 20.0, 0.4), _hit("V3", 1, 10.0, 0.8)],
    ]
    stage2 = [
        [_hit("V1", 1, 10.0, 0.9), _hit("V1", 2, 12.0, 0.7)],
        [_hit("V1", 5, 20.0, 0.4), _hit("V1", 6, 22.0, 0.6)],
    ]
    calls = []

    class TwoStageMilvus:
        def search_batch(self, embeddings, topk=20, expr=None):
            calls.append(expr)
            return stage1 if len(calls) == 1 else stage2

    monkeypatch.setattr(
        hs, "embed_text", lambda texts: np.array([[1.0] * 4 for _ in texts], dtype=np.float32)
    )
    monkeypatch.setattr(hs, "enhance_queries", lambda qs: list(qs))
    monkeypatch.setattr(hs, "get_milvus_client", lambda: TwoStageMilvus())
    monkeypatch.setattr(hs, "filter_frames", lambda frames, *args, **kwargs: frames)
    monkeypatch.setattr(hs, "_filter_by_keywords", lambda frames, *a, **k: frames)

    boxes = [{"text": "a"}, {"text": "b"}]
    per_box, _ = hs._retrieve_boxes(boxes, topk=20, enhance=False, two_stage=True)

    assert len(calls) == 2, "expected exactly one stage-1 and one stage-2 RPC"
    assert calls[0] is None
    assert "video_id in [" in calls[1]
    assert per_box[0][0]["video_id"] == "V1"


def test_parallel_mode_uses_a_single_rpc(monkeypatch, stub):
    fake, _ = stub
    boxes = [{"text": "a"}, {"text": "b"}, {"text": "c"}]
    hs.multi_box_search(boxes, topk=20, enhance=False, mode="parallel")
    assert len(fake.calls) == 1
