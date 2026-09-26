# Dịch truy vấn Việt → Anh

Tài liệu này mô tả cơ chế **Dịch Việt → Anh** của FrameSeeker và các điểm cần sửa khi
muốn customize.

> Tên gọi “Google Translate” trong trao đổi của team có thể gây nhầm lẫn. Code hiện tại
> không gọi website Google Translate và cũng không dùng Google Cloud Translation API.
> Luồng ưu tiên dùng **Chrome Translator API** trong trình duyệt, sau đó fallback sang
> **Gemini API** ở backend.

Tài liệu chính thức của Chrome:
[Translation with built-in AI](https://developer.chrome.com/docs/ai/translator-api).

## Luồng hiện tại

Khi người dùng bật toggle **Dịch Việt → Anh** và tìm kiếm bằng text:

1. Frontend gọi `prepareSearchText()` trước khi gửi request search.
2. Nếu Chrome Translator API dùng được:
   - Dịch trực tiếp `vi` → `en` trong trình duyệt.
   - Gửi câu tiếng Anh xuống API.
   - Gửi `enhance: false` để backend không gọi Gemini lần nữa.
3. Nếu Translator API không tồn tại, không hỗ trợ cặp ngôn ngữ hoặc dịch lỗi:
   - Giữ nguyên câu tiếng Việt.
   - Gửi `enhance: true` xuống API.
   - Backend gọi Gemini để dịch và viết lại thành mô tả cảnh trực quan.
4. Nếu Gemini thiếu API key hoặc gọi thất bại, backend dùng nguyên câu đầu vào để search.

```text
Text query + toggle ON
          |
          v
Chrome Translator API khả dụng?
      /                 \
    Có                  Không/lỗi
    |                       |
dịch vi → en          giữ nguyên tiếng Việt
enhance=false          enhance=true
    |                       |
    |                  Gemini backend
    |                       |
    +-----------> vector search
```

Toggle tắt thì frontend giữ nguyên text và gửi `enhance: false`; cả Chrome Translator và
Gemini đều không chạy.

## File liên quan

| Khu vực | File | Vai trò |
|---|---|---|
| UI | `apps/web/src/components/query-box.tsx` | Toggle **Dịch Việt → Anh** |
| Frontend request | `apps/web/src/lib/api.ts` | Gọi `prepareSearchText()` cho từng text box |
| Dịch trong Chrome | `apps/web/src/lib/local-translation.ts` | Feature detection, tạo translator và fallback |
| Gemini backend | `apps/api/app/services/query_enhance.py` | Dịch + rewrite câu query |
| Cấu hình | `apps/api/app/config.py` | Model, API key, timeout và worker count |
| Env mẫu | `apps/api/.env.example` | Các biến môi trường Gemini |

## Chrome Translator API

Code đang cố định cặp ngôn ngữ tại
`apps/web/src/lib/local-translation.ts`:

```ts
const options = { sourceLanguage: "vi", targetLanguage: "en" };
```

Chrome kiểm tra bằng:

```ts
await Translator.availability(options);
```

Sau đó tạo và tái sử dụng một translator:

```ts
const translator = await Translator.create(options);
const translated = await translator.translate(text);
```

### Điều kiện chạy

- Chrome desktop có hỗ trợ Translator API; không nên giả định Safari, Firefox hoặc Chrome
  mobile có API này.
- Đây là API yêu cầu secure context. `http://localhost` thường được browser xem là origin
  đáng tin cậy, nhưng một địa chỉ Tailscale dạng `http://100.x.x.x:3000` không phải HTTPS và
  có thể không cung cấp `globalThis.Translator`.
- Language pack được Chrome tải theo nhu cầu ở lần sử dụng đầu tiên. Lần đầu có thể chậm hơn.
- Cặp `vi` → `en` phải được `Translator.availability()` báo là dùng được hoặc tải được.

Kiểm tra nhanh trong DevTools Console:

```js
globalThis.isSecureContext
"Translator" in globalThis
await Translator.availability({ sourceLanguage: "vi", targetLanguage: "en" })
```

Nếu `Translator` không tồn tại thì ứng dụng tự fallback sang Gemini; search không bị chặn.

## Gemini fallback

Backend đọc các biến sau từ `apps/api/.env`:

```env
GEMINI_API_KEY=your_gemini_key
GEMINI_MODEL=gemini-2.5-flash-lite
GEMINI_TIMEOUT=5
ENHANCE_MAX_WORKERS=8
```

Prompt hiện tại nằm trong `_gemini_translate()`:

```text
Translate to English if needed, then rewrite this query as one descriptive
visual scene sentence for image retrieval. Return only the rewritten sentence.
```

Gemini không chỉ dịch mà còn **viết lại câu thành mô tả hình ảnh**. Vì vậy kết quả của
Gemini có thể giàu ngữ cảnh hơn bản dịch local, nhưng chậm hơn và cần mạng/API key.

Backend cache tối đa 512 kết quả dịch thành công trong RAM. Lỗi tạm thời không được cache.
Nhiều query box được enhance song song, giới hạn bởi `ENHANCE_MAX_WORKERS`.

## Các cách customize thường gặp

### Đổi cặp ngôn ngữ

Sửa `sourceLanguage` và `targetLanguage` trong `local-translation.ts`, ví dụ:

```ts
const options = { sourceLanguage: "ja", targetLanguage: "en" };
```

Nếu đổi khỏi tiếng Việt, nên đổi luôn:

- Tên hàm `translateVietnameseToEnglish`.
- Label toggle trong `query-box.tsx`.
- Prompt Gemini nếu có yêu cầu riêng cho ngôn ngữ mới.

Không cần thêm dependency chỉ để đổi cặp ngôn ngữ.

### Chỉ dịch, không rewrite bằng Gemini

Sửa prompt trong `query_enhance.py` thành yêu cầu dịch nguyên nghĩa, ví dụ:

```text
Translate this query to English. Preserve all details and return only the translation.
```

Thay đổi này ảnh hưởng riêng fallback Gemini. Chrome Translator vẫn chỉ dịch như trước.

### Luôn dùng Gemini

Bỏ bước `prepareSearchText()` ở frontend hoặc để hàm luôn trả:

```ts
return { text, enhance: true };
```

Cách này cho output đồng nhất giữa các browser nhưng tăng latency, chi phí và phụ thuộc mạng.

### Chỉ dùng local, không gửi query ra ngoài

Khi Translator API không khả dụng, trả `enhance: false` thay vì `true`:

```ts
return { text, enhance: false };
```

Khi đó câu tiếng Việt nguyên bản được đưa thẳng vào encoder nếu local translation thất bại.
Đây là thay đổi về chất lượng search, cần so sánh kết quả trước khi dùng trong thi đấu.

### Hiển thị trạng thái tải language pack

`Translator.create()` hỗ trợ theo dõi `downloadprogress`. Có thể mở rộng state của query box
để hiển thị `Downloading translator…` ở lần đầu. Chỉ nên thêm khi team thật sự cần vì luồng
hiện tại cố tình fallback im lặng để thao tác search không bị gián đoạn.

## Test sau khi customize

Nên kiểm tra tối thiểu bốn trường hợp:

1. Toggle tắt: text giữ nguyên, `enhance=false`.
2. Translator khả dụng: text được dịch, `enhance=false`.
3. Translator không khả dụng hoặc throw: text giữ nguyên, `enhance=true`.
4. Gemini lỗi hoặc thiếu key: backend trả lại raw query, request search vẫn thành công.

Frontend có thể thêm test tại:

```text
apps/web/src/lib/local-translation.test.ts
```

Các lệnh kiểm tra:

```bash
cd apps/web
pnpm exec vitest run
pnpm build

cd ../api
uv run pytest tests/test_query_enhance.py
uv run ruff check app/services/query_enhance.py
```

## Khi nào cần rebuild

- Sửa TypeScript/frontend và chạy bằng Docker:

  ```bash
  docker compose build web
  docker compose up -d --no-deps web
  ```

- Sửa Python backend và đang dùng volume trong `docker-compose.yml`: restart API để Gunicorn
  nạp code mới. Rebuild API nếu cần đóng thay đổi vào image để chia sẻ/deploy.

  ```bash
  docker compose restart api
  ```

- Chỉ đổi `apps/api/.env`: recreate container để nạp lại environment; không cần build image.

  ```bash
  docker compose up -d --force-recreate api
  ```

Trong chế độ development (`pnpm dev`), frontend sẽ hot reload sau khi sửa file.

## Lưu ý về dữ liệu và quyền riêng tư

- Nhánh Chrome Translator xử lý query ở browser; backend chỉ nhận bản dịch tiếng Anh.
- Nhánh fallback gửi raw query tới Gemini API.
- Không gọi endpoint không chính thức của trang `translate.google.com`; endpoint đó không phải
  API ổn định cho ứng dụng.
- Không commit `GEMINI_API_KEY` vào repository.
