# Nhập môn Elasticsearch và DSL trong FrameSeeker

Elasticsearch (ES) là công cụ tìm kiếm và phân tích dữ liệu dạng document. Trong FrameSeeker, ES không thay Milvus: Milvus tìm frame gần nghĩa với câu/ảnh; ES tìm frame có **nội dung OCR hoặc ASR** khớp với từ khóa. Hai hệ thống này bổ sung cho nhau.

Tài liệu này đi từ kiến thức nền đến Elasticsearch Query DSL, sau đó diễn giải chính xác cách UI và API của dự án tìm kiếm `ocr_text`/`asr_text`, gồm `match`, `match_phrase` và mọi Advanced option.

> Phạm vi: tài liệu bao quát các khái niệm và nhóm DSL quan trọng để vận hành, gỡ lỗi và mở rộng FrameSeeker. Elasticsearch còn có nhiều tính năng chuyên biệt khác (EQL, SQL, transforms, ML, cross-cluster search…), nhưng không phải bề mặt tích hợp hiện tại của dự án.

## 1. Elasticsearch trong kiến trúc FrameSeeker

```text
concatenate-data.json
        │
        ├─ embedding 1024 chiều ──> Milvus: data_frames_metaclip
        │                               │
        │                               └─ tìm theo ý nghĩa text/ảnh
        │
        └─ ocr_text + audio_text ──> Elasticsearch: video_texts
                                            │
                                            └─ tìm theo từ/cụm từ OCR, ASR
```

Mỗi document ES tương ứng một keyframe. Những field chính được tạo bởi `scripts/load_data.py` là:

| Field | Kiểu ES | Ý nghĩa |
| --- | --- | --- |
| `video_id` | `keyword` | Mã video, ví dụ `L21_V001` |
| `video_path`, `frame_path` | `keyword` | Đường dẫn dữ liệu |
| `frame_id`, `frame_idx` | `integer` | Chỉ số frame |
| `timestamp` | `float` | Thời điểm trong video (giây) |
| `ocr_text` | `text` | Văn bản nhìn thấy trong keyframe |
| `asr_text` | `text` | Lời nói/ASR gắn với frame |

Index hiện tại là `video_texts`. Mapping được khai báo tập trung ở [`apps/api/app/services/es_schema.py`](../apps/api/app/services/es_schema.py); cả loader và code truy vấn đều dựa vào cùng schema này.

## 2. Các khái niệm nền tảng

### 2.1 Cluster, node, index, document và shard

- **Cluster**: một cụm Elasticsearch, ví dụ service `elasticsearch` trong Docker Compose.
- **Node**: một tiến trình ES trong cluster. Môi trường local hiện là single-node.
- **Index**: tập document có schema tương tự, gần với “table” trong cơ sở dữ liệu quan hệ. Ví dụ: `video_texts`.
- **Document**: một JSON object trong index, gần với một “row”. Một document của dự án là một frame.
- **Field**: một thuộc tính JSON, ví dụ `ocr_text`.
- **Shard**: phần vật lý của index. ES chia document thành primary shard và có thể replica shard để mở rộng/khả dụng. Local single-node không cần tinh chỉnh shard cho use case này.

ES là document store có inverted index: thay vì quét toàn bộ text của mọi frame, ES lập danh sách document chứa từng token. Vì vậy truy vấn full-text nhanh hơn tìm chuỗi tuần tự trong JSON.

### 2.2 Mapping và kiểu dữ liệu

**Mapping** mô tả field và cách ES lập chỉ mục. Hai kiểu quan trọng nhất trong dự án:

| Kiểu | Dùng khi | Ví dụ |
| --- | --- | --- |
| `keyword` | Lọc/chính xác, không token hóa | `video_id`, `frame_path` |
| `text` | Full-text, được phân tích thành token | `ocr_text`, `asr_text` |
| `integer`, `float` | So sánh/range/sort số | `frame_id`, `timestamp` |

Không dùng `term` query cho `text` nếu ý định là tìm ngôn ngữ tự nhiên. `text` được analyzer biến đổi; `term` không phân tích query và thường chỉ phù hợp với `keyword` hoặc field chuẩn hóa riêng.

### 2.3 Analysis pipeline: character filter, tokenizer, token filter, analyzer

Một analyzer xác định text được tách và chuẩn hóa như thế nào khi index/query:

```text
"Thủ tướng Việt Nam"
       │
       ├─ tokenizer standard  → ["Thủ", "tướng", "Việt", "Nam"]
       ├─ lowercase           → ["thủ", "tướng", "việt", "nam"]
       └─ asciifolding        → ["thu", "tuong", "viet", "nam"]
```

Schema dự án dùng custom analyzer `vietnamese_folded`:

```json
{
  "tokenizer": "standard",
  "filter": ["lowercase", "vietnamese_ascii_folding"]
}
```

`asciifolding` bỏ dấu để người dùng có thể gõ `thu tuong viet nam` thay cho `Thủ tướng Việt Nam`. `preserve_original: false` nghĩa là ES chỉ giữ dạng folded trong index token; đó là chủ đích của dự án.

> [!IMPORTANT]
> Analyzer tại lúc index và `search_analyzer` tại lúc query đều là `vietnamese_folded`. Nếu thay analyzer trong mapping, document cũ **không tự được phân tích lại**: phải tạo index mới/reindex toàn bộ dữ liệu.

### 2.4 Kiểm tra analyzer

Chạy trong PowerShell sau khi ES hoạt động:

```powershell
Invoke-RestMethod -Method Post http://localhost:9200/video_texts/_analyze `
  -ContentType 'application/json' `
  -Body '{"analyzer":"vietnamese_folded","text":"Thủ tướng Việt Nam"}' |
  ConvertTo-Json -Depth 10
```

Kết quả cần có token `thu`, `tuong`, `viet`, `nam`. API `_analyze` là công cụ đầu tiên nên dùng khi nghi ngờ mismatch analyzer, dấu tiếng Việt hoặc ký tự OCR lạ.

## 3. Elasticsearch Query DSL

Query DSL là JSON mô tả truy vấn gửi đến endpoint `/{index}/_search`. Khung tối thiểu:

```json
{
  "query": { "match_all": {} },
  "_source": ["video_id", "frame_id", "ocr_text"],
  "size": 20,
  "from": 0,
  "sort": [{ "timestamp": "asc" }]
}
```

- `query`: điều kiện và cách tính relevance score.
- `_source`: field trả về; giới hạn field giúp giảm dữ liệu truyền.
- `size`: số hit trả về.
- `from`: offset cho phân trang nông. Với tập kết quả lớn, dùng `search_after` thay vì `from` lớn.
- `sort`: thứ tự. Nếu sort theo field thay vì `_score`, relevance không còn là thứ tự chính.

Mỗi hit thường có `_id`, `_score` và `_source`. `_score` là điểm relevance; không nên so sánh tuyệt đối score của hai query khác nhau vì BM25/DSL có thể cho scale khác nhau.

### 3.1 Full-text query: `match`

`match` phân tích query bằng search analyzer của field rồi tìm các document chứa token phù hợp. Đây là query mặc định trong UI.

```json
{
  "query": {
    "match": {
      "ocr_text": {
        "query": "thu tuong viet nam",
        "operator": "and"
      }
    }
  }
}
```

Sau analyzer, query thành `thu`, `tuong`, `viet`, `nam`. Với `operator: "and"`, document phải chứa mọi token.

`match` phù hợp khi thứ tự từ không quan trọng hoặc text có xen thêm từ. Ví dụ query `quoc hoi hop` vẫn có thể khớp OCR `"Quốc hội đang họp phiên toàn thể"`.

### 3.2 Full-text query: `match_phrase`

`match_phrase` yêu cầu token xuất hiện gần nhau theo đúng thứ tự. Mặc định `slop: 0` nghĩa là các token phải liền kề.

```json
{
  "query": {
    "match_phrase": {
      "asr_text": {
        "query": "xin chao viet nam",
        "slop": 0
      }
    }
  }
}
```

`match_phrase` phù hợp với tên riêng, slogan, tiêu đề, câu nói hoặc số/địa danh cần đúng thứ tự. Nó hẹp hơn `match`, do đó dễ bỏ sót text ASR có chèn từ đệm hoặc OCR bị chen ký tự.

### 3.3 `term`, `terms`, `exists`, `range`, `prefix`

Đây là các **term-level query**: chúng không đưa text query qua analyzer.

```json
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "video_id": "L21_V001" } },
        { "terms": { "frame_id": [100, 101, 102] } },
        { "range": { "timestamp": { "gte": 30, "lt": 60 } } },
        { "exists": { "field": "ocr_text" } }
      ]
    }
  }
}
```

- `term`: một giá trị chính xác, phù hợp `keyword`/số.
- `terms`: một trong nhiều giá trị chính xác.
- `exists`: field có giá trị đã index.
- `range`: `gt`, `gte`, `lt`, `lte` cho số/ngày.
- `prefix`: tiền tố, ví dụ tìm `video_id` bắt đầu bằng `L21`.

### 3.4 `bool`: ghép điều kiện

`bool` là nền tảng để biểu diễn logic phức tạp:

| Nhánh | Ý nghĩa | Có tính score? |
| --- | --- | --- |
| `must` | tất cả điều kiện phải khớp | Có |
| `should` | một/nhiều điều kiện nên khớp | Có |
| `filter` | điều kiện bắt buộc, hay dùng cho metadata | Không; có thể cache |
| `must_not` | loại trừ document | Không |

Ví dụ: tìm OCR có cụm `khai mac`, chỉ trong một video và không lấy frame trước giây 10:

```json
{
  "query": {
    "bool": {
      "must": [
        { "match_phrase": { "ocr_text": { "query": "khai mac", "slop": 1 } } }
      ],
      "filter": [
        { "term": { "video_id": "L21_V001" } },
        { "range": { "timestamp": { "gte": 10 } } }
      ],
      "must_not": [
        { "match": { "ocr_text": "quang cao" } }
      ]
    }
  }
}
```

### 3.5 `minimum_should_match`

`minimum_should_match` quy định số clause hoặc token tối thiểu cần khớp. Trong `match`, nó chủ yếu dùng cùng `operator: "or"`.

```json
{
  "match": {
    "asr_text": {
      "query": "le khai mac dai hoi",
      "operator": "or",
      "minimum_should_match": "75%"
    }
  }
}
```

Với bốn token, `75%` yêu cầu khoảng ba token. Các biểu thức ES thông dụng:

| Giá trị | Ý nghĩa |
| --- | --- |
| `100%` | tất cả token |
| `75%` | 75% token |
| `2` | đúng/tối thiểu 2 token |
| `-1` | tất cả trừ 1 token |
| `2<75%` | nếu có không quá 2 token thì cần tất cả; từ 3 token trở lên dùng 75% |

Trong UI hiện tại, khi token operator là `AND`, `minimum_should_match` bị khóa tại `100%` để semantic rõ ràng. Backend cũng từ chối cấu hình `AND` với giá trị khác `100%`.

### 3.6 Fuzzy matching

Fuzzy tìm token có khoảng cách chỉnh sửa (Levenshtein edit distance) nhỏ với query token. Dự án dùng `fuzziness: "AUTO"` khi bật fuzzy.

```json
{
  "match": {
    "ocr_text": {
      "query": "viet nam",
      "operator": "and",
      "fuzziness": "AUTO",
      "prefix_length": 2,
      "max_expansions": 20
    }
  }
}
```

Fuzzy hữu ích với OCR/ASR nhiễu, ví dụ `vietn am`, `vlet nam` hoặc từ bị nhận dạng lệch nhẹ. Nó không phải công cụ sửa mọi lỗi OCR: text bị mất hẳn từ, sai segmentation nặng hay sai ngôn ngữ không thể luôn được cứu bằng fuzzy.

Hai giới hạn hiệu năng quan trọng:

- `prefix_length`: số ký tự đầu bắt buộc giống nhau, không fuzzy. Tăng giá trị giúp nhanh/chặt hơn nhưng giảm khả năng sửa lỗi đầu từ.
- `max_expansions`: số biến thể fuzzy tối đa mỗi token. Tăng giúp recall nhưng tốn CPU và có thể thêm match nhiễu.

Fuzzy chỉ được UI/API hỗ trợ cho `match`; không bật cho `match_phrase`. Elasticsearch không hỗ trợ `fuzziness` trực tiếp trên `match_phrase`, và phrase-fuzzy cần kỹ thuật DSL khác phức tạp hơn, không thuộc luồng dự án.

### 3.7 `slop` của phrase

`slop` cho phép số vị trí xen giữa token phrase:

| Query | `slop` | Có thể khớp |
| --- | ---: | --- |
| `"thu tuong"` | 0 | `thủ tướng` |
| `"thu tuong"` | 1 | `thủ tướng chính phủ` |
| `"thu tuong viet nam"` | 2 | `thủ tướng của Việt Nam` |

Slop càng cao, phrase càng rộng và có thể trả kết quả không còn đúng “cụm từ” theo ý người dùng. UI giới hạn từ 0 đến 10.

### 3.8 Các nhóm DSL quan trọng khác

Các query sau chưa phải bề mặt UI hiện tại nhưng cần biết khi mở rộng:

| Nhóm | Ví dụ | Dùng khi |
| --- | --- | --- |
| Full-text | `multi_match`, `query_string`, `simple_query_string` | tìm nhiều field hoặc cho phép cú pháp người dùng |
| Compound | `dis_max`, `constant_score`, `function_score`, `boosting` | phối hợp/điều chỉnh score |
| Join/nested | `nested`, `has_child`, `has_parent` | document có nested object hoặc relation |
| Geo | `geo_distance`, `geo_bounding_box` | dữ liệu tọa độ |
| Vector ES | `dense_vector`, `knn` | vector lưu trực tiếp ở Elasticsearch; FrameSeeker hiện dùng Milvus thay thế |
| Aggregation | `terms`, `date_histogram`, `avg`, `filter` | faceted search/thống kê |
| Highlight | `highlight` | trả đoạn text khớp để giải thích kết quả |

Không đưa trực tiếp input người dùng vào `query_string`: nó có toán tử và cú pháp riêng, dễ gây query bất ngờ. Với UI keyword hiện tại, `match` và `match_phrase` an toàn/dễ dự đoán hơn.

## 4. OCR và ASR: chọn nguồn nào?

| Nguồn | Dữ liệu | Nên dùng khi | Hạn chế thường gặp |
| --- | --- | --- | --- |
| **OCR** | Chữ xuất hiện trên ảnh: biển hiệu, banner, phụ đề, tên người, số áo, giá, logo chữ | Query có text nhìn thấy hoặc số/địa danh hiển thị | ký tự bị nhiễu, font nhỏ/nhòe, text nhiều ngôn ngữ |
| **ASR** | Lời nói được gắn với frame: hội thoại, lời dẫn, phát biểu | Query là nội dung được nói | từ đệm, nhận dạng sai tên riêng, mốc frame có thể lệch lời nói |

OCR của Batch1 được tạo bằng Gemini nên thông thường có chất lượng tốt. Mặc định nên bắt đầu bằng OCR strict cho nội dung trên màn hình. ASR nên dùng khi câu/từ được nói, hoặc khi frame không có chữ.

Nếu nhập cả OCR và ASR, backend đặt hai nhóm trong `bool.must`: **một frame phải thỏa OCR và thỏa ASR**. Đây không phải phép OR giữa hai nguồn.

Ví dụ ý định “trên màn hình có `VTV` và lời nói nhắc `thời sự`”:

```json
{
  "bool": {
    "must": [
      { "bool": { "should": [{ "match": { "ocr_text": { "query": "vtv", "operator": "and" } } }], "minimum_should_match": 1 } },
      { "bool": { "should": [{ "match": { "asr_text": { "query": "thoi su", "operator": "and" } } }], "minimum_should_match": 1 } }
    ]
  }
}
```

Muốn tìm *OCR hoặc ASR* trong cùng một câu hỏi, hiện tại hãy chạy hai search/box riêng rồi so sánh kết quả; không nên điền cùng keyword vào cả hai nếu bạn muốn phép OR.

## 5. Cách dùng giao diện Keywords

Mỗi Query Box có phần **Keywords**, gồm hai vùng độc lập: **OCR** và **ASR**.

### 5.1 Thêm keyword

Mỗi tag trong `TagInput` là **một clause độc lập**. Ví dụ OCR tags:

```text
[viet nam]  [quoc hoi]
```

khác với một tag:

```text
[viet nam quoc hoi]
```

Trường hợp đầu dùng OCR keyword relation để ghép hai clause; trường hợp sau các token được xử lý bởi token operator bên trong chính `match` clause.

### 5.2 OCR/ASR keyword relation

Nút `OCR keyword relation` và `ASR keyword relation` điều khiển quan hệ **giữa các tag keyword** của đúng nguồn đó:

| Relation | Ví dụ tags | DSL tương đương | Ý nghĩa |
| --- | --- | --- | --- |
| `AND` | `[viet nam]`, `[quoc hoi]` | `bool.should` + `minimum_should_match: 2` | cả hai tag phải khớp |
| `OR` | `[viet nam]`, `[quoc hoi]` | `bool.should` + `minimum_should_match: 1` | ít nhất một tag khớp |

`AND` là mặc định, phù hợp khi mỗi tag biểu diễn một ý bắt buộc. `OR` phù hợp với từ đồng nghĩa, biến thể tên hoặc nhiều khả năng thay thế.

Ví dụ tìm chữ `Hà Nội` hoặc `TP Hồ Chí Minh` trên ảnh:

```text
OCR tags: [ha noi] [tp ho chi minh]
OCR keyword relation: OR
```

### 5.3 Query mode cho từng nguồn

Ở khung OCR hoặc ASR, chọn **Query mode**:

| Mode | DSL sinh ra | Nên chọn |
| --- | --- | --- |
| `Match` | `match` | tìm theo token, không buộc thứ tự; mặc định và linh hoạt hơn |
| `Match phrase` | `match_phrase` | tên/câu/cụm từ cần giữ thứ tự |

Cấu hình OCR không ảnh hưởng ASR và ngược lại. Ví dụ có thể dùng OCR `match_phrase` cho biển hiệu, nhưng ASR `match` cho phát biểu dài.

## 6. Advanced options: ý nghĩa, DSL và khuyến nghị

Advanced options được mở riêng cho OCR hoặc ASR. Cả hai nguồn có cùng bộ option, nhưng lựa chọn tốt có thể khác nhau vì loại nhiễu khác nhau.

### 6.1 Advanced cho `Match`

| UI option | DSL | Giá trị/giới hạn | Tác động |
| --- | --- | --- | --- |
| Token operator | `operator` | `AND` hoặc `OR` | quan hệ giữa token trong **một tag keyword** |
| Minimum should match | `minimum_should_match` | preset `100%`, `75%`, `2<75%` hoặc biểu thức ES | số token tối thiểu khi operator là `OR` |
| Enable fuzzy matching | `fuzziness: "AUTO"` | bật/tắt | cho phép sai khác nhỏ từng token |
| Prefix length | `prefix_length` | 0–10 | số ký tự đầu không fuzzy |
| Max expansions | `max_expansions` | 1–100 | giới hạn biến thể fuzzy |

**Default an toàn của dự án** là:

```json
{
  "query_type": "match",
  "fuzzy": false,
  "operator": "and",
  "minimum_should_match": "100%",
  "prefix_length": 2,
  "max_expansions": 20,
  "slop": 0
}
```

Khi operator là `AND`, UI hiển thị/khóa `Minimum should match = 100%`; backend không gửi option này vào `match` vì `operator: "and"` đã biểu đạt đúng yêu cầu.

#### Ví dụ A — Match strict cho OCR

Mục tiêu: tìm frame chứa mọi từ của `dai hoc quoc gia` nhưng không quan tâm thứ tự tuyệt đối.

```text
OCR keyword: [dai hoc quoc gia]
Query mode: Match
Token operator: AND
Fuzzy: Off
```

```json
{
  "match": {
    "ocr_text": {
      "query": "dai hoc quoc gia",
      "operator": "and"
    }
  }
}
```

#### Ví dụ B — Recall rộng hơn cho ASR dài

Mục tiêu: ASR có thể thiếu một từ trong câu dài.

```text
ASR keyword: [le khai mac dai hoi]
Query mode: Match
Token operator: OR
Minimum should match: 75%
Fuzzy: Off
```

```json
{
  "match": {
    "asr_text": {
      "query": "le khai mac dai hoi",
      "operator": "or",
      "minimum_should_match": "75%"
    }
  }
}
```

#### Ví dụ C — OCR nhiễu nhẹ

Mục tiêu: tên trên banner có nguy cơ nhầm 1–2 ký tự.

```text
OCR keyword: [nguyen van a]
Query mode: Match
Token operator: AND
Fuzzy: On
Prefix length: 2
Max expansions: 20
```

Chỉ bật fuzzy sau khi strict match không đủ kết quả. Với keyword quá ngắn như `AI`, `TV`, `VTV`, fuzzy thường tăng nhiễu nhiều hơn lợi ích.

### 6.2 Advanced cho `Match phrase`

Khi chọn `Match phrase`, UI chỉ hiển thị `Slop`:

| UI option | DSL | Giá trị/giới hạn | Tác động |
| --- | --- | --- | --- |
| Slop | `slop` | 0–10 | số khoảng token được phép xen giữa các token phrase |

Fuzzy bị tắt tự động và không thể bật trong phrase mode. `operator`, `minimum_should_match`, `prefix_length`, `max_expansions` không tham gia vào `match_phrase` của dự án.

#### Ví dụ D — Cụm từ chính xác trong ASR

```text
ASR keyword: [chuc mung nam moi]
Query mode: Match phrase
Slop: 0
```

```json
{
  "match_phrase": {
    "asr_text": {
      "query": "chuc mung nam moi",
      "slop": 0
    }
  }
}
```

#### Ví dụ E — Phrase OCR có từ xen giữa

```text
OCR keyword: [thu tuong viet nam]
Query mode: Match phrase
Slop: 2
```

Ví dụ này có thể bắt các câu như `"Thủ tướng của Việt Nam"`, nhưng nên tránh tăng slop quá sớm vì title/bảng chữ có thể chứa nhiều token không liên quan.

### 6.3 Bảng chọn nhanh

| Tình huống | Nguồn | Cấu hình nên bắt đầu |
| --- | --- | --- |
| Số áo, giá, mã, text ngắn trên banner | OCR | `Match`, `AND`, fuzzy off |
| Tên riêng/tiêu đề cần đúng thứ tự | OCR | `Match phrase`, slop 0–1 |
| Câu nói dài, có thể khác trật tự nhẹ | ASR | `Match`, `OR`, `75%` hoặc `2<75%` |
| Câu thoại/slogan đặc trưng | ASR | `Match phrase`, slop 0–2 |
| Ký tự OCR sai nhẹ | OCR | `Match`, fuzzy on, prefix 2, max expansions 20 |
| Kết quả quá nhiều | OCR/ASR | đổi `OR` → `AND`, tăng MSM, giảm slop hoặc tắt fuzzy |
| Không có kết quả | OCR/ASR | kiểm tra analyzer, nới `AND` → `OR`, thử `75%`, tăng slop hoặc bật fuzzy có kiểm soát |

## 7. API payload tương ứng

Frontend gửi snake_case đến `/api/frames` qua `MultiBoxRequest`. Ví dụ một box vector + keyword:

```json
{
  "box_queries": [
    {
      "text": "news broadcast",
      "ocr_keywords": ["thoi su", "vtv"],
      "ocr_match_mode": "and",
      "ocr_search_config": {
        "query_type": "match",
        "fuzzy": false,
        "operator": "and",
        "minimum_should_match": "100%",
        "prefix_length": 2,
        "max_expansions": 20,
        "slop": 0
      },
      "asr_keywords": ["ban tin toi nay"],
      "asr_match_mode": "and",
      "asr_search_config": {
        "query_type": "match_phrase",
        "fuzzy": false,
        "operator": "and",
        "minimum_should_match": "100%",
        "prefix_length": 2,
        "max_expansions": 20,
        "slop": 1
      },
      "topk": 1000,
      "enhance": true
    }
  ],
  "mode": "parallel",
  "temporal_window_seconds": 90
}
```

Backend validation:

- `query_type` chỉ nhận `match` hoặc `match_phrase`.
- Fuzzy với `match_phrase` trả validation error.
- `operator: and` chỉ nhận `minimum_should_match: "100%"`.
- `prefix_length` nằm trong 0–10; `max_expansions` 1–100; `slop` 0–10.
- Cú pháp `minimum_should_match` phải là biểu thức ES hợp lệ, ví dụ `75%`, `2`, `-1`, `2<75%`.

## 8. Indexing, cập nhật và vận hành

### 8.1 Index document

Lệnh index cơ bản:

```http
POST /video_texts/_doc
{
  "video_id": "L21_V001",
  "frame_id": 120,
  "ocr_text": "Thủ tướng Việt Nam",
  "asr_text": "Xin chào quý vị khán giả",
  "timestamp": 12.5
}
```

Loader dự án dùng Bulk API để gửi nhiều action `index` trong một request. Bulk tăng throughput nhưng cần kiểm tra `errors` trong response; loader hiện in một vài lỗi đầu nếu bulk có lỗi.

### 8.2 Refresh và near real-time

ES là near-real-time: một document vừa index có thể chưa search được ngay cho đến refresh. Loader dùng `refresh="wait_for"` cho Bulk API, vì vậy batch hoàn tất sẽ chờ document có thể tìm kiếm.

Không nên gọi refresh từng document khi import lớn; chi phí rất cao. `refresh="wait_for"` theo batch là trade-off phù hợp cho loader hiện tại.

### 8.3 Tạo lại mapping/analyzer

Mapping của `text` không thể đổi analyzer đã index chỉ bằng update mapping. Luồng an toàn:

1. Dừng truy vấn/import ghi đồng thời.
2. Sao lưu nếu cần.
3. Xóa hoặc tạo index version mới với mapping mới.
4. Nạp lại toàn bộ document từ nguồn gốc.
5. Kiểm tra `_analyze`, `_mapping`, `_count` và sample query.

Tham khảo hướng dẫn thực tế ở [data-import.md](data-import.md). Không xóa checkpoint đơn lẻ rồi import lại, vì loader không upsert theo frame key.

### 8.4 Pagination và search lớn

- `from` + `size`: đơn giản nhưng không dùng offset quá sâu.
- `search_after`: phân trang ổn định/hiệu quả hơn cho kết quả lớn; `iter_keyword_frame_hits()` hiện dùng cách này với sort `_score desc`, `video_id asc`, `frame_id asc`.
- Scroll/PIT: phù hợp export hoặc quét tập document lớn; không phải pagination UI thông thường.

### 8.5 Aggregation

Aggregation tạo thống kê/facet mà không cần kéo tất cả document về app:

```json
{
  "size": 0,
  "aggs": {
    "videos": {
      "terms": { "field": "video_id", "size": 20 }
    },
    "frames_by_time": {
      "histogram": { "field": "timestamp", "interval": 30 }
    }
  }
}
```

Vì `video_id` là `keyword`, nó dùng được cho `terms` aggregation. Với text, thường cần field `keyword` multi-field nếu muốn aggregation/sort nguyên văn; không nên aggregate trực tiếp `text` field có cardinality lớn.

### 8.6 Highlight

Highlight giúp UI chỉ ra đoạn OCR/ASR nào khớp:

```json
{
  "query": { "match": { "ocr_text": "thu tuong" } },
  "highlight": {
    "fields": {
      "ocr_text": {}
    }
  }
}
```

Tính năng này chưa được client hiện tại trả về, nhưng là extension hợp lý để làm rõ vì sao một frame được lọc bởi keyword.

### 8.7 Bảo mật và vận hành production

Docker Compose local tắt `xpack.security` và TLS để dễ phát triển. Production cần tối thiểu:

- bật authentication và TLS;
- không publish cổng ES ra internet công khai nếu không cần;
- dùng secret manager/biến môi trường thay vì commit mật khẩu;
- snapshot định kỳ vào storage ngoài cluster;
- theo dõi disk, JVM heap, latency, rejected requests và health;
- dùng ILM/index lifecycle khi dữ liệu có nhiều version hoặc tăng liên tục.

## 9. Gỡ lỗi truy vấn OCR/ASR

### 9.1 Quy trình chẩn đoán

1. Xác định text cần tìm thực sự nằm trong `ocr_text` hay `asr_text` bằng `_search` sample.
2. Gọi `_analyze` với text document và query để so token folded.
3. Chạy strict `match` + `AND` trước.
4. Nếu cần, giảm độ chặt theo từng bước: `OR` + `75%`, fuzzy cho `match`, hoặc slop nhỏ cho phrase.
5. Kiểm tra keyword relation: nhiều tag đang dùng `AND` hay `OR`?
6. Nếu nhập cả OCR và ASR, nhớ rằng hai nguồn bị AND; bỏ bớt một nguồn để cô lập lỗi.
7. Kiểm tra mapping đúng analyzer và index đã được reindex sau thay đổi schema.

### 9.2 Query kiểm tra trực tiếp

```powershell
$body = @'
{
  "size": 10,
  "_source": ["video_id", "frame_id", "ocr_text"],
  "query": {
    "match": {
      "ocr_text": {
        "query": "thu tuong viet nam",
        "operator": "and"
      }
    }
  }
}
'@

Invoke-RestMethod -Method Post http://localhost:9200/video_texts/_search `
  -ContentType 'application/json' -Body $body | ConvertTo-Json -Depth 20
```

### 9.3 Các lỗi tư duy phổ biến

| Hiểu nhầm | Thực tế |
| --- | --- |
| “Fuzzy sửa được mọi lỗi OCR.” | Fuzzy chỉ sửa sai khác ký tự nhỏ theo từng token và có chi phí/false positive. |
| “OR giữa token cũng là OR giữa các keyword tag.” | Đây là hai tầng logic khác nhau: `operator` nằm trong một tag; keyword relation nằm giữa các tag. |
| “Điền keyword ở cả OCR và ASR sẽ mở rộng kết quả.” | Ngược lại: các nguồn hiện được AND. |
| “Đổi analyzer xong search mới sẽ dùng ngay với dữ liệu cũ.” | Token lúc index không đổi; phải reindex. |
| “`term` tìm text chính xác hơn `match`.” | `term` không analyze query; nó không phải lựa chọn đúng cho `ocr_text`/`asr_text`. |
| “Score ES là xác suất.” | `_score` là điểm relevance tương đối, không phải xác suất và không ổn định giữa các query khác nhau. |

## 10. Checklist thực hành

Trước khi thay đổi search OCR/ASR:

- [ ] Xác định nguồn đúng: OCR hay ASR.
- [ ] Bắt đầu từ `Match` + `AND` + fuzzy off.
- [ ] Dùng `Match phrase` chỉ khi thứ tự cụm từ quan trọng.
- [ ] Chỉ nới lỏng từng thông số một và quan sát thay đổi kết quả.
- [ ] Ghi rõ keyword relation giữa nhiều tag là `AND` hay `OR`.
- [ ] Không quên OCR và ASR cùng xuất hiện sẽ AND.
- [ ] Kiểm tra analyzer bằng `_analyze` khi có dấu tiếng Việt/ký tự bất thường.
- [ ] Reindex hoàn chỉnh nếu schema/analyzer thay đổi.

## Liên kết nội bộ

- [Quy trình import dữ liệu](data-import.md)
- [Schema Elasticsearch của ứng dụng](../apps/api/app/services/es_schema.py)
- [Builder DSL và ES client](../apps/api/app/services/es_client.py)
- [Tài liệu DSL nhập môn cũ trong data/document](../data/document/elasticsearch-dsl-nhap-mon.md)
- [Báo cáo indexing và keyword search](../data/document/elasticsearch-indexing-va-keyword-search-main.md)
