"""Frame retrieval over Milvus (dense) + Elasticsearch (OCR/ASR text).

Both multi-box modes share one fan-out stage:

    enhance (concurrent)  ->  embed (one batch)  ->  Milvus (one RPC per
    retrieval stage)  ->  Polars object filter  ->  ES keyword filter (one
    query)  ->  enrich (in-memory)  ->  merge

`parallel` fuses the per-box hit lists with Reciprocal Rank Fusion; `sequential`
treats each box as one shot of a temporal sequence and keeps only chains that
occur in a single video, in box order, within `temporal_window` seconds.
"""

import base64
from collections import deque
from collections.abc import Iterable, Sequence
from typing import Any

from app.services import video_meta
from app.services.encoders import manager
from app.services.es_client import es_client
from app.services.milvus_client import clamp_milvus_topk, get_milvus_client
from app.services.object_filter import filter_frames
from app.services.query_enhance import enhance_queries, enhance_query

Frame = dict[str, Any]
Box = dict[str, Any]
FrameKey = tuple[Any, Any]
Vector = list[float] | None

RRF_K = 60
STAGE1_TOPK = 300
STAGE2_TOPK = 500
MAX_CANDIDATE_VIDEOS = 60


# ── Filter expressions ──────────────────────────────────────────────────────
def _quote(value: Any) -> str:
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _video_expr(video_ids: Sequence[str]) -> str | None:
    if not video_ids:
        return None
    return f"video_id in [{', '.join(_quote(v) for v in video_ids)}]"


# ── Enrichment ──────────────────────────────────────────────────────────────
def _frame_key(frame: Frame) -> FrameKey:
    return (frame.get("video_id"), frame.get("frame_index"))


def _enrich_frames(frames: Iterable[Frame]) -> list[Frame]:
    """Attach video metadata and dedupe by (video_id, frame_index).

    Metadata comes from the in-process media-info cache; the previous ES lookup
    cost one round-trip per video and returned fields the index does not store.
    """
    seen: set[FrameKey] = set()
    deduped: list[Frame] = []
    for f in frames:
        key = _frame_key(f)
        if key in seen:
            continue
        seen.add(key)
        meta = video_meta.get(f.get("video_id", ""))
        f["title"] = meta.get("title", "")
        # Omit bulky per-video fields from every hit — they dominate JSON size at
        # large topk and the UI does not render them on result cards.
        f["description"] = ""
        f["keywords"] = []
        f["author"] = meta.get("author", "")
        f["publish_date"] = meta.get("publish_date", "")
        f["watch_url"] = f.get("youtube_url") or meta.get("watch_url", "")
        f["thumbnail_url"] = f"/api/keyframes/{f.get('video_id', '')}/{f.get('frame_index', 0)}"
        deduped.append(f)
    return deduped


def _filter_by_keywords(
    frames: list[Frame],
    ocr_keywords: Sequence[str] | None = None,
    asr_keywords: Sequence[str] | None = None,
    mode: str = "and",
    *,
    keywords: Sequence[str] | None = None,
    source: str = "all",
    ocr_mode: str | None = None,
    asr_mode: str | None = None,
) -> list[Frame]:
    """Drop frames whose OCR/ASR text does not match, in one ES round-trip."""
    has_any = bool(ocr_keywords) or bool(asr_keywords) or bool(keywords)
    if not has_any or not frames:
        return frames
    matched = es_client.match_frames_by_keywords(
        [_frame_key(f) for f in frames],
        keywords=keywords,
        mode=mode,
        source=source,
        ocr_keywords=ocr_keywords,
        asr_keywords=asr_keywords,
        ocr_mode=ocr_mode,
        asr_mode=asr_mode,
    )
    return [f for f in frames if _frame_key(f) in matched]


# ── Single-query search ─────────────────────────────────────────────────────
def search_text(
    query: str = "",
    tags: Sequence[str] | None = None,
    keywords: Sequence[str] | None = None,
    topk: int = 20,
    enhance: bool = True,
    tag_mode: str = "and",
    keyword_mode: str = "and",
    keyword_source: str = "all",
    ocr_keywords: Sequence[str] | None = None,
    asr_keywords: Sequence[str] | None = None,
    ocr_mode: str | None = None,
    asr_mode: str | None = None,
) -> list[Frame]:
    """Text search: enhance -> embed -> Milvus -> Polars tags -> ES keywords."""
    if enhance and query:
        query = enhance_query(query)
    if query:
        vec: list[float] = manager.embed_text([query])[0].tolist()
        frames = get_milvus_client(manager.active_collection_name()).search(
            vec, topk=clamp_milvus_topk(topk * 2)
        )
    else:
        return []
    frames = filter_frames(frames, tags, tag_mode)
    frames = _filter_by_keywords(
        frames,
        ocr_keywords=ocr_keywords,
        asr_keywords=asr_keywords,
        mode=keyword_mode,
        keywords=keywords,
        source=keyword_source,
        ocr_mode=ocr_mode,
        asr_mode=asr_mode,
    )
    frames = _enrich_frames(frames)
    for f in frames:
        f["score"] = f.get("vector_score", 0.0)
    frames.sort(key=lambda f: float(f["score"]), reverse=True)
    return frames[:topk]


def search_image(
    image_bytes: bytes,
    tags: Sequence[str] | None = None,
    keywords: Sequence[str] | None = None,
    topk: int = 20,
    tag_mode: str = "and",
    keyword_mode: str = "and",
    keyword_source: str = "all",
    ocr_keywords: Sequence[str] | None = None,
    asr_keywords: Sequence[str] | None = None,
    ocr_mode: str | None = None,
    asr_mode: str | None = None,
) -> list[Frame]:
    """Image search: embed -> Milvus -> Polars tags -> ES keywords."""
    vec: list[float] = manager.embed_image(image_bytes).tolist()
    frames = get_milvus_client(manager.active_collection_name()).search(
        vec, topk=clamp_milvus_topk(topk * 2)
    )
    frames = filter_frames(frames, tags, tag_mode)
    frames = _filter_by_keywords(
        frames,
        ocr_keywords=ocr_keywords,
        asr_keywords=asr_keywords,
        mode=keyword_mode,
        keywords=keywords,
        source=keyword_source,
        ocr_mode=ocr_mode,
        asr_mode=asr_mode,
    )
    frames = _enrich_frames(frames)
    for f in frames:
        f["score"] = f.get("vector_score", 0.0)
    frames.sort(key=lambda f: float(f["score"]), reverse=True)
    return frames[:topk]


def search_video_frames(
    video_id: str, frame_index: int | None = None, range: int = 5
) -> list[Frame]:
    """List a video's frames, optionally windowed around `frame_index`.

    Uses a scalar query — an ANN search with a zero vector scans the index for
    nothing.
    """
    try:
        milvus_frames = get_milvus_client(manager.active_collection_name()).query_frames(
            f"video_id == {_quote(video_id)}"
        )
    except Exception:
        return []
    frames = _enrich_frames(milvus_frames)
    frames.sort(key=lambda f: int(f.get("frame_index") or 0))
    if frame_index is None:
        return frames
    pos = next((i for i, f in enumerate(frames) if f.get("frame_index") == frame_index), None)
    if pos is None:
        return frames
    return frames[max(0, pos - range):pos + range + 1]


def search_similar_frames(video_id: str, frame_index: int, topk: int = 12) -> list[Frame]:
    milvus = get_milvus_client(manager.active_collection_name())
    embedding = milvus.get_frame_embedding(video_id, frame_index)
    if embedding is None:
        return []
    milvus_frames = milvus.search(embedding, topk=topk + 1)
    milvus_frames = [
        f for f in milvus_frames
        if not (f.get("video_id") == video_id and f.get("frame_index") == frame_index)
    ][:topk]
    for f in milvus_frames:
        f["score"] = f.get("vector_score", 0.0)
    frames = _enrich_frames(milvus_frames)
    frames.sort(key=lambda f: float(f.get("score", 0.0)), reverse=True)
    return frames


# ── Multi-box fan-out ───────────────────────────────────────────────────────
def _resolve_enhance(box: Box, default: bool) -> bool:
    override = box.get("enhance")
    return default if override is None else bool(override)


def _box_vectors(boxes: Sequence[Box], enhance_default: bool) -> list[Vector]:
    """One CLIP forward pass for all text boxes and one for all image boxes.

    Returns a list aligned to `boxes`; entries are None for boxes that carry
    neither text nor an image.
    """
    vectors: list[Vector] = [None] * len(boxes)

    text_idx = [i for i, b in enumerate(boxes) if b.get("text")]
    image_idx = [i for i, b in enumerate(boxes) if not b.get("text") and b.get("image")]

    if text_idx:
        texts = {i: str(boxes[i]["text"]) for i in text_idx}
        to_enhance = [i for i in text_idx if _resolve_enhance(boxes[i], enhance_default)]
        if to_enhance:
            enhanced = enhance_queries([texts[i] for i in to_enhance])
            texts.update(dict(zip(to_enhance, enhanced)))
        encoded = manager.embed_text([texts[i] for i in text_idx])
        for i, vec in zip(text_idx, encoded):
            vectors[i] = vec.tolist()

    if image_idx:
        blobs: list[bytes] = []
        decoded_idx: list[int] = []
        for i in image_idx:
            try:
                blobs.append(base64.b64decode(boxes[i]["image"]))
                decoded_idx.append(i)
            except Exception:
                continue
        if blobs:
            encoded = manager.embed_images(blobs)
            for i, vec in zip(decoded_idx, encoded):
                vectors[i] = vec.tolist()

    return vectors


def _grouped_search(
    boxes: Sequence[Box],
    vectors: Sequence[Vector],
    topk: int,
    extra_expr: str | None = None,
) -> list[list[Frame]]:
    """Search vector-bearing boxes in batches that share a Milvus expression."""
    per_box: list[list[Frame]] = [[] for _ in boxes]
    groups: dict[str, list[int]] = {}
    for i, vec in enumerate(vectors):
        if vec is not None:
            groups.setdefault(extra_expr or "", []).append(i)
    if not groups:
        return per_box

    milvus = get_milvus_client(manager.active_collection_name())
    for expr_key, indices in groups.items():
        batch = [v for i in indices if (v := vectors[i]) is not None]
        batched = milvus.search_batch(batch, topk=topk, expr=expr_key or None)
        for i, frames in zip(indices, batched):
            per_box[i] = frames
    return per_box


def _apply_box_object_filters(
    boxes: Sequence[Box], per_box: list[list[Frame]]
) -> list[list[Frame]]:
    """Post-filter every box's ranked Milvus candidates by RF-DETR classes."""
    for i, box in enumerate(boxes):
        per_box[i] = filter_frames(
            per_box[i], box.get("tags"), box.get("tag_match_mode", "and")
        )
    return per_box


def _apply_box_keywords(
    boxes: Sequence[Box], per_box: list[list[Frame]]
) -> list[list[Frame]]:
    for i, box in enumerate(boxes):
        per_box[i] = _filter_by_keywords(
            per_box[i],
            ocr_keywords=box.get("ocr_keywords"),
            asr_keywords=box.get("asr_keywords"),
            mode=box.get("key_match_mode", "and"),
            keywords=box.get("keywords"),
            source=box.get("keyword_source", "all"),
            ocr_mode=box.get("ocr_match_mode"),
            asr_mode=box.get("asr_match_mode"),
        )
    return per_box


def _retrieve_boxes(
    boxes: Sequence[Box], topk: int, enhance: bool, two_stage: bool
) -> tuple[list[list[Frame]], list[Vector]]:
    """Fan out every box. With `two_stage`, narrow to shared candidate videos
    first, then search deeper inside only those videos."""
    vectors = _box_vectors(boxes, enhance)

    # Overfetch for filters/RRF, but never exceed Milvus's ANN ceiling.
    raw_stage1 = max(topk, STAGE1_TOPK) if two_stage else topk * 2
    stage1_topk = clamp_milvus_topk(raw_stage1)
    per_box = _grouped_search(boxes, vectors, stage1_topk)
    per_box = _apply_box_object_filters(boxes, per_box)
    per_box = _apply_box_keywords(boxes, per_box)

    if not two_stage:
        return per_box, vectors

    active = [i for i, frames in enumerate(per_box) if frames]
    counts: dict[str, int] = {}
    for i in active:
        for vid in {f.get("video_id") for f in per_box[i]}:
            if vid:
                counts[vid] = counts.get(vid, 0) + 1
    if not counts:
        return per_box, vectors

    # Videos seen by more boxes are likelier to hold the full sequence; keep the
    # best MAX_CANDIDATE_VIDEOS so stage 2 stays cheap.
    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    candidates = [vid for vid, _ in ranked[:MAX_CANDIDATE_VIDEOS]]
    video_expr = _video_expr(candidates)
    if video_expr is None:
        return per_box, vectors

    deep = _grouped_search(
        boxes, vectors, clamp_milvus_topk(max(topk, STAGE2_TOPK)), extra_expr=video_expr
    )
    deep = _apply_box_object_filters(boxes, deep)
    deep = _apply_box_keywords(boxes, deep)
    for i in active:
        if deep[i]:
            per_box[i] = deep[i]
    return per_box, vectors


# ── Merge strategies ────────────────────────────────────────────────────────
def merge_rrf(per_box: Sequence[list[Frame]], topk: int, k: int = RRF_K) -> list[Frame]:
    """Reciprocal Rank Fusion.

    Raw inner-product scores are not comparable across different CLIP queries —
    an easy box would otherwise dominate the whole ranking. RRF uses only the
    rank within each box and rewards frames that several boxes agree on.
    """
    active = [frames for frames in per_box if frames]
    if not active:
        return []
    if len(active) == 1:
        single = _enrich_frames(list(active[0]))
        for f in single:
            f["score"] = f.get("vector_score", 0.0)
        single.sort(key=lambda f: float(f["score"]), reverse=True)
        return single[:topk]

    fused: dict[FrameKey, float] = {}
    best: dict[FrameKey, Frame] = {}
    for frames in active:
        for rank, f in enumerate(frames):
            key = _frame_key(f)
            fused[key] = fused.get(key, 0.0) + 1.0 / (k + rank + 1)
            current = best.get(key)
            if current is None or f.get("vector_score", 0) > current.get("vector_score", 0):
                best[key] = f

    max_score = len(active) / (k + 1)
    results: list[Frame] = []
    for key, score in fused.items():
        frame = best[key]
        frame["score"] = score / max_score
        results.append(frame)
    results.sort(key=lambda f: float(f["score"]), reverse=True)
    return _enrich_frames(results[:topk])


Chain = tuple[float, float, tuple[Frame, ...]]


def _best_chain(by_box: Sequence[list[Frame]], window: float) -> Chain | None:
    """Pick one frame per box forming a strictly forward-in-time chain whose
    consecutive gaps stay within `window`, maximising the summed score.

    Each box's frames arrive sorted by time, so the set of reachable
    predecessors is a sliding window; a monotonic deque keeps the best one in
    amortised O(1) instead of rescanning the previous box for every frame.
    """
    prev: list[Chain] = [
        (float(f.get("pts_time") or 0.0), float(f.get("vector_score") or 0.0), (f,))
        for f in by_box[0]
    ]
    if not prev:
        return None

    for frames in by_box[1:]:
        best: list[Chain] = []
        dq: deque[int] = deque()
        hi = 0
        for f in frames:
            t = float(f.get("pts_time") or 0.0)
            while hi < len(prev) and prev[hi][0] < t:
                while dq and prev[dq[-1]][1] <= prev[hi][1]:
                    dq.pop()
                dq.append(hi)
                hi += 1
            while dq and prev[dq[0]][0] < t - window:
                dq.popleft()
            if dq:
                p = prev[dq[0]]
                best.append((t, p[1] + float(f.get("vector_score") or 0.0), p[2] + (f,)))
        if not best:
            return None
        prev = best

    return max(prev, key=lambda item: item[1])


def merge_temporal(
    per_box: Sequence[list[Frame]], window: float, topk: int
) -> list[Frame]:
    """Keep sequences where every box matches inside one video, in box order."""
    if not per_box or any(not frames for frames in per_box):
        return []

    common = set.intersection(*[{f.get("video_id") for f in box} for box in per_box])
    common.discard(None)
    if not common:
        return []

    n = len(per_box)
    sequences: list[tuple[float, tuple[Frame, ...]]] = []
    for vid in common:
        by_box = [
            sorted(
                (f for f in box if f.get("video_id") == vid),
                key=lambda f: float(f.get("pts_time") or 0.0),
            )
            for box in per_box
        ]
        chain = _best_chain(by_box, window)
        if chain is None:
            continue
        sequences.append((chain[1] / n, chain[2]))

    sequences.sort(key=lambda item: item[0], reverse=True)

    results: list[Frame] = []
    for score, chain_frames in sequences:
        head = chain_frames[0]
        sequence_id = f"{head.get('video_id')}:{head.get('frame_index')}"
        for position, frame in enumerate(chain_frames):
            frame["score"] = score
            frame["sequence_idx"] = position
            frame["sequence_id"] = sequence_id
            results.append(frame)
        if len(results) >= topk:
            break
    return _enrich_frames(results[:topk])


def multi_box_search(
    box_queries: Sequence[Box],
    temporal_window: float = 120.0,
    topk: int = 200,
    enhance: bool = True,
    mode: str = "parallel",
) -> list[Frame]:
    """Multi-box search.

    `parallel` unions the boxes and fuses them with RRF. `sequential` reads the
    boxes as consecutive shots of one scene and returns temporal chains.
    """
    if not box_queries:
        return []

    temporal = mode == "sequential"
    per_box, _ = _retrieve_boxes(box_queries, topk, enhance, two_stage=temporal)

    if temporal:
        return merge_temporal(per_box, temporal_window, topk)
    return merge_rrf(per_box, topk)
