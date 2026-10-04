# 📺 Kênh TV Trực Tuyến (KenhVN) - Tự Động Cập Nhật Token 24/7

Kho danh sách kênh truyền hình trực tuyến (VTV, HTV, VTC, SCTV, VTVCab, Thể thao, Giải trí...) được cập nhật tự động bằng GitHub Actions Bot mỗi 4 tiếng để token không bao giờ bị hết hạn.

---

## 🔗 Link Playlist M3U Trực Tiếp (Dùng Cho Trình Phát)

Chỉ cần sao chép các đường dẫn bên dưới dán vào trình phát (PotPlayer, VLC, TiviMate, v.v.):

### 1. Dành cho PotPlayer / VLC (Khuyên dùng trên PC / Laptop)
> Chắt lọc **140 kênh chuẩn HLS (.m3u8)**, loại bỏ DRM/link lỗi, mở lên là xem ngay lập tức:
```text
https://raw.githubusercontent.com/thepersonlovecat/kenhvn/main/danh_sach_kenh_potplayer.m3u
```

### 2. Dành cho TiviMate / OTT Navigator (Smart TV / Android Box / Phone)
> Tối ưu kèm định dạng Pipe Headers:
```text
https://raw.githubusercontent.com/thepersonlovecat/kenhvn/main/danh_sach_kenh_tivimate.m3u
```

### 3. Đầy đủ toàn bộ kênh (191 kênh)
```text
https://raw.githubusercontent.com/thepersonlovecat/kenhvn/main/danh_sach_kenh_film4k.m3u
```

---

## 🛠 Cách dùng trên PotPlayer

1. Mở phần mềm **PotPlayer**.
2. Nhấn tổ hợp phím **`Ctrl + U`** (hoặc chuột phải > **Mở** > **Mở địa chỉ URL...**).
3. Dán link playlist PotPlayer ở trên vào và bấm **Đồng ý**.
4. PotPlayer sẽ tự động nạp toàn bộ danh sách kênh và phát mượt mà kênh đầu tiên!

---

## 🤖 Cơ chế Bot Tự Động
- Sử dụng **GitHub Actions** (`update_channels.yml`).
- Chạy định kỳ mỗi 4 tiếng (`cron: '0 */4 * * *'`) để làm mới token TV360 trước khi hết hạn.
- Hỗ trợ chạy thủ công bằng cách bấm **Actions > Auto Update IPTV Channels & Tokens > Run workflow**.
