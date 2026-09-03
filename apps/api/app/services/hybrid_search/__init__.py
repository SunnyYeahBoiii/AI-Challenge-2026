"""Dense retrieval and post-filtering for single and temporal frame search.

Package layout (see docs/rules/clean-code.md — one reason to change per module):

- ``common`` — frame aliases, shared helpers, enrichment, keyword filtering.
- ``retrieval`` — single-query search and multi-box fan-out (parallel/sequential).
- ``temporal_paths`` — reachability flags and the best-path dynamic program.
- ``temporal_response`` — structured video/sequence response building.

Every temporal query box owns its raw Milvus Top-K and its enhancement, object,
OCR, and ASR settings. Parallel mode batches independent ANN requests into at
most three Top-K ranges. Sequential mode progressively restricts later ANN
requests to videos with a reachable predecessor. Both modes then retain nodes
on complete ordered paths and rank videos by their best dynamic-programming
path.
"""

from app.services import video_meta
from app.services.encoders import manager
from app.services.es_client import es_client
from app.services.hybrid_search.common import (
    FILTER_FETCH_CHUNK,
    TOPK_BUCKET_MAXIMA,
    Box,
    Frame,
    FrameKey,
    Vector,
    _enrich_frames,
    _filter_by_keywords,
)
from app.services.milvus_client import get_milvus_client
from app.services.hybrid_search.retrieval import (
    _apply_box_keywords,
    _box_vectors,
    _filter_only_candidates,
    _parallel_retrieve,
    _sequential_retrieve,
    search_image,
    search_similar_frames,
    search_text,
    search_video_frames,
)
from app.services.hybrid_search.temporal_response import (
    add_text_display_scores,
    build_temporal_response,
    multi_box_search,
)

__all__ = [
    "FILTER_FETCH_CHUNK",
    "TOPK_BUCKET_MAXIMA",
    "Box",
    "Frame",
    "FrameKey",
    "Vector",
    # Test patch seams: singletons and lookup helpers stay importable from the
    # hybrid_search namespace the tests monkeypatch against.
    "es_client",
    "get_milvus_client",
    "manager",
    "video_meta",
    "_apply_box_keywords",
    "_box_vectors",
    "_enrich_frames",
    "_filter_by_keywords",
    "_filter_only_candidates",
    "_parallel_retrieve",
    "_sequential_retrieve",
    "add_text_display_scores",
    "build_temporal_response",
    "multi_box_search",
    "search_image",
    "search_similar_frames",
    "search_text",
    "search_video_frames",
]
