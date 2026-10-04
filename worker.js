// Cloudflare Worker: KenhVN Dynamic IPTV & Real-time TV360 Stream Proxy
// Tự động nhận diện thiết bị & Dynamic Redirect token cho các kênh TV360+ theo thời gian thực

const TV360_MAP = {
  // TV360+ 1 đến 15
  "1": 2554,
  "2": 1,
  "3": 148,
  "4": 2458,
  "5": 9867,
  "6": 9868,
  "7": 9869,
  "8": 9870,
  "9": 9887,
  "10": 9957,
  "11": 9958,
  "12": 10001,
  "13": 10022,
  "14": 10023,
  "15": 10024,
  // Mã bpk-tv tương ứng
  "198": 2554,
  "199": 1,
  "200": 148,
  "201": 2458,
  "367": 9867,
  "368": 9868,
  "369": 9869,
  "370": 9870,
  "379": 9887,
  "449": 9957,
  "450": 9958,
  "465": 10001,
  "471": 10022,
  "472": 10023,
  "473": 10024
};

// Global cache trong worker isolate
let cachedSessionCookie = null;
let sessionExpires = 0;
const streamCache = new Map(); // key -> { url, expire }

async function getFilm4kSession(env, clientIp) {
  const now = Date.now();
  if (cachedSessionCookie && sessionExpires > now) {
    return cachedSessionCookie;
  }

  const email = (env && env.FILM4K_EMAIL) || "thepersonlovecat@gmail.com";
  const password = (env && env.FILM4K_PASS) || "123123qwe";
  const ip = clientIp || (env && env.CLIENT_IP) || "113.22.246.62";

  const resp = await fetch("https://fiml4k.fun/api/auth/signin", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "User-Agent": "Mozilla/5.0 (Linux; Android 14; Mobile) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
      "Accept": "application/json",
      "X-Forwarded-For": ip,
      "X-Real-IP": ip,
      "Client-IP": ip
    },
    body: JSON.stringify({ email, password })
  });

  if (!resp.ok) {
    throw new Error(`Film4K đăng nhập thất bại (HTTP ${resp.status})`);
  }

  let cookies = [];
  if (typeof resp.headers.getSetCookie === "function") {
    cookies = resp.headers.getSetCookie();
  } else {
    const cookieStr = resp.headers.get("set-cookie");
    if (cookieStr) cookies = [cookieStr];
  }

  const cookieHeader = cookies.map(c => c.split(";")[0]).join("; ");
  cachedSessionCookie = cookieHeader;
  sessionExpires = now + 4 * 3600 * 1000; // Lưu session 4 tiếng
  return cachedSessionCookie;
}

async function resolveStreamUrl(cid, env, requestClientIp, bypassCache = false) {
  const now = Date.now();
  const cacheKey = `cid_${cid}`;
  if (!bypassCache) {
    const cached = streamCache.get(cacheKey);
    if (cached && cached.expire > now) {
      return cached.url;
    }
  }

  const clientIp = requestClientIp || (env && env.CLIENT_IP) || "113.22.246.62";
  let cookie = await getFilm4kSession(env, clientIp);
  let streamResp = await fetch(`https://fiml4k.fun/api/tv/${cid}/stream`, {
    headers: {
      "Cookie": cookie,
      "User-Agent": "Mozilla/5.0 (Linux; Android 14; Mobile) AppleWebKit/537.36",
      "Accept": "application/json",
      "X-Forwarded-For": clientIp,
      "X-Real-IP": clientIp,
      "Client-IP": clientIp
    }
  });

  // Nếu session hết hạn, thử refresh lại 1 lần
  if (streamResp.status === 401 || streamResp.status === 403) {
    cachedSessionCookie = null;
    sessionExpires = 0;
    cookie = await getFilm4kSession(env);
    streamResp = await fetch(`https://fiml4k.fun/api/tv/${cid}/stream`, {
      headers: {
        "Cookie": cookie,
        "User-Agent": "Mozilla/5.0 (Linux; Android 14; Mobile) AppleWebKit/537.36",
        "Accept": "application/json"
      }
    });
  }

  if (!streamResp.ok) {
    throw new Error(`Lỗi lấy luồng kênh ID ${cid} (HTTP ${streamResp.status})`);
  }

  const data = await streamResp.json();
  let streamUrl = data.url;
  if (!streamUrl) {
    throw new Error(`Không tìm thấy luồng cho kênh ID ${cid}`);
  }

  if (streamUrl.startsWith("/")) {
    streamUrl = `https://fiml4k.fun${streamUrl}`;
  }

  // Nếu là kênh TV360 có bpk-tv cần trích xuất bpk-token từ CDN thực tế
  let debugInfo = null;
  if (streamUrl.includes("/bpk-tv/")) {
    try {
      const r2 = await fetch(streamUrl, {
        method: "GET",
        redirect: "follow",
        headers: {
          "User-Agent": "Dalvik/2.1.0"
        }
      });

      const finalUrl = r2.url || streamUrl;
      const text = await r2.text();
      debugInfo = { status: r2.status, finalUrl, bodySnippet: text.slice(0, 150) };
      const m = finalUrl.match(/https:\/\/([^/:]+)(?::\d+)?\/bpk-token\/([^/]+)\/bpk-tv\/(\d+)\/output\/index\.mpd/);
      if (m) {
        const [_, host, token, chNum] = m;
        streamUrl = `https://${host}/bpk-token/${token}/bpk-tv/${chNum}/output/index.mpd`;
      }
    } catch (e) {
      debugInfo = { error: e.message };
    }
  }

  // Lưu cache 45 phút (thời gian an toàn trước khi token 4-6 tiếng hết hạn)
  streamCache.set(cacheKey, { url: streamUrl, expire: now + 45 * 60 * 1000, debugInfo });
  return { url: streamUrl, debugInfo };
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = url.pathname.toLowerCase();
    const ua = (request.headers.get("user-agent") || "").toLowerCase();
    const accept = (request.headers.get("accept") || "").toLowerCase();

    // -------------------------------------------------------------
    // 1. REAL-TIME STREAM REDIRECT: /live/tv360/:id
    // -------------------------------------------------------------
    if (path.startsWith("/live/tv360/")) {
      const rawParam = path.replace("/live/tv360/", "").replace(/\.(mpd|m3u8)$/i, "");
      const cid = TV360_MAP[rawParam];
      if (!cid) {
        return new Response("Kênh TV360 không hợp lệ. Vui lòng chọn từ 1 đến 15 (hoặc mã kênh TV360).", {
          status: 404,
          headers: { "Content-Type": "text/plain; charset=utf-8" }
        });
      }

      try {
        const clientIp = request.headers.get("cf-connecting-ip") || request.headers.get("x-real-ip") || "113.22.246.62";
        const bypassCache = url.searchParams.get("refresh") === "1";
        const result = await resolveStreamUrl(cid, env, clientIp, bypassCache);
        if (url.searchParams.get("json") === "1") {
          return new Response(JSON.stringify(result), {
            headers: { "Content-Type": "application/json" }
          });
        }
        return new Response(null, {
          status: 302,
          headers: {
            "Location": result.url,
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
            "Cache-Control": "public, max-age=1800"
          }
        });
      } catch (err) {
        return new Response("Lỗi cấp luồng TV360+: " + err.message, {
          status: 502,
          headers: { "Content-Type": "text/plain; charset=utf-8" }
        });
      }
    }

    // -------------------------------------------------------------
    // 2. REAL-TIME STREAM REDIRECT: /live/channel/:cid hoặc /live/film4k/:cid
    // -------------------------------------------------------------
    if (path.startsWith("/live/channel/") || path.startsWith("/live/film4k/")) {
      const parts = path.split("/");
      const cidStr = (parts[3] || "").replace(/\.(mpd|m3u8)$/i, "");
      const cid = parseInt(cidStr, 10);
      if (isNaN(cid)) {
        return new Response("Mã kênh không hợp lệ.", { status: 400 });
      }

      try {
        const clientIp = request.headers.get("cf-connecting-ip") || request.headers.get("x-real-ip") || "113.22.246.62";
        const result = await resolveStreamUrl(cid, env, clientIp);
        return new Response(null, {
          status: 302,
          headers: {
            "Location": result.url,
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
            "Cache-Control": "public, max-age=1800"
          }
        });
      } catch (err) {
        return new Response("Lỗi cấp luồng kênh: " + err.message, { status: 502 });
      }
    }

    // -------------------------------------------------------------
    // 3. TỰ ĐỘNG XÁC ĐỊNH DANH SÁCH M3U PHÙ HỢP
    // -------------------------------------------------------------
    let targetFile = "danh_sach_kenh_potplayer.m3u";

    if (path.includes("tv360") || path.includes("clearkey") || url.searchParams.get("type") === "tv360") {
      targetFile = "tv360.m3u";
    } else if (path.includes("tivi") || url.searchParams.get("type") === "tivi") {
      targetFile = "danh_sach_kenh_tivimate.m3u";
    } else if (path.includes("all") || url.searchParams.get("type") === "all") {
      targetFile = "danh_sach_kenh_film4k.m3u";
    } else if (path.includes("pot") || url.searchParams.get("type") === "pot") {
      targetFile = "danh_sach_kenh_potplayer.m3u";
    } else {
      // Nhận diện theo thiết bị
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

    // Giao diện Web thân thiện khi người dùng mở bằng trình duyệt
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

    // Tải nội dung M3U trực tiếp từ GitHub
    const cacheMinute = Math.floor(Date.now() / 60000);
    const githubRawUrl = `https://raw.githubusercontent.com/thepersonlovecat/kenhvn/main/${targetFile}?t=${cacheMinute}`;

    try {
      const response = await fetch(githubRawUrl, {
        headers: {
          "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        },
        cf: {
          cacheTtl: 60,
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
  <title>KenhVN - Kho Kênh IPTV & Realtime TV360 Stream</title>
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
    <div class="badge"><span class="dot"></span> Real-time Dynamic Redirect TV360+ Hoạt động 24/7</div>
    <h1>📺 KenhVN IPTV Cloudflare</h1>
    <p class="desc">Chỉ cần 1 đường link duy nhất. Hệ thống tự động nhận diện thiết bị (PotPlayer, TiviMate, K20 Player) và cấp token TV360 tươi mới theo thời gian thực.</p>

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

    <div class="box">
      <div class="box-title">⚡ Link chuyên kênh TV360+ & VTVPrime ClearKey</div>
      <div class="url-row">
        <span id="url-tv360">${origin}/tv360.m3u</span>
        <button class="copy-btn" onclick="copyToClipboard('${origin}/tv360.m3u', this)">Sao chép</button>
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
