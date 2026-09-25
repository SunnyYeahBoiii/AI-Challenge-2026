# ADR 0001 — Tối ưu đường phân phối video HLS

Ngày: 2026-09-05
Trạng thái: Đề xuất

## Bối cảnh

Người dùng báo "minio tải video chậm". Giả định ban đầu là tranh chấp tài nguyên
giữa minio và love2gether trên cùng máy prod `sunny`, hướng xử lý dự kiến là tách
2 máy ảo.

Đo đạc bác bỏ giả định đó.

## Số liệu đo được

Máy prod `sunny`: Intel i5-4200U (4 thread, 1.6GHz), 7.1 GiB RAM, 1 SSD SATA
238G, Ubuntu bare-metal (`systemd-detect-virt: none`).

### Không phải nghẽn tài nguyên máy

| Nghi ngờ | Đo được |
|---|---|
| Thiếu RAM | 1.3G/7.1G dùng, swap 0 byte, không OOM kill (`dmesg`, `journalctl -k`) |
| Tranh CPU | load 0.37, 94% idle |
| Đĩa chậm | GET segment tại `127.0.0.1:9000` = **11ms** |
| `exit 137` của love2gether-api | `docker stop` thủ công, app không xử lý SIGTERM trong 10s. Không phải crash |

### Nghẽn 1 — Cloudflare Tunnel không cache `.m4s`

Đo từ client thật (Mac trên tailnet), 10 segment tuần tự:

| Đường | Mỗi segment | Throughput |
|---|---|---|
| `https://s3.sunnydev.qzz.io` (Cloudflare) | 1,028ms | 1.16 MB/s |
| `http://100.94.178.42:9000` (Tailscale trực tiếp) | 468ms | 2.54 MB/s |

Nguyên nhân: `cf-cache-status: DYNAMIC` cho `.m4s`, dù origin gửi
`cache-control: public, max-age=31536000, immutable`. Đuôi `.m4s` không nằm
trong danh sách cache mặc định của Cloudflare. Đối chiếu: `.webp` cho
`cf-cache-status: HIT`.

Tailscale là kết nối **direct** (không qua DERP relay), RTT 7ms.

### Nghẽn 2 — Trần băng thông upload

Tăng số luồng song song gần như không cải thiện:

| Song song | Throughput |
|---|---|
| 1 | 20.0 Mbps |
| 4 | 23.2 Mbps |
| 8 | 24.2 Mbps |

Đường upload của `sunny` cứng ở ~24 Mbps. Không sửa được bằng phần mềm.

Tuy nhiên đây **không** phải nút thắt thực tế: video chỉ 1.49 Mbps, thừa băng
thông cho ~16 luồng xem đồng thời.

### Nghẽn 3 — Đóng gói HLS sai cho thao tác tua (nguyên nhân chính)

```
#EXT-X-TARGETDURATION:12
#EXTINF:11.960000
```

`ffprobe` trên `L23_V009/segment005.m4s`:

```
codec_name=h264, profile=Main, 1280x720, r_frame_rate=25/1, bit_rate=1486413
keyframe trong toàn segment 12s: chỉ 1 (pts_time=34.04)
```

`apps/api/scripts/hls_migrate.py:42` đặt `HLS_SEGMENT_SECONDS = 6`, nhưng thực
tế ra 11.96s. Lý do: `-c copy` (dòng 89) chỉ cắt được tại keyframe; `-hls_time`
là ngưỡng tối thiểu chứ không ép được. Video nguồn có GOP ~300 frame (12s).

Hệ quả với bài toán tìm frame: mỗi lần tua phải tải trọn segment 1.4MB **và**
giải mã tuần tự tới 300 frame kể từ keyframe. Không thể sửa bằng cách chia lại
segment — GOP đã nướng trong stream, bắt buộc encode lại.

## Vì sao không dùng máy ảo

Tách minio và love2gether thành 2 VM không chạm được nút thắt nào ở trên:

- Hai VM vẫn dùng chung 1 NIC, 1 đường upload 24 Mbps, 1 tiến trình `cloudflared`.
- Thêm guest kernel ăn RAM, thêm tầng virtio ăn IOPS, thêm vCPU scheduling ăn CPU —
  trên máy 4 thread @1.6GHz là lỗ ròng.
- UTM là ứng dụng macOS/iOS, không chạy trên Linux. Tương đương trên Linux là
  KVM/libvirt hoặc Incus/LXD.

## Bộ dữ liệu

873 video (L21–L30), ~10.4 phút/video, ≈151 giờ, 79G, 720p h264 1.49 Mbps.
232,906 object trong minio (152,856 keyframe + 80,050 segment video).

## Quyết định đề xuất

### Bước 1 — Đổi endpoint sang Tailscale (ngay, miễn phí)

`apps/api/app/config.py:40-42` đã thiết kế sẵn cho việc này:

```
MINIO_ENDPOINT=100.94.178.42:9000
MINIO_SECURE=false
```

Lợi: 2.2× ngay, không đổi code, không rủi ro TOS. Toàn đội đã ở trên tailnet.
Web chạy tại `http://localhost:3000` nên không dính mixed-content (http→http).

### Bước 2 — Encode lại với GOP ngắn (fix thật)

Ép keyframe theo chu kỳ để `-hls_time` có hiệu lực:

```
-c:v libx264 -g <fps*N> -keyint_min <fps*N> -sc_threshold 0 \
-force_key_frames "expr:gte(t,n_forced*N)" -hls_time N
```

Chạy trên máy Apple Silicon (VideoToolbox) — i5-4200U không đủ sức cho 151 giờ.

### Bước 3 (tuỳ chọn) — Cache Rule Cloudflare cho `.m4s`

Chỉ cần nếu vẫn muốn giữ đường public. Lưu ý Cloudflare free TOS §2.8 hạn chế
phục vụ lượng lớn video qua CDN — 79G video streaming là rủi ro thật.

## Hệ quả

- Bỏ hướng ảo hoá UTM/KVM. Không giải quyết vấn đề đã đo.
- Bước 2 tốn thời gian encode và băng thông upload lại dữ liệu; cần chốt tham số
  trước khi chạy (xem phần bỏ ngỏ).

## Bỏ ngỏ

Tham số encode ở bước 2 là đánh đổi thật, cần chủ dự án quyết:
độ dài segment/GOP (tua nhanh ↔ dung lượng tăng do nhiều keyframe hơn),
độ phân giải giữ 720p hay hạ, và mức CRF.
