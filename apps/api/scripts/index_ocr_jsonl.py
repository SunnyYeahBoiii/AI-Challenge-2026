"""Merge Vertex batch-OCR predictions (JSONL) into Elasticsearch `ocr_text`.

Each line is a Gemini batch record whose request carries the keyframe
`gs://.../keyframes/<GROUP>/<VIDEO>/<frame>.webp` URI and whose response holds
the extracted text. Writes are partial updates on `frame_key`, so an existing
doc keeps its `asr_text`/timestamp and only `ocr_text` changes. Frames with no
existing doc are created (asr_text empty, shot_idx/timestamp 0 — unknown here).
Empty OCR results are skipped so they never blank an existing value.

Usage:
    cd apps/api
    uv run python scripts/index_ocr_jsonl.py --jsonl ~/Downloads/ocr-merged-all.jsonl --dry-run
    uv run python scripts/index_ocr_jsonl.py --jsonl ~/Downloads/ocr-merged-all.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Iterator

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))

from es_common import (  # noqa: E402
    ES_BATCH,
    connect_elasticsearch,
    ensure_es_index,
    finalize_es_index,
    normalize_text,
)

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.services.es_schema import frame_key  # noqa: E402

_PREFIX = re.compile(r"^\s*ocr text\s*:\s*", re.IGNORECASE)
_URI = re.compile(r"/keyframes/(?P<path>[^/]+/(?P<video>[^/]+))/(?P<frame>\d+)\.webp$")


def ocr_doc(rec: dict[str, Any]) -> tuple[dict[str, object], dict[str, object]] | None:
    """Return (partial update, full upsert doc), or None when there is no text."""
    if rec.get("status"):
        return None
    try:
        raw = rec["response"]["candidates"][0]["content"]["parts"][0]["text"]
        uri = rec["request"]["contents"][0]["parts"][0]["fileData"]["fileUri"]
    except (KeyError, IndexError, TypeError):
        return None
    text = normalize_text(_PREFIX.sub("", str(raw)))
    m = _URI.search(uri)
    if not text or not m:
        return None
    video_id, frame_id = m["video"], int(m["frame"])
    group = m["path"].split("/")[0]
    key = frame_key(video_id, frame_id)
    upsert: dict[str, object] = {
        "frame_key": key,
        "video_id": video_id,
        "video_path": f"keyframes/{group}/{video_id}/",
        "frame_id": frame_id,
        "frame_idx": frame_id,
        "shot_idx": 0,
        "frame_path": f"keyframes/{group}/{video_id}/{m['frame']}.webp",
        "ocr_text": text,
        "asr_text": "",
        "timestamp": 0.0,
    }
    return {"frame_key": key, "ocr_text": text}, upsert


def iter_docs(path: Path) -> Iterator[tuple[dict[str, object], dict[str, object]] | None]:
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield ocr_doc(json.loads(line))


def main() -> None:
    parser = argparse.ArgumentParser(description="Index OCR JSONL into ES ocr_text")
    parser.add_argument("--jsonl", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    path = Path(args.jsonl).expanduser()

    if args.dry_run:
        n = skipped = 0
        for item in iter_docs(path):
            if item is None:
                skipped += 1
            else:
                n += 1
                if n == 1:
                    print(f"Sample: {item[1]}")
        print(f"Would index {n} docs (skip {skipped} empty).")
        return

    es = connect_elasticsearch()
    index = ensure_es_index(es)
    body: list[dict[str, object]] = []
    count = skipped = created = updated = errors = 0
    t0 = time.time()

    def flush() -> None:
        nonlocal body, created, updated, errors
        if not body:
            return
        resp = es.bulk(body=body)
        for it in resp["items"]:
            u = it["update"]
            if u.get("error"):
                errors += 1
                if errors <= 3:
                    print(f"  ES error: {u['error']}")
            elif u["result"] == "created":
                created += 1
            else:
                updated += 1
        body = []

    for item in iter_docs(path):
        if item is None:
            skipped += 1
            continue
        update, upsert = item
        body.append({"update": {"_index": index, "_id": update["frame_key"]}})
        body.append({"doc": {"ocr_text": update["ocr_text"]}, "upsert": upsert})
        count += 1
        if count % ES_BATCH == 0:
            flush()
            if count % 20000 == 0:
                print(f"  [{count}] created {created} updated {updated} err {errors}", flush=True)
    flush()
    finalize_es_index(es, index)
    print(
        f"Done: {count} docs in {time.time() - t0:.1f}s "
        f"(created {created}, updated {updated}, errors {errors}, skipped {skipped} empty)"
    )
    es.indices.refresh(index=index)
    print(f"  Count in '{index}': {es.count(index=index)['count']}")


if __name__ == "__main__":
    main()
