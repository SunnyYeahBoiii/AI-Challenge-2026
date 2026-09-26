"""
Index Gemini OCR output (*.jsonl) into the `video_texts` Elasticsearch index.

Usage:
    cd apps/api
    uv run python scripts/index_ocr_jsonl.py --file ../../ocr-merged-all.jsonl --dry-run
    uv run python scripts/index_ocr_jsonl.py --file ../../ocr-merged-all.jsonl --limit 1000
    uv run python scripts/index_ocr_jsonl.py --file ../../ocr-merged-all.jsonl

Input: one JSON object per line with a Gemini `request` (the keyframe fileUri)
and `response` (the generated text). Only the OCR span of the response is
indexed; camera angle, sprint flag, top-3 riders and surroundings are dropped
because `ocr_text` is meant to hold text visible in the frame.

Writes are `update` actions keyed by `frame_key`, so existing `asr_text` and
frame metadata survive. Frames absent from the index are skipped unless
`--create-missing` is passed.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from es_common import ES_BATCH, connect_elasticsearch, ensure_es_index, normalize_text  # noqa: E402
from app.services.es_schema import frame_key  # noqa: E402

CAMERA_ANGLES = ("góc quay ngang", "góc quay trên cao", "góc quay trực diệp")
OCR_PREFIX = "OCR text:"
SCROLL = "2m"
PAGE_SIZE = 10_000
DEFAULT_FILE = Path(__file__).resolve().parents[3] / "ocr-merged-all.jsonl"


def response_text(doc: dict[str, Any]) -> str:
    """Concatenate every text part the model returned."""
    parts: list[str] = []
    for candidate in doc.get("response", {}).get("candidates", []) or []:
        for part in (candidate.get("content", {}) or {}).get("parts", []) or []:
            parts.append(part.get("text", ""))
    return "".join(parts)


def frame_identity(doc: dict[str, Any]) -> tuple[str, int] | None:
    """Return (video_id, frame_id) parsed from the request's keyframe fileUri."""
    for content in doc.get("request", {}).get("contents", []) or []:
        for part in content.get("parts", []) or []:
            uri = (part.get("fileData", {}) or {}).get("fileUri", "")
            segments = uri.split("/")
            if len(segments) < 2 or not segments[-1]:
                continue
            try:
                return segments[-2], int(segments[-1].split(".")[0])
            except ValueError:
                return None
    return None


def extract_ocr(text: str) -> str:
    """Keep only the OCR span: drop the optional prefix and everything from the camera angle on.

    The angle is matched case-insensitively because the model writes it both
    ways ("góc quay ngang" and "Góc quay ngang"), and the cut is taken at the
    earliest angle found rather than the first one in `CAMERA_ANGLES`, so two
    angles in one answer cannot leave a later section behind.
    """
    body = text.split(OCR_PREFIX, 1)[1] if OCR_PREFIX in text else text
    lowered = body.lower()
    cut = len(body)
    for angle in CAMERA_ANGLES:
        found = lowered.find(angle)
        if found >= 0:
            cut = min(cut, found)
    return normalize_text(body[:cut])


def iter_ocr_records(path: Path) -> Iterator[tuple[str, int, str]]:
    """Stream (video_id, frame_id, ocr_text) for every frame with usable OCR."""
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            doc = json.loads(line)
            identity = frame_identity(doc)
            if identity is None:
                continue
            ocr_text = extract_ocr(response_text(doc))
            if ocr_text:
                yield identity[0], identity[1], ocr_text


# --- vehicle-caption files -----------------------------------------------------
# A caption file is not OCR output. Its prompt fixes the answer order as
# vehicle OCR → vehicle types → colour/movement → parked → human actions, so
# only the span before the first taxonomy token is readable text. The rest is a
# controlled vocabulary repeated across tens of thousands of frames, and
# indexing it as OCR would swamp keyword search — "xe nhỏ" alone matches a large
# share of them — while the UI would label it as text visible in the frame.
CAPTION_TAXONOMY_HEADS = (
    "xe chuyên biệt",
    "xe nhỏ",
    "xe oto",
    "xe lớn",
    "xe buýt",
    "màu",
)


def extract_caption_ocr(text: str) -> str:
    """Keep only the readable text from a vehicle-caption answer."""
    lowered = text.lower()
    cut = len(text)
    for marker in CAPTION_TAXONOMY_HEADS:
        found = lowered.find(marker)
        if found >= 0:
            cut = min(cut, found)
    return normalize_text(text[:cut])


def iter_caption_records(path: Path) -> Iterator[tuple[str, int, str]]:
    """Stream (video_id, frame_id, ocr_text) for a vehicle-caption file.

    A caption is produced from two consecutive frames; `frame_identity` reads
    the first one, which is the frame the caption belongs to.
    """
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            doc = json.loads(line)
            identity = frame_identity(doc)
            if identity is None:
                continue
            ocr_text = extract_caption_ocr(response_text(doc))
            if ocr_text:
                yield identity[0], identity[1], ocr_text


def frame_keys_in_es(es: Any, index: str) -> set[str]:
    """Collect every document id currently in `index` (doc _id is the frame_key)."""
    keys: set[str] = set()
    response = es.search(
        index=index,
        body={"query": {"match_all": {}}, "_source": False, "size": PAGE_SIZE},
        scroll=SCROLL,
    )
    scroll_id = response.get("_scroll_id")
    while response["hits"]["hits"]:
        keys.update(hit["_id"] for hit in response["hits"]["hits"])
        if not scroll_id:
            break
        response = es.scroll(scroll_id=scroll_id, scroll=SCROLL)
    if scroll_id:
        es.clear_scroll(scroll_id=scroll_id)
    return keys


def _doc_fields(video_id: str, frame_id: int, ocr_text: str, *, upsert: bool) -> dict[str, Any]:
    """Fields for one bulk `update`.

    A plain update only needs `ocr_text`: the document already exists and its
    identity fields are already there. An upsert creates the document from
    scratch, so it has to carry `video_id` and `frame_id` too — every reader
    (`fetch_frame_texts`, `score_frames_by_keywords`) filters on those *fields*
    rather than on `_id`, so a doc without them is invisible to all of them.
    """
    doc: dict[str, Any] = {"ocr_text": ocr_text}
    if upsert:
        doc["frame_key"] = frame_key(video_id, frame_id)
        doc["video_id"] = video_id
        doc["frame_id"] = frame_id
    return doc


def flush(es: Any, index: str, buffer: list[tuple[str, int, str]], *, upsert: bool) -> int:
    """Send one bulk `update` batch and report the number of accepted actions."""
    if not buffer:
        return 0
    body: list[dict[str, Any]] = []
    for video_id, frame_id, ocr_text in buffer:
        body.append({"update": {"_index": index, "_id": frame_key(video_id, frame_id)}})
        body.append({"doc": _doc_fields(video_id, frame_id, ocr_text, upsert=upsert), "doc_as_upsert": upsert})
    sent = len(buffer)
    response = es.bulk(body=body)
    if response.get("errors"):
        failed = [item for item in response["items"] if item.get("update", {}).get("error")]
        print(f"  bulk: {len(failed)}/{sent} failed, first: {failed[:1]}")
    buffer.clear()
    return sent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, default=DEFAULT_FILE, help="Gemini JSONL output")
    parser.add_argument("--limit", type=int, help="Stop after N frames with OCR text")
    parser.add_argument("--dry-run", action="store_true", help="Parse only; no ES writes")
    parser.add_argument(
        "--create-missing",
        action="store_true",
        help="Also create docs for frames that are not in the index yet",
    )
    parser.add_argument("--batch", type=int, default=ES_BATCH)
    parser.add_argument(
        "--caption",
        action="store_true",
        help="Input is a vehicle-caption file: keep only the readable text span "
        "(plates, signs) and drop the vehicle-type/movement vocabulary",
    )
    args = parser.parse_args()

    if not args.file.is_file():
        parser.error(f"File not found: {args.file}")

    es = connect_elasticsearch()
    index = ensure_es_index(es)
    existing = set() if args.create_missing else frame_keys_in_es(es, index)
    print(f"  index={index} existing_docs={len(existing)} create_missing={args.create_missing}")

    buffer: list[tuple[str, int, str]] = []
    stats = {"ocr": 0, "skipped_missing": 0, "matched": 0, "videos": set()}
    started = time.time()

    records = iter_caption_records(args.file) if args.caption else iter_ocr_records(args.file)
    for video_id, frame_id, ocr_text in records:
        stats["ocr"] += 1
        stats["videos"].add(video_id)
        if not args.create_missing and frame_key(video_id, frame_id) not in existing:
            stats["skipped_missing"] += 1
            continue
        stats["matched"] += 1
        buffer.append((video_id, frame_id, ocr_text))
        if len(buffer) >= args.batch and not args.dry_run:
            flush(es, index, buffer, upsert=args.create_missing)
            print(f"  [{stats['matched']}] processed...")
        if args.limit and stats["ocr"] >= args.limit:
            break

    if not args.dry_run:
        flush(es, index, buffer, upsert=args.create_missing)
        es.indices.refresh(index=index)

    elapsed = time.time() - started
    print(
        f"\nframes_with_ocr={stats['ocr']} videos={len(stats['videos'])} "
        f"matched_in_index={stats['matched']} skipped_missing={stats['skipped_missing']} "
        f"in {elapsed:.1f}s{' (DRY RUN)' if args.dry_run else ''}"
    )


if __name__ == "__main__":
    main()
