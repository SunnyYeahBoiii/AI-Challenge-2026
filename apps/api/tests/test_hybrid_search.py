"""Unit tests for the pure ranking/merging logic of hybrid_search.

Nothing here touches Milvus, Elasticsearch or CLIP.
"""

import pytest

from app.services import hybrid_search as hs


def frame(video_id, frame_index, pts_time=0.0, score=0.0):
    return {
        "video_id": video_id,
        "frame_index": frame_index,
        "pts_time": pts_time,
        "vector_score": score,
        "youtube_url": "",
    }


# ── Tag expressions ─────────────────────────────────────────────────────────
# ── RRF ─────────────────────────────────────────────────────────────────────
def test_rrf_rewards_frames_matched_by_several_boxes():
    box1 = [frame("V1", 1, score=0.9), frame("V1", 2, score=0.8)]
    box2 = [frame("V2", 9, score=0.99), frame("V1", 1, score=0.30)]

    results = hs.merge_rrf([box1, box2], topk=10)
    top = results[0]

    # V1/1 is rank 1 + rank 2; V2/9 is rank 1 only, despite a far higher raw score.
    assert (top["video_id"], top["frame_index"]) == ("V1", 1)


def test_rrf_is_insensitive_to_score_scale():
    """A box whose raw scores are uniformly higher must not dominate."""
    strong = [frame("A", i, score=0.9 - i * 0.01) for i in range(3)]
    weak = [frame("B", i, score=0.2 - i * 0.01) for i in range(3)]

    results = hs.merge_rrf([strong, weak], topk=10)
    order = [(f["video_id"], f["frame_index"]) for f in results[:2]]

    assert set(order) == {("A", 0), ("B", 0)}


def test_rrf_scores_are_normalised():
    box = [frame("A", 0, score=0.5)]
    results = hs.merge_rrf([box, box.copy()], topk=10)
    assert 0.0 < results[0]["score"] <= 1.0


def test_rrf_single_box_passes_through():
    box = [frame("A", 1, score=0.4), frame("A", 2, score=0.7)]
    results = hs.merge_rrf([box, []], topk=10)
    assert [f["frame_index"] for f in results] == [2, 1]


# ── Temporal chains ─────────────────────────────────────────────────────────
def test_temporal_requires_every_box():
    box1 = [frame("V1", 1, pts_time=10.0, score=0.9)]
    box2 = [frame("V2", 1, pts_time=12.0, score=0.9)]
    assert hs.merge_temporal([box1, box2], window=60.0, topk=10) == []


def test_temporal_enforces_forward_order():
    """Box 2 matching a shot that happens *before* box 1 is not a sequence."""
    box1 = [frame("V1", 5, pts_time=50.0, score=0.9)]
    box2 = [frame("V1", 1, pts_time=10.0, score=0.9)]
    assert hs.merge_temporal([box1, box2], window=120.0, topk=10) == []


def test_temporal_enforces_window():
    box1 = [frame("V1", 1, pts_time=10.0, score=0.9)]
    box2 = [frame("V1", 9, pts_time=500.0, score=0.9)]
    assert hs.merge_temporal([box1, box2], window=60.0, topk=10) == []
    assert hs.merge_temporal([box1, box2], window=600.0, topk=10) != []


def test_temporal_returns_ordered_chain():
    box1 = [frame("V1", 1, pts_time=12.4, score=0.8)]
    box2 = [frame("V1", 2, pts_time=15.1, score=0.6), frame("V1", 7, pts_time=99.0, score=0.9)]
    box3 = [frame("V1", 3, pts_time=41.0, score=0.7)]

    results = hs.merge_temporal([box1, box2, box3], window=120.0, topk=10)

    assert [f["frame_index"] for f in results] == [1, 2, 3]
    assert [f["sequence_idx"] for f in results] == [0, 1, 2]
    assert len({f["sequence_id"] for f in results}) == 1
    # frame 7 at t=99 would break the chain to box 3 at t=41
    assert 7 not in [f["frame_index"] for f in results]


def test_temporal_score_is_mean_of_chain():
    box1 = [frame("V1", 1, pts_time=1.0, score=0.6)]
    box2 = [frame("V1", 2, pts_time=2.0, score=0.4)]
    results = hs.merge_temporal([box1, box2], window=10.0, topk=10)
    assert results[0]["score"] == pytest.approx(0.5)


def test_temporal_prefers_higher_scoring_chain():
    box1 = [frame("V1", 1, pts_time=1.0, score=0.1), frame("V1", 2, pts_time=2.0, score=0.9)]
    box2 = [frame("V1", 3, pts_time=3.0, score=0.5)]
    results = hs.merge_temporal([box1, box2], window=10.0, topk=10)
    assert [f["frame_index"] for f in results] == [2, 3]


def test_best_chain_handles_long_pools():
    """The deque keeps this linear; a quadratic scan would crawl here."""
    box1 = [frame("V1", i, pts_time=float(i), score=i / 1000) for i in range(1000)]
    box2 = [frame("V1", 1000 + i, pts_time=1000.0 + i, score=0.5) for i in range(1000)]
    chain = hs._best_chain([box1, box2], window=2000.0)
    assert chain is not None
    assert len(chain[2]) == 2


def test_temporal_sorts_sequences_by_score():
    boxes = [
        [frame("A", 1, pts_time=1.0, score=0.2), frame("B", 1, pts_time=1.0, score=0.9)],
        [frame("A", 2, pts_time=2.0, score=0.2), frame("B", 2, pts_time=2.0, score=0.9)],
    ]
    results = hs.merge_temporal(boxes, window=10.0, topk=10)
    assert results[0]["video_id"] == "B"


# ── Enrichment ──────────────────────────────────────────────────────────────
def test_enrich_dedupes_by_frame_key():
    frames = [frame("V1", 1), frame("V1", 1), frame("V1", 2)]
    enriched = hs._enrich_frames(frames)
    assert len(enriched) == 2


def test_enrich_sets_thumbnail_url():
    enriched = hs._enrich_frames([frame("V1", 7)])
    assert enriched[0]["thumbnail_url"] == "/api/keyframes/V1/7"


def test_enrich_omits_bulky_video_fields(monkeypatch):
    monkeypatch.setattr(
        hs.video_meta,
        "get",
        lambda _vid: {
            "title": "T",
            "description": "very long description " * 50,
            "keywords": ["a", "b", "c"],
            "author": "me",
            "publish_date": "01/01/2024",
            "watch_url": "https://example.com",
        },
    )
    enriched = hs._enrich_frames([frame("V1", 1)])
    assert enriched[0]["title"] == "T"
    assert enriched[0]["description"] == ""
    assert enriched[0]["keywords"] == []
    assert enriched[0]["author"] == "me"

