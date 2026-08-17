# 0003: Multi-Box Search Pipeline

> **Amended 2026-08:** the RRF fusion described below for `parallel` mode was
> never shipped. Both modes now share the same merge: retain frames that sit on
> complete ordered paths and rank videos by their best dynamic-programming path
> (see `app/services/hybrid_search/temporal_response.py`). The modes differ
> only in retrieval — `parallel` retrieves boxes independently (bucketed into
> at most three concurrent Milvus batches by Top-K range); `sequential`
> restricts each later box to videos with a reachable predecessor result.

Both multi-box modes share one fan-out stage — concurrent query enhancement, a single CLIP forward pass, one Milvus RPC per distinct filter expression, one Elasticsearch keyword query, in-memory enrichment — and differ only in how they retrieve the per-box hit lists (see amendment above for the merge).

**Considered alternatives:**

- **Per-box round-trips (the previous shape)** — `_parallel_search` ran a serial list comprehension, so N boxes cost N enhancement round-trips, N CLIP forward passes and N Milvus RPCs. `_sequential_search` was worse: it re-ranked inside the previous box's results by building a Milvus expression with one `(video_id == … and frame_index == …)` clause per candidate frame. Rejected: latency grew linearly in box count for work the backends batch natively.
- **Raw score union for `parallel`** — CLIP inner-product scores are not calibrated across different queries, so a box with an "easy" query dominated the entire ranking regardless of agreement between boxes. Rejected in favour of within-video best-path scoring (sum of per-box similarities along the chain, averaged over boxes).
- **Progressive narrowing for `sequential`** — keeping the old "each box filters within the previous box's results" semantics. Rejected: it answers a different question (one frame matching every description) than the competition's TRAKE tasks (a sequence of distinct shots), and `_merge_temporal_sequences` was already written for the latter but never wired up.
- **One-stage recall for temporal chains** — a single large-`limit` search per box, then intersect. Rejected: recall is bounded by the weakest box, and a video whose shot for box 2 falls outside that box's top-K disappears entirely. Two stages instead: find candidate videos, then re-search *inside* those videos with `video_id in [...]`, which is also cheaper per RPC because the ANN scan is bounded.
- **Video-level keyword filtering** — the previous code matched keywords against an Elasticsearch `tags` field that the `video_texts` mapping does not define (so every keyword query returned nothing) and joined on `video_id` alone. Both sides are frame-level now: `ocr_text`/`asr_text` matched per frame and joined on `(video_id, frame_id)`.

**Consequences:**

- Milvus applies a single expression to a whole `nq > 1` batch, so boxes are grouped by their tag filter. Boxes with differing tags cost one RPC per distinct expression; the common case (no tags, or the same tags everywhere) is one RPC for the request.
- Tag filtering uses `array_contains_all` / `array_contains_any` — the `tags` field is `ARRAY<VARCHAR>`, which `like "%…%"` does not address. `tag_match_mode` is now honoured instead of silently dropping every tag past the first.
- Video metadata comes from an in-process cache of `data/media-info/*.json` (`app/services/video_meta.py`), not Elasticsearch. The index stores frame text only, so the old per-video lookup paid a round-trip to read empty strings. `title`, `description`, `keywords`, `author` and `publish_date` are populated for the first time as a side effect.
- Request threads share the CLIP model and the Milvus connection, so both lazy singletons are lock-guarded (double-checked, `embed._model_lock` and `milvus_client._client_lock`); two concurrent cold requests cannot each load the model. `create_app()` is pure wiring — nothing is loaded at startup, so the first search of a process pays for the model load (~38s on CPU) and `Collection.load()`. `scripts/bench_search.py` calls `embed.warmup()` / `milvus_client.warmup()` explicitly to keep that cost out of its measurements.
- Query-time encoding uses `hf-hub:apple/DFN5B-CLIP-ViT-H-14-384`, the checkpoint that produced the pre-computed `.npy` embeddings — verified by re-encoding stored keyframes and recovering their indexed vectors at cosine 1.0000. The previous `ViT-H-14`/`dfn5b` (224px) build reached only 0.92, so every query landed slightly off the region of the space the index occupies; nothing errored and the degradation was invisible. `Config.MODEL_ID` had named the right checkpoint all along but nothing read it, so the constant now lives in one place (`app/config.py`) and `embed.py` imports it.
- The 384px checkpoint is ~4GB and is fetched from the Hugging Face hub on first use. Nothing in the test suite constructs the model, and neither `apps/api/Dockerfile` nor the `api` service in `docker-compose.yml` pre-fetches it or mounts a cache volume — so in a fresh container the first query pays the download *and* the model load, serially, with no warmup to hide it. Mount `HF_HOME` (or bake the weights into the image) before running in Docker at competition.
- Every search path now sets `score`; the multi-box paths previously set only `vector_score`, which the frontend does not read — result sorting and the score badge were silently broken.
- Each video's result carries one `best_sequence` (with a `sequence_id` of `video:frame-ids` and per-frame `query_index` marking which box matched). Chains are strictly forward in time; consecutive gaps must stay within `temporal_window_seconds`.
- Chain selection is a dynamic program with a monotonic-deque sliding-window maximum, so it stays linear in pool size. A naive pairwise scan is quadratic and does not survive a 500-frame-per-box recall pool across dozens of candidate videos.
- A box carrying tags but no text or image is answered with a scalar `query()` instead of an ANN search — it contributes membership to the path, not ordering, so its `vector_score` is 0. Previously such a box returned nothing at all, silently. Keywords alone still do not constitute a query: they narrow an existing hit set, so the frontend keeps requiring text or tags per box.
- Elasticsearch keyword matching pages at `ES_MAX_KEYWORD_HITS` (default 10000). Hitting the page size now logs a warning; truncation is otherwise indistinguishable from "the keyword matched nothing".
- `enhance_query` results are cached in-process (successes only) and enhanced concurrently with a 5s timeout. A hung OpenAI call no longer hangs the whole request.

**Benchmarking:** `uv run python scripts/bench_search.py --boxes 3 --mode sequential` reports per-stage p50/p95 against a live Milvus. The round-trip reduction above is counted from the code, not measured — no run against live infrastructure has been recorded yet.
