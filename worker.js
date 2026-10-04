export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = url.pathname.toLowerCase();
    const ua = (request.headers.get("user-agent") || "").toLowerCase();
    const accept = (request.headers.get("accept") || "").toLowerCase();

    // 1. Tự động xác định danh sách phù hợp
    let targetFile = "danh_sach_kenh_potplayer.m3u";

    // Cho phép người dùng hoặc ứng dụng chọn theo URL param (?type=tv360, ?type=tivi, ?type=pot, ?type=all)
    if (path.includes("tv360") || path.includes("clearkey") || url.searchParams.get("type") === "tv360") {
      targetFile = "tv360.m3u";
    } else if (path.includes("tivi") || url.searchParams.get("type") === "tivi") {
      targetFile = "danh_sach_kenh_tivimate.m3u";
    } else if (path.includes("all") || url.searchParams.get("type") === "all") {
      targetFile = "danh_sach_kenh_film4k.m3u";
    } else if (path.includes("pot") || url.searchParams.get("type") === "pot") {
      targetFile = "danh_sach_kenh_potplayer.m3u";
    } else {
      // SMART AUTO-DETECTION: Tự nhận diện thiết bị qua User-Agent
      // Nếu là TiviMate, OTT Navigator, Android TV, ExoPlayer -> Trả về bản pipe header của TiviMate
      // Nếu là PotPlayer, VLC, PC -> Trả về bản clean HLS của PotPlayer
      if (
        ua.includes("tivimate") ||
        ua.includes("ott") ||
        ua.includes("exoplayer") ||
        ua.includes("okhttp") ||
        ua.includes("android")
      ) {
        targetFile = "danh_sach_kenh_tivimate.m3u";
      } else {
        targetFile = "danh_sach_kenh_potplayer.m3u";
      }
    }

    // 2. Giao diện Web thân thiện khi người dùng mở bằng trình duyệt thông thường
    const isBrowser = accept.includes("text/html") &&
      !path.endsWith(".m3u") &&
      !path.endsWith(".m3u8") &&
      !ua.includes("potplayer") &&
      !ua.includes("vlc") &&
      !ua.includes("tivimate");

    if (isBrowser && (path === "/" || path === "")) {
      return new Response(renderWebUI(url.origin), {
        status: 200,
        headers: { "Content-Type": "text/html; charset=utf-8" }
      });
    }

    // 3. Tải nội dung M3U trực tiếp từ GitHub (kèm cache-buster theo phút để luôn lấy dữ liệu mới nhất)
    const cacheMinute = Math.floor(Date.now() / 60000);
    const githubRawUrl = `https://raw.githubusercontent.com/thepersonlovecat/kenhvn/main/${targetFile}?t=${cacheMinute}`;

    try {
      const response = await fetch(githubRawUrl, {
        headers: {
          "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        },
        cf: {
          cacheTtl: 60, // Cache 1 phút tại Cloudflare Edge
          cacheEverything: true
        }
      });

      if (!response.ok) {
        return new Response(`Lỗi kết nối GitHub (Status: ${response.status})`, { status: 502 });
      }

      const content = await response.text();

      return new Response(content, {
        status: 200,
        headers: {
          "Content-Type": "application/vnd.apple.mpegurl; charset=utf-8",
          "Content-Disposition": `inline; filename="${targetFile}"`,
          "Access-Control-Allow-Origin": "*",
          "Access-Control-Allow-Headers": "*",
          "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
          "Cache-Control": "public, max-age=60"
        }
      });
    } catch (e) {
      return new Response("Lỗi máy chủ: " + e.message, { status: 500 });
    }
  }
};

function renderWebUI(origin) {
  return `<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>KenhVN - Kho Kênh IPTV Tự Động 24/7</title>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #090d16;
      --card: rgba(255, 255, 255, 0.04);
      --card-border: rgba(255, 255, 255, 0.08);
      --primary: #3b82f6;
      --accent: #10b981;
      --text: #f3f4f6;
      --text-muted: #9ca3af;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Plus Jakarta Sans', sans-serif; }
    body {
      background: radial-gradient(circle at 50% 0%, #172554 0%, var(--bg) 70%);
      color: var(--text);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 24px;
    }
    .container {
      max-width: 680px;
      width: 100%;
      background: var(--card);
      backdrop-filter: blur(20px);
      border: 1px solid var(--card-border);
      border-radius: 24px;
      padding: 36px;
      box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
    }
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 6px 14px;
      background: rgba(16, 185, 129, 0.15);
      color: #34d399;
      border: 1px solid rgba(16, 185, 129, 0.3);
      border-radius: 999px;
      font-size: 13px;
      font-weight: 600;
      margin-bottom: 20px;
    }
    .dot { width: 8px; height: 8px; border-radius: 50%; background: #34d399; animation: pulse 2s infinite; }
    @keyframes pulse { 0%, 100% { opacity: 1; transform: scale(1); } 50% { opacity: 0.4; transform: scale(1.2); } }
    h1 { font-size: 28px; font-weight: 800; margin-bottom: 10px; }
    p.desc { color: var(--text-muted); font-size: 15px; margin-bottom: 28px; line-height: 1.6; }
    .box {
      background: rgba(0, 0, 0, 0.35);
      border: 1px solid var(--card-border);
      border-radius: 16px;
      padding: 20px;
      margin-bottom: 20px;
    }
    .box-title { font-size: 14px; font-weight: 700; color: #60a5fa; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 10px; }
    .url-row {
      display: flex;
      gap: 10px;
      align-items: center;
      background: rgba(255, 255, 255, 0.05);
      padding: 10px 14px;
      border-radius: 10px;
      font-family: monospace;
      font-size: 14px;
      color: #93c5fd;
      word-break: break-all;
    }
    button.copy-btn {
      padding: 8px 16px;
      background: var(--primary);
      color: #fff;
      border: none;
      border-radius: 8px;
      font-weight: 600;
      font-size: 13px;
      cursor: pointer;
      white-space: nowrap;
      transition: all 0.2s;
    }
    button.copy-btn:hover { background: #2563eb; transform: translateY(-1px); }
    .features {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
      margin-top: 24px;
    }
    .feature-item {
      background: rgba(255, 255, 255, 0.02);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 14px;
      font-size: 13px;
      color: var(--text-muted);
    }
    .feature-item strong { color: var(--text); display: block; margin-bottom: 4px; }
  </style>
</head>
<body>
  <div class="container">
    <div class="badge"><span class="dot"></span> Tự động làm mới token mỗi 4 tiếng</div>
    <h1>📺 KenhVN IPTV Cloudflare</h1>
    <p class="desc">Chỉ cần 1 đường link duy nhất. Hệ thống tự động nhận diện thiết bị để phát mượt mà trên cả <strong>PotPlayer</strong> (PC) lẫn <strong>TiviMate</strong> (Smart TV / Android Box).</p>

    <div class="box">
      <div class="box-title">🌟 Đường link đa năng duy nhất (Khuyên dùng cho tất cả)</div>
      <div class="url-row">
        <span id="url-main">${origin}/playlist.m3u</span>
        <button class="copy-btn" onclick="copyToClipboard('${origin}/playlist.m3u', this)">Sao chép</button>
      </div>
      <div style="font-size: 12px; color: #9ca3af; margin-top: 8px;">
        👉 Dán link này vào <strong>PotPlayer</strong> hoặc <strong>TiviMate</strong> đều tự nhận đúng định dạng tối ưu!
      </div>
    </div>

    <div class="features">
      <div class="feature-item">
        <strong>💻 Trên PotPlayer (PC)</strong>
        Nhấn <code>Ctrl + U</code> > Dán link trên vào là xong.
      </div>
      <div class="feature-item">
        <strong>📺 Trên TiviMate (TV)</strong>
        Thêm Playlist M3U > Nhập link trên và bấm Tiếp tục.
      </div>
    </div>
  </div>

  <script>
    function copyToClipboard(text, btn) {
      navigator.clipboard.writeText(text).then(() => {
        const orig = btn.innerText;
        btn.innerText = "Đã sao chép! ✓";
        btn.style.background = "#10b981";
        setTimeout(() => {
          btn.innerText = orig;
          btn.style.background = "";
        }, 2000);
      });
    }
  </script>
</body>
</html>`;
}
