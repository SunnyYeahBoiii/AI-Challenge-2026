"""Shared Elasticsearch helpers for load_data.py and index_es.py."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any

from elasticsearch import Elasticsearch

# Both callers (load_data.py, index_es.py) run as standalone scripts, so
# apps/api must be on sys.path before app.services is importable here too.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.es_schema import ES_ALIAS, ES_INDEX_PREFIX, ES_MAPPING, frame_key  # noqa: E402

ES_URL = os.getenv("ES_URL", "http://localhost:9200")
ES_USER = os.getenv("ES_USER", "")
ES_PASS = os.getenv("ES_PASS", "")
ES_INDEX = ES_ALIAS
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


def _resolve_alias_target(es: Elasticsearch) -> str | None:
    """Return the concrete index `ES_ALIAS` currently resolves to, or None."""
    if not es.indices.exists_alias(name=ES_ALIAS):
        return None
    aliases = es.indices.get_alias(name=ES_ALIAS)
    return next(iter(aliases), None)


def _versions(es: Elasticsearch) -> dict[int, str]:
    existing = es.indices.get(index=f"{ES_INDEX_PREFIX}*", ignore_unavailable=True)
    return {
        int(suffix): name
        for name in existing
        if (suffix := name[len(ES_INDEX_PREFIX):]).isdigit()
    }


def ensure_es_index(es: Elasticsearch, *, recreate: bool = False) -> str:
    """Return the concrete index name to bulk-write into.

    If the alias already exists and `recreate` is not set, reuse it: writes use
    `_id=frame_key`, so re-running is an upsert, not a duplicate. If a previous
    run built a versioned index but was interrupted before `finalize_es_index`
    ran (checkpointed loaders resume across processes), reuse that staging
    index rather than abandoning it — upsert-by-`frame_key` makes replaying
    already-loaded records harmless. `recreate` skips both and always starts a
    fresh version, letting `finalize_es_index` point the alias at it once
    loading is done.

    The very first migration off the legacy concrete `video_texts` index (no
    analyzer, pre-dates this alias scheme) cannot be zero-downtime: Elasticsearch
    refuses to create an alias with the same name as an existing concrete
    index, so that index has to be deleted before the alias can claim the name.
    Every reindex after this one is atomic.
    """
    target = _resolve_alias_target(es)
    if target and not recreate:
        print(f"Alias '{ES_ALIAS}' -> '{target}' exists; writing into it (upsert by frame_key).")
        return target

    if target is None and es.indices.exists(index=ES_ALIAS):
        print(f"'{ES_ALIAS}' is a legacy concrete index (pre-migration mapping).")

    versions = _versions(es)
    if versions and not recreate:
        latest = versions[max(versions)]
        print(f"Reusing unfinished staging index '{latest}' (upsert by frame_key).")
        return latest

    new_index = f"{ES_INDEX_PREFIX}{max(versions, default=0) + 1}"
    # Disable refresh for the duration of the bulk load; finalize_es_index
    # restores it. Deep-copy the settings so this doesn't mutate the shared
    # ES_MAPPING dict for later callers in the same process.
    body = {**ES_MAPPING, "settings": {**ES_MAPPING["settings"], "refresh_interval": "-1"}}
    es.indices.create(index=new_index, body=body)
    print(f"Created index '{new_index}' (refresh disabled for bulk load).")
    return new_index


def finalize_es_index(es: Elasticsearch, index: str) -> None:
    """Make `index` searchable and point the `video_texts` alias at it.

    Bulk loading runs with `refresh_interval: -1` for throughput; this restores
    it and refreshes once — skipping this step leaves every future write
    permanently invisible to search. The alias swap is a single `_aliases` call
    (remove old + add new), so it is atomic for every migration except the
    very first one, which must delete the legacy concrete index first (see
    `ensure_es_index`).
    """
    es.indices.put_settings(index=index, body={"index": {"refresh_interval": "1s"}})
    es.indices.refresh(index=index)

    if es.indices.exists(index=ES_ALIAS) and not es.indices.exists_alias(name=ES_ALIAS):
        es.indices.delete(index=ES_ALIAS)
        print(f"Deleted legacy concrete index '{ES_ALIAS}'.")

    previous = _resolve_alias_target(es)
    actions: list[dict[str, object]] = []
    if previous and previous != index:
        actions.append({"remove": {"index": previous, "alias": ES_ALIAS}})
    actions.append({"add": {"index": index, "alias": ES_ALIAS}})
    es.indices.update_aliases(body={"actions": actions})
    print(f"Alias '{ES_ALIAS}' -> '{index}'.")

    if previous and previous != index:
        es.indices.delete(index=previous)
        print(f"Deleted old index '{previous}'.")


def frame_doc_from_record(record: dict[str, Any]) -> dict[str, object] | None:
    """Build one ES document from a concatenate-data.json record."""
    file_path = record.get("file_path", "")
    if not file_path:
        return None
    video_path, frame_id, frame_path = extract_frame_info(file_path)
    key_info = record.get("keyframe_info") or {}
    video_id = str(record.get("video_path", "")).rstrip("/").split("/")[-1]
    frame_idx = int(key_info.get("frame_idx") or 0)
    shot_idx = int(key_info.get("shot_idx") or 0)
    pts_time = float(key_info.get("timestamp") or key_info.get("pts_time") or 0.0)
    return {
        "frame_key": frame_key(video_id, frame_id),
        "video_id": video_id,
        "video_path": video_path,
        "frame_id": frame_id,
        "frame_idx": frame_idx,
        "shot_idx": shot_idx,
        "frame_path": frame_path,
        "ocr_text": normalize_text(str(record.get("ocr_text", "") or "")),
        "asr_text": normalize_text(str(record.get("audio_text", "") or "")),
        "timestamp": pts_time,
    }


def bulk_insert_es(es: Elasticsearch, docs: list[dict[str, object]], *, index: str = ES_INDEX) -> None:
    """Bulk-index docs, keyed by `frame_key` so re-running upserts instead of duplicating.

    No per-batch refresh: callers load with `refresh_interval: -1` for
    throughput and call `finalize_es_index` once at the end.
    """
    body: list[dict[str, object]] = []
    for doc in docs:
        body.append({"index": {"_index": index, "_id": doc["frame_key"]}})
        body.append(doc)
    resp = es.bulk(body=body)
    if resp.get("errors"):
        errors = [item for item in resp["items"] if item.get("index", {}).get("error")]
        print(f"  ES bulk: {len(errors)} errors out of {len(docs)} docs")
        for err in errors[:3]:
            print(f"    {err['index']['error']}")
