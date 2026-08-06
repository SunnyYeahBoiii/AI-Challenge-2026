"""Tests for the metadata cache and the ES keyword filter."""

import json

from app.services import video_meta
from app.services.es_client import ESClient
from app.services.text_normalize import normalize_text


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
        return {"hits": {"hits": [{"_source": h} for h in self.hits]}}


def _client(hits):
    client = ESClient.__new__(ESClient)
    client.es = FakeES(hits)
    return client


def _must(client):
    return client.es.body["query"]["bool"]["must"]


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


def test_query_filters_on_both_video_and_frame():
    client = _client([])
    client.match_frames_by_keywords([("V1", 1), ("V2", 4)], ocr_keywords=["hello"])
    filters = client.es.body["query"]["bool"]["filter"]
    assert {"terms": {"video_id": ["V1", "V2"]}} in filters
    assert {"terms": {"frame_id": [1, 4]}} in filters


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


def test_ocr_keywords_search_ocr_field_only():
    client = _client([])
    client.match_frames_by_keywords([("V1", 1)], ocr_keywords=["hd"])
    must = _must(client)
    assert len(must) == 1
    clause = must[0]["bool"]["should"][0]["multi_match"]
    assert clause["fields"] == ["ocr_text"]
    assert clause["fuzziness"] == "AUTO"


def test_asr_keywords_search_asr_field_only():
    client = _client([])
    client.match_frames_by_keywords([("V1", 1)], asr_keywords=["chao"])
    must = _must(client)
    assert len(must) == 1
    clause = must[0]["bool"]["should"][0]["multi_match"]
    assert clause["fields"] == ["asr_text"]


def test_ocr_and_asr_groups_are_anded():
    client = _client([])
    client.match_frames_by_keywords(
        [("V1", 1)],
        ocr_keywords=["1172"],
        asr_keywords=["chao mung"],
    )
    must = _must(client)
    assert len(must) == 2
    fields = {
        group["bool"]["should"][0]["multi_match"]["fields"][0] for group in must
    }
    assert fields == {"ocr_text", "asr_text"}


def test_query_keywords_are_normalized():
    client = _client([])
    client.match_frames_by_keywords([("V1", 1)], asr_keywords=["Chào Mừng!"])
    clause = _must(client)[0]["bool"]["should"][0]["multi_match"]
    assert clause["query"] == normalize_text("Chào Mừng!")
    assert clause["query"] == "chao mung"


def test_legacy_source_ocr_maps_to_ocr_field():
    client = _client([])
    client.match_frames_by_keywords([("V1", 1)], ["a"], source="ocr")
    clause = _must(client)[0]["bool"]["should"][0]["multi_match"]
    assert clause["fields"] == ["ocr_text"]


def test_legacy_source_asr_maps_to_asr_field():
    client = _client([])
    client.match_frames_by_keywords([("V1", 1)], ["a"], source="asr")
    clause = _must(client)[0]["bool"]["should"][0]["multi_match"]
    assert clause["fields"] == ["asr_text"]


def test_legacy_source_all_ands_both_fields():
    client = _client([])
    client.match_frames_by_keywords([("V1", 1)], ["a"], source="all")
    assert len(_must(client)) == 2
