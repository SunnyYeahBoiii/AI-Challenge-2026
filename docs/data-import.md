# Data Import Guide

How to load keyframe data into Milvus (embeddings) and Elasticsearch (metadata) for the FrameSeeker search system.

## Prerequisites

- Docker Desktop running
- Python 3.11+ with `uv` installed
- ~20 GB disk space (35k keyframe images + database storage)
- GPU optional but recommended (CPU works but is ~10x slower)

## Architecture

```
data/
├── keyframes/keyframes/{L21-L24}/{video_id}/*.webp   → CLIP embed → Milvus
├── map_keyframes/map_keyframes/{L21-L24}/{video_id}.csv  → frame metadata → Milvus
└── media-info-aic25-b1/media-info/{video_id}.json       → video metadata → Elasticsearch
```

- **Milvus collection `keyframes`**: 35,396 frame embeddings (1024-dim) + shot/timing metadata
- **Elasticsearch index `videos`**: 873 video metadata docs (title, description, keywords)

## Step 1: Start databases

```bash
docker compose up milvus elasticsearch -d
```

Wait for health checks (~30s):

```bash
docker compose ps  # both should show "healthy"
```

## Step 2: Configure environment

```bash
cd apps/api
cp .env.example .env
```

`.env` should contain:

```
MILVUS_URI=http://localhost:19530
MILVUS_TOKEN=
ES_URL=http://localhost:9200
ES_USER=elastic
ES_PASS=
OPENAI_API_KEY=
SECRET_KEY=dev-secret-key
FLASK_ENV=development
```

## Step 3: Install Python dependencies

```bash
cd apps/api
uv sync
```

## Step 4: Run data loading

```bash
uv run python scripts/load_data.py
```

Expected output:

```
Loading CLIP model on cpu...
CLIP model loaded.
Connecting to Milvus at http://localhost:19530...
Milvus connected.
Created collection 'keyframes'.
Connecting to Elasticsearch at http://localhost:9200...
Elasticsearch connected.
Created index 'videos'.

Found 873 videos to process.

[1/873] L21_V001: 525 frames | 525 total embedded | 1.2 frames/s
[2/873] L21_V002: 312 frames | 837 total embedded | 1.1 frames/s
...
Done! 35396 frames loaded in 2847.3s
  Milvus collection: keyframes (35396 entities)
  ES index: videos
```

Timing estimate:
- GPU (M1/M2/CUDA): ~15-30 minutes
- CPU: ~30-60 minutes

## Step 5: Verify

```bash
# Check Milvus
curl -s http://localhost:19530/v2/vectordb/collections/list | python3 -m json.tool

# Check Elasticsearch
curl -s http://localhost:9200/videos/_count | python3 -m json.tool
# Should return: {"count": 873}

# Test search (after starting API)
docker compose up api -d
curl -s -X POST http://localhost:5000/api/search \
  -H "Content-Type: application/json" \
  -d '{"text": "red car", "topk": 5}' | python3 -m json.tool
```

## Troubleshooting

**Milvus connection refused**
```bash
docker compose logs milvus | tail -20
# Common: port 19530 already in use → stop other milvus container
```

**Elasticsearch yellow status**
```bash
curl -s http://localhost:9200/_cluster/health?pretty
# yellow = single node (normal), red = disk space issue
```

**CLIP model download fails**
```bash
# Model downloads to ~/.cache/huggingface on first run
# If behind proxy, set HF_ENDPOINT before running:
export HF_ENDPOINT=https://hf-mirror.com
```

**Out of memory on CPU**
- Reduce `BATCH_SIZE` in `scripts/load_data.py` (default 64, try 16)
- Script processes one video at a time, so memory usage is bounded by largest video

**Resume after partial run**
- Milvus auto-increments IDs, duplicate frames get new IDs
- For clean re-run: delete collection first
```bash
uv run python -c "
from pymilvus import connections, utility
connections.connect(uri='http://localhost:19530')
utility.drop_collection('keyframes')
print('Dropped.')
"
```
