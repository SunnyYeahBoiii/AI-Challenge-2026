# Inference + Ensemble — Bản ngắn gọn

FrameSeeker dùng nhiều model image-text để tìm keyframe. Mỗi model encode ảnh và câu query trong không gian embedding riêng, truy vấn Top-K riêng, sau đó kết hợp các bảng xếp hạng bằng Weighted RRF.

## Các model

| Model | Trạng thái | Tác dụng |
|---|---|---|
| **DFN5B CLIP ViT-H/14** | Đang bật | Model inference chính và baseline. Tìm kiếm text-to-image tốt, dimension 1024, dùng collection `data_frames`. |
| **SigLIP2 SO400M 384** | Đã cấu hình, chưa bật | Bổ sung góc nhìn khác cho câu query và hình ảnh, giúp tăng recall khi kết hợp với DFN5B. Dimension 1152. |
| **MetaCLIP2 Worldwide Huge** | Đã cấu hình, chưa bật | Bổ sung khả năng hiểu nội dung đa dạng và đa ngôn ngữ. Dimension 1024. Cần kiểm tra giấy phép trước khi sử dụng chính thức. |

## Cách ensemble hoạt động

```text
Query
  ├─ Encode bằng DFN5B   → Top-K DFN5B
  ├─ Encode bằng SigLIP2 → Top-K SigLIP2
  └─ Encode bằng MetaCLIP2 → Top-K MetaCLIP2
                           ↓
                    Weighted RRF
                           ↓
                  Kết quả cuối cùng
```

Không trộn trực tiếp embedding của các model vì chúng có dimension và không gian đặc trưng khác nhau. Hệ thống chỉ kết hợp thứ hạng kết quả bằng công thức:

```text
score(frame) = Σ weight(model) / (rrf_k + rank(frame))
```

Baseline dùng `rrf_k = 60` và weight `1.0` cho mỗi model. Weight cuối cùng phải được chọn bằng validation mAP/Recall@K.

## Cách thêm hoặc bật một model

1. Thêm model vào `apps/api/config/ensemble.json`, gồm:
   - `id`, adapter và checkpoint;
   - embedding dimension;
   - tên Milvus collection riêng;
   - weight và trạng thái `enabled`.
2. Encode toàn bộ keyframe bằng model đó:

   ```powershell
   cd apps/api
   uv run python scripts/embed_keyframes.py --input ../../data/manifests/frames.jsonl --images-root ../../data --output ../../data/ensemble-embeddings --model <model-id>
   ```

3. Kiểm tra artifact trước khi nạp:

   ```powershell
   uv run python scripts/load_ensemble_embeddings.py ../../data/ensemble-embeddings/<model-id>/manifest.json --dry-run
   ```

4. Nạp embedding vào Milvus:

   ```powershell
   uv run python scripts/load_ensemble_embeddings.py ../../data/ensemble-embeddings/<model-id>/manifest.json
   ```

5. Kiểm tra collection có đủ cùng tập `frame_uid` với các model khác.
6. Đổi `enabled` thành `true` trong `ensemble.json` và khởi động lại API.
7. Chạy validation để đo model đơn lẻ và ensemble trước khi chỉnh weight.

> Không bật model nếu chưa encode và nạp đầy đủ gallery của model đó vào Milvus.

