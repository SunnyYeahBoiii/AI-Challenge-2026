"""Tests for the metadata cache and the ES keyword filter."""

import json

from app.services import video_meta
from app.services.es_client import ESClient


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


def test_no_keywords_keeps_everything():
    client = _client([])
    keys = [("V1", 1), ("V1", 2)]
    assert client.match_frames_by_keywords(keys, []) == set(keys)


def test_filter_is_frame_level_not_video_level():
    """One matching frame must not drag in the rest of its video."""
    client = _client([{"video_id": "V1", "frame_id": 1}])
    matched = client.match_frames_by_keywords([("V1", 1), ("V1", 2)], ["hello"])
    assert matched == {("V1", 1)}


def test_query_filters_on_both_video_and_frame():
    client = _client([])
    client.match_frames_by_keywords([("V1", 1), ("V2", 4)], ["hello"])
    filters = client.es.body["query"]["bool"]["filter"]
    assert {"terms": {"video_id": ["V1", "V2"]}} in filters
    assert {"terms": {"frame_id": [1, 4]}} in filters


def test_and_mode_requires_every_keyword():
    client = _client([])
    client.match_frames_by_keywords([("V1", 1)], ["a", "b"], mode="and")
    assert client.es.body["query"]["bool"]["minimum_should_match"] == 2


def test_or_mode_requires_one_keyword():
    client = _client([])
    client.match_frames_by_keywords([("V1", 1)], ["a", "b"], mode="or")
    assert client.es.body["query"]["bool"]["minimum_should_match"] == 1


def test_keyword_source_selects_fields():
    client = _client([])
    client.match_frames_by_keywords([("V1", 1)], ["a"], source="ocr")
    clause = client.es.body["query"]["bool"]["should"][0]["multi_match"]
    assert clause["fields"] == ["ocr_text"]

    client.match_frames_by_keywords([("V1", 1)], ["a"], source="asr")
    clause = client.es.body["query"]["bool"]["should"][0]["multi_match"]
    assert clause["fields"] == ["asr_text"]
