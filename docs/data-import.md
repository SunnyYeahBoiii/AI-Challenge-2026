# Nhập dữ liệu Batch1 vào Milvus và Elasticsearch

Tài liệu này hướng dẫn nạp dữ liệu frame của AI Challenge 2026 từ `data/Data/Batch1/` vào hai hệ thống tìm kiếm của FrameSeeker:

- **Milvus** lưu embedding MetaCLIP và metadata frame, phục vụ tìm kiếm ngữ nghĩa theo text hoặc ảnh.
- **Elasticsearch** lưu OCR và ASR theo frame, phục vụ tìm kiếm từ khóa toàn văn.

Script chính là [`apps/api/scripts/load_data.py`](../apps/api/scripts/load_data.py). Script nạp cả hai hệ thống trong cùng một lượt để các bản ghi được căn chỉnh theo cùng `video_id` và `frame_index`.

> [!IMPORTANT]
> Script hiện chỉ hỗ trợ **Batch1**. Không có tham số `--batch`; các ví dụ cũ dùng Batch2 hoặc `--batch` không còn đúng.

## 1. Dữ liệu nguồn và điều kiện căn chỉnh

Script yêu cầu đủ ba nhóm file sau:

```text
data/
└── Data/
    └── Batch1/
        ├── concatenate-data.json
        ├── embeddings/
        │   ├── embeddings-00000.npy
        │   ├── embeddings-00001.npy
        │   └── ...                         # hiện có 146 shard
        └── records/
            ├── records-00000.jsonl
            ├── records-00001.jsonl
            └── ...                         # hiện có 146 shard
```

### Quy tắc căn chỉnh

`concatenate-data.json` là danh sách metadata theo frame. Embedding tại chỉ số `i` trong danh sách này được lấy từ:

```text
embeddings-{i // 1000:05d}.npy, hàng i % 1000
```

Mỗi shard embedding thường có 1.000 vector. Script kiểm tra tổng số hàng của toàn bộ `.npy` phải bằng số record JSON; nếu khác nhau, import dừng ngay với lỗi `JSON/embedding count mismatch`.

`records/*.jsonl` cung cấp `youtube_url`, được nối với metadata qua khóa:

```text
{video_id}:{frame_idx:08d}
```

Trong đó `video_id` là phần cuối của `video_path`, còn `frame_idx` lấy từ `keyframe_info.frame_idx`.

### Kiểm tra nhanh trước khi import

Chạy từ thư mục gốc repository:

```powershell
Get-ChildItem data\Data\Batch1\embeddings -Filter "embeddings-*.npy" | Measure-Object
Get-ChildItem data\Data\Batch1\records -Filter "records-*.jsonl" | Measure-Object

cd apps\api
uv run python scripts/load_data.py --dry-run --limit 10
```

`--dry-run` vẫn đọc JSON, JSONL và embedding để kiểm tra cấu trúc/căn chỉnh, nhưng không kết nối và không ghi vào Milvus hoặc Elasticsearch.

## 2. Dữ liệu được tạo ra

### Milvus

Collection đích là `data_frames_metaclip`, lấy từ `MetaClipEncoder.collection_name`. Embedding MetaCLIP-2 có **1.024 chiều**, dùng chỉ mục `AUTOINDEX` với metric `IP` (inner product).

Mỗi frame có các trường chính:

| Trường | Nguồn |
| --- | --- |
| `video_id`, `video_path`, `youtube_url` | `video_path` và JSONL record |
| `frame_index`, `frame_idx`, `frame_path` | `keyframe_info` và `file_path` |
| `shot_idx`, `start_time`, `end_time`, `pts_time`, `fps`, `timestamp` | `keyframe_info` |
| `tags` | hợp nhất `OD_tags` và `RAM_tags`, tối đa 100 tag, mỗi tag tối đa 32 ký tự |
| `embedding` | vector từ shard `.npy` tương ứng |

Collection sử dụng khóa chính `id` tự tăng. Vì vậy script không upsert theo frame key.

### Elasticsearch

Index đích là `video_texts`. Mỗi document biểu diễn một frame với các trường:

| Trường | Cách tạo |
| --- | --- |
| `video_id` | phần cuối của `video_path` |
| `video_path`, `frame_path` | từ `file_path` |
| `frame_id` | tên file keyframe, bỏ phần mở rộng, ví dụ `000123.webp` → `123` |
| `frame_idx`, `timestamp` | từ `keyframe_info` |
| `ocr_text` | `ocr_text` từ JSON |
| `asr_text` | `audio_text` từ JSON |

Trước khi ghi, text được chuyển thường và gom whitespace. Mapping từ [`es_schema.py`](../apps/api/app/services/es_schema.py) sau đó áp dụng analyzer `vietnamese_folded` cho **cả index và search** ở `ocr_text` và `asr_text`. Analyzer này dùng `standard`, `lowercase` và `asciifolding`, do đó truy vấn tiếng Việt không dấu vẫn khớp với dữ liệu có dấu.

Khi index `video_texts` đã tồn tại, script so sánh mapping thực tế với mapping ứng dụng. Nếu analyzer hoặc field không khớp, script dừng và yêu cầu tạo lại index trước khi tiếp tục, tránh trộn dữ liệu có analyzer khác nhau.

## 3. Chuẩn bị môi trường

### 3.1 Khởi động database

Từ thư mục gốc repository:

```powershell
docker compose up -d milvus elasticsearch
docker compose ps
```

Chỉ tiếp tục khi cả `milvus` và `elasticsearch` ở trạng thái `healthy`. Có thể xem log khi cần:

```powershell
docker compose logs --tail 100 milvus
docker compose logs --tail 100 elasticsearch
```

### 3.2 Cấu hình `.env` cho import trên máy host

`load_data.py` được thiết kế để chạy từ **host** tại `apps/api`; Docker Compose hiện không mount `data/Data/Batch1/` hoặc `apps/api/scripts/` vào container API. Vì vậy địa chỉ database trong `apps/api/.env` phải trỏ tới port được publish trên host:

```dotenv
MILVUS_URI=http://localhost:19530
MILVUS_TOKEN=
ES_URL=http://localhost:9200
ES_USER=
ES_PASS=
```

Các giá trị `http://milvus:19530` và `http://elasticsearch:9200` trong `.env.example` là hostname dành cho container `api` trong Docker Compose, không dùng được khi chạy script trực tiếp trên host.

### 3.3 Cài dependency Python

```powershell
cd apps\api
uv sync
```

Bạn cần Python 3.11 trở lên và `uv`. Không cần khởi động API web để thực hiện import.

## 4. Chạy import

### Chạy lần đầu

```powershell
cd apps\api
uv run python scripts/load_data.py
```

Quy trình thực hiện:

1. Kết nối Milvus và tạo `data_frames_metaclip` nếu chưa tồn tại.
2. Kết nối Elasticsearch và tạo `video_texts` nếu chưa tồn tại.
3. Đọc toàn bộ metadata, kiểm tra số record và số embedding.
4. Đọc URL YouTube từ các file JSONL.
5. Nạp embedding vào Milvus theo batch 8.000 frame.
6. Nạp document OCR/ASR vào Elasticsearch theo batch 1.000 document, dùng `refresh="wait_for"`.
7. Flush Milvus và ghi checkpoint sau khi chạy xong.

### Import thử một phần dữ liệu

```powershell
cd apps\api
uv run python scripts/load_data.py --limit 100
```

`--limit` giới hạn số record **mới** được xử lý trong lượt chạy. Nó phù hợp để smoke test, nhưng không phải cơ chế nạp từng batch dữ liệu.

### Dry run

```powershell
cd apps\api
uv run python scripts/load_data.py --dry-run --limit 100
```

Dry run không tạo collection/index, không kết nối database, không ghi checkpoint và không insert dữ liệu. Đây là lệnh nên chạy đầu tiên khi thay đổi dữ liệu nguồn hoặc script.

## 5. Checkpoint, resume và import lại

Checkpoint nằm tại:

```text
apps/api/scripts/.load_checkpoint.json
```

File ghi danh sách `file_path` đã xử lý. Khi chạy lại bình thường, script bỏ qua các path có trong checkpoint.

> [!WARNING]
> Checkpoint chỉ được lưu sau khi toàn bộ lượt import hoàn tất. Nếu tiến trình bị dừng giữa chừng, checkpoint chưa phản ánh phần đã insert. Chạy lại có thể tạo duplicate trong Milvus và Elasticsearch vì cả hai nơi không dùng idempotent document ID theo frame.

### Resume sau khi chạy xong

Chỉ cần chạy lại cùng lệnh. Những frame đã có trong checkpoint sẽ bị bỏ qua.

### Chạy lại toàn bộ Batch1

Chỉ làm khi bạn chủ động tạo lại **cả hai** storage. Xóa checkpoint đơn lẻ rồi chạy script sẽ chèn duplicate.

1. Dừng API để không có truy vấn đồng thời.
2. Xác nhận chính xác tên target là `data_frames_metaclip` và `video_texts`.
3. Xóa collection, index và checkpoint.
4. Chạy import từ đầu.

Ví dụ PowerShell (lệnh xóa là không thể hoàn tác):

```powershell
cd apps\api
uv run python -c "from pymilvus import connections, utility; connections.connect(uri='http://localhost:19530'); utility.drop_collection('data_frames_metaclip'); print('Dropped data_frames_metaclip')"
Invoke-RestMethod -Method Delete http://localhost:9200/video_texts
Remove-Item -LiteralPath scripts\.load_checkpoint.json
uv run python scripts/load_data.py
```

Nếu collection hoặc index không tồn tại, hãy kiểm tra tên/endpoint thay vì bỏ qua lỗi một cách mù quáng.

## 6. Kiểm tra sau import

### Kiểm tra số document Elasticsearch

```powershell
Invoke-RestMethod http://localhost:9200/video_texts/_count
Invoke-RestMethod http://localhost:9200/video_texts/_mapping | ConvertTo-Json -Depth 20
```

`count` nên tương ứng với số record có `file_path` hợp lệ trong `concatenate-data.json`. Mapping của `ocr_text` và `asr_text` phải có analyzer `vietnamese_folded`.

### Kiểm tra Milvus

```powershell
cd apps\api
uv run python -c "from pymilvus import connections, Collection; connections.connect(uri='http://localhost:19530'); collection=Collection('data_frames_metaclip'); collection.load(); print({'name': collection.name, 'entities': collection.num_entities, 'schema': str(collection.schema)})"
```

Số entity Milvus và số document Elasticsearch thường bằng nhau sau import hoàn chỉnh. Nếu khác nhau, kiểm tra log import và số record có `file_path` hợp lệ trước khi chạy lại.

### Kiểm tra text thực tế trong Elasticsearch

```powershell
Invoke-RestMethod -Method Post http://localhost:9200/video_texts/_search -ContentType 'application/json' -Body '{"size":1,"_source":["video_id","frame_id","ocr_text","asr_text"],"query":{"exists":{"field":"ocr_text"}}}' | ConvertTo-Json -Depth 10
```

Để kiểm tra analyzer với câu có dấu/không dấu:

```powershell
Invoke-RestMethod -Method Post http://localhost:9200/video_texts/_analyze -ContentType 'application/json' -Body '{"analyzer":"vietnamese_folded","text":"Thủ tướng Việt Nam"}' | ConvertTo-Json -Depth 10
```

### Công cụ quan sát

- Attu (Milvus): <http://localhost:3001>
- Kibana (Elasticsearch): <http://localhost:5601>

Nếu cần chạy toàn bộ stack ứng dụng sau import:

```powershell
cd ..\..
pnpm dev
```

Hoặc:

```powershell
docker compose up --build
```

## 7. Sự cố thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `Cannot ping Elasticsearch` | `ES_URL` dùng hostname Docker khi script chạy trên host, hoặc ES chưa healthy | Dùng `http://localhost:9200`; kiểm tra `docker compose ps` và log ES. |
| Không kết nối được Milvus | `MILVUS_URI` sai hoặc Milvus chưa sẵn sàng | Dùng `http://localhost:19530`; chờ health check qua cổng 9091. |
| `Missing embeddings/ or records/ chunks` | Thiếu thư mục/file input | Khôi phục đủ `embeddings/` và `records/` của Batch1. |
| `JSON/embedding count mismatch` | JSON không cùng phiên bản với các shard `.npy` | Không import; dùng bộ dữ liệu được tạo cùng nhau. |
| Lỗi mapping Elasticsearch | `video_texts` được tạo bằng schema/analyzer cũ | Sao lưu nếu cần, xóa index, xóa checkpoint và import lại toàn bộ. |
| Số lượng bản ghi tăng bất thường sau chạy lại | Checkpoint bị xóa/mất hoặc tiến trình trước bị ngắt | Tạo lại đồng bộ collection + index + checkpoint; không chỉ import đè. |
| Vector dimension lỗi khi insert | Embedding không phải MetaCLIP 1.024 chiều | Kiểm tra shard bằng môi trường `uv`; phải dùng dữ liệu tương ứng với `MetaClipEncoder`. |
| API không trả kết quả vector sau import | Model active dùng collection khác | Trong Admin chọn model MetaCLIP hoặc cấu hình collection active là `data_frames_metaclip`. |

## 8. Giới hạn hiện tại

- Script chưa hỗ trợ lựa chọn Batch2 hoặc import nhiều batch bằng CLI.
- Import không idempotent theo frame; không chạy song song nhiều tiến trình loader trên cùng database.
- Script nạp dữ liệu từ filesystem host; chạy riêng trong container API hiện tại không có các mount dữ liệu cần thiết.
- Thay đổi analyzer trong `es_schema.py` yêu cầu tạo lại `video_texts` và reindex toàn bộ dữ liệu để analyzer lúc index/search nhất quán.
