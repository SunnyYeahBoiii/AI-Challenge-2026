# 0002: Multi-model retrieval with reciprocal-rank fusion

## Status

Accepted.

## Context

FrameSeeker originally encoded every Frame and Query with one OpenCLIP DFN5B model and
searched one Milvus collection (`data_frames`). The AIC retrieval papers show that models
with different strengths can improve recall when their independent rankings are fused.
Their raw cosine/IP scores are not calibrated, and embeddings from different models are
not compatible with each other.

## Decision

- Give every Frame a canonical `frame_uid` derived from `video_id` and extracted
  `frame_index`. Preserve the organizer-facing `frame_idx` and `pts_time` separately.
- Store one complete gallery and one Milvus collection per embedding model.
- Encode a Query only with the text tower paired with each model's image tower.
- Retrieve Top-K independently from every model/Query-variant source.
- Fuse sources with weighted reciprocal-rank fusion:

  `score(d) = sum(weight(source) / (rrf_k + rank(source, d)))`

- Use `rrf_k = 60` as the baseline from the reviewed systems. Tune it and model weights
  only on a held-out validation set.
- Keep original and enhanced Query rankings. Split a model's total weight equally across
  its Query variants so adding a rewrite does not silently double-count that model.
- Compose text and selected-image feedback inside each model's own joint embedding space,
  using text weight `0.75` by default, before applying RRF across models.
- Keep the legacy `data_frames` collection readable. New artifact loading requires the
  canonical `frame_uid` schema; migration of the legacy collection must be explicit.

## Consequences

- Adding a model requires re-encoding the entire Frame gallery and provisioning a new
  collection, but no retraining is required for the initial zero-shot baseline.
- Storage and offline inference costs scale approximately linearly with model count.
- RRF is robust to incompatible score scales and missing results, while model-specific raw
  scores remain available for diagnostics.
- Model contribution is measurable through single-model and all-subset ablations using the
  same production fusion implementation.
- Model configuration, preprocessing, dimensions and collection names are versioned in
  `apps/api/config/ensemble.json`.

