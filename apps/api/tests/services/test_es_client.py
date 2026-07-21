from __future__ import annotations

from typing import Any

import pytest

from app.services import es_client as module


class FakeElasticsearch:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.args = args
        self.kwargs = kwargs
        self.responses: list[dict[str, Any]] = []
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.ping_result: object = True

    def search(self, *, index: str, body: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((index, body))
        return self.responses.pop(0)

    def ping(self) -> object:
        if isinstance(self.ping_result, Exception):
            raise self.ping_result
        return self.ping_result


def _client(monkeypatch: Any, *, credentials: bool = False) -> tuple[module.ESClient, FakeElasticsearch]:
    fake = FakeElasticsearch()
    monkeypatch.setattr(module, "ES_USER", "user" if credentials else "")
    monkeypatch.setattr(module, "ES_PASS", "pass" if credentials else "")

    def factory(*args: Any, **kwargs: Any) -> FakeElasticsearch:
        fake.args = args
        fake.kwargs = kwargs
        return fake

    monkeypatch.setattr(module, "Elasticsearch", factory)
    return module.ESClient(), fake


def test_search_videos_builds_unique_video_query_with_tags(monkeypatch: Any) -> None:
    client, fake = _client(monkeypatch, credentials=True)
    fake.responses = [
        {"hits": {"hits": [{"_source": {"video_id": "V1"}, "_score": 2.5}]}},
        {"hits": {"hits": []}},
    ]

    results = client.search_videos("L21_", tags=[" Street ", "street", "Car"], size=7)
    empty = client.search_videos(size=3)

    assert fake.kwargs["basic_auth"] == ("user", "pass")
    assert results == [{"_source": {"video_id": "V1"}, "score": 2.5}]
    first_body = fake.calls[0][1]
    query_clause = first_body["query"]["bool"]["must"][0]["bool"]
    assert query_clause["should"][0]["prefix"]["video_id"]["value"] == "L21_"
    assert query_clause["should"][1]["multi_match"]["query"] == "L21_"
    assert first_body["query"]["bool"]["filter"] == [
        {"term": {"tags": "street"}},
        {"term": {"tags": "car"}},
    ]
    assert first_body["collapse"] == {"field": "video_id"}
    assert fake.calls[1][1]["query"] == {"match_all": {}}
    assert fake.calls[1][1]["collapse"] == {"field": "video_id"}
    assert empty == []


def test_get_video_and_keyword_filter_preserve_requested_order(monkeypatch: Any) -> None:
    client, fake = _client(monkeypatch)
    fake.responses = [
        {"hits": {"hits": [{"_source": {"video_id": "V1", "title": "one"}}]}},
        {"hits": {"hits": []}},
        {"hits": {"hits": [{"_source": {"video_id": "V2"}}]}},
        {"hits": {"hits": [{"_source": {"video_id": "V1"}}]}},
    ]

    assert client.get_video("V1") == {"video_id": "V1", "title": "one"}
    assert client.get_video("missing") is None
    assert client.filter_videos_by_keywords(["V1", "V2"], ["hello"], source="ocr") == ["V2"]
    assert client.filter_videos_by_keywords(
        ["V1", "V2"], ["hello", "world"], mode="or", source="asr"
    ) == ["V1"]
    assert fake.calls[2][1]["query"]["bool"]["must"][0]["multi_match"]["fields"] == [
        "ocr_text"
    ]
    assert fake.calls[3][1]["query"]["bool"]["minimum_should_match"] == 1


def test_get_videos_batches_metadata_lookup(monkeypatch: Any) -> None:
    client, fake = _client(monkeypatch)
    fake.responses = [
        {
            "hits": {
                "hits": [
                    {"_source": {"video_id": "V2", "title": "two"}},
                    {"_source": {"video_id": "V1", "title": "one"}},
                ]
            }
        }
    ]

    videos = client.get_videos(["V1", "V2", "V1"])

    assert set(videos) == {"V1", "V2"}
    assert fake.calls[0][1]["query"] == {"terms": {"video_id": ["V1", "V2"]}}
    assert client.get_videos([]) == {}


def test_keyword_filter_short_circuits_and_rejects_source(monkeypatch: Any) -> None:
    client, _ = _client(monkeypatch)
    assert client.filter_videos_by_keywords(["V1"], []) == ["V1"]
    assert client.filter_videos_by_keywords([], ["x"]) == []
    with pytest.raises(ValueError, match="source"):
        client.filter_videos_by_keywords(["V1"], ["x"], source="captions")


def test_connectivity_handles_false_and_exception(monkeypatch: Any) -> None:
    client, fake = _client(monkeypatch)
    assert client.is_connected() is True
    fake.ping_result = False
    assert client.is_connected() is False
    fake.ping_result = RuntimeError("offline")
    assert client.is_connected() is False
