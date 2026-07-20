"""
Smoke test for Milvus and Elasticsearch data loading.

Usage:
    cd apps/api
    uv run python scripts/smoke_test.py

Checks:
1. Milvus entity count
2. ES document count
3. Sample Milvus vector search
4. Sample ES text search
"""

import os
import sys
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from elasticsearch import Elasticsearch
from pymilvus import Collection, connections

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

MILVUS_URI = os.getenv("MILVUS_URI", "http://localhost:19530")
ES_URL = os.getenv("ES_URL", "http://localhost:9200")
ES_USER = os.getenv("ES_USER", "")
ES_PASS = os.getenv("ES_PASS", "")

COLLECTION_NAME = "data_frames"
ES_INDEX = "video_texts"

# Expected counts (L21-L24)
EXPECTED_MIN_FRAMES = 100_000


def check_milvus() -> bool:
    print("\n=== Milvus Check ===")
    try:
        connections.connect(alias="default", uri=MILVUS_URI)
        col = Collection(COLLECTION_NAME)
        col.load()
        count = col.num_entities
        print(f"  Entity count: {count}")
        if count < EXPECTED_MIN_FRAMES:
            print(f"  FAIL: Expected >= {EXPECTED_MIN_FRAMES}, got {count}")
            return False
        print("  PASS: Entity count OK")
        return True
    except Exception as e:
        print(f"  FAIL: {e}")
        return False
    finally:
        try:
            connections.disconnect("default")
        except Exception:
            pass


def check_elasticsearch() -> bool:
    print("\n=== Elasticsearch Check ===")
    try:
        if ES_USER and ES_PASS:
            es = Elasticsearch(ES_URL, basic_auth=(ES_USER, ES_PASS))
        else:
            es = Elasticsearch(ES_URL)

        if not es.ping():
            print("  FAIL: Cannot ping ES")
            return False

        resp = es.count(index=ES_INDEX)
        count = resp["count"]
        print(f"  Document count: {count}")
        if count < EXPECTED_MIN_FRAMES:
            print(f"  FAIL: Expected >= {EXPECTED_MIN_FRAMES}, got {count}")
            return False
        print("  PASS: Document count OK")
        return True
    except Exception as e:
        print(f"  FAIL: {e}")
        return False


def check_milvus_search() -> bool:
    print("\n=== Milvus Vector Search ===")
    try:
        connections.connect(alias="default", uri=MILVUS_URI)
        col = Collection(COLLECTION_NAME)
        col.load()

        # Random query vector
        query_vec = np.random.randn(1024).astype(np.float32).tolist()
        results = col.search(
            data=[query_vec],
            anns_field="embedding",
            param={"metric_type": "IP", "params": {"ef": 128}},
            limit=5,
            output_fields=["video_id", "video_path", "frame_index", "pts_time"],
        )

        if not results or not results[0]:
            print("  FAIL: No results returned")
            return False

        print(f"  Got {len(results[0])} results")
        for i, hit in enumerate(results[0]):
            vid = hit.entity.get("video_id")
            path = hit.entity.get("video_path")
            frame = hit.entity.get("frame_index")
            score = float(hit.score)
            print(f"    [{i}] {vid} | {path} | frame {frame} | score {score:.4f}")
        print("  PASS: Vector search OK")
        return True
    except Exception as e:
        print(f"  FAIL: {e}")
        return False
    finally:
        try:
            connections.disconnect("default")
        except Exception:
            pass


def check_es_search() -> bool:
    print("\n=== Elasticsearch Text Search ===")
    try:
        if ES_USER and ES_PASS:
            es = Elasticsearch(ES_URL, basic_auth=(ES_USER, ES_PASS))
        else:
            es = Elasticsearch(ES_URL)

        resp = es.search(
            index=ES_INDEX,
            body={
                "query": {"match_all": {}},
                "size": 3,
            },
        )

        hits = resp["hits"]["hits"]
        if not hits:
            print("  FAIL: No results returned")
            return False

        print(f"  Got {len(hits)} results")
        for i, hit in enumerate(hits):
            src = hit["_source"]
            print(f"    [{i}] {src.get('video_id')} | {src.get('video_path')} | frame {src.get('frame_id')}")
        print("  PASS: Text search OK")
        return True
    except Exception as e:
        print(f"  FAIL: {e}")
        return False


def main() -> int:
    print("=== Smoke Test ===")
    print(f"Milvus: {MILVUS_URI}")
    print(f"ES: {ES_URL}")

    results = [
        ("Milvus count", check_milvus()),
        ("ES count", check_elasticsearch()),
        ("Milvus search", check_milvus_search()),
        ("ES search", check_es_search()),
    ]

    print("\n=== Summary ===")
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    for name, ok in results:
        print(f"  {name}: {'PASS' if ok else 'FAIL'}")

    print(f"\n{passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
