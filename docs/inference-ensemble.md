# Inference and Ensemble Pipeline

This is the operational contract for FrameSeeker's image/text inference, multi-model
retrieval, RRF fusion and offline ablation workflow.

## 1. Model configuration

Models are declared in `apps/api/config/ensemble.json`. The DFN5B entry points to the
legacy `data_frames` collection so current deployments remain readable. SigLIP2,
MetaCLIP2, BEiT-3 Large, BGE-VL-Large and Perception Encoder are included but disabled
until their galleries have been encoded and indexed.

Each entry fixes:

- model id and adapter (`open_clip`, `huggingface`, `beit3`, `bge_vl` or `perception`);
- checkpoint/model name and optional revision;
- inference dtype when a checkpoint needs a tracked reduced-precision runtime;
- embedding dimension;
- Milvus collection;
- RRF weight;
- enabled state.

The optional Hugging Face checkpoints are pinned to immutable repository revisions.
BGE-VL-Large uses revision `40fb48217f521df22a2a5bf15edd52ed1146ef05`. BEiT-3 uses
Microsoft's official 384x384 COCO retrieval checkpoint and official SentencePiece model.
Both files are checked against pinned SHA-256 values before loading; the artifact manifest
records those hashes, tokenizer URL and image size. BEiT-3 and BGE-VL are MIT-licensed.
SigLIP2 is Apache-2.0; the configured MetaCLIP2 checkpoint is
CC-BY-NC-4.0, so confirm that the competition and any later deployment qualify before
enabling it.

Perception uses `PE-Core-L14-336` (1024 dimensions, 336 px) through the OpenCLIP/timm
conversion pinned at revision `8eff41b3f687e50a323662c2dda5eb3588c6dd35`; the 2.68 GB
checkpoint is verified against SHA-256
`b1fff7093c32a01d98a2d82098f9adf788b30f0efee639916520b3e4302f786b`. Its official
mean/std, bilinear interpolation and squash resize settings are applied. The two AIC
papers name Perception Encoder but do not disclose the exact PE variant/checkpoint. This
is therefore FrameSeeker's reproducible reconstruction, not a claimed unpublished detail.

Do not enable a model before its collection contains the same canonical Frame set as the
other enabled models. Do not compare a text embedding from one model to an image gallery
from another model.

Install model adapters and development tools:

```bash
cd apps/api
uv sync --extra models --extra dev
```

On Windows, the project pins the official PyTorch CUDA 13.0 index because PyPI's Windows
wheel is CPU-only. Verify GPU execution before starting a long gallery job:

```powershell
uv run --frozen python -c "import torch; print(torch.__version__, torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

The configured MetaCLIP2 Worldwide Huge checkpoint is approximately 7.4 GB in FP32, so
FrameSeeker loads it as tracked FP16 inference. The dtype is part of the artifact identity;
resume and Milvus loading reject an artifact created with a different dtype.

For a small GPU, process models one at a time. `embed_keyframes.py` unloads each completed
model before loading the next one.

The API container defaults to one Gunicorn worker because every worker owns an independent
model registry and therefore an independent copy of each loaded model. Increase
`GUNICORN_WORKERS` only when memory has been measured. Docker mounts `./data` read-only at
`/data` and keeps Hugging Face/Torch downloads in the persistent `model_cache` volume.

## 2. Canonical Frame manifest

JSONL is recommended for large datasets. A record can use the existing AIC metadata shape:

```json
{
  "file_path": "keyframes/L21/L21_V001/0007.webp",
  "video_path": "keyframes/L21/L21_V001",
  "youtube_url": "https://www.youtube.com/watch?v=example",
  "keyframe_info": {
    "frame_idx": 180,
    "shot_idx": 3,
    "start_time": 5.0,
    "end_time": 7.0,
    "pts_time": 6.0,
    "fps": 30.0
  },
  "OD_tags": ["person"],
  "RAM_tags": ["street"]
}
```

FrameSeeker normalizes this to:

- `frame_uid`: stable cross-model identity, for example `L21_V001:00000007`;
- `frame_index`: extracted image number (`0007`);
- `frame_idx`: original-video frame index supplied by metadata (`180`);
- `pts_time`: organizer/video timestamp in seconds.
- `youtube_url` (or input alias `watch_url`): optional playback URL preserved in every
  model artifact and Milvus collection.

Never replace supplied `frame_idx` with `round(pts_time * fps)` unless the source metadata
is unavailable and the original video is known to have constant frame rate.

## 3. Offline image inference

Encode one or more configured models:

```bash
cd apps/api
uv run python scripts/embed_keyframes.py \
  --input ../../data/manifests/frames.jsonl \
  --images-root ../../data \
  --output ../../data/ensemble-embeddings \
  --model dfn5b \
  --batch-size 64 \
  --shard-size 10000
```

Run the Top-2 visual models independently so VRAM is released between them:

```bash
uv run python scripts/embed_keyframes.py \
  --input ../../data/manifests/frames.jsonl \
  --images-root ../../data \
  --output ../../data/ensemble-embeddings \
  --model beit3-large-coco-retrieval-384 \
  --batch-size 1

uv run python scripts/embed_keyframes.py \
  --input ../../data/manifests/frames.jsonl \
  --images-root ../../data \
  --output ../../data/ensemble-embeddings \
  --model bge-vl-large \
  --batch-size 1

uv run python scripts/embed_keyframes.py \
  --input ../../data/manifests/frames.jsonl \
  --images-root ../../data \
  --output ../../data/ensemble-embeddings \
  --model metaclip2-worldwide-huge \
  --batch-size 1

uv run python scripts/embed_keyframes.py \
  --input ../../data/manifests/frames.jsonl \
  --images-root ../../data \
  --output ../../data/ensemble-embeddings \
  --model perception-core-l14-336 \
  --batch-size 1
```

Use `--resume` after an interrupted job. Every flushed shard updates `manifest.json`,
allowing restart at the last durable shard. Tune the conservative batch sizes upward
only after measuring available VRAM.

Each model artifact contains:

```text
ensemble-embeddings/<model-id>/
  manifest.json
  embeddings-00000.npy
  records-00000.jsonl
  embeddings-00001.npy
  records-00001.jsonl
```

The manifest records model/checkpoint identity, preprocessing identity, dimension,
collection, counts and SHA-256 checksums. The script refuses to overwrite a non-empty
artifact directory without `--resume`.

## 4. Load each gallery into Milvus

Dry-run validation first:

```bash
uv run python scripts/load_ensemble_embeddings.py \
  ../../data/ensemble-embeddings/beit3-large-coco-retrieval-384/manifest.json \
  --dry-run
```

Then preflight and load all model galleries together. The loader rejects the operation
before touching Milvus when their canonical `frame_uid` sets differ:

```bash
uv run python scripts/load_ensemble_embeddings.py \
  ../../data/ensemble-embeddings/beit3-large-coco-retrieval-384/manifest.json \
  ../../data/ensemble-embeddings/bge-vl-large/manifest.json \
  ../../data/ensemble-embeddings/metaclip2-worldwide-huge/manifest.json \
  ../../data/ensemble-embeddings/perception-core-l14-336/manifest.json
```

The loader verifies checksums and shapes before writing. It refuses to load the new column
format into a legacy or incomplete schema, rejects stale collection rows, and verifies the
final `frame_uid` set after every load. To migrate `data_frames`, first produce and verify a
complete DFN5B artifact, back up the old collection, and only then use the explicit
`--recreate` option. A safer rollout is to choose a new collection name, validate it, then
change the config.

## 5. Online retrieval and fusion

The API defaults `ENSEMBLE_MAX_LOADED_MODELS=1`. On the target 6 GB GPU, the registry
therefore loads and evicts encoders sequentially instead of retaining all four checkpoints
and causing an out-of-memory failure. Machines with enough VRAM may raise this value.
Keep `GUNICORN_WORKERS=1` when models share one GPU.

`POST /api/search` automatically uses every enabled model:

```json
{
  "text": "a person drops a pink bear keychain near a fruit stall",
  "topk": 20,
  "enhance": true,
  "ensemble": {
    "candidate_topk": 500,
    "rrf_k": 60,
    "preserve_original_query": true,
    "diversity_time_seconds": 2.0,
    "max_per_video": 5
  }
}
```

After all matching galleries have been loaded and the four models enabled, reproduce the
published model selections with a named profile:

```json
{
  "text": "a person drops a pink bear keychain near a fruit stall",
  "topk": 20,
  "ensemble": {
    "profile": "top2_2025",
    "candidate_topk": 500
  }
}
```

`top1_2025` selects BEiT-3 + MetaCLIP2 + Perception. `top2_2025` selects BEiT-3 +
BGE-VL-Large + MetaCLIP2 + Perception for text/image retrieval. The Top-2 paper does not
publish its RRF smoothing constant; FrameSeeker records `k=60` as a reproducible default.

The response keeps `results` for frontend compatibility and adds `meta` with model ids,
source ids, Query variants and partial-model errors. Every Frame includes `fusion_score`,
`model_ranks` and `model_scores` when ensemble retrieval is used.

Weighted RRF can be tested per request:

```json
{
  "ensemble": {
    "model_weights": {
      "dfn5b": 1.0,
      "siglip2-so400m-384": 1.2
    }
  }
}
```

Weights must come from validation. Keep all weights at `1.0` for the baseline.

## 6. Image feedback / composed retrieval

`POST /api/search/composed` is multipart form data:

- `original_text`: original Query intent;
- `feedback_text`: requested change to the selected Frame;
- `text`: legacy single-text input, supported when the two fields above are absent;
- `image`: user-selected relevant Frame;
- `text_weight`: default `0.75`;
- `topk`: final result count;
- `ensemble`: optional JSON object with the controls above.

For the Top-1 profile, BEiT-3, MetaCLIP2 and Perception encode the feedback text
without prepending the original query, then compute the published baseline:

`f_composed = text_weight * f_text + (1 - text_weight) * f_image`

The `top2_2025` composed profile selects BGE-VL-Large, reconstructs the text as
`original query + feedback text`, and calls the model's native joint input
`{"image": selected_frame, "text": reconstructed_query}`. This preserves the original
context described in the paper instead of searching from feedback text alone. The response
records `originalQuery`, `feedbackText`, `contextQuery`, and the actual `encodedText` in
`meta.compositionInput`, plus the encoder path in
`meta.compositionModes`.

Custom model selections remain supported: BGE-VL uses the native 768-dimensional joint
embedding, while other dual encoders use the linear fallback. Retrieval always happens in
the matching model gallery; embeddings from different models are never mixed.

## 7. Reproducible evaluation and ablation

Create a held-out Query JSONL:

```json
{"query_id":"q1","text":"a red-shirted man eats alone","query_class":"entity-action"}
```

Generate independent model runs:

```bash
uv run python scripts/generate_retrieval_runs.py \
  --queries validation/queries.jsonl \
  --output validation/runs.jsonl \
  --model dfn5b \
  --model siglip2-so400m-384 \
  --top-k 1000
```

Ground truth format:

```json
{"query_id":"q1","relevant_frame_uids":["L21_V001:00000007"]}
```

Evaluate every non-empty model subset with the production RRF implementation:

```bash
uv run python scripts/evaluate_ensemble.py \
  --ground-truth validation/ground-truth.jsonl \
  --runs validation/runs.jsonl \
  --rrf-k 60 \
  --recall-at 1 5 10 \
  --output validation/ablation.json
```

The report contains Recall@K, MRR and mAP. `generate_retrieval_runs.py` also records text
encoding and ANN-search latency per model. Compare at least:

1. each model alone;
2. equal-weight RRF for each pair;
3. all enabled models;
4. original Query only versus original + enhanced;
5. RRF `k` and candidate Top-K;
6. surveillance versus sousveillance and each Query class.

Only promote a model or weight when its gain survives held-out evaluation. Fine-tuning is a
later experiment after zero-shot baselines identify a repeatable domain error.

## 8. Failure policy

Online retrieval defaults to partial-model tolerance: a failed optional model is reported in
`meta.errors`, while healthy model rankings still produce results. Set
`allow_partial_models=false` during validation or correctness checks so any missing model or
collection fails the Query.
