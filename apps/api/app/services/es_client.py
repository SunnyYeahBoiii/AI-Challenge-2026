import os
from elasticsearch import Elasticsearch

ES_URL = os.getenv("ES_URL", "http://localhost:9200")
ES_USER = os.getenv("ES_USER", "")
ES_PASS = os.getenv("ES_PASS", "")
ES_INDEX = "video_texts"


class ESClient:
    def __init__(self):
        if ES_USER and ES_PASS:
            self.es = Elasticsearch(ES_URL, basic_auth=(ES_USER, ES_PASS))
        else:
            self.es = Elasticsearch(ES_URL)

    def search_videos(self, query=None, tags=None, size=50):
        must = []
        if query:
            must.append({
                "multi_match": {
                    "query": query,
                    "fields": ["ocr_text^3", "asr_text^2"],
                    "fuzziness": "AUTO",
                }
            })
        body = {"size": size}
        if must:
            body["query"] = {"bool": {"must": must}}
        else:
            body["query"] = {"match_all": {}}
        resp = self.es.search(index=ES_INDEX, body=body)
        return [
            {"_source": hit["_source"], "score": hit["_score"]}
            for hit in resp["hits"]["hits"]
        ]

    def get_video(self, video_id):
        resp = self.es.search(
            index=ES_INDEX,
            body={"query": {"term": {"video_id": video_id}}, "size": 1},
        )
        hits = resp["hits"]["hits"]
        return hits[0]["_source"] if hits else None

    def filter_videos_by_keywords(self, video_ids, keywords, mode="and"):
        if not keywords or not video_ids:
            return video_ids
        should = [{"term": {"tags": kw}} for kw in keywords]
        body = {
            "query": {"bool": {"should": should, "minimum_should_match": 1 if mode == "or" else len(should)}},
            "_source": ["video_id"],
            "size": len(video_ids),
        }
        resp = self.es.search(index=ES_INDEX, body=body)
        matching_ids = {hit["_source"]["video_id"] for hit in resp["hits"]["hits"]}
        return [vid for vid in video_ids if vid in matching_ids]

    def is_connected(self):
        try:
            return self.es.ping()
        except Exception:
            return False


es_client = ESClient()
