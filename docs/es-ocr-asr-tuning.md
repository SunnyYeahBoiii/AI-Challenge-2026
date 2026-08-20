# ES OCR/ASR Tuning — thay đổi & cải tiến

Branch `feat/es-ocr-asr-tuning`. Mục tiêu: search text trên OCR/ASR chính xác hơn, nhanh hơn, và fuse tốt với vector search.

## 1. Tách match strategy cho OCR vs ASR

Trước đây cả OCR lẫn ASR dùng chung `match_phrase` (khớp cụm từ, đúng thứ tự). Vấn đề: OCR trên dataset này là **bag of words xáo trộn, không dấu, không thứ tự ổn định** — `match_phrase` không bao giờ khớp keyword nhiều từ.

- **OCR**: đổi sang `match` không thứ tự + fuzzy.
  - `minimum_should_match = "2<75%"` — giữ chặt cho keyword ngắn (≤2 từ phải khớp hết), nới dần 75% cho keyword dài. (Threshold "75%" bo tròn xuống với 2 từ → coi như AND, nên phải tách riêng.)
  - `fuzziness: AUTO` + `prefix_length=2`, `max_expansions=20` — chịu lỗi gõ nhưng giới hạn số term expand (đo thực tế: "ajinomoto" 264ms fuzzy AUTO prefix mặc định → 4ms strict, chỉ đổi 1% recall; siết `prefix_length=2` đưa về <30ms).
  - Skip fuzziness nếu keyword chứa số (biển số, timecode, video id kiểu "51F", "L21_V001") — số này không có "hàng xóm" gần đúng edit-distance, đo được 3 hit strict vs 223 hit fuzzy (noise).

- **ASR**: giữ `match_phrase` (transcript có thứ tự tuần tự nên phrase match hợp lý), nhưng:
  - Field chính giữ nguyên dấu (không fold) + subfield `.folded` để fallback khi query gõ không dấu — field chính boost x3 để ưu tiên khớp đúng dấu.
  - Slop cấu hình qua `ES_ASR_PHRASE_SLOP` (mặc định 0 = khớp liền kề đúng thứ tự).

## 2. Trả BM25 score thay vì boolean

`match_frames_by_keywords` (trả `set`) → `score_frames_by_keywords` (trả `dict[key, score]`). Lý do: boolean không phân biệt được keyword *định danh* frame với keyword khớp nửa corpus — watermark "htv online" xuất hiện trên 49% frame. Chỉ IDF (BM25 score) mới demote được loại này. Score này sau đó tham gia fusion (mục 4).

## 3. Mapping ES rebuild

- `ocr_text`: giữ nguyên phân tích analyzer fold dấu (OCR nguồn vốn đã mất dấu).
- `asr_text`: thêm subfield `.folded` (xem mục 1).
- Thêm field `frame_key` (keyword) = `"{video_id}:{frame_id}"`, dùng làm `_id` document và làm filter thay cho 2 `terms` clause `video_id`/`frame_id` riêng — filter 2 clause độc lập match theo **tích Descartes**, không phải theo từng cặp thực sự cần.
- Thêm `shot_idx` (dùng để collapse near-duplicate ở mục 5).
- `number_of_shards: 1`, `number_of_replicas: 0` — cluster 1 node, để replica không gán được sẽ treo cluster ở trạng thái yellow vĩnh viễn.

## 4. Fuse vector + BM25 bằng RRF

`_fuse_scores`: Reciprocal Rank Fusion trên **rank**, không trên score thô — cosine similarity và BM25 không cùng thang đo, chuẩn hoá 2 phân phối không chặn khác dạng là nguồn lỗi phổ biến nhất ở bước này.

```
score = Σ weight_source / (RRF_K + rank_source)
```

Config: `RRF_K` (mặc định 60), `RRF_VECTOR_WEIGHT`, `RRF_TEXT_WEIGHT` (mặc định 1.0 mỗi bên). Nguồn nào không có (frame không được vector-rank hoặc không có text-score) bị loại khỏi fusion hoàn toàn — không cho điểm giả bằng 0 lẫn vào.

## 5. Collapse near-duplicate theo shot

ASR transcribe theo rolling window nên các keyframe liền kề cùng shot có text gần như giống hệt nhau — đo được 89k cặp kề nhau byte-identical. Không collapse → 1 câu transcript hit tràn ngập kết quả cùng 1 khoảnh khắc lặp lại.

`_collapse_shots`: giữ frame điểm cao nhất mỗi `(video_id, shot_idx)`, các frame còn lại đẩy vào `shot_siblings` (dạng thumbnail-ref, không mất, UI có thể expand). Bật/tắt qua `ES_DEDUPE_BY_SHOT` (mặc định true). **Không áp dụng cho path TRAKE** — temporal search cần đủ mọi frame của shot để dựng chuỗi event.

## 6. Reindex an toàn, không downtime, upsert được

`ensure_es_index`/`finalize_es_index` (scripts/es_common.py):

- Alias `video_texts` trỏ tới index versioned `video_texts_v{n}`. Reindex tạo index mới, load xong mới swap alias atomic (`remove` cũ + `add` mới trong 1 lệnh `_aliases`) — chỉ lần migrate đầu tiên từ index concrete cũ (pre-alias) mới cần xoá trước, sau đó mọi lần đều zero-downtime.
- Bulk load tắt `refresh_interval: -1` để tăng throughput, `finalize_es_index` bật lại + refresh 1 lần cuối — trước đây bỏ bước này thì ghi xong vẫn "vô hình" với search mãi mãi.
- `_id` document = `frame_key` → chạy lại script là **upsert**, không tạo trùng bản ghi. Script bị interrupt giữa chừng chạy lại cũng tự nối tiếp an toàn (idempotent), kể cả dùng index staging chưa finalize từ lần chạy trước.

## 7. Fix liên quan: Milvus query theo composite id

`query_frame_keys` trước đó filter `id in ["video_id/frame_index", ...]` — nhưng field `id` của collection là Int64 primary key auto-generate, biểu thức này **không bao giờ khớp**, Milvus còn reject thẳng ("value ... cannot be casted to Int64"). Fix: filter theo `video_id` + `frame_index` riêng, chạy **từng video một** để `frame_index in [...]` không cross-match sang video khác.

## 8. Test coverage mới

`tests/test_clients.py`, `tests/test_hybrid_search.py`: cover fuzzy OCR match, phrase ASR + slop, filter theo `frame_key`, BM25 score trả về, RRF fusion, dedupe theo shot.

## Tóm tắt config mới (`app/config.py`)

| Env var | Mặc định | Ý nghĩa |
|---|---|---|
| `ES_MAX_KEYWORD_HITS` | 10000 | Trần số hit trả về khi filter keyword |
| `ES_ASR_PHRASE_SLOP` | 0 | Độ "lỏng" thứ tự/khoảng cách từ khi phrase-match ASR |
| `RRF_K` | 60 | Hằng số k trong công thức RRF |
| `RRF_VECTOR_WEIGHT` | 1.0 | Trọng số nhánh vector khi fuse |
| `RRF_TEXT_WEIGHT` | 1.0 | Trọng số nhánh BM25 khi fuse |
| `ES_DEDUPE_BY_SHOT` | true | Bật/tắt collapse near-duplicate theo shot |
| `MILVUS_SEARCH_EF` | 128 | Tham số ef khi search Milvus |
