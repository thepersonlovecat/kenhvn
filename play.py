import http.server
import urllib.request
import urllib.parse
import ssl
import webbrowser

PORT = 8080
MASTER_URL = "https://fiml4k.fun/api/hls/pbWO12_0JSMIH1JnHip2tWu6Vqok9oDoi3lUfvdxvEgJIhw5DXkRKyK5zj-FlZRt7XiUDW13AZmYaIaZHLqI7TW06eCvWOLTsg/master.m3u8"
HEADERS = {'User-Agent': 'Mozilla/5.0 (Linux; Android 14; Mobile)'}

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

class StreamHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        # 1. Trang Web Player để xem trực tiếp trên trình duyệt
        if self.path == "/" or self.path == "/index.html":
            html = f"""<!DOCTYPE html>
<html>
<head><title>Film4K Player</title><script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script></head>
<body style="margin:0;background:#000;display:flex;justify-content:center;align-items:center;height:100vh;">
  <video id="v" controls autoplay style="max-width:100%;max-height:100vh;"></video>
  <script>
    const v = document.getElementById('v');
    const hls = new Hls();
    hls.loadSource('/master.m3u8');
    hls.attachMedia(v);
  </script>
</body>
</html>"""
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(html.encode())

        # 2. Xử lý Master Playlist
        elif self.path == "/master.m3u8":
            req = urllib.request.Request(MASTER_URL, headers=HEADERS)
            with urllib.request.urlopen(req, context=ctx) as resp:
                text = resp.read().decode('utf-8')
                text = text.replace('/api/hls/', '/sub?url=https://fiml4k.fun/api/hls/')
            self.send_m3u8(text)

        # 3. Xử lý Playlist con (Video / Audio)
        elif self.path.startswith("/sub?url="):
            target = urllib.parse.unquote(self.path[9:])
            req = urllib.request.Request(target, headers=HEADERS)
            with urllib.request.urlopen(req, context=ctx) as resp:
                text = resp.read().decode('utf-8')
                text = text.replace('https://cdn.fiml4k.fun/tt/', f'http://localhost:{PORT}/seg?url=https://cdn.fiml4k.fun/tt/')
            self.send_m3u8(text)

        # 4. Xử lý Segment: Tải về và cắt bỏ đúng 67 byte Fake PNG
        elif self.path.startswith("/seg?url="):
            target = urllib.parse.unquote(self.path[9:])
            req = urllib.request.Request(target, headers=HEADERS)
            try:
                with urllib.request.urlopen(req, context=ctx, timeout=20) as resp:
                    data = resp.read()
                    # Nếu có header PNG giả mạo thì cắt bỏ 67 byte
                    if data[:8] == b'\x89PNG\r\n\x1a\n':
                        data = data[67:]
                    
                    self.send_response(200)
                    self.send_header('Content-Type', 'video/mp4')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.send_header('Content-Length', str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
            except Exception as e:
                self.send_error(500, str(e))

    def send_m3u8(self, text):
        self.send_response(200)
        self.send_header('Content-Type', 'application/vnd.apple.mpegurl')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(text.encode())

print(f"🎬 Server đang chạy tại: http://localhost:{PORT}")
print(f"👉 Link dán vào VLC / PotPlayer: http://localhost:{PORT}/master.m3u8")
webbrowser.open(f"http://localhost:{PORT}")
http.server.HTTPServer(('127.0.0.1', PORT), StreamHandler).serve_forever()
