"""Tests for the metadata cache and the ES keyword filter."""

import json

from app.services import video_meta
from app.services.es_client import ESClient
from app.services.es_schema import frame_key
from app.services.hybrid_search.common import _collapse_shots, _fuse_scores


# ── video_meta ──────────────────────────────────────────────────────────────
def _write_media(directory, video_id, **fields):
    payload = {"title": f"title {video_id}", "watch_url": f"https://y/{video_id}"}
    payload.update(fields)
    (directory / f"{video_id}.json").write_text(json.dumps(payload))


def test_load_reads_every_file(tmp_path):
    _write_media(tmp_path, "L21_V001")
    _write_media(tmp_path, "L21_V002")
    assert video_meta.load(tmp_path) == 2


def test_load_skips_malformed_json(tmp_path):
    _write_media(tmp_path, "L21_V001")
    (tmp_path / "broken.json").write_text("{not json")
    assert video_meta.load(tmp_path) == 1


def test_get_returns_metadata(tmp_path):
    _write_media(tmp_path, "L21_V001", keywords=["a", "b"], author="me")
    video_meta.load(tmp_path)
    meta = video_meta.get("L21_V001")
    assert meta["title"] == "title L21_V001"
    assert meta["keywords"] == ["a", "b"]
    assert meta["author"] == "me"


def test_get_unknown_video_is_empty(tmp_path):
    video_meta.load(tmp_path)
    assert video_meta.get("nope") == {}


def test_null_keywords_become_a_list(tmp_path):
    _write_media(tmp_path, "L21_V001", keywords=None)
    video_meta.load(tmp_path)
    assert video_meta.get("L21_V001")["keywords"] == []


# ── ES keyword filter ───────────────────────────────────────────────────────
class FakeES:
    def __init__(self, hits):
        self.hits = hits
        self.body = None

    def search(self, index=None, body=None):
        self.body = body
        return {
            "hits": {
                "hits": [
                    {"_source": h, "_score": h.pop("_score", 1.0) if isinstance(h, dict) else 1.0}
                    for h in self.hits
                ]
            }
        }


def _client(hits):
    client = ESClient.__new__(ESClient)
    client.es = FakeES(hits)
    return client


def _must(client):
    return client.es.body["query"]["bool"]["must"]


def test_search_videos_prefix_matches_video_id():
    client = _client([])
    client.search_videos(query="K01")
    should = _must(client)[0]["bool"]["should"]
    assert {"prefix": {"video_id": "K01"}} in should


def test_search_videos_also_tries_uppercase():
    client = _client([])
    client.search_videos(query="l21")
    should = _must(client)[0]["bool"]["should"]
    assert {"prefix": {"video_id": "L21"}} in should


def test_search_videos_without_query_is_match_all():
    client = _client([])
    client.search_videos()
    assert client.es.body["query"] == {"match_all": {}}


def test_no_keywords_keeps_everything():
    client = _client([])
    keys = [("V1", 1), ("V1", 2)]
    assert client.match_frames_by_keywords(keys, []) == set(keys)


def test_filter_is_frame_level_not_video_level():
    """One matching frame must not drag in the rest of its video."""
    client = _client([{"video_id": "V1", "frame_id": 1}])
    matched = client.match_frames_by_keywords(
        [("V1", 1), ("V1", 2)], ocr_keywords=["hello"]
    )
    assert matched == {("V1", 1)}


def test_query_filters_on_frame_key():
    """One keyed `terms` clause, not independent video_id/frame_id lists.

    Independent lists would match their cross product — every video_id paired
    with every frame_id — instead of only the (video_id, frame_id) pairs asked
    about.
    """
    client = _client([])
    client.match_frames_by_keywords([("V1", 1), ("V2", 4)], ocr_keywords=["hello"])
    filters = client.es.body["query"]["bool"]["filter"]
    assert filters == [{"terms": {"frame_key": [frame_key("V1", 1), frame_key("V2", 4)]}}]


def test_and_mode_requires_every_keyword():
    client = _client([])
    client.match_frames_by_keywords([("V1", 1)], ocr_keywords=["a", "b"], mode="and")
    ocr_group = _must(client)[0]["bool"]
    assert ocr_group["minimum_should_match"] == 2


def test_or_mode_requires_one_keyword():
    client = _client([])
    client.match_frames_by_keywords([("V1", 1)], ocr_keywords=["a", "b"], mode="or")
    ocr_group = _must(client)[0]["bool"]
    assert ocr_group["minimum_should_match"] == 1


def _phrase_terms(clause: dict) -> dict:
    """Flatten one exact-mode keyword clause to {field: query}.

    An exact keyword is a nested bool: the boosted diacritic-preserving phrase
    plus its `.folded` twin. Tests assert on the terms, not on that shape.
    """
    return {
        field: params["query"] if isinstance(params, dict) else params
        for phrase in clause["bool"]["should"]
        for field, params in phrase["match_phrase"].items()
    }


def test_ocr_keywords_search_ocr_field_only():
    """OCR defaults to the exact phrase; only `ocr_search_mode="fuzzy"` loosens it."""
    client = _client([])
    client.match_frames_by_keywords([("V1", 1)], ocr_keywords=["hd"])
    must = _must(client)
    assert len(must) == 1
    assert _phrase_terms(must[0]["bool"]["should"][0]) == {
        "ocr_text": "hd",
        "ocr_text.folded": "hd",
    }


def test_ocr_fuzzy_mode_uses_the_unordered_bag_of_words_match():
    """OCR text can be a scrambled, undiacritized bag of words — `fuzzy` matches it."""
    client = _client([])
    client.match_frames_by_keywords(
        [("V1", 1)], ocr_keywords=["hd"], ocr_search_mode="fuzzy"
    )
    clause = _must(client)[0]["bool"]["should"][0]
    assert clause == {
        "match": {
            "ocr_text": {
                "query": "hd",
                "minimum_should_match": "2<75%",
                "fuzziness": "AUTO",
                "prefix_length": 2,
                "max_expansions": 20,
            }
        }
    }


def test_ocr_digit_keyword_skips_fuzziness():
    """Fuzzy-matching a keyword with any digit (plates, timecodes, video ids)

    pulls in unrelated matches — "51F" measured 223 fuzzy hits against 3 strict.
    """
    client = _client([])
    client.match_frames_by_keywords(
        [("V1", 1)], ocr_keywords=["063127"], ocr_search_mode="fuzzy"
    )
    clause = _must(client)[0]["bool"]["should"][0]
    assert clause == {
        "match": {"ocr_text": {"query": "063127", "minimum_should_match": "2<75%"}}
    }


def test_ocr_alphanumeric_keyword_skips_fuzziness():
    client = _client([])
    client.match_frames_by_keywords(
        [("V1", 1)], ocr_keywords=["51F"], ocr_search_mode="fuzzy"
    )
    clause = _must(client)[0]["bool"]["should"][0]
    assert "fuzziness" not in clause["match"]["ocr_text"]


def test_asr_keywords_search_asr_field_only():
    """Each ASR keyword tries the diacritic-preserving field (boosted) first,

    then falls back to the folded subfield — both stay `match_phrase`, so this
    only loosens spelling, never word order.
    """
    client = _client([])
    client.match_frames_by_keywords([("V1", 1)], asr_keywords=["chao"])
    must = _must(client)
    assert len(must) == 1
    group = must[0]
    clause = group["bool"]["should"][0]
    assert clause == {
        "bool": {
            "should": [
                {"match_phrase": {"asr_text": {"query": "chao", "boost": 3}}},
                {"match_phrase": {"asr_text.folded": {"query": "chao"}}},
            ],
            "minimum_should_match": 1,
        }
    }


def _clause_field(clause: dict) -> str:
    if "match" in clause:
        return next(iter(clause["match"]))
    if "match_phrase" in clause:
        return next(iter(clause["match_phrase"]))
    # ASR keyword clause: bool.should = [exact match_phrase, folded match_phrase].
    return _clause_field(clause["bool"]["should"][0])


def test_ocr_and_asr_groups_are_anded():
    client = _client([])
    client.match_frames_by_keywords(
        [("V1", 1)],
        ocr_keywords=["1172"],
        asr_keywords=["chao mung"],
    )
    must = _must(client)
    assert len(must) == 2
    fields = {_clause_field(group["bool"]["should"][0]) for group in must}
    assert fields == {"ocr_text", "asr_text"}


def test_ocr_and_asr_groups_can_be_ored():
    client = _client([])
    client.match_frames_by_keywords(
        [("V1", 1)],
        ocr_keywords=["1172"],
        asr_keywords=["chao mung"],
        keyword_field_mode="or",
    )
    must = _must(client)
    assert len(must) == 1
    field_group = must[0]["bool"]
    assert field_group["minimum_should_match"] == 1
    assert len(field_group["should"]) == 2
    assert _phrase_terms(field_group["should"][0]["bool"]["should"][0]) == {
        "ocr_text": "1172",
        "ocr_text.folded": "1172",
    }
    assert _phrase_terms(field_group["should"][1]["bool"]["should"][0]) == {
        "asr_text": "chao mung",
        "asr_text.folded": "chao mung",
    }


def test_ocr_mode_and_asr_mode_are_independent():
    """or on OCR, and on ASR: each group keeps its own minimum_should_match."""
    client = _client([])
    client.match_frames_by_keywords(
        [("V1", 1)],
        ocr_keywords=["a", "b"],
        asr_keywords=["c", "d"],
        ocr_mode="or",
        asr_mode="and",
    )
    must = _must(client)
    groups = {
        _clause_field(group["bool"]["should"][0]): group["bool"] for group in must
    }
    assert groups["ocr_text"]["minimum_should_match"] == 1
    assert groups["asr_text"]["minimum_should_match"] == 2


def test_ocr_mode_and_asr_mode_fall_back_to_mode():
    client = _client([])
    client.match_frames_by_keywords(
        [("V1", 1)], ocr_keywords=["a", "b"], mode="or"
    )
    ocr_group = _must(client)[0]["bool"]
    assert ocr_group["minimum_should_match"] == 1


def test_query_keywords_are_passed_to_elasticsearch_unchanged():
    client = _client([])
    client.match_frames_by_keywords([("V1", 1)], asr_keywords=["Chào Mừng!"])
    assert _phrase_terms(_must(client)[0]["bool"]["should"][0]) == {
        "asr_text": "Chào Mừng!",
        "asr_text.folded": "Chào Mừng!",
    }


def test_ocr_query_is_passed_to_elasticsearch_unchanged():
    client = _client([])
    client.match_frames_by_keywords([("V1", 1)], ocr_keywords=["ĐỒNG, Vietnan!"])
    assert _phrase_terms(_must(client)[0]["bool"]["should"][0]) == {
        "ocr_text": "ĐỒNG, Vietnan!",
        "ocr_text.folded": "ĐỒNG, Vietnan!",
    }


def test_legacy_source_ocr_maps_to_ocr_field():
    client = _client([])
    client.match_frames_by_keywords([("V1", 1)], ["a"], source="ocr")
    assert _phrase_terms(_must(client)[0]["bool"]["should"][0]) == {
        "ocr_text": "a",
        "ocr_text.folded": "a",
    }


def test_legacy_source_asr_maps_to_asr_field():
    client = _client([])
    client.match_frames_by_keywords([("V1", 1)], ["a"], source="asr")
    group = _must(client)[0]
    clause = group["bool"]["should"][0]
    assert _clause_field(clause) == "asr_text"


def test_legacy_source_all_ands_both_fields():
    client = _client([])
    client.match_frames_by_keywords([("V1", 1)], ["a"], source="all")
    assert len(_must(client)) == 2


# ── BM25 scoring ─────────────────────────────────────────────────────────────
def test_score_frames_by_keywords_returns_bm25_score():
    client = _client([{"video_id": "V1", "frame_id": 1, "_score": 4.2}])
    scores = client.score_frames_by_keywords([("V1", 1)], ocr_keywords=["hello"])
    assert scores == {("V1", 1): 4.2}


def test_score_frames_by_keywords_omits_unmatched_frames():
    client = _client([])
    scores = client.score_frames_by_keywords([("V1", 1)], ocr_keywords=["hello"])
    assert scores == {}


def test_match_frames_by_keywords_still_returns_a_set():
    client = _client([{"video_id": "V1", "frame_id": 1, "_score": 4.2}])
    matched = client.match_frames_by_keywords([("V1", 1)], ocr_keywords=["hello"])
    assert matched == {("V1", 1)}


# ── RRF fusion and shot collapsing (app/services/hybrid_search/common.py) ────
def test_fuse_scores_weights_the_configured_source_higher(monkeypatch):
    from app.services.hybrid_search import common

    monkeypatch.setattr(common.Config, "RRF_TEXT_WEIGHT", 10.0)
    monkeypatch.setattr(common.Config, "RRF_VECTOR_WEIGHT", 1.0)
    frames = [
        {"video_id": "V1", "frame_index": 1, "vector_score": 0.9, "text_score": 1.0},
        {"video_id": "V1", "frame_index": 2, "vector_score": 0.1, "text_score": 5.0},
    ]
    fused = _fuse_scores(frames)
    # Frame 2 is #1 on text; a heavier text weight should let it win overall
    # despite ranking last on vector.
    assert fused[0]["frame_index"] == 2
    assert fused[0]["score"] > fused[1]["score"]


def test_fuse_scores_degenerates_to_single_source():
    frames = [
        {"video_id": "V1", "frame_index": 1, "vector_score": 0.1},
        {"video_id": "V1", "frame_index": 2, "vector_score": 0.9},
    ]
    fused = _fuse_scores(frames)
    assert [f["frame_index"] for f in fused] == [2, 1]


def test_collapse_shots_keeps_highest_scoring_frame_per_shot():
    frames = [
        {"video_id": "V1", "frame_index": 1, "shot_idx": 0, "score": 0.9},
        {"video_id": "V1", "frame_index": 2, "shot_idx": 0, "score": 0.5},
        {"video_id": "V1", "frame_index": 3, "shot_idx": 1, "score": 0.7},
    ]
    collapsed = _collapse_shots(frames)
    assert [f["frame_index"] for f in collapsed] == [1, 3]
    assert [s["frame_index"] for s in collapsed[0]["shot_siblings"]] == [2]


def test_global_keyword_search_uses_field_or_group_when_requested():
    client = _client([])
    list(
        client.iter_keyword_frame_hits(
            ocr_keywords=["tên vận động viên"],
            asr_keywords=["chào mừng"],
            keyword_field_mode="or",
        )
    )
    must = _must(client)
    assert len(must) == 1
    assert must[0]["bool"]["minimum_should_match"] == 1
    assert len(must[0]["bool"]["should"]) == 2


def test_global_keyword_search_restricts_allowed_videos():
    client = _client([])
    list(client.iter_keyword_frame_hits(asr_keywords=["hồ Long Ẩn"], allowed_video_ids=["V2"]))
    filters = client.es.body["query"]["bool"]["filter"]
    assert {"terms": {"video_id": ["V2"]}} in filters


def test_collapse_shots_keeps_frames_without_shot_idx():
    frames = [{"video_id": "V1", "frame_index": 1, "score": 0.9}]
    assert _collapse_shots(frames) == frames


def _phrase_slops(clause: dict) -> dict:
    """Flatten one exact-mode keyword clause to {field: slop or None}."""
    return {
        field: params.get("slop")
        for phrase in clause["bool"]["should"]
        for field, params in phrase["match_phrase"].items()
    }


def test_asr_phrase_slop_reaches_both_the_original_and_folded_phrase():
    """Slop must loosen adjacency on the folded twin too, or the fallback is stricter."""
    client = _client([])
    client.match_frames_by_keywords(
        [("V1", 1)], asr_keywords=["xin chao"], asr_phrase_slop=2
    )
    assert _phrase_slops(_must(client)[0]["bool"]["should"][0]) == {
        "asr_text": 2,
        "asr_text.folded": 2,
    }


def test_asr_phrase_slop_defaults_to_strict_adjacency():
    """Unset slop falls back to ES_ASR_PHRASE_SLOP, which ships as 0."""
    client = _client([])
    client.match_frames_by_keywords([("V1", 1)], asr_keywords=["xin chao"])
    assert _phrase_slops(_must(client)[0]["bool"]["should"][0]) == {
        "asr_text": None,
        "asr_text.folded": None,
    }


def test_asr_phrase_slop_leaves_the_ocr_phrase_adjacent():
    """Slop is an ASR knob: an exact OCR phrase stays strictly adjacent."""
    client = _client([])
    client.match_frames_by_keywords(
        [("V1", 1)],
        ocr_keywords=["bien so"],
        asr_keywords=["xin chao"],
        asr_phrase_slop=3,
    )
    ocr_group, asr_group = _must(client)
    assert _phrase_slops(ocr_group["bool"]["should"][0]) == {
        "ocr_text": None,
        "ocr_text.folded": None,
    }
    assert _phrase_slops(asr_group["bool"]["should"][0]) == {
        "asr_text": 3,
        "asr_text.folded": 3,
    }
