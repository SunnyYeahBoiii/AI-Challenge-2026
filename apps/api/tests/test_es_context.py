"""Contract tests for Elasticsearch neighbour-keyframe lookup."""

from app.services.es_client import ESClient


class FakeElasticsearch:
    def __init__(self) -> None:
        self.searches = []

    def msearch(self, *, index, searches):
        assert index == "video_texts"
        self.searches = searches
        return {
            "responses": [
                {"hits": {"hits": [
                    {"_source": {"video_id": "V1", "frame_id": 90}},
                    {"_source": {"video_id": "V1", "frame_id": 80}},
                ]}},
                {"hits": {"hits": [
                    {"_source": {"video_id": "V1", "frame_id": 110}},
                    {"_source": {"video_id": "V1", "frame_id": 120}},
                ]}},
            ]
        }


def test_context_frame_keys_uses_non_ann_range_queries():
    client = object.__new__(ESClient)
    client.es = FakeElasticsearch()

    contexts = client.context_frame_keys([("V1", 100, 105)], count=10)

    assert contexts == [([("V1", 80), ("V1", 90)], [("V1", 110), ("V1", 120)])]
    before_body = client.es.searches[1]
    after_body = client.es.searches[3]
    assert before_body["query"]["bool"]["filter"][-1] == {"range": {"frame_id": {"lt": 100}}}
    assert after_body["query"]["bool"]["filter"][-1] == {"range": {"frame_id": {"gt": 105}}}
