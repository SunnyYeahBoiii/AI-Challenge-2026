from __future__ import annotations

import os
from collections.abc import Sequence
from typing import Any

from dotenv import load_dotenv
from elasticsearch import Elasticsearch

load_dotenv()
ES_URL = os.getenv("ES_URL", "http://localhost:9200")
ES_USER = os.getenv("ES_USER", "")
ES_PASS = os.getenv("ES_PASS", "")
ES_INDEX = "video_texts"


class ESClient:
    """Elasticsearch data access for OCR, ASR and display metadata."""

    def __init__(self) -> None:
        if ES_USER and ES_PASS:
            self.es = Elasticsearch(ES_URL, basic_auth=(ES_USER, ES_PASS))
        else:
            self.es = Elasticsearch(ES_URL)

    def search_videos(
        self,
        query: str | None = None,
        tags: Sequence[str] | None = None,
        size: int = 50,
    ) -> list[dict[str, Any]]:
        must: list[dict[str, Any]] = []
        cleaned_query = (query or "").strip()
        if cleaned_query:
            must.append(
                {
                    "bool": {
                        "should": [
                            {
                                "prefix": {
                                    "video_id": {
                                        "value": cleaned_query,
                                        "case_insensitive": True,
                                        "boost": 5.0,
                                    }
                                }
                            },
                            {
                                "multi_match": {
                                    "query": cleaned_query,
                                    "fields": [
                                        "ocr_text^3",
                                        "asr_text^2",
                                        "title",
                                        "description",
                                    ],
                                    "fuzziness": "AUTO",
                                }
                            },
                        ],
                        "minimum_should_match": 1,
                    }
                }
            )
        cleaned_tags = list(
            dict.fromkeys(tag.strip().casefold() for tag in tags or () if tag.strip())
        )
        filters = [{"term": {"tags": tag}} for tag in cleaned_tags]
        body: dict[str, Any] = {
            "size": size,
            "collapse": {"field": "video_id"},
            "query": (
                {"bool": {"must": must, "filter": filters}}
                if must or filters
                else {"match_all": {}}
            ),
        }
        response = self.es.search(index=ES_INDEX, body=body)
        return [
            {"_source": hit["_source"], "score": hit.get("_score", 0.0)}
            for hit in response["hits"]["hits"]
        ]

    def get_video(self, video_id: str) -> dict[str, Any] | None:
        response = self.es.search(
            index=ES_INDEX,
            body={"query": {"term": {"video_id": video_id}}, "size": 1},
        )
        hits = response["hits"]["hits"]
        return dict(hits[0]["_source"]) if hits else None

    def get_videos(self, video_ids: Sequence[str]) -> dict[str, dict[str, Any]]:
        """Fetch display metadata for many Videos in one Elasticsearch request."""
        unique_ids = list(dict.fromkeys(str(video_id) for video_id in video_ids if video_id))
        if not unique_ids:
            return {}
        response = self.es.search(
            index=ES_INDEX,
            body={
                "query": {"terms": {"video_id": unique_ids}},
                "size": min(len(unique_ids), 10_000),
            },
        )
        videos: dict[str, dict[str, Any]] = {}
        for hit in response["hits"]["hits"]:
            source = dict(hit["_source"])
            video_id = str(source.get("video_id", ""))
            if video_id:
                videos[video_id] = source
        return videos

    def filter_videos_by_keywords(
        self,
        video_ids: Sequence[str],
        keywords: Sequence[str],
        *,
        mode: str = "and",
        source: str = "all",
    ) -> list[str]:
        """Return Videos whose OCR/ASR text satisfies the requested keyword policy."""
        if not keywords or not video_ids:
            return list(video_ids)
        fields = {
            "all": ["ocr_text^3", "asr_text^2"],
            "ocr": ["ocr_text"],
            "asr": ["asr_text"],
        }.get(source)
        if fields is None:
            raise ValueError(f"unknown keyword source: {source}")
        clauses = [
            {"multi_match": {"query": keyword, "fields": fields, "operator": "and"}}
            for keyword in keywords
        ]
        bool_query: dict[str, Any] = {
            "filter": [{"terms": {"video_id": list(video_ids)}}],
        }
        if mode == "and":
            bool_query["must"] = clauses
        else:
            bool_query["should"] = clauses
            bool_query["minimum_should_match"] = 1
        response = self.es.search(
            index=ES_INDEX,
            body={
                "query": {"bool": bool_query},
                "_source": ["video_id"],
                "size": min(len(video_ids) * 20, 10_000),
            },
        )
        matching_ids = {
            str(hit["_source"]["video_id"]) for hit in response["hits"]["hits"]
        }
        return [video_id for video_id in video_ids if video_id in matching_ids]

    def is_connected(self) -> bool:
        try:
            return bool(self.es.ping())
        except Exception:
            return False


es_client = ESClient()
