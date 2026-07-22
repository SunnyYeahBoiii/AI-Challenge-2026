# Inference + Ensemble — Bản ngắn gọn

FrameSeeker đã tích hợp đúng các nhánh visual retrieval được công bố bởi đội Top 1 và
Top 2 AIC 2025. Mỗi model tạo một bảng xếp hạng Top-K trong Milvus collection riêng;
các vector khác model không bị trộn trực tiếp.

## Model sử dụng

| Model | Tác dụng | Cách thêm vào hệ thống |
|---|---|---|
| **BEiT-3 Large COCO Retrieval 384** | Cân bằng độ chính xác và tốc độ; vector ảnh/text 1024 chiều. | Adapter BEiT-3, checkpoint và tokenizer chính thức có SHA-256, collection riêng. |
| **MetaCLIP2 Worldwide Huge** | Mạnh với entity, landmark và nội dung phổ biến; vector 1024 chiều. | Adapter Hugging Face, checkpoint ghim revision, collection riêng. |
| **Perception Encoder PE-Core-L14-336** | Bổ sung khả năng xử lý query phức tạp, nhiều cụm mô tả; vector 1024 chiều. | Adapter Perception dựa trên OpenCLIP conversion của checkpoint chính thức, ghim revision và SHA-256, collection riêng. |
| **BGE-VL-Large** | Model feedback chính: encode chung ảnh đã chọn và câu sửa đổi; vector 768 chiều. | Adapter BGE-VL native joint image–text, checkpoint ghim revision, collection riêng. |

Hai preset có sẵn trong `apps/api/config/ensemble.json`:

- `top1_2025`: BEiT-3 + MetaCLIP2 + Perception Encoder; hợp nhất bằng RRF.
- `top2_2025`: BEiT-3 + BGE-VL-Large + MetaCLIP2 + Perception Encoder; hợp nhất bằng RRF.

Top 2 paper không nêu biến thể Perception, checkpoint cụ thể hoặc giá trị RRF `k`.
FrameSeeker chọn `PE-Core-L14-336` và `k=60` làm cấu hình tái lập, không giả vờ đây là
hyperparameter được paper công bố.

## Cách hoạt động

```text
Query
  ├─ BEiT-3       → Top-K riêng
  ├─ MetaCLIP2    → Top-K riêng
  ├─ Perception   → Top-K riêng
  └─ BGE-VL       → Top-K riêng (preset Top 2)
                         ↓
                   RRF / Weighted RRF
                         ↓
                   Kết quả cuối cùng
```

Composed feedback chuẩn Top 2 nhận ba đầu vào:

```text
original query + selected frame + feedback text
```

Hệ thống ghép lại ngữ cảnh gốc với feedback rồi đưa ảnh + text vào joint encoder của
BGE-VL-Large. Preset Top 1 chỉ encode câu feedback, trộn với frame đã chọn theo công
thức đã công bố: `0.75 × feedback_text_embedding + 0.25 × image_embedding`, sau đó
RRF ba model.

Các model paper hiện chưa bật mặc định vì phải encode toàn bộ keyframe, nạp đủ từng
gallery vào Milvus và xác minh cùng tập `frame_uid` trước. Sau khi có dataset:

1. Chạy `scripts/embed_keyframes.py --model <model-id>` cho từng model.
2. Chạy `scripts/load_ensemble_embeddings.py <manifest> --dry-run`.
3. Nạp mỗi artifact vào collection tương ứng.
4. Bật model và gọi API với `ensemble.profile = "top1_2025"` hoặc `"top2_2025"`.
5. Chạy validation mAP/Recall@K trước khi chỉnh weight.
