from app.main import create_app
from app.routes import search as search_routes
from app.services.es_client import ElasticsearchSearchError


def test_api_frames_returns_gateway_error_when_elasticsearch_is_unavailable(monkeypatch):
    def fail_search(**_kwargs):
        raise ElasticsearchSearchError("keyword_frame_hits")

    monkeypatch.setattr(search_routes, "multi_box_search", fail_search)
    client = create_app().test_client()

    response = client.post("/api/frames", json={"box_queries": [{"ocr_keywords": ["cat soi"]}]})

    assert response.status_code == 502
    assert response.get_json() == {
        "error": {
            "code": "ELASTICSEARCH_UNAVAILABLE",
            "message": "Elasticsearch is temporarily unavailable. Please retry.",
            "details": {"operation": "keyword_frame_hits"},
        }
    }
