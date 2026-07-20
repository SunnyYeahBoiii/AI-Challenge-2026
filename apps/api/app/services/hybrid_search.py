from app.services.milvus_client import get_milvus_client
from app.services.es_client import es_client
from app.services.embed import embed_text, embed_image, enhance_query


def _enrich_frames(milvus_frames):
    """Enrich Milvus results with video metadata from ES."""
    video_ids = list({f["video_id"] for f in milvus_frames if f.get("video_id")})
    video_cache = {}
    for vid in video_ids:
        video = es_client.get_video(vid)
        if video:
            video_cache[vid] = video
    for f in milvus_frames:
        vid = f.get("video_id", "")
        meta = video_cache.get(vid, {})
        f["title"] = meta.get("title", "")
        f["description"] = meta.get("description", "")
        f["keywords"] = meta.get("keywords", [])
        f["watch_url"] = f.get("youtube_url") or meta.get("watch_url", "")
        f["thumbnail_url"] = f"/api/keyframes/{vid}/{f.get('frame_index', 0)}"
    # Deduplicate by (video_id, frame_index)
    seen = set()
    deduped = []
    for f in milvus_frames:
        key = (f.get("video_id"), f.get("frame_index"))
        if key not in seen:
            seen.add(key)
            deduped.append(f)
    return deduped


def search_text(query="", tags=None, keywords=None, topk=20, enhance=True):
    """Text hybrid search: enhance -> embed -> Milvus -> ES filter."""
    if enhance and query:
        query = enhance_query(query)
    if not query and not tags and not keywords:
        return []
    vec = embed_text([query])[0].tolist() if query else None

    exprs = []
    if tags:
        for tag in tags:
            exprs.append(f'tags like "%{tag}%"')

    if vec:
        milvus = get_milvus_client()
        milvus_frames = milvus.search(vec, topk=topk * 2, expr=exprs[0] if len(exprs) == 1 else None)
    else:
        milvus_frames = []
    frames = _enrich_frames(milvus_frames)
    if keywords and frames:
        video_ids = list({f["video_id"] for f in frames})
        matched_ids = es_client.filter_videos_by_keywords(video_ids, keywords, mode="and")
        frames = [f for f in frames if f["video_id"] in matched_ids]
    frames.sort(key=lambda f: f["vector_score"], reverse=True)
    return frames[:topk]


def search_image(image_bytes, tags=None, keywords=None, topk=20):
    """Image hybrid search: embed -> Milvus -> ES filter."""
    vec = embed_image(image_bytes).tolist()
    milvus = get_milvus_client()
    milvus_frames = milvus.search(vec, topk=topk * 2)
    frames = _enrich_frames(milvus_frames)
    if keywords and frames:
        video_ids = list({f["video_id"] for f in frames})
        matched_ids = es_client.filter_videos_by_keywords(video_ids, keywords, mode="and")
        frames = [f for f in frames if f["video_id"] in matched_ids]
    frames.sort(key=lambda f: f["vector_score"], reverse=True)
    return frames[:topk]


def search_video_frames(video_id, frame_index=None, range=5):
    """Get frames for a video, optionally filtered by position ± range around frame_index."""
    milvus = get_milvus_client()
    expr = f'video_id == "{video_id}"'
    try:
        milvus_frames = milvus.search([0.0] * 1024, topk=10000, expr=expr)
    except Exception:
        return []
    for f in milvus_frames:
        del f["vector_score"]
    frames = _enrich_frames(milvus_frames)
    frames.sort(key=lambda f: f.get("frame_index", 0))
    if frame_index is None:
        return frames
    pos = next((i for i, f in enumerate(frames) if f.get("frame_index") == frame_index), None)
    if pos is None:
        return frames
    return frames[max(0, pos - range):pos + range + 1]


def search_similar_frames(video_id, frame_index, topk=12):
    milvus = get_milvus_client()
    embedding = milvus.get_frame_embedding(video_id, frame_index)
    if embedding is None:
        return []
    milvus_frames = milvus.search(embedding, topk=topk + 1)
    milvus_frames = [
        f for f in milvus_frames
        if not (f.get("video_id") == video_id and f.get("frame_index") == frame_index)
    ][:topk]
    for f in milvus_frames:
        f["score"] = f.pop("vector_score")
    frames = _enrich_frames(milvus_frames)
    frames.sort(key=lambda f: f.get("score", 0), reverse=True)
    return frames


def _merge_temporal_sequences(per_box, window):
    """Temporal merge: find videos in ALL boxes, enforce time window."""
    box_sets = [set(f["video_id"] for f in box) for box in per_box]
    common = set.intersection(*box_sets) if box_sets else set()
    results = []
    for vid in common:
        groups = []
        for box_idx, box in enumerate(per_box):
            groups.append([f for f in box if f["video_id"] == vid])
        seqs = [[g[0]] for g in groups if g]
        for _ in range(10):
            changed = False
            for bi in range(1, len(seqs)):
                prev = seqs[bi - 1][-1]
                best = None
                for f in seqs[bi]:
                    diff = abs(f.get("pts_time", 0) - prev.get("pts_time", 0))
                    if diff <= window and (best is None or diff < abs(best.get("pts_time", 0) - prev.get("pts_time", 0))):
                        best = f
                if best:
                    seqs[bi] = [best]
                else:
                    changed = True
            if not changed:
                break
        if all(seqs):
            score = sum(s[0].get("vector_score", 1.0) for s in seqs) / len(seqs)
            for s in seqs:
                s[0]["score"] = score
                s[0]["sequence_idx"] = seqs.index(s)
                results.append(s[0])
    results.sort(key=lambda f: f.get("score", 0), reverse=True)
    return results


def multi_box_search(box_queries, temporal_window=120.0, topk=200, enhance=True):
    """Multi-box temporal search."""
    if not box_queries:
        return []

    per_box = []
    for box in box_queries:
        text = box.get("text", "")
        image = box.get("image", "")
        if text:
            frames = search_text(
                query=text,
                tags=box.get("tags"),
                keywords=box.get("keywords"),
                topk=box.get("topk", topk),
                enhance=box.get("enhance") if box.get("enhance") is not None else enhance,
            )
            per_box.append(frames)
        elif image:
            import base64
            image_bytes = base64.b64decode(image)
            frames = search_image(
                image_bytes=image_bytes,
                tags=box.get("tags"),
                keywords=box.get("keywords"),
                topk=box.get("topk", topk),
            )
            per_box.append(frames)

    if len(per_box) <= 1:
        return per_box[0] if per_box else []

    results = _merge_temporal_sequences(per_box, temporal_window)
    return results[:topk]
