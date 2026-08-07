# Data Import Guide

Load pre-computed CLIP embeddings + metadata into Milvus (vector search) và Elasticsearch (full-text search).

## Prerequisites

- Docker Desktop running
- Python 3.11+ with `uv` installed
- Dữ liệu đã có trong `data/Data/Batch{1,2}/`

## Cấu trúc dữ liệu

```
data/
├── Data/
│   ├── Batch1/
│   │   ├── clip-embeddings-batch1-aic25.npy   # (N, 1024) float32 embeddings
│   │   └── concatenate-data.json               # metadata per frame
│   └── Batch2/
│       ├── clip-embeddings-batch2-aic25.npy
│       └── concatenate-data.json
├── keyframes/                                  # Ảnh keyframe .webp
└── media-info/                                 # JSON metadata YouTube per video
```

- **Milvus collection `data_frames`**: frame embeddings (1024-dim) + timing/tags metadata
- **Elasticsearch index `video_texts`**: OCR text + ASR text per frame (full-text search)

## Bước 1: Khởi động dịch vụ

```bash
docker compose up -d milvus elasticsearch
```

Đợi health checks (~30s):

```bash
docker compose ps
# milvus và elasticsearch phải ở trạng thái "healthy"
```

## Bước 2: Cấu hình Environment

File `apps/api/.env` đã có sẵn:

```
MILVUS_URI=http://localhost:19530
MILVUS_TOKEN=
ES_URL=http://localhost:9200
ES_USER=elastic
ES_PASS=
```

## Bước 3: Cài dependencies

```bash
cd apps/api
uv sync
```

## Bước 4: Import dữ liệu

```bash
cd apps/api

# Import cả 2 batch
uv run python scripts/load_data.py

# Import từng batch
uv run python scripts/load_data.py --batch 1
uv run python scripts/load_data.py --batch 2

# Test nhanh - chỉ 100 records
uv run python scripts/load_data.py --limit 100

# Dry run - kiểm tra logic, không insert thật
uv run python scripts/load_data.py --dry-run --limit 50
```

Output mẫu:

```
Connecting to Milvus at http://localhost:19530...
Milvus connected.
Collection 'data_frames' exists.
Connecting to Elasticsearch at http://localhost:9200...
Elasticsearch connected.
Index 'video_texts' exists.
Loaded 873 YouTube URL mappings.

Loading from Batch1...
  JSON: data/Data/Batch1/concatenate-data.json
  NPY: data/Data/Batch1/clip-embeddings-batch1-aic25.npy
  Loaded 17698 JSON records.
  Loaded 17698 embeddings with shape (17698, 1024).
  [1000] 1000 frames | 142.3 frames/s
  [2000] 2000 frames | 145.1 frames/s
  Done: 17698 records, 17698 frames in 123.4s
```

## Bước 5: Verify

```bash
# Kiểm tra Milvus
uv run python -c "
from dotenv import load_dotenv; load_dotenv('apps/api/.env')
from pymilvus import connections, Collection
connections.connect(uri='http://localhost:19530')
col = Collection('data_frames')
print(f'Entities: {col.num_entities}')
"

# Kiểm tra Elasticsearch
curl -s http://localhost:9200/video_texts/_count | python3 -m json.tool
```

Hoặc mở UI:
- **Attu** (Milvus): http://localhost:3001
- **Kibana** (ES): http://localhost:5601

## Checkpoint & Resume

Script tự động lưu checkpoint tại `apps/api/scripts/.load_checkpoint.json`. Records đã import sẽ bị bỏ qua khi chạy lại.

Để re-import toàn bộ:

```bash
rm apps/api/scripts/.load_checkpoint.json
```

Để xóa sạch data:

```bash
# Xóa Milvus collection
uv run python -c "
from pymilvus import connections, utility
connections.connect(uri='http://localhost:19530')
utility.drop_collection('data_frames')
print('Dropped data_frames')
"

# Xóa ES index
curl -X DELETE http://localhost:9200/video_texts
```

## Troubleshooting

| Vấn đề | Giải pháp |
|--------|-----------|
| Milvus connection refused | `docker compose logs milvus` — đợi health check hoặc port 19530 bị冲突 |
| ES connection refused | Kiểm tra `ES_URL` trong `.env`, `docker compose logs elasticsearch` |
| JSON/NPY count mismatch | Script tự cắt về min cả hai, xem log warning |
| Muốn thêm OCR/ASR text | Chạy `uv run python scripts/index_es.py` (tách riêng) |
| Muốn tạo index mới từ đầu | Thêm `recreate=True` vào `ensure_es_index()` |
| Duplicate frames | Xóa checkpoint + drop collection trước khi chạy lại |
