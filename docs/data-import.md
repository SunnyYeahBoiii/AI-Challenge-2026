# Data Import Guide

This guide explains how to load the pre-computed MetaCLIP2 embeddings and
frame metadata into Milvus and Elasticsearch for FrameSeeker.

The importer does not run a CLIP model and does not generate embeddings. It
streams the existing metadata JSON and embedding ZIP archive, validates that
all rows are aligned, then writes the same frame records to both databases.

## Prerequisites

- Python 3.11 or newer
- [`uv`](https://docs.astral.sh/uv/) installed
- Milvus and Elasticsearch running
- The repository data files available under `data/`
- Enough disk space for the databases and existing media files

GPU is not required for importing because the embeddings have already been
computed.

## Data layout

The importer expects the following files by default:

```text
data/
├── embeddings/
│   └── metaclip2-worldwide-huge.zip
├── metadata/
│   └── concatenate-data.json
├── keyframes/
│   └── <level>/<video_id>/<frame>.webp
└── media-info/
    └── <video_id>.json
```

`concatenate-data.json` is a top-level JSON array. Each metadata record is
paired by position with one vector from the embedding archive. The record's
`clip_embeddings.index` must match that position.

The ZIP archive contains ordered NumPy chunks named like:

```text
embeddings-00000.npy
embeddings-00001.npy
...
```

Every chunk must contain `float32` vectors with the configured dimension. The
importer also verifies that every vector is finite and L2-normalized.

The current archive contains 152,856 vectors with dimension 1024.

## Start the databases

Start Milvus and Elasticsearch using the project's existing Docker Compose
setup:

```bash
docker compose up milvus elasticsearch -d
docker compose ps
```

Wait until both services are ready before running the importer.

## Configure the environment

Create the API environment file:

```bash
cd apps/api
cp .env.example .env
```

When running the importer directly from the host, use host-accessible service
URLs:

```dotenv
MILVUS_URI=http://localhost:19530
MILVUS_TOKEN=
ES_URL=http://localhost:9200
ES_USER=elastic
ES_PASS=
EMBEDDING_DIM=1024
MILVUS_BATCH_SIZE=8000
```

The Compose service names `milvus` and `elasticsearch` should be used only
when the importer itself runs inside the Compose network.

`DATA_ROOT` can be set when the data directory is not located at the
repository root:

```dotenv
DATA_ROOT=D:/path/to/AI-Challenge-2026/data
```

The importer also supports overriding individual paths with command-line
arguments.

## Install dependencies

```bash
cd apps/api
uv sync
```

## Validate the data without writing to databases

Run the full validation first:

```bash
uv run python scripts/load_data.py --validate-only
```

For a quick validation of only a few records:

```bash
uv run python scripts/load_data.py --limit 10 --dry-run
```

Validation checks include:

- metadata and embedding row counts
- contiguous embedding chunk names
- embedding dtype, dimension, finite values, and normalization
- `clip_embeddings.index` alignment
- keyframe file existence
- media-info file existence and YouTube URL lookup
- required frame timing information

Both options validate the inputs and exit without connecting to or modifying
Milvus or Elasticsearch.

## Import the data

Import all records:

```bash
cd apps/api
uv run python scripts/load_data.py

# Import từng batch
uv run python scripts/load_data.py --batch 1
uv run python scripts/load_data.py --batch 2

# Test nhanh - chỉ 100 records
uv run python scripts/load_data.py --limit 100

# Dry run - kiểm tra logic, không insert thật
uv run python scripts/load_data.py --dry-run --limit 50
```

Import a small sample without writing to the databases:

```bash
uv run python scripts/load_data.py --limit 10 --dry-run
```

The expected final message for the current dataset is:

```text
Import complete: 152,856 rows in Milvus and Elasticsearch.
```

The importer writes each batch to Milvus and Elasticsearch, prints the
processed row count and throughput, flushes Milvus, and refreshes the
Elasticsearch index before reporting completion.

## Command-line options

| Option | Description |
| --- | --- |
| `--metadata PATH` | Override `concatenate-data.json` |
| `--embeddings PATH` | Override the embedding ZIP archive |
| `--keyframes PATH` | Override the keyframe directory |
| `--media-info PATH` | Override the media-info directory |
| `--embedding-dim N` | Override `EMBEDDING_DIM` |
| `--batch-size N` | Override `MILVUS_BATCH_SIZE` |
| `--limit N` | Process only the first `N` aligned records |
| `--validate-only` | Validate inputs without database writes |
| `--dry-run` | Validate inputs without database writes |
| `--recreate` | Delete and recreate both database targets before importing |

For example:

```bash
uv run python scripts/load_data.py \
  --embeddings data/embeddings/metaclip2-worldwide-huge.zip \
  --embedding-dim 1024 \
  --batch-size 4000
```

## Database schema

### Milvus

The collection name is `data_frames`. Its schema is based on the main branch
schema, with the legacy `tags` field removed:

| Field | Type |
| --- | --- |
| `id` | `INT64`, primary key, auto-generated |
| `video_id` | `VARCHAR(64)` |
| `video_path` | `VARCHAR(500)` |
| `youtube_url` | `VARCHAR(500)` |
| `frame_index` | `INT64` |
| `frame_idx` | `INT64` |
| `frame_path` | `VARCHAR(500)` |
| `shot_idx` | `INT64` |
| `start_time` | `FLOAT` |
| `end_time` | `FLOAT` |
| `pts_time` | `FLOAT` |
| `fps` | `FLOAT` |
| `timestamp` | `FLOAT` |
| `embedding` | `FLOAT_VECTOR(EMBEDDING_DIM)` |

The vector index uses inner product (`IP`) with Milvus `AUTOINDEX`. Since the
vectors are normalized, inner product is equivalent to cosine similarity for
ranking.

The `tags` field is not stored in Milvus. Object/tag filtering is handled
separately by the application using the object-detection data.

### Elasticsearch

The index name is `video_texts`:

| Field | Type |
| --- | --- |
| `video_id` | `keyword` |
| `video_path` | `keyword` |
| `frame_id` | `integer` |
| `frame_idx` | `integer` |
| `frame_path` | `keyword` |
| `ocr_text` | `text` |
| `asr_text` | `text` |
| `timestamp` | `float` |

OCR is read from `ocr_text`. It is already normalized in the current metadata
export. ASR is read from `normalized_audio_text`; the raw `audio_text` field
is intentionally not indexed.

Each Elasticsearch document uses the stable ID:

```text
<video_id>/<frame_index>
```

This makes repeated imports overwrite the corresponding Elasticsearch
document instead of creating a new document ID.

## Re-importing data

Milvus uses an auto-generated primary key and the importer uses `insert`, so
running the importer again without `--recreate` adds duplicate Milvus rows.
Elasticsearch uses stable document IDs and will overwrite the matching frame
documents.

To rebuild both targets from scratch:

```bash
uv run python scripts/load_data.py --recreate
```

`--recreate` deletes the `data_frames` Milvus collection and the
`video_texts` Elasticsearch index. Use it only when a clean rebuild is
intended.

## Verify the import

Check the Elasticsearch document count:

```bash
curl -s http://localhost:9200/video_texts/_count | python -m json.tool
```

The expected count for the current dataset is `152856`.

Check the API health after starting the API service:

```bash
docker compose up api -d
curl -s http://localhost:5000/api/health | python -m json.tool
```

Test text search:

```bash
curl -s -X POST http://localhost:5000/api/search \
  -H "Content-Type: application/json" \
  -d '{"text":"red car","topk":5}' | python -m json.tool
```

The query-time embedding model must be the same model and preprocessing
pipeline that produced the stored MetaCLIP2 vectors. Matching vector
dimension alone is not sufficient.

## Troubleshooting

### Milvus connection refused

```bash
docker compose logs milvus --tail=50
docker compose ps
```

If the importer runs on the host, check that `MILVUS_URI` uses
`http://localhost:19530`, not the internal Compose hostname.

### Elasticsearch connection refused

```bash
docker compose logs elasticsearch --tail=50
curl -s http://localhost:9200/_cluster/health?pretty
```

### Existing schema does not match

The importer stops when an existing Milvus schema or Elasticsearch mapping
does not match the current definition. Confirm the intended configuration,
then use `--recreate` for a clean rebuild.

### Metadata and embeddings have different row counts

Run validation with the explicit paths and inspect the embedding archive:

```bash
uv run python scripts/load_data.py \
  --metadata data/metadata/concatenate-data.json \
  --embeddings data/embeddings/metaclip2-worldwide-huge.zip \
  --validate-only
```

The metadata array and the ordered embedding chunks must represent the same
number of frames and remain in the same order.

### Embedding dimension mismatch

Check the configured value:

```bash
uv run python scripts/load_data.py --validate-only --embedding-dim 1024
```

`EMBEDDING_DIM` must match both the stored vectors and the Milvus collection
schema. Query-time model output must use the same dimension as well.

### Import was interrupted

The importer does not provide resume semantics. For a clean retry, recreate
both targets before importing again:

```bash
uv run python scripts/load_data.py --recreate
```
