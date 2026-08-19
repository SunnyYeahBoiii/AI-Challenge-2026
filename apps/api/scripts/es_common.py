"""Shared Elasticsearch helpers for load_data.py and index_es.py."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from elasticsearch import Elasticsearch

# Scripts run as standalone modules, so expose apps/api before importing the
# application-owned schema. This prevents ingest and query mappings drifting.
API_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(API_DIR))
load_dotenv(API_DIR / ".env")

from app.services.es_schema import ES_MAPPING, mismatched_mapping_fields  # noqa: E402

ES_URL = os.getenv("ES_URL", "http://localhost:9200")
ES_USER = os.getenv("ES_USER", "")
ES_PASS = os.getenv("ES_PASS", "")
ES_INDEX = "video_texts"
ES_BATCH = 1000


def normalize_text(text: str) -> str:
    """Lowercase and collapse whitespace — preserves Vietnamese diacritics."""
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_frame_info(file_path: str) -> tuple[str, int, str]:
    """Extract video_path, frame_id, frame_path from 'keyframes/L21/L21_V001/0001.webp'."""
    parts = file_path.split("/")
    video_path = "/".join(parts[:-1])
    frame_file = parts[-1]
    frame_id = int(frame_file.split(".")[0])
    return video_path, frame_id, file_path


def connect_elasticsearch() -> Elasticsearch:
    print(f"Connecting to Elasticsearch at {ES_URL}...")
    if ES_USER and ES_PASS:
        es = Elasticsearch(ES_URL, basic_auth=(ES_USER, ES_PASS))
    else:
        es = Elasticsearch(ES_URL)
    if not es.ping():
        raise ConnectionError("Cannot ping Elasticsearch")
    print("Elasticsearch connected.")
    return es


def ensure_es_index(es: Elasticsearch, *, recreate: bool = False) -> None:
    exists = bool(es.indices.exists(index=ES_INDEX))
    if exists and recreate:
        es.indices.delete(index=ES_INDEX)
        print(f"Deleted index '{ES_INDEX}'.")
        exists = False
    if exists:
        mapping: dict[str, Any] = es.indices.get_mapping(index=ES_INDEX)
        index_mapping = next(iter(mapping.values()))
        properties = index_mapping.get("mappings", {}).get("properties", {})
        mismatched_fields = mismatched_mapping_fields(properties)
        if mismatched_fields:
            fields = ", ".join(mismatched_fields)
            raise RuntimeError(
                f"Elasticsearch index '{ES_INDEX}' does not use the application mapping "
                f"for: {fields}. Recreate and reindex it before inserting more data."
            )
        print(f"Index '{ES_INDEX}' exists.")
        return
    es.indices.create(index=ES_INDEX, body=ES_MAPPING)
    print(f"Created index '{ES_INDEX}'.")


def frame_doc_from_record(record: dict[str, Any]) -> dict[str, object] | None:
    """Build one ES document from a concatenate-data.json record."""
    file_path = record.get("file_path", "")
    if not file_path:
        return None
    video_path, frame_id, frame_path = extract_frame_info(file_path)
    key_info = record.get("keyframe_info") or {}
    video_id = str(record.get("video_path", "")).rstrip("/").split("/")[-1]
    frame_idx = int(key_info.get("frame_idx") or 0)
    pts_time = float(key_info.get("timestamp") or key_info.get("pts_time") or 0.0)
    return {
        "video_id": video_id,
        "video_path": video_path,
        "frame_id": frame_id,
        "frame_idx": frame_idx,
        "frame_path": frame_path,
        "ocr_text": normalize_text(str(record.get("ocr_text", "") or "")),
        "asr_text": normalize_text(str(record.get("audio_text", "") or "")),
        "timestamp": pts_time,
    }


def bulk_insert_es(es: Elasticsearch, docs: list[dict[str, object]]) -> None:
    body: list[dict[str, object]] = []
    for doc in docs:
        body.append({"index": {"_index": ES_INDEX}})
        body.append(doc)
    resp = es.bulk(body=body, refresh="wait_for")
    if resp.get("errors"):
        errors = [item for item in resp["items"] if item.get("index", {}).get("error")]
        print(f"  ES bulk: {len(errors)} errors out of {len(docs)} docs")
        for err in errors[:3]:
            print(f"    {err['index']['error']}")
