"""Unit tests for the pure ranking/merging logic of hybrid_search.

Nothing here touches Milvus, Elasticsearch or CLIP.
"""

import pytest

from app.services import hybrid_search as hs
from app.services.hybrid_search import retrieval


def frame(video_id, frame_index, timestamp=0.0, score=0.0):
    return {
        "video_id": video_id,
        "frame_index": frame_index,
        "frame_idx": frame_index,
        "timestamp": timestamp,
        "vector_score": score,
        "youtube_url": "",
    }


# ── Tag expressions ─────────────────────────────────────────────────────────
def test_apply_box_keywords_forwards_ocr_and_asr_mode(monkeypatch):
    """box dict's ocr_match_mode/asr_match_mode must reach es_client as-is."""
    captured = {}

    def fake_score(frame_keys, keywords=None, mode="and", source="all", **kwargs):
        captured.update(kwargs)
        return dict.fromkeys(frame_keys, 0.0)

    monkeypatch.setattr(hs.es_client, "score_frames_by_keywords", fake_score)

    box = {
        "ocr_keywords": ["a"],
        "asr_keywords": ["b"],
        "ocr_match_mode": "or",
        "asr_match_mode": "and",
    }
    frames = [frame("V1", 1)]
    hs._apply_box_keywords([box], [frames])

    assert captured["ocr_mode"] == "or"
    assert captured["asr_mode"] == "and"


# ── Temporal response ───────────────────────────────────────────────────────
def test_temporal_requires_every_box():
    box1 = [frame("V1", 1, timestamp=10.0, score=0.9)]
    box2 = [frame("V2", 1, timestamp=12.0, score=0.9)]
    response = hs.build_temporal_response([box1, box2], window=60.0, mode="parallel")
    assert response["videos"] == []


def test_temporal_enforces_forward_order():
    """Box 2 matching a shot that happens *before* box 1 is not a sequence."""
    box1 = [frame("V1", 5, timestamp=50.0, score=0.9)]
    box2 = [frame("V1", 1, timestamp=10.0, score=0.9)]
    response = hs.build_temporal_response([box1, box2], window=120.0, mode="parallel")
    assert response["videos"] == []


def test_temporal_enforces_window():
    box1 = [frame("V1", 1, timestamp=10.0, score=0.9)]
    box2 = [frame("V1", 9, timestamp=500.0, score=0.9)]
    assert hs.build_temporal_response([box1, box2], 60.0, "parallel")["videos"] == []
    assert hs.build_temporal_response([box1, box2], 600.0, "parallel")["videos"]


def test_temporal_keeps_all_and_only_nodes_on_complete_paths():
    boxes = [
        [frame("V1", i, timestamp=float(i), score=0.5) for i in (1, 3, 7, 9)],
        [frame("V1", i, timestamp=float(i), score=0.5) for i in (2, 4, 5, 15)],
        [frame("V1", i, timestamp=float(i), score=0.5) for i in (6, 8, 11, 12)],
    ]

    video = hs.build_temporal_response(boxes, window=6.0, mode="parallel")["videos"][0]

    matches = {
        match["query_index"]: []
        for result in video["valid_frames"]
        for match in result["matches"]
    }
    for result in video["valid_frames"]:
        for match in result["matches"]:
            matches[match["query_index"]].append(result["frame_index"])
    assert matches == {0: [1, 3], 1: [2, 4, 5], 2: [6, 8, 11]}


def test_temporal_returns_best_sequence_in_query_order():
    box1 = [frame("V1", 1, timestamp=12.4, score=0.8)]
    box2 = [frame("V1", 2, timestamp=15.1, score=0.6), frame("V1", 7, timestamp=99.0, score=0.9)]
    box3 = [frame("V1", 3, timestamp=41.0, score=0.7)]

    response = hs.build_temporal_response([box1, box2, box3], window=120.0, mode="parallel")
    results = response["videos"][0]["best_sequence"]["frames"]

    assert [f["frame_index"] for f in results] == [1, 2, 3]
    assert [f["query_index"] for f in results] == [0, 1, 2]
    # frame 7 at t=99 would break the chain to box 3 at t=41
    assert 7 not in [f["frame_index"] for f in results]


def test_temporal_score_is_mean_of_chain():
    box1 = [frame("V1", 1, timestamp=1.0, score=0.6)]
    box2 = [frame("V1", 2, timestamp=2.0, score=0.4)]
    response = hs.build_temporal_response([box1, box2], window=10.0, mode="parallel")
    assert response["videos"][0]["video_score"] == pytest.approx(0.5)


def test_temporal_prefers_higher_scoring_chain():
    box1 = [frame("V1", 1, timestamp=1.0, score=0.1), frame("V1", 2, timestamp=2.0, score=0.9)]
    box2 = [frame("V1", 3, timestamp=3.0, score=0.5)]
    response = hs.build_temporal_response([box1, box2], window=10.0, mode="parallel")
    results = response["videos"][0]["best_sequence"]["frames"]
    assert [f["frame_index"] for f in results] == [2, 3]


def test_temporal_uses_dense_positions_for_large_raw_frame_indexes():
    boxes = [
        [frame("V1", 1_000_000_000, timestamp=1.0, score=0.8)],
        [frame("V1", 2_000_000_000, timestamp=2.0, score=0.9)],
    ]
    response = hs.build_temporal_response(boxes, window=90.0, mode="parallel")
    frames = response["videos"][0]["best_sequence"]["frames"]
    assert [f["frame_index"] for f in frames] == [1_000_000_000, 2_000_000_000]


def test_temporal_sorts_sequences_by_score():
    boxes = [
        [frame("A", 1, timestamp=1.0, score=0.2), frame("B", 1, timestamp=1.0, score=0.9)],
        [frame("A", 2, timestamp=2.0, score=0.2), frame("B", 2, timestamp=2.0, score=0.9)],
    ]
    response = hs.build_temporal_response(boxes, window=10.0, mode="parallel")
    assert response["videos"][0]["video_id"] == "B"


def test_temporal_dedupes_same_frame_and_keeps_query_matches():
    shared = frame("V1", 2, timestamp=2.0, score=0.8)
    boxes = [
        [frame("V1", 1, timestamp=1.0, score=0.7), shared.copy()],
        [shared.copy(), frame("V1", 3, timestamp=3.0, score=0.6)],
    ]

    video = hs.build_temporal_response(boxes, window=90.0, mode="parallel")["videos"][0]
    result = next(item for item in video["valid_frames"] if item["frame_index"] == 2)
    assert result["matches"] == [
        {"query_index": 0, "similarity": pytest.approx(0.8)},
        {"query_index": 1, "similarity": pytest.approx(0.8)},
    ]


# ── Enrichment ──────────────────────────────────────────────────────────────
def test_enrich_dedupes_by_frame_key():
    frames = [frame("V1", 1), frame("V1", 1), frame("V1", 2)]
    enriched = hs._enrich_frames(frames)
    assert len(enriched) == 2


def test_enrich_sets_thumbnail_url():
    enriched = hs._enrich_frames([frame("V1", 7)])
    assert enriched[0]["thumbnail_url"].endswith("/keyframes/V1/V1/7.webp")


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


def test_video_frame_window_gets_original_ocr_asr_text(monkeypatch):
    class FakeMilvus:
        def query_frames(self, _expr):
            return [frame("V1", 7)]

    monkeypatch.setattr(hs.manager, "active_collection_name", lambda: "frames")
    monkeypatch.setattr(retrieval, "get_milvus_client", lambda _name: FakeMilvus())
    monkeypatch.setattr(
        hs.es_client,
        "fetch_frame_texts",
        lambda _keys: {("V1", 7): {"ocr_text": "LONG AN", "asr_text": "hồ Long Ẩn"}},
    )
    result = hs.search_video_frames("V1", 7)
    assert result[0]["ocr_text"] == "LONG AN"
    assert result[0]["asr_text"] == "hồ Long Ẩn"


def test_video_frame_window_survives_elasticsearch_failure(monkeypatch):
    class FakeMilvus:
        def query_frames(self, _expr):
            return [frame("V1", 7)]

    monkeypatch.setattr(hs.manager, "active_collection_name", lambda: "frames")
    monkeypatch.setattr(retrieval, "get_milvus_client", lambda _name: FakeMilvus())

    def fail(_keys):
        raise RuntimeError("ES unavailable")

    monkeypatch.setattr(hs.es_client, "fetch_frame_texts", fail)
    result = hs.search_video_frames("V1", 7)
    assert result[0]["ocr_text"] == ""
    assert result[0]["asr_text"] == ""


def test_filter_only_scores_are_neutral_in_temporal_dp():
    first = frame("V1", 1, timestamp=1.0, score=0.8)
    second = frame("V1", 2, timestamp=2.0, score=0.0)
    second["filter_only"] = True
    response = hs.build_temporal_response([[first], [second]], 90.0, "parallel")
    assert response["videos"][0]["video_score"] == pytest.approx(0.4)
    assert response["videos"][0]["has_vector_score"] is True


def test_siglip_text_display_score_does_not_change_raw_temporal_score():
    result = hs.build_temporal_response([[frame("V1", 1, score=0.16)]], 90.0, "parallel")

    hs.add_text_display_scores(result, {0}, lambda similarity: similarity + 0.68)

    displayed = result["videos"][0]["valid_frames"][0]
    assert displayed["score"] == pytest.approx(0.16)
    assert displayed["display_score"] == pytest.approx(0.84)
    assert displayed["display_score_kind"] == "siglip2_text_confidence"
